"""python -I -m bo.metrics.denominator_invariance ID [--stubs] [--symbolic ARQ ...] [--limit N]

Para todo documento de política (C06 term kind=document, format=policy_json) da configuração simbólica do
módulo: a contagem de decisões (leitura por decisão) é a mesma no documento original, nas variantes que não
mudam o significado (reserializar, reordenar chaves, partir listas, inverter a ordem das declarações) e no
mesmo documento explodido em campos de blocos statement; e a leitura por campo do explodido tem MAIS campos
que a do original (um documento é um campo só). Fontes, em ordem: --symbolic; --stubs (contracts/stubs/C06);
entradas *symbolic_config.jsonl do módulo no catálogo; $BO_DATA/HCL/symbolic_config.jsonl.
Documento em formato que a normalização não conhece é contado à parte (nunca vira 1 decisão por linha).
Saída 0 = invariante; 1 = defeito ou nenhum documento; 2 = uso.
"""
from __future__ import annotations

import argparse
import json
import sys

from . import units as U
from ._cli import catalog, expand, say
from .invariance import NotExplodable, policy_to_block_records, policy_variants
from .spec import repo_root


def sources(mid: str, a) -> list:
    if a.symbolic:
        return [expand(x) for x in a.symbolic]
    if a.stubs:
        return [repo_root() / "contracts" / "stubs" / "C06" / "symbolic_config.jsonl"]
    ins = [expand(i) for i in catalog().get(mid, {}).get("inputs", []) if i.endswith("symbolic_config.jsonl")]
    return ins or [expand("$BO_DATA/HCL/symbolic_config.jsonl")]


def check_record(rec: dict) -> list[str]:
    errs = []
    f0 = U.fields_from_symbolic([rec])
    d0 = U.decision_units(f0)
    n0 = len(d0)
    ids0 = [d.decision_id for d in d0]
    for name, tree in policy_variants(rec["term"]["tree"]).items():
        r2 = {**rec, "term": {**rec["term"], "tree": tree}}
        d2 = U.decision_units(U.fields_from_symbolic([r2]))
        if [d.decision_id for d in d2] != ids0:
            errs.append(f"variante {name}: {len(d2)} decisão(ões) contra {n0}")
    try:
        blocks = policy_to_block_records(rec)
    except NotExplodable:
        return errs + ["__not_explodable__"]
    fb = U.fields_from_symbolic(blocks)
    db = U.decision_units(fb)
    if [d.decision_id for d in db] != ids0:
        errs.append(f"explodido em campos: {len(db)} decisão(ões) contra {n0}")
    if n0 and len(U.field_units(fb)) <= len(U.field_units(f0)):
        errs.append(f"explodido em campos: {len(fb)} campo(s), não mais que {len(f0)}")
    return errs


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="bo.metrics.denominator_invariance")
    ap.add_argument("module")
    ap.add_argument("--stubs", action="store_true")
    ap.add_argument("--symbolic", action="append")
    ap.add_argument("--limit", type=int, default=0, help="no máximo N documentos (0 = todos)")
    a = ap.parse_args(argv)
    if a.module not in catalog():
        print(f"módulo {a.module} fora do catálogo")
        return 2
    n_docs = n_unsup = n_noexp = 0
    errs = []
    srcs = sources(a.module, a)
    for src in srcs:
        if not src.is_file():
            errs.append(f"{src}: não existe")
            continue
        with open(src, encoding="utf-8") as fh:
            for line in fh:
                if '"policy_json"' not in line:
                    continue
                rec = json.loads(line)
                t = rec["term"]
                if t.get("kind") != "document" or t.get("format") != "policy_json":
                    continue
                try:
                    e = check_record(rec)
                except U.UnsupportedPolicyFormat:
                    n_unsup += 1
                    continue
                n_docs += 1
                if "__not_explodable__" in e:
                    n_noexp += 1
                    e = [x for x in e if x != "__not_explodable__"]
                errs += [f"{rec['repo_id']}|{rec['resource_address']}: {x}" for x in e]
                if a.limit and n_docs >= a.limit:
                    break
    for e in errs[:50]:
        print("  FAIL " + e)
    if n_docs == 0:
        say(f"denominator_invariance {a.module}: nenhum documento de política conferido (nada passa por vacuidade)")
        return 1
    say(f"denominator_invariance {a.module}: {n_docs} documento(s), {n_unsup} em formato não normalizável, "
        f"{n_noexp} sem forma de bloco (só variantes), {len(errs)} defeito(s) -> {'OK' if not errs else 'REPROVADO'}")
    return 0 if not errs else 1


if __name__ == "__main__":
    sys.exit(main())
