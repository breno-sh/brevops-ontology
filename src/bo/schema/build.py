"""Átomos (C01) e tipos (C02) de um schema extraído, para os produtores (SCHEMA-*, HIST-*, SCHEMA-POST).

  python -I -m bo.schema.build --schema DIR/schema.json.gz --provider aws [--version V]
                               --atoms OUT/atoms.jsonl --types OUT/types.jsonl [--no-validate]

A versão sai do receipt.json ao lado do schema (gravado por bo.schema.extract) ou de --version; se os dois
existem e divergem, reprova (o 'providers schema -json' não traz a versão: ela nunca é adivinhada).
Saída ordenada por (tipo, caminho), uma linha JSON com chaves ordenadas: regenerar dá os mesmos bytes.
Valida os dois arquivos com bo.contracts.validate (C01, C02) e sai 1 se algum não conferir.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import core


def resolve_version(schema: Path, version: str | None) -> str:
    rc = schema.parent / "receipt.json"
    rv = None
    if rc.exists():
        rv = json.loads(rc.read_text(encoding="utf-8")).get("provider", {}).get("version")
    if version and rv and version != rv:
        raise SystemExit(f"build: --version {version} != receipt.json {rv}")
    v = version or rv
    if not v:
        raise SystemExit("build: sem versão (passe --version ou deixe o receipt.json do extract ao lado do schema)")
    return v


def build(schema: Path, provider: str, version: str | None, atoms_out: Path, types_out: Path,
          elements: bool = False) -> dict:
    """elements=False (padrão): o atoms.jsonl de sempre (TypeSchema.atoms). elements=True: também os átomos de
    elemento de coleção do C01 2.2.0 (TypeSchema.all_atoms()); a troca nos produtores é da fase 2."""
    ver = resolve_version(schema, version)
    ps = core.providers(core.load(schema))
    if provider not in ps:
        raise SystemExit(f"build: o schema não traz o provedor {provider} (traz: {', '.join(ps)})")
    types = list(core.iter_types(ps[provider], provider, ver))
    na = core.write_jsonl(atoms_out, (a for ts in types for a in (ts.all_atoms() if elements else ts.atoms)))
    nt = core.write_jsonl(types_out, (core.type_record(ts) for ts in types))
    return {"provider": provider, "provider_version": ver, "types": nt, "atoms": na,
            **({"element_atoms": sum(len(v) for ts in types for v in ts.elements.values())} if elements else {}),
            "schema_sha256": core.canonical_sha256(ps[provider])}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="bo.schema.build", description=__doc__.split("\n")[0])
    ap.add_argument("--schema", required=True, type=Path)
    ap.add_argument("--provider", required=True)
    ap.add_argument("--version")
    ap.add_argument("--atoms", required=True, type=Path)
    ap.add_argument("--types", required=True, type=Path)
    ap.add_argument("--no-validate", action="store_true")
    ap.add_argument("--elements", action="store_true", help="inclui os átomos de elemento de coleção (C01 2.2.0)")
    a = ap.parse_args(argv)
    r = build(a.schema, a.provider, a.version, a.atoms, a.types, a.elements)
    ok = True
    if not a.no_validate:
        from bo.contracts import validate as V
        for alias, p in (("C01_atoms", a.atoms), ("C02_types", a.types)):
            res = V.validate(alias, p)
            r[f"{alias}_ok"] = res.ok
            ok &= res.ok
            for e in res.errors[:10]:
                print(f"  FAIL {alias}: {e}", file=sys.stderr)
    print(json.dumps(r, ensure_ascii=False, sort_keys=True))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
