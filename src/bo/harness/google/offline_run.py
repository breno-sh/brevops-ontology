"""Rodada offline do executor com todas as respostas gravadas (_templates/recorded/*.json).

  python -I -m bo.harness.google.offline_run

Cada gravação diz a fixture, as ligações sintéticas dos símbolos e o desfecho esperado. Roda o executor completo
(identidade e intenção simuladas que só registram; RecordedRunner; nenhum terraform, nenhuma nuvem), grava a saída
C12 redigida em $BO_DATA/HARNESS-GCP/offline_run/ (readback.jsonl, outcomes.jsonl, run_events.jsonl), valida no
validador único e confere desfecho e resíduo de cada gravação. Saída 0 só se tudo confere.
"""

from __future__ import annotations

import json
import shutil
import sys
import uuid

from . import common as C
from . import executor as X


def case_for(plan: dict, n: int) -> dict:
    return {"case_id": f"CASE-HGOFF-{n:03d}", "group_id": "G-HGOFF-0001", "claim_id": "CLM-EX-01",
            "claim_version_id": "CLM-EX-01@2", "comparator": {"name": "exact"}, "cost_class": "low",
            "frame_ref": {"path": "$BO_DATA/DEPSAMPLE/frame.jsonl", "sha256": "0" * 64},
            "lowering_plan": {"plan_id": plan["plan_id"], "graph_id": plan["graph_id"]}, "origin": "sample",
            "side": "object", "stratum": {"cardinality": "1:1", "direction": "forward", "domain": "DB",
                                          "pair": "AWSGCP", "relation": "exact"},
            "values": [{"term": {"datatype": "number", "kind": "literal", "value": 7}, "var": "pa:x"}], "weight": 1.0}


def main(argv=None) -> int:
    out = C.module_data() / "offline_run"
    if out.exists():
        shutil.rmtree(out)
    run_id = "off-" + uuid.uuid4().hex[:8]
    runs, checks = [], []
    recs = sorted((C.templates() / "recorded").glob("*.json"))
    for n, p in enumerate(recs, 1):
        rec = json.loads(p.read_text(encoding="utf-8"))
        d = C.templates() / "plans" / rec["fixture"]
        plan, graph = C.read_jsonl(d / "lowering_plan.jsonl")[0], C.read_jsonl(d / "graph_ir.jsonl")[0]
        intents = []
        ex = X.Executor(X.RecordedRunner(rec), identity_guard=lambda: True,
                        intent=lambda stage, *a: intents.append(stage) or True, run_id=f"{run_id}-{n:02d}",
                        sleep=lambda s: None, allow_disk_ephemeral=True)
        r = ex.run_case(case_for(plan, n), plan, graph, bindings=rec["bindings"],
                        runtime_context={"region": "us-central1"})
        runs.append(r)
        got = r.outcome["outcome"]["value"]
        ok = got == rec["expected_outcome"] and bool(r.residue) == rec["expected_residue"]
        checks.append({"recording": p.name, "outcome": got, "expected": rec["expected_outcome"],
                       "residue": len(r.residue), "intents": intents, "ok": ok})
    try:
        ex.write(runs, out)
        residue_raised = False
    except X.ResidueError:
        residue_raised = True
    errs = C.validate("C12", out / "readback.jsonl") + C.validate("C12", out / "outcomes.jsonl")
    shutil.rmtree(C.tmp() / "runs", ignore_errors=True)
    want_residue = any(c["residue"] for c in checks)
    good = all(c["ok"] for c in checks) and not errs and residue_raised == want_residue
    rep = {"schema": "bo.harness_google.offline_run/1", "module": C.MODULE, "generated_at": C.now(),
           "recordings": len(recs), "checks": checks, "c12_errors": errs, "residue_error_raised": residue_raised,
           "verdict": "PASS" if good else "FAIL"}
    (out / "offline_run_report.json").write_text(C.dump(rep), encoding="utf-8")
    print(f"[{C.now()}] offline_run: {len(recs)} gravação(ões); "
          f"{sum(c['ok'] for c in checks)}/{len(checks)} desfechos conferem; C12 {'OK' if not errs else 'REPROVADO'}; "
          f"resíduo {'levantado' if residue_raised else 'não levantado'} (esperado: {want_residue})")
    for c in checks:
        print(f"  {c['recording']}: {c['outcome']} (esperado {c['expected']}){' RESÍDUO' if c['residue'] else ''}"
              f"{'' if c['ok'] else '  <- DIVERGE'}")
    return 0 if good else 1


if __name__ == "__main__":
    sys.exit(main())
