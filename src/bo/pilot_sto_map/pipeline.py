"""Um comando, de ponta a ponta, sobre o pacote atual (entradas por hash), tudo em $BO_DATA/PILOT-STO-MAP/.staging.

Uso: python -I -m bo.pilot_sto_map.pipeline [--promote | --promote-only]
  1. build: pacote (MANIFEST conferido) + decisões -> mapping.sssom.tsv, build_record.json
  2. validador oficial do C09 (bo.contracts.validate correspondences)
  3. ida e volta SKOS do arquivo (bo.semantics.skos_roundtrip --file); exceção da biblioteca vira falha registrada
  4. árbitro (bo.arbiter.run --check-unproven, instante fixo decisions.DECIDED_AT; --frozen quando o
     congelamento confere, senão roda sem e registra as divergências): verdicts, cycles, relatório, run_record
  5. pipeline_report.json: entradas por sha256, saída de cada etapa, contagens, bloqueios
  --promote       depois das etapas, troca o staging pelo definitivo (só com a trava merge-base deste módulo)
  --promote-only  só a troca (o staging já gerado), também só com a trava
Saída 0 só se todas as etapas passam; com bloqueio externo (congelamento, C21 do árbitro, ida e volta) sai 1,
mas deixa tudo gravado e diz qual etapa e por quê.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import shutil
from collections import Counter
from pathlib import Path

from . import build as B
from . import decisions as DEC
from .common import (MODULE, OUTPUTS, STAGED, data_root, dump_json, emit, load_bundle, mapper_brief, now,
                     out_dir, run_main, sha256_file, staging_dir)


def _quiet(fn, *a, **k):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
        try:
            rc = fn(*a, **k)
        except SystemExit as e:        # argparse e afins
            rc = e.code if isinstance(e.code, int) else 1
    return rc, buf.getvalue()


def step_validate(path: Path) -> dict:
    from bo.contracts import validate as CV
    rc, out = _quiet(CV.main, ["correspondences", str(path)])
    return {"step": "c09_validate", "ok": rc == 0, "rc": rc, "tail": out.strip().splitlines()[-3:]}


def step_skos(path: Path) -> dict:
    from bo.semantics import skos_roundtrip as SR
    try:
        res = SR.file_checks(path)
    except Exception as e:      # noqa: BLE001 - defeito da biblioteca vira resultado, não queda do pipeline
        return {"step": "skos_roundtrip", "ok": False, "error": f"{type(e).__name__}: {e}"}
    bad = [c for c in res if not c["ok"]]
    return {"step": "skos_roundtrip", "ok": not bad, "checks": len(res), "failed": [c["check"] for c in bad]}


def step_arbiter(path: Path, out: Path) -> dict:
    from bo.arbiter import freeze as AF
    from bo.arbiter import run as AR
    drift = AF.verify()
    args = ["--in", str(path), "--out", str(out), "--decided-at", DEC.DECIDED_AT, "--check-unproven"]
    if not drift:
        args.append("--frozen")
    rc, text = _quiet(AR.main, args)
    c21 = AR.validate_c21(out / "verdicts.jsonl") if (out / "verdicts.jsonl").is_file() else ["verdicts ausente"]
    gaps = [l.strip() for l in text.splitlines() if "check-unproven" in l]
    return {"step": "arbiter", "ok": rc == 0 and not drift and not c21, "rc": rc, "frozen_checked": not drift,
            "freeze_drift": drift, "c21_errors": c21[:10], "n_c21_errors": len(c21), "check_unproven": gaps,
            "tail": text.strip().splitlines()[-2:]}


def verdict_counts(out: Path) -> dict:
    vs = [json.loads(l) for l in (out / "verdicts.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    base = [v for v in vs if "∘" not in v["claim_id"]]
    none = [v for v in base if "-STO-NONE-" in v["claim_id"]]
    claims = [v for v in base if "-STO-NONE-" not in v["claim_id"]]
    return {"claims": dict(Counter(v["verdict"] for v in claims)),
            "absences": dict(Counter(v["verdict"] for v in none)),
            "composites": dict(Counter(v["verdict"] for v in vs if "∘" in v["claim_id"])),
            "rules_on_claims": dict(Counter(r for v in claims for r in v["rules"]))}


def lock_owned() -> tuple[bool, str]:
    f = data_root() / "locks" / "merge-base" / "owner"
    if not f.is_file():
        return False, "trava merge-base livre (a troca para o definitivo só acontece dentro dela)"
    owner = next((l.split("=", 1)[1] for l in f.read_text().splitlines() if l.startswith("owner=")), "")
    if not owner.startswith(MODULE):
        return False, f"trava merge-base pertence a {owner!r}"
    return True, owner


def promote() -> int:
    ok, who = lock_owned()
    if not ok:
        emit(f"[{now()}] promote: recusado: {who}")
        return 3
    st, dst = staging_dir(), out_dir()
    miss = [n for n in STAGED if not (st / n).is_file()]
    if miss:
        emit(f"[{now()}] promote: staging incompleto: {miss}")
        return 1
    for n in STAGED:
        tmp = dst / f".{n}.promote"
        shutil.copyfile(st / n, tmp)
        tmp.replace(dst / n)
    emit(f"[{now()}] promote: {len(STAGED)} arquivo(s) do staging -> {dst} (trava de {who})")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="bo.pilot_sto_map.pipeline")
    ap.add_argument("--promote", action="store_true")
    ap.add_argument("--promote-only", action="store_true")
    a = ap.parse_args(argv)
    if a.promote_only:
        return promote()
    st = staging_dir()
    st.mkdir(parents=True, exist_ok=True)
    b = load_bundle()
    rec = B.build(b, st)
    tsv = st / "mapping.sssom.tsv"
    steps = [{"step": "build", "ok": True, "rows": rec["counts"]["rows"], "dropped": len(rec["dropped"]),
              "downgraded": len(rec["downgraded"]), "exhaustive_gaps": len(B.exhaustive_gaps(b, B.build_records(b)[0]))}]
    steps.append(step_validate(tsv))
    steps.append(step_skos(tsv))
    steps.append(step_arbiter(tsv, st))
    report = {"schema": "bo.pilot_sto_map.pipeline/1", "module": MODULE, "generated_at": now(),
              "timezone": "America/Recife", "decided_at": DEC.DECIDED_AT,
              "inputs": {"bundle_manifest_sha256": b.sha256, "bundle_files": b.hashes,
                         "mapper_brief_sha256": sha256_file(mapper_brief()),
                         "code": rec["inputs"]["code"]},
              "outputs": {n: sha256_file(st / n) for n in ("mapping.sssom.tsv", "build_record.json", "verdicts.jsonl")
                          if (st / n).is_file()},
              "counts": rec["counts"], "verdicts": verdict_counts(st) if (st / "verdicts.jsonl").is_file() else {},
              "steps": steps, "blocked": [s["step"] for s in steps if not s["ok"]]}
    (st / "pipeline_report.json").write_text(dump_json(report), encoding="utf-8")
    for s in steps:
        extra = {k: v for k, v in s.items() if k not in ("step", "ok", "tail")}
        emit(f"  {'OK   ' if s['ok'] else 'FALHA'} {s['step']}: {json.dumps(extra, ensure_ascii=False)[:400]}")
    emit(f"[{now()}] pipeline: {rec['counts']['rows']} linha(s); vereditos {json.dumps(report['verdicts'].get('claims', {}), sort_keys=True)}"
         f"; bloqueios {report['blocked'] or 'nenhum'} -> {st}")
    rc = 0 if not report["blocked"] else 1
    if a.promote:
        prc = promote()
        rc = rc or prc
    return rc


if __name__ == "__main__":
    run_main(main)
