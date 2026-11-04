"""Piloto NET de ponta a ponta nos 3 controles (gate: mesma entrada, perda e transformações nos 3).

  python -I -m bo.pilot.run --slice net --controls c1_table,c2_taxonomy,c3_full --fixtures calib
         [--claims mapping|synthetic] [--out DIR] [--write-results]

Roda fixtures x 12 direções x controles, grava no staging (traço C23, plano e IR C26, módulo OWL e C14, casos,
HCL renderizado) e confere: (1) os controles pedidos são exatamente os três; (2) o conjunto de casos é o mesmo nos
três; (3) a ABox de c2 e c3 é a mesma (sha256) e o c1 não usa ABox; (4) a política de perda é a única do
loss_policy e todo código de perda usado está nela; (5) cada alegação usou sempre a mesma transformação; (6) todo
caso tem estado tipado; (7) traço (C23), plano e IR (C26) e tabelas C14 passam no validador único.
--write-results grava results/PILOT-NET-E2E/controls.json (C15). Sai 0 só se (1)-(7) valem.
"""

from __future__ import annotations

import json

from bo.pilot.net import CONTROLS
from bo.pilot.net import loss_policy as LP
from bo.pilot.net import results as RS

from .common import dump, load_report, out_dir, parser, results_dir, run_pipeline, say, validate

STATES = {"TRANSLATED", "UNSUPPORTED", "REFUSED", "RENDER_BLOCKED"}


def main(argv=None) -> int:
    ap = parser("bo.pilot.run", __doc__)
    ap.add_argument("--controls", default=",".join(CONTROLS))
    ap.add_argument("--write-results", action="store_true")
    a = ap.parse_args(argv)
    ctl = a.controls.split(",")
    fails = []
    if sorted(ctl) != sorted(CONTROLS):
        fails.append(f"controles pedidos {ctl} != {list(CONTROLS)}")
    rep = run_pipeline(a)
    out = out_dir(a)
    inv = rep["invariants"]
    if not inv["same_case_set"]:
        fails.append("conjunto de casos difere entre controles")
    if not inv["same_transform_per_claim"]:
        fails.append("alguma alegação usou transformações diferentes entre controles")
    used = {c for v in inv["loss_policy_codes_used"].values() for c in v}
    if used - set(LP.POLICY):
        fails.append(f"códigos de perda fora da política: {sorted(used - set(LP.POLICY))}")
    rows = [json.loads(l) for l in (out / "cases.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    bad = [r["case_id"] for r in rows if r["status"] not in STATES]
    if bad:
        fails.append(f"{len(bad)} caso(s) sem estado tipado")
    for contract, f in (("C23", "translation_trace.jsonl"), ("lowering_plan", "lowering_plan.jsonl"),
                        ("graph_ir", "graph_ir.jsonl"), ("classes", "ontology/classes.jsonl"),
                        ("properties", "ontology/properties.jsonl"), ("realizations", "ontology/realizations.jsonl")):
        p = out / f
        if p.stat().st_size == 0:
            continue
        rc, last = validate(contract, p)
        if rc != 0:
            fails.append(f"{f} reprova no validador ({contract}): {last}")
    c = rep["counts"]
    for k in CONTROLS:
        say(f"{k}: {json.dumps(c.get(k, {}), ensure_ascii=False, sort_keys=True)}")
    if a.write_results:
        doc = RS.controls(out, rep)
        dump(results_dir() / "controls.json", doc)
        rc, last = validate("result", results_dir() / "controls.json")
        if rc != 0:
            fails.append(f"controls.json reprova no C15: {last}")
    for f in fails:
        say("FALHA " + f)
    say(f"run: {'OK' if not fails else 'REPROVADO'} (alegações: {rep['claims']['mode']}, "
        f"{rep['claims']['ok']} OK de {rep['claims']['records']}; ABox {rep['abox_sha256'][:12]})")
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main())
