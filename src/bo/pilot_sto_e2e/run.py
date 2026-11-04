"""Gate G2: os três controles com a mesma entrada, a mesma política de perda e as mesmas transformações.

  python -I -m bo.pilot.run --slice sto --controls c1_table,c2_taxonomy,c3_full --fixtures calib

Gera o módulo OWL a partir das alegações OK, sobe as fixtures para ABox, traduz as 181 entradas de direção pelos três
controles, constrói IR de grafo e plano de lowering, renderiza pelos harness e grava o staging e o controls.json.
Sai 0 se os três controles leram o mesmo sha de entrada, de política, de transformações e de alegações, e se todo
arquivo gravado confere com o contrato (C14, C23, C26, C15).
"""

from __future__ import annotations

from bo.contracts import validate as V
from bo.pilot.sto import common as C
from bo.pilot.sto import stage as ST

from ._cli import check_slice, parser, say


def main(argv=None) -> int:
    ap = parser("bo.pilot.run", __doc__)
    ap.add_argument("--controls", default=",".join(C.CONTROLS))
    ap.add_argument("--fixtures", default="calib", choices=["calib"])
    a = ap.parse_args(argv)
    check_slice(a)
    controls = tuple(x.strip() for x in a.controls.split(",") if x.strip())
    bad = [c for c in controls if c not in C.CONTROLS]
    if bad or set(controls) != set(C.CONTROLS):
        raise SystemExit(f"controles têm de ser exatamente {','.join(C.CONTROLS)} (pedido: {a.controls})")
    out = ST.run_all(controls)
    doc = ST.controls_doc(out)
    p = C.results_dir() / "controls.json"
    C.write_result(p, doc)
    errs = ST.validate_contracts()
    r = V.validate("result", p)
    errs += [f"controls.json: {e}" for e in r.errors[:5]]
    same = doc["data"]["same_input"]["checks"]
    say("run", {"same_input": same, "controls": {k: {kk: v[kk] for kk in ("entries", "config_values", "carried_values",
                                                                         "lowered_units", "scope_losses_declared")}
                                                 for k, v in doc["data"]["controls"].items()},
                "contract_errors": errs[:5], "timings_s": out["timings"]})
    return 0 if all(same.values()) and not errs else 1


if __name__ == "__main__":
    raise SystemExit(main())
