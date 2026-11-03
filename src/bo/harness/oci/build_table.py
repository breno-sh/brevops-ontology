"""Gera a tabela compacta de schema do provider oci fixado (src/bo/harness/oci/data/oci-<versão>.schema_table.jsonl).

  python -I -m bo.harness.oci.build_table           regrava a tabela a partir do dump bruto
  python -I -m bo.harness.oci.build_table --check   regenera em memória e compara byte a byte (saída 1 se difere)

Fonte: os bytes de `terraform providers schema -json` do oci 9.11.0, obtidos pelo HARNESS-OCI num sandbox sem
credenciais (decisão D1) e guardados em $BO_DATA/downloads/registry-oci-9.11.0/schema.json.gz. O sha256 dos bytes
descomprimidos tem de ser o SCHEMA_SHA256 fixado (o mesmo do universe/pins.json); senão nada é gerado.

A tabela guarda só a estrutura (tipos, required/optional/computed, sensitive, write_only, deprecated, blocos com
modo e min/max); descrições ficam de fora. Uma linha de cabeçalho e uma linha por tipo (recurso ou data source),
em ordem.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import sys
from pathlib import Path

from . import (PROVIDER, PROVIDER_REGISTRY_SOURCE, PROVIDER_VERSION, SCHEMA_SHA256, SCHEMA_TABLE,
               TERRAFORM_VERSION, raw_schema_path)

HEADER_SCHEMA = "bo.harness.oci.schema_table/1"
FLAGS = (("required", "r"), ("optional", "o"), ("computed", "c"), ("sensitive", "s"), ("write_only", "w"),
         ("deprecated", "d"))


def _cty(t):
    """Tipo cty com objeto como lista de pares [nome, tipo] (nunca {"nome": "tipo"}, que o linter lê como atribuição)."""
    if isinstance(t, list) and t and t[0] == "object":
        return ["object", [[k, _cty(t[1][k])] for k in sorted(t[1])]]
    if isinstance(t, list) and t and t[0] in ("list", "set", "map"):
        return [t[0], _cty(t[1])]
    if isinstance(t, list) and t and t[0] == "tuple":
        return ["tuple", [_cty(x) for x in t[1]]]
    return t


def strip_block(b: dict) -> dict:
    """Bloco compacto: a = [[nome, tipo cty, flags]], b = [[nome, modo, min, max, deprecated, bloco]].

    flags: r required, o optional, c computed, s sensitive, w write_only, d deprecated. Listas de pares em vez de
    objetos para que nome de atributo nunca apareça como chave JSON seguida de ':' (o privacy_lint é lexical).
    """
    out: dict = {}
    attrs = b.get("attributes") or {}
    if attrs:
        a_out = []
        for name in sorted(attrs):
            a = attrs[name]
            if "nested_type" in a:
                raise ValueError(f"atributo {name}: nested_type não suportado pela tabela (0 no oci {PROVIDER_VERSION})")
            flags = "".join(short for long, short in FLAGS if a.get(long))
            a_out.append([name, _cty(a["type"]), flags])
        out["a"] = a_out
    blocks = b.get("block_types") or {}
    if blocks:
        b_out = []
        for name in sorted(blocks):
            bt = blocks[name]
            b_out.append([name, bt["nesting_mode"], int(bt.get("min_items") or 0), int(bt.get("max_items") or 0),
                          1 if bt["block"].get("deprecated") else 0, strip_block(bt["block"])])
        out["b"] = b_out
    return out


def load_raw(path: Path | None = None) -> dict:
    path = path or raw_schema_path()
    if not path.exists():
        raise FileNotFoundError(f"dump bruto do schema ausente: {path} (refaça o download do D1)")
    raw = gzip.decompress(path.read_bytes())
    got = hashlib.sha256(raw).hexdigest()
    if got != SCHEMA_SHA256:
        raise ValueError(f"sha256 do schema bruto {got[:12]}… difere do fixado {SCHEMA_SHA256[:12]}…")
    return json.loads(raw)


def build_lines(raw: dict) -> list[str]:
    ps = raw["provider_schemas"][PROVIDER_REGISTRY_SOURCE]
    header = {
        "schema": HEADER_SCHEMA, "provider": PROVIDER, "source": PROVIDER_REGISTRY_SOURCE,
        "version": PROVIDER_VERSION, "terraform": TERRAFORM_VERSION, "schema_sha256": SCHEMA_SHA256,
        "generated_by": "bo.harness.oci.build_table",
        "counts": {"resource": len(ps["resource_schemas"]), "data": len(ps["data_source_schemas"])},
        "provider_block": strip_block(ps["provider"]["block"]),
    }
    lines = [json.dumps(header, sort_keys=True, separators=(",", ":"), ensure_ascii=False)]
    for kind, key in (("resource", "resource_schemas"), ("data", "data_source_schemas")):
        for t in sorted(ps[key]):
            rec = {"kind": kind, "type": t, "block": strip_block(ps[key][t]["block"])}
            lines.append(json.dumps(rec, sort_keys=True, separators=(",", ":"), ensure_ascii=False))
    return lines


def render_text(raw: dict) -> str:
    return "\n".join(build_lines(raw)) + "\n"


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    check = "--check" in argv
    try:
        text = render_text(load_raw())
    except (FileNotFoundError, ValueError) as e:
        print(f"build_table: {e}", file=sys.stderr)
        return 3
    if check:
        cur = SCHEMA_TABLE.read_text(encoding="utf-8") if SCHEMA_TABLE.exists() else ""
        if cur != text:
            print(f"build_table --check: {SCHEMA_TABLE.name} difere da regeneração", file=sys.stderr)
            return 1
        print(f"build_table --check: {SCHEMA_TABLE.name} idêntica à regeneração "
              f"({len(text.splitlines()) - 1} tipos, sha256 {hashlib.sha256(text.encode()).hexdigest()[:12]}…)")
        return 0
    SCHEMA_TABLE.parent.mkdir(parents=True, exist_ok=True)
    SCHEMA_TABLE.write_text(text, encoding="utf-8")
    print(f"build_table: {SCHEMA_TABLE} ({len(text.splitlines()) - 1} tipos)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
