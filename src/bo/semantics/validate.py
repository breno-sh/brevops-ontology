"""Validador do produtor (enquanto bo.contracts.validate não existe):

  python -I -m bo.semantics.validate c09 ARQ.sssom.tsv|ARQ.jsonl [--assess]
  python -I -m bo.semantics.validate composition_table semantics/composition_table.json
  python -I -m bo.semantics.validate counterexamples semantics/counterexamples.jsonl

Confere o JSON Schema proposto (results/SEMANTICS/C09_proposta, C10_proposta) e as regras que o schema não
exprime: guarda na gramática; semantic_relation = predicate_id; ids únicos. --assess roda também as
obrigações de prova e imprime o veredito por alegação (o veredito oficial é do árbitro, ARBITERLIB).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import jsonschema

from . import common
from . import guards as G
from .claims import Claim, check_predicate
from .obligations import assess
from .rules import RULES
from .schemas import BY_KIND
from .sssom_io import read_tsv


def validate_records(kind: str, recs: list[dict]) -> list[str]:
    sch = BY_KIND[kind]
    v = jsonschema.Draft202012Validator(sch)
    errs = []
    ids = []
    for i, r in enumerate(recs, 1):
        for e in v.iter_errors(r):
            errs.append(f"registro {i}: {'/'.join(str(x) for x in e.absolute_path)}: {e.message}")
        if kind == "c09":
            ids.append(r.get("claim_version_id"))
            try:
                G.typecheck(r.get("guard") or {"all": []})
            except G.GuardTypeError as e:
                errs.append(f"registro {i}: guarda: {e}")
            errs.extend(f"registro {i}: {e}" for e in check_predicate(Claim(r)))
        if kind == "counterexample":
            ids.append(r.get("ce_id"))
            if r.get("rule_id") not in RULES:
                errs.append(f"registro {i}: regra desconhecida {r.get('rule_id')}")
    dup = sorted({x for x in ids if ids.count(x) > 1})
    if dup:
        errs.append(f"ids repetidos: {dup}")
    return errs


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) < 2:
        print(__doc__)
        return 2
    kind, path = argv[0], Path(argv[1])
    do_assess = "--assess" in argv
    if kind == "c09":
        recs = read_tsv(path.read_text(encoding="utf-8"))[1] if path.suffix == ".tsv" else common.load_jsonl(path)
    elif kind == "composition_table":
        recs = [json.loads(path.read_text(encoding="utf-8"))]
    elif kind == "counterexamples":
        kind, recs = "counterexample", common.load_jsonl(path)
    else:
        print(f"tipo desconhecido: {kind}")
        return 2
    errs = validate_records(kind, recs)
    for e in errs:
        common.emit(f"  ERRO {e}")
    if do_assess and kind == "c09":
        for r in recs:
            a = assess(r)
            common.emit(f"  {a.verdict:<16} {a.claim_id}  {', '.join(a.rules)}")
    common.emit(f"[{common.now()}] validate {kind} {path.name}: {len(recs)} registro(s), {len(errs)} erro(s)")
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
