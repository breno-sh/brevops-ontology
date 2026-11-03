"""Validador do C24 do lado do produtor: python -I -m bo.requirements.validate {requirements|commitments|cq_spec} ARQ

Mesma interface do bo.contracts.validate <contrato> <arquivo>. Confere o JSON Schema proposto (schemas.py)
registro a registro e depois as regras semânticas de model.validate_*. Referências cruzadas usam os
arquivos irmãos da mesma pasta, quando existem. Sai 0 se tudo confere.
"""

from __future__ import annotations

import sys
from pathlib import Path

import jsonschema

from . import common, model, schemas


def schema_errors(kind: str, recs: list[dict]) -> list[str]:
    v = jsonschema.Draft202012Validator(schemas.BY_KIND[kind])
    out = []
    for n, r in enumerate(recs, 1):
        for e in sorted(v.iter_errors(r), key=lambda e: list(e.absolute_path)):
            path = "/".join(str(p) for p in e.absolute_path) or "(raiz)"
            out.append(f"{kind}[{n}] schema {path}: {e.message[:200]}")
    return out


def validate_file(kind: str, path: Path) -> list[str]:
    recs = common.load_jsonl(path)
    if not recs:
        return [f"{path}: arquivo vazio"]
    errs = schema_errors(kind, recs)
    sib = path.parent
    req_ids = cmt_ids = None
    if kind != "requirements" and (sib / common.KIND_FILE["requirements"]).is_file():
        req_ids = {r.get("req_id") for r in common.load_jsonl(sib / common.KIND_FILE["requirements"])}
    if kind == "cq_spec" and (sib / common.KIND_FILE["commitments"]).is_file():
        cmt_ids = {c.get("commitment_id") for c in common.load_jsonl(sib / common.KIND_FILE["commitments"])}
    if kind == "requirements":
        errs += model.validate_requirements(recs)
    elif kind == "commitments":
        errs += model.validate_commitments(recs, req_ids)
    else:
        errs += model.validate_cq_spec(recs, req_ids, cmt_ids)
    return errs


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) != 2 or argv[0] not in common.KIND_FILE:
        print(__doc__.strip().splitlines()[0], file=sys.stderr)
        return 2
    kind, path = argv[0], Path(argv[1])
    if not path.is_file():
        print(f"arquivo não existe: {path}", file=sys.stderr)
        return 2
    errs = validate_file(kind, path)
    if errs:
        return common.fail(errs, f"C24 {kind} {path}")
    n = len(common.load_jsonl(path))
    print(f"C24 {kind}: {n} registro(s) conferem (schema proposto + regras semânticas) em {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
