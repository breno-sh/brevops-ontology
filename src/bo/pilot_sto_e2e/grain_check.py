"""Gate G1: decomposição = gabarito nos casos obrigatórios; invariância a reordenação e à embalagem.

  python -I -m bo.pilot.grain_check --slice sto

Compara a decomposição do lifting (evidência C25, sem o oráculo) com as conferências de decomposição do gabarito de
calibração (expected_answers.json), exige que toda alegação-contraexemplo de decomposição seja recusada pelo c3 e que
a decomposição neutra não mude com ordem de recursos/chaves/blocos (3 sementes) nem com a embalagem (versionamento
AWS embutido × recurso separado; grupos de invariância do gabarito). Relatório no staging: grain_report.json.
"""

from __future__ import annotations

from bo.pilot.sto import common as C
from bo.pilot.sto import evaluate as E
from bo.pilot.sto import pipeline as PL

from ._cli import check_slice, parser, say


def main(argv=None) -> int:
    a = parser("bo.pilot.grain_check", __doc__).parse_args(argv)
    check_slice(a)
    ctx = PL.prepare(out_dir=C.tmp_dir() / "grain_owl")
    g = E.grain(ctx)
    g.update({"generated_at": C.now(), "module": C.MODULE, "inputs": ctx.inputs})
    C.write_json(PL.stage_dir() / "grain_report.json", g)
    fails = (len(g["decomposition_mismatches"]) + len(g["negative_not_rejected"]) + len(g["reorder_failures"])
             + len(g["packaging_failures"]))
    ok = fails == 0 and g["decomposition_checks"] > 0 and g["reorder_trials"] > 0 and g["packaging_trials"] > 0
    say("grain_check", {"decomposition_checks": g["decomposition_checks"], "mismatches": len(g["decomposition_mismatches"]),
                        "negative_claims": g["negative_claims"], "negative_not_rejected": len(g["negative_not_rejected"]),
                        "reorder_trials": g["reorder_trials"], "reorder_failures": len(g["reorder_failures"]),
                        "packaging_trials": g["packaging_trials"], "packaging_failures": len(g["packaging_failures"]),
                        "ok": ok})
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
