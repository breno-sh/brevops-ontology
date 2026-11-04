"""Gate E2: decomposição = gabarito nos casos obrigatórios; invariância a reordenação e à embalagem.

  python -I -m bo.pilot.grain_check --slice net [--fixtures calib|DIR] [--out DIR]

Para cada fixture de calibração dos casos obrigatórios (expected_answers.json, mandatory_cases): decompõe pela
biblioteca de grão (bo.pilot.net.decompose -> bo.grain.instance) e compara com o gabarito pelo comparador do próprio
oráculo (net_oracle.compare_decomposition: unidade faltando, sobrando ou de tipo errado; camada Terraform ignorada;
disputas spec x doc aplicadas ao gabarito). Invariância: (1) reordenação — 3 embaralhamentos de recursos e blocos
dão as mesmas unidades; (2) embalagem — os pares decomposition_invariant_with (embutido x separado) dão as mesmas
unidades a menos da camada Terraform (net_oracle.decomposing.invariant). Grava grain_check.json no staging.
Sai 0 só se toda comparação e toda invariância passam.
"""

from __future__ import annotations

import json

from bo.pilot.net import decompose as DC
from bo.pilot.net import oracle as O

from .common import dump, fixtures_args, out_dir, parser, say


def main(argv=None) -> int:
    ap = parser("bo.pilot.grain_check", __doc__)
    a = ap.parse_args(argv)
    d, split = fixtures_args(a)
    fxs = {fx["fixture_id"]: fx for fx in O.fixtures(d, split)}
    no = O.load()
    from net_oracle import decomposing as ND
    exp = json.loads((O.repo() / "pilot" / "net" / "expected_answers.json").read_text(encoding="utf-8"))
    # casos obrigatórios com gabarito de decomposição (os de tradução, NETC-T-*, são do oracle_eval)
    mandatory = sorted({f for c in exp["mandatory_cases"].values() for lst in c["calib"].values() for f in lst
                        if f in fxs})
    rows, fails = [], []
    for fid in mandatory:
        fx = fxs.get(fid)
        if fx is None:
            fails.append({"fixture_id": fid, "why": "fixture obrigatória ausente"})
            continue
        try:
            units = DC.decompose(fx)
        except Exception as e:  # noqa: BLE001 - erro da biblioteca é resultado, registrado
            fails.append({"fixture_id": fid, "why": f"decomposição falhou: {type(e).__name__}: {e}"[:300]})
            continue
        cmp = no.compare_decomposition(fx["expected"]["decomposition"], units)
        reorder = all(ND.invariant(units, DC.decompose(DC.shuffled(fx, s))) for s in (1, 2, 3))
        row = {"fixture_id": fid, "equal": cmp["equal"], "missing": cmp["missing"], "extra": cmp["extra"],
               "wrong_kind": cmp["wrong_kind"], "reorder_invariant": reorder,
               "kinds": sorted({u["kind"] for u in units})}
        rows.append(row)
        if not cmp["equal"]:
            fails.append({"fixture_id": fid, "why": f"{len(cmp['missing'])} faltando, {len(cmp['extra'])} sobrando, "
                                                    f"{len(cmp['wrong_kind'])} tipo errado"})
        if not reorder:
            fails.append({"fixture_id": fid, "why": "decomposição muda com a reordenação"})
    pack = []
    for fid, fx in sorted(fxs.items()):
        other = fx["expected"].get("decomposition_invariant_with")
        if not other or other not in fxs or fid > other:
            continue
        ok = ND.invariant(DC.decompose(fx), DC.decompose(fxs[other]))
        pack.append({"pair": [fid, other], "invariant": ok})
        if not ok:
            fails.append({"fixture_id": f"{fid}+{other}", "why": "embalagem muda a decomposição"})
    rep = {"schema": "bo.pilot_net.grain_check/1", "mandatory": len(mandatory), "rows": rows, "packaging": pack,
           "failures": fails}
    dump(out_dir(a) / "grain_check.json", rep)
    kinds = {}
    for r in rows:
        for k in r["kinds"]:
            kinds[k] = kinds.get(k, 0) + 1
    say(f"grain_check: {sum(r['equal'] for r in rows)}/{len(rows)} iguais ao gabarito; reordenação "
        f"{sum(r['reorder_invariant'] for r in rows)}/{len(rows)}; embalagem {sum(p['invariant'] for p in pack)}/"
        f"{len(pack)}; tipos {kinds}; falhas {len(fails)} -> {'OK' if not fails else 'REPROVADO'}")
    for f in fails[:12]:
        say(f"  {f['fixture_id']}: {f['why']}")
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main())
