"""Conferência de $BO_DATA/DOCS-OCI/type_subcategory.jsonl.

O catálogo de artefatos do plano diz 'type_subcategory.jsonl  DOCS-OCI  C03@3.0.0', mas o C03 3.0.0 só define
o tipo de arquivo docs_facts (registro por átomo). Até a emenda (results/DOCS-OCI/CONTRACT_CHANGE.txt), o
formato é o JSON Schema abaixo, que é exatamente o proposto lá: um registro por tipo (recurso ou data source)
com subcategoria e, para recurso, o ID de importação, cada um com status stated|unknown e fonte doc_source do
C00 (repo, tag, file, line, sentence). Também confere: type_id único e = 'oci:' + resource_type, versão do PINS,
e que todo tipo de recurso e de data source do schema fixado tem registro.

  python -I -m bo.docs_oci.typecheck [ARQ]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import jsonschema

from bo.contracts import catalog

from . import build, source

C00 = "https://w3id.org/brevops/contracts/C00/conventions.schema.json#/$defs/"

_STATUS = {
    "type": "object",
    "properties": {
        "status": {"enum": ["stated", "unknown"]},
        "value": {"type": "string", "minLength": 1},
        "unknown_reason": {"enum": ["not_documented", "ambiguous", "contradictory", "out_of_pin"]},
        "source": {"$ref": C00 + "doc_source"},
        "statement": {"$ref": C00 + "doc_source"},
        "extraction_method": {"enum": ["parser", "regex", "table", "manual", "model"]},
        "evidence_level": {"$ref": C00 + "evidence_level"},
        "id_format": {"type": "string", "minLength": 1},
        "id_is_plain_id": {"type": "boolean"},
        "placeholders": {"type": "array", "items": {"type": "string", "minLength": 1}},
    },
    "required": ["status", "extraction_method", "evidence_level"],
    "additionalProperties": False,
    "allOf": [
        {"if": {"properties": {"status": {"const": "stated"}}},
         "then": {"required": ["source"], "not": {"required": ["unknown_reason"]}}},
        {"if": {"properties": {"status": {"const": "unknown"}}},
         "then": {"required": ["unknown_reason"],
                  "not": {"anyOf": [{"required": ["value"]}, {"required": ["id_format"]}]}}},
    ],
}

SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "C03 type_subcategory (proposto pelo DOCS-OCI): subcategoria e ID de importação por tipo",
    "type": "object",
    "properties": {
        "type_id": {"type": "string", "pattern": "^[a-z][a-z0-9_]*:[a-z][a-z0-9_]*$"},
        "provider": {"type": "string", "pattern": "^[a-z][a-z0-9_]*$"},
        "provider_version": {"$ref": C00 + "semver"},
        "resource_type": {"type": "string", "pattern": "^[a-z][a-z0-9_]*$"},
        "kind": {"enum": ["resource", "data_source"]},
        "doc_file": {"type": "string", "minLength": 1},
        "documented_as_alias_of": {"type": "string", "pattern": "^[a-z][a-z0-9_]*$"},
        "aliases": {"type": "array", "items": {"type": "string", "pattern": "^[a-z][a-z0-9_]*$"}},
        "subcategory": {"allOf": [{"$ref": "#/$defs/status"},
                                  {"if": {"properties": {"status": {"const": "stated"}}},
                                   "then": {"required": ["value"]}}]},
        "import": {"allOf": [{"$ref": "#/$defs/status"},
                             {"if": {"properties": {"status": {"const": "stated"}}},
                              "then": {"required": ["id_format"]}}]},
    },
    "required": ["type_id", "provider", "provider_version", "resource_type", "kind", "subcategory"],
    "additionalProperties": False,
    "allOf": [{"if": {"properties": {"kind": {"const": "resource"}}}, "then": {"required": ["import"]},
               "else": {"not": {"required": ["import"]}}}],
    "$defs": {"status": _STATUS},
}


def check(path: Path) -> list[str]:
    reg = catalog.registry(catalog.schemas())
    v = jsonschema.Draft202012Validator(SCHEMA, registry=reg)
    ver = source.version()
    ps = build.load_schema(ver)
    want = {("resource", t) for t in ps.get("resource_schemas") or {}} | \
           {("data_source", t) for t in ps.get("data_source_schemas") or {}}
    errs, seen = [], set()
    with open(path, encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            r = json.loads(line)
            for e in v.iter_errors(r):
                errs.append(f"linha {i}: {'/'.join(map(str, e.absolute_path)) or '(raiz)'}: {e.message[:160]}")
            key = (r.get("kind"), r.get("resource_type"))
            if key in seen:
                errs.append(f"linha {i}: tipo repetido {key}")
            seen.add(key)
            if r.get("type_id") != f"oci:{r.get('resource_type')}" or r.get("provider_version") != ver:
                errs.append(f"linha {i}: type_id ou provider_version fora do padrão")
    for k in sorted(want - seen):
        errs.append(f"tipo do schema sem registro: {k}")
    for k in sorted(seen - want):
        errs.append(f"registro de tipo fora do schema: {k}")
    return errs


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    p = Path(argv[0]) if argv else build.out_dir() / "type_subcategory.jsonl"
    errs = check(p)
    if errs:
        print("\n".join(errs[:30]))
        print(f"type_subcategory: {len(errs)} erro(s) -> REPROVADO")
        return 1
    n = sum(1 for _ in open(p, encoding="utf-8"))
    print(f"type_subcategory: {n} tipos, 0 erros (schema proposto no CONTRACT_CHANGE) -> OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
