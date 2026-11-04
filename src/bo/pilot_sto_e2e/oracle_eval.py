"""Gate G3: toda divergência do oráculo coberta por perda declarada; zero transporte em caso negativo.

  python -I -m bo.pilot.oracle_eval --slice sto --set calib

Refaz a corrida (determinística) e confere que os planos são os do staging (mesmo sha). O oráculo julga cada
tradução que desceu com as perdas que o plano declara. O pipeline é o c3; c1 e c2 são controles, relatados.
Reprova se, no c3: algum julgamento é REJECT (perda silenciosa ou divergência nunca cobrível); alguma
alegação-contraexemplo das fixtures é aceita; alguma configuração-alvo negativa das entradas é aceita pela
conferência do pipeline. Grava results/PILOT-STO-E2E/oracle_calib.json (C15). Só calibração: as retidas ficam
cifradas e não são lidas.
"""

from __future__ import annotations

import collections

from bo.contracts import validate as V
from bo.pilot.sto import common as C
from bo.pilot.sto import evaluate as E
from bo.pilot.sto import oracle_io
from bo.pilot.sto import pipeline as PL
from bo.pilot.sto import stage as ST

from ._cli import check_slice, parser, say


def main(argv=None) -> int:
    ap = parser("bo.pilot.oracle_eval", __doc__)
    ap.add_argument("--set", default="calib", choices=["calib"])
    a = ap.parse_args(argv)
    check_slice(a)
    sd = PL.stage_dir()
    if not (sd / "lowering_plan.jsonl").exists():
        say("oracle_eval", "staging sem lowering_plan.jsonl: rode bo.pilot.run antes")
        return 2
    staged = C.sha256_file(sd / "lowering_plan.jsonl")
    out = ST.run_all(write=False)
    plans = [r.plan for runs in out["res"]["runs"].values() for r in runs if r.plan]
    if C.sha256_text("".join(C.canon(p) + "\n" for p in plans)) != staged:
        say("oracle_eval", "planos recalculados ≠ staging: rode bo.pilot.run de novo")
        return 2
    judged = E.judge_runs(out["res"])
    neg = E.negatives(out["ctx"], out["res"])
    O = oracle_io.load()
    metrics, data = [], {"oracle": {"version": O.ORACLE_VERSION, "sha256": oracle_io.expected_sha()},
                         "set": "calib", "heldout_read": False, "by_control": {}}
    fails = []
    for ctl, rows in judged.items():
        code = C.CONTROL_CODE[ctl].upper()
        v = collections.Counter(r["verdict"] for r in rows)
        lowered = [r for r in rows if r["verdict"] != "NOT_TRANSPORTED"]
        ok = [r for r in lowered if r["verdict"] in E.ACCEPTING]
        rej = [r for r in lowered if r["verdict"] == "REJECT"]
        fc = neg[ctl]["fixture_claims"]
        cand = neg[ctl]["candidates"]
        acc_claims = [x for x in fc if x["answer"] == "ACCEPT"]
        acc_cand = [x for x in cand if x["answer"] == "ACCEPT"]
        per_dir = {}
        for d in C.DIRECTIONS:
            rs = [r for r in rows if r["direction"] == d]
            per_dir[d] = dict(collections.Counter(r["verdict"] for r in rs))
        data["by_control"][ctl] = {"verdicts": dict(v), "rejects": rej, "per_direction": per_dir,
                                   "negative_fixture_claims": {"n": len(fc), "accepted": acc_claims,
                                                               "answers": dict(collections.Counter(x["answer"] for x in fc))},
                                   "negative_candidates": {"n": len(cand), "accepted": acc_cand,
                                                           "answers": dict(collections.Counter(x["answer"] for x in cand))},
                                   "spurious_declared": sum(len(r.get("spurious_declared") or []) for r in lowered)}
        for name, k, n, reading, axis in (
                ("julgamentos aceitos (com ou sem perda declarada) entre os que desceram", len(ok), len(lowered), "complete_unit", "operational"),
                ("entradas de direção que desceram e foram julgadas", len(lowered), len(rows), "complete_unit", "transportability"),
                ("contraexemplos não aceitos (alegações das fixtures)", len(fc) - len(acc_claims), len(fc), "decision", "representability")):
            metrics.append({"metric_id": f"M-PSTO-{code}-{reading.upper().replace('_', '-')}-{axis.upper()[:5]}-{len(metrics)}",
                            "name": f"{ctl}: {name}", "reading": reading, "axis": axis, "quantifier": "observed_fraction",
                            "operational_coverage": E.wilson(k, n),
                            "frame": {"description": "fixtures de calibração do PILOT-STO-ORACLE"},
                            "inclusion": {"rule_id": "INC-PSTO-CALIB", "text": "entrada de direção ou alegação-contraexemplo de calibração"},
                            "weights": {"scheme": "uniform"}, "joint_uncertainty": {"method": "none"}})
        if ctl == "c3_full":
            if rej:
                fails.append(f"c3: {len(rej)} julgamento(s) REJECT: " + ", ".join(f"{r['entry_id']}:{r['code']}" for r in rej[:5]))
            if acc_claims:
                fails.append(f"c3: {len(acc_claims)} contraexemplo(s) aceito(s)")
            if acc_cand:
                fails.append(f"c3: {len(acc_cand)} configuração(ões)-alvo negativa(s) aceita(s)")
    data["gate"] = {"criteria": ["c3 sem REJECT", "c3 não aceita contraexemplo de fixture",
                                 "c3 não aceita configuração-alvo negativa"], "failures": fails}
    doc = {"schema": "bo.result/1", "contract": "C15", "contract_version": "3.1.0", "module": C.MODULE,
           "generated_at": C.now(), "metrics": metrics,
           "notes": "Julgamento do oráculo offline nas fixtures de calibração. A fração de acerto é relatada, não é limiar (E4).",
           "data": data}
    p = C.results_dir() / "oracle_calib.json"
    C.write_result(p, doc)
    errs = [f"oracle_calib.json: {e}" for e in V.validate("result", p).errors[:5]]
    say("oracle_eval", {ctl: data["by_control"][ctl]["verdicts"] for ctl in data["by_control"]} |
        {"failures": fails, "contract_errors": errs})
    return 0 if not fails and not errs else 1


if __name__ == "__main__":
    raise SystemExit(main())
