"""Gate: contagem por tipo bate com a tabela Resources do sqlite do TerraDS (±2%).

  python -I -m bo.hcl.crosscheck

Unidade (decisão do coordenador, 2026-11-04): a da tabela de referência, (diretório de módulo, Managed|Data,
tipo, nome) único, contada por bo.hcl.unitcount em $BO_DATA/HCL/unit_counts.json. Tipos: os dos quatro
provedores do C00 (prefixos aws_, google_, azurerm_, oci_).
Critério (fixado antes de ver o resultado, inalterado): para todo tipo, |nosso - sqlite| <= max(ceil(0.02 *
sqlite), 1), e o total dentro de ±2%. Tipo só de um lado entra com 0 do outro.
Também grava a contagem ORIGINAL por bloco (parse_stats.json, sem alinhar a unidade) e o resultado dela,
para registro. Tipo fora da tolerância cuja diferença é toda falta em diretório com arquivo que o
python-hcl2 recusou (sem ela o tipo cabe na tolerância) é achado de cobertura do parser (lista em results/HCL/parser_coverage_types.json).
Sai 0 só se todos os tipos alinhados estão dentro e o total também.
"""

from __future__ import annotations

import json
import math
import sys

from .common import PROVIDERS, now, out_dir, results_dir, sha256_file, write_json
from . import source


def compare(ours: dict, theirs: dict) -> dict:
    keys = sorted(set(ours) | set(theirs))
    rows, bad = [], []
    for k in keys:
        a, b = ours.get(k, 0), theirs.get(k, 0)
        tol = max(math.ceil(0.02 * b), 1)
        r = {"type": k, "ours": a, "sqlite": b, "diff": a - b, "tolerance": tol, "ok": abs(a - b) <= tol}
        rows.append(r)
        if not r["ok"]:
            bad.append(r)
    ta, tb = sum(ours.values()), sum(theirs.values())
    return {"types": len(rows), "types_ok": len(rows) - len(bad), "types_exact": sum(r["diff"] == 0 for r in rows),
            "total_ours": ta, "total_sqlite": tb, "total_rel_diff": round((ta - tb) / tb, 6) if tb else None,
            "total_ok": bool(tb) and abs(ta - tb) <= 0.02 * tb, "failing": sorted(bad, key=lambda r: -abs(r["diff"]))}


def main(argv=None) -> int:
    d = out_dir()
    st = json.load(open(d / "parse_stats.json", encoding="utf-8"))
    uc = json.load(open(d / "unit_counts.json", encoding="utf-8"))
    if uc["tar_sha256"] != sha256_file(source.TAR) or uc["repos"] != st["repos"]:
        print("FAIL unit_counts.json não é do tar/extração atuais")
        return 1
    con = source.sqlite_conn()
    theirs = {}
    for kind, typ, n in con.execute("select ResourceType, Type, count(*) from Resources group by 1, 2"):
        if "_" in typ and typ.split("_", 1)[0] in PROVIDERS:
            theirs[f"{kind}:{typ}"] = n
    if theirs != uc["sqlite"]:
        print("FAIL a contagem do sqlite em unit_counts.json difere da tabela")
        return 1
    raw = {k: v for k, v in st["blocks_by_type"].items() if k.split(":", 1)[1].split("_", 1)[0] in PROVIDERS}
    original = compare(raw, theirs)
    aligned = compare(uc["ours"], theirs)
    dec = uc["decomposition"]
    coverage, other = [], []
    for r in aligned["failing"]:
        x = dec.get(r["type"], {})
        refused = x.get("falta_em_dir_com_arquivo_recusado", 0)
        item = {"type": r["type"], "ours": r["ours"], "sqlite": r["sqlite"], "diff": r["diff"],
                "tolerance": r["tolerance"], "decomposition": x}
        # explicado só pelo parser: tirando a falta em diretórios com arquivo recusado, o tipo fica na tolerância
        if r["diff"] < 0 and abs(r["diff"] + refused) <= r["tolerance"]:
            coverage.append(item)
        else:
            other.append(item)
    ok = not aligned["failing"] and aligned["total_ok"]
    rep = {"at": now(), "criterion": "|nosso-sqlite| <= max(ceil(0.02*sqlite),1) por tipo; total ±2%",
           "unit": uc["unit"], "original_block_count": {k: v for k, v in original.items() if k != "failing"},
           "aligned": {k: v for k, v in aligned.items() if k != "failing"},
           "aligned_failing_parser_coverage": len(coverage), "aligned_failing_other": len(other),
           "failing": aligned["failing"], "result": "PASS" if ok else "FAIL"}
    write_json(d / "crosscheck.json", rep)
    write_json(results_dir() / "parser_coverage_types.json", {
        "note": "tipos fora de ±2% na unidade alinhada cuja diferença é só falta em diretório com arquivo que o "
                "python-hcl2 8.1.4 recusou (cobertura do parser); 'other' = fora por outra causa",
        "original_block_count": {k: original[k] for k in ("types", "types_ok", "total_rel_diff")},
        "aligned": {k: aligned[k] for k in ("types", "types_ok", "total_rel_diff")},
        "parser_coverage": coverage, "other": other})
    o, a = original, aligned
    print(f"[{now()}] bo.hcl.crosscheck: original (bloco) {o['types_ok']}/{o['types']} tipos dentro, total "
          f"{o['total_rel_diff']}; alinhado (tipo.nome único por diretório) {a['types_ok']}/{a['types']} dentro, "
          f"{a['types_exact']} exatos, total {a['total_ours']} vs {a['total_sqlite']} ({a['total_rel_diff']}); "
          f"fora: {len(coverage)} só por arquivo recusado pelo parser, {len(other)} por outra causa -> {rep['result']}")
    for r in other[:15]:
        print(f"  FORA (outra causa) {r['type']}: nosso {r['ours']} sqlite {r['sqlite']} {r['decomposition']}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
