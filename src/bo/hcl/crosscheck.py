"""Gate: contagem por tipo bate com a tabela Resources do sqlite do TerraDS (±2%).

  python -I -m bo.hcl.crosscheck

Unidade: (Managed|Data, tipo) dos quatro provedores do C00 (prefixos aws_, google_, azurerm_, oci_).
Nossa contagem: blocos resource/data lidos pelo parser (parse_stats.json, antes de qualquer deduplicação).
Critério (fixado antes de ver o resultado): para todo tipo, |nosso - sqlite| <= max(ceil(0.02 * sqlite), 1)
(2% arredondado para cima, pelo menos 1 bloco, porque 2% de um tipo com menos de 50 blocos é menos de 1),
e o total dos quatro provedores dentro de ±2%. Tipo só de um lado também entra (o outro lado conta 0).
O relatório inteiro vai para $BO_DATA/HCL/crosscheck.json.
"""

from __future__ import annotations

import json
import math
import sys

from . import source
from .common import PROVIDERS, now, out_dir, write_json


def main(argv=None) -> int:
    d = out_dir()
    st = json.load(open(d / "parse_stats.json", encoding="utf-8"))
    ours = {k: v for k, v in st["blocks_by_type"].items() if k.split(":", 1)[1].split("_", 1)[0] in PROVIDERS}
    con = source.sqlite_conn()
    theirs = {}
    for kind, typ, n in con.execute("select ResourceType, Type, count(*) from Resources group by 1, 2"):
        if "_" in typ and typ.split("_", 1)[0] in PROVIDERS:
            theirs[f"{kind}:{typ}"] = n
    keys = sorted(set(ours) | set(theirs))
    bad, rows = [], []
    for k in keys:
        a, b = ours.get(k, 0), theirs.get(k, 0)
        tol = max(math.ceil(0.02 * b), 1)
        ok = abs(a - b) <= tol
        rows.append({"type": k, "ours": a, "sqlite": b, "diff": a - b, "tolerance": tol, "ok": ok})
        if not ok:
            bad.append(rows[-1])
    ta, tb = sum(ours.values()), sum(theirs.values())
    total_ok = tb > 0 and abs(ta - tb) <= 0.02 * tb
    exact = sum(1 for r in rows if r["diff"] == 0)
    rep = {"at": now(), "criterion": "|nosso-sqlite| <= max(ceil(0.02*sqlite),1) por tipo; total ±2%",
           "types": len(rows), "types_ok": len(rows) - len(bad), "types_exact": exact,
           "total_ours": ta, "total_sqlite": tb, "total_rel_diff": round((ta - tb) / tb, 6) if tb else None,
           "by_provider": {p: {"ours": sum(v for k, v in ours.items() if k.split(":", 1)[1].startswith(p + "_")),
                               "sqlite": sum(v for k, v in theirs.items() if k.split(":", 1)[1].startswith(p + "_"))}
                           for p in PROVIDERS},
           "failing": sorted(bad, key=lambda r: -abs(r["diff"])), "result": "PASS" if (not bad and total_ok) else "FAIL"}
    write_json(d / "crosscheck.json", rep)
    print(f"[{now()}] bo.hcl.crosscheck: {len(rows)} tipos, {len(rows) - len(bad)} dentro da tolerância, "
          f"{exact} exatos; total {ta} vs {tb} ({rep['total_rel_diff']}) -> {rep['result']}")
    for r in rep["failing"][:15]:
        print(f"  FORA {r['type']}: nosso {r['ours']} sqlite {r['sqlite']} (tol {r['tolerance']})")
    return 0 if rep["result"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
