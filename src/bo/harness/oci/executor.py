"""Executor do caso: render -> identidade -> intenção -> apply -> espera -> leitura -> destroy -> desfecho.

  python -I -m bo.harness.oci.executor CASES.jsonl --plan PLANO.jsonl --recording CASE_ID=GRAVACAO.json ...
                                       [--bindings B.json] [--evidence-before DOC_SUPPORTED] [--out DIR]

Só roda com respostas gravadas (RecordedRunner + OfflineKit) nesta fase. Para cada caso (C11):
  1. diretório de trabalho exclusivo em $BO_TMP/exec/<case_id>-<n> (criado com mkdir que falha se existe);
  2. render do plano do caso (só ele); plano que não sai RENDERED não chega ao apply: desfecho UNKNOWN com o código
     (UNKNOWN_INPUT ou INVALID_PLAN) no detalhe;
  3. identidade conferida pelo kit; intenção gravada ANTES do apply; apply; erro da API classificado
     (REJECTED_BY_API ou INFRA_ERROR);
  4. espera: o state é relido até todo recurso com lifecycle sair de estado transitório (limite de leituras);
  5. leitura: projeção redigida na origem (readback.project) e comparação em memória;
  6. destroy sempre que houve apply (finally), seguido de state list vazio; resíduo é erro alto;
  7. readback.jsonl e outcomes.jsonl (C12) passam pelo redator do kit e pelo privacy_lint antes de ir para disco
     e são validados pelo validador único depois.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path

from . import MODULE_ID, PROVIDER, tmp_root
from . import readback as RB
from . import render as R
from .kits import OfflineKit
from .runners import RecordedRunner, classify_error

PROTOCOL_VERSION = "1.0.0"
MAX_POLLS = 6


class WorkdirError(RuntimeError):
    pass


class ResidueError(RuntimeError):
    pass


def exclusive_workdir(case_id: str, base: Path | None = None) -> Path:
    base = (base or tmp_root() / "exec").resolve()
    root = tmp_root().resolve()
    if not (base == root or root in base.parents):
        raise WorkdirError(f"diretório de trabalho fora de $BO_TMP: {base}")
    if str(base).startswith(("/tmp", "/private/tmp")):
        raise WorkdirError("diretório de trabalho em /tmp é proibido")
    base.mkdir(parents=True, exist_ok=True)
    for n in range(1, 10000):
        d = base / f"{case_id}-{n:04d}"
        try:
            d.mkdir()
            return d
        except FileExistsError:
            continue
    raise WorkdirError("sem nome livre para o diretório de trabalho")


@dataclass
class CaseResult:
    case_id: str
    outcome: str
    detail: str
    workdir: Path
    readback: dict | None = None
    outcome_record: dict | None = None
    fields: list = field(default_factory=list)
    events: list = field(default_factory=list)
    residue: list = field(default_factory=list)


def _ids(case: dict, n: int) -> tuple[str, str]:
    suffix = case["case_id"][len("CASE-"):]
    return f"RB-{suffix}-{n:04d}", f"OUT-{suffix}-{n:04d}"


def run_case(case: dict, plan_path: Path, runner, kit, bindings_path: Path | None = None,
             evidence_before: str = "DOC_SUPPORTED", clock=R.now_iso, seq: int = 1,
             workdir_base: Path | None = None) -> CaseResult:
    wd = exclusive_workdir(case["case_id"], workdir_base)
    plan_id = case["lowering_plan"]["plan_id"]
    rr = R.render(plan_path, wd / "tf", bindings_path=bindings_path, plan_ids=[plan_id])
    pr = rr.renders[0]
    rep_plan = rr.report["plans"][0]
    if pr.graph_id != case["lowering_plan"]["graph_id"]:
        raise ValueError(f"caso {case['case_id']}: graph_id do plano difere do caso")
    rb_id, out_id = _ids(case, seq)
    base_out = {"outcome_id": out_id, "case_id": case["case_id"], "group_id": case["group_id"],
                "claim_id": case["claim_id"], "side": case["side"], "evidence_state_before": evidence_before,
                "rule_id": RB.RULE_ID}
    res = CaseResult(case["case_id"], "", "", wd)

    if pr.status != "RENDERED":
        codes = sorted({i.code for i in pr.issues}) or [pr.status]
        detail = f"{pr.status}: " + ", ".join(codes)
        res.outcome, res.detail = "UNKNOWN", detail
        res.outcome_record = dict(base_out, outcome={"axis": "persistence", "value": "UNKNOWN", "detail": detail},
                                  evidence_state_after=evidence_before, decided_at=clock())
        _write(wd, kit, [], [res.outcome_record])
        res.events = list(kit.events)
        return res

    module_sha = rr.report["files"][f"{pr.module}/main.tf"]
    kit.check_identity(runner)
    var_values = kit.var_values(list(pr.variables.values()))
    if getattr(runner, "recorded", False):
        runner.bind(module_sha, plan_id, kit.context())
    tfdir = wd / "tf"
    applied = False
    readback_rec = None
    fields: list = []
    try:
        kit.record("intent", case["case_id"])
        runner.init(tfdir)
        applied = True
        ap = runner.apply(tfdir, var_values)
        if not ap.ok:
            ec = classify_error(ap.status, ap.code, "apply")
            res.outcome, res.detail = ec.outcome, ec.detail
        else:
            kit.record("created", case["case_id"])
            state, pending = None, []
            for _ in range(MAX_POLLS):
                state = runner.show_state(tfdir)
                pending = RB.unready(state, pr.module)
                if not pending or any(p.split(":")[-1] in RB.FAILED_STATES for p in pending):
                    break
            failed = [p for p in pending if p.split(":")[-1] in RB.FAILED_STATES]
            if failed or pending:
                res.outcome = "INFRA_ERROR"
                res.detail = (f"recurso em estado terminal depois do apply ({len(failed)})" if failed else
                              f"WAIT_TIMEOUT: {len(pending)} recurso(s) sem ficar pronto em {MAX_POLLS} leituras")
            else:
                kit.record("confirmed", case["case_id"])
                plan = next(p for p in R.load_jsonl(plan_path) if p["plan_id"] == plan_id)
                fields = RB.project(state, rep_plan, plan, kit.redactor)
                RB.compare_fields(fields, case["comparator"])
                res.outcome, res.detail = RB.decide(fields)
                readback_rec = {"readback_id": rb_id, "case_id": case["case_id"], "group_id": case["group_id"],
                                "claim_id": case["claim_id"], "side": case["side"], "provider": PROVIDER,
                                "read_at": clock(), "protocol_version": PROTOCOL_VERSION,
                                "fields": [f.c12() for f in fields]}
    finally:
        if applied:
            kit.record("removal_requested", case["case_id"])
            d = runner.destroy(tfdir, var_values)
            left = runner.state_list(tfdir)
            if d.ok and not left:
                kit.record("removed", case["case_id"])
            else:
                kit.record("residue", case["case_id"])
                res.residue = left or ["(destroy falhou)"]
    after = RB.evidence_after(evidence_before, res.outcome)
    rec = dict(base_out, outcome={"axis": "persistence", "value": res.outcome, "detail": res.detail},
               evidence_state_after=after, decided_at=clock())
    if readback_rec is not None and res.outcome in ("PERSISTED", "ALTERED", "NOT_READABLE", "UNKNOWN"):
        rec["readback_id"] = rb_id
    res.outcome_record, res.readback, res.fields = rec, readback_rec, fields
    _write(wd, kit, [readback_rec] if readback_rec else [], [rec])
    res.events = list(kit.events)
    if res.residue:
        raise ResidueError(f"{case['case_id']}: resíduo depois do destroy ({len(res.residue)} item(ns)); "
                           f"desfecho gravado em {wd}")
    return res


def _write(wd: Path, kit, readbacks: list, outcomes: list) -> None:
    """Grava C12 só depois do redator do kit (que também roda o privacy_lint) e valida no validador único."""
    from bo.contracts import validate as V
    for name, recs in (("readback.jsonl", readbacks), ("outcomes.jsonl", outcomes)):
        if not recs:
            continue
        text = kit.redact_records(recs, f"{wd.name}/{name}")
        p = wd / name
        p.write_text(text, encoding="utf-8")
        r = V.validate(name.split(".")[0], p)
        if not r.ok:
            p.rename(p.with_suffix(".invalid"))
            raise ValueError(f"{name} fora do C12: {r.errors[:3]}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="bo.harness.oci.executor", description="executor offline com respostas gravadas")
    ap.add_argument("cases", type=Path)
    ap.add_argument("--plan", type=Path, required=True)
    ap.add_argument("--recording", action="append", default=[], help="CASE_ID=arquivo de gravação")
    ap.add_argument("--bindings", type=Path)
    ap.add_argument("--evidence-before", default="DOC_SUPPORTED")
    a = ap.parse_args(argv)
    recs = dict(x.split("=", 1) for x in a.recording)
    cases = R.load_jsonl(a.cases)
    rc = 0
    for c in cases:
        if c["case_id"] not in recs:
            print(f"  {c['case_id']}: sem gravação; nada roda (nuvem proibida nesta fase)")
            continue
        kit = OfflineKit()
        res = run_case(c, a.plan, RecordedRunner(Path(recs[c["case_id"]])), kit, a.bindings, a.evidence_before)
        print(f"[{R.now_iso()}] {MODULE_ID} {c['case_id']}: {res.outcome} ({res.detail}) -> {res.workdir}")
    return rc


if __name__ == "__main__":
    sys.exit(main())
