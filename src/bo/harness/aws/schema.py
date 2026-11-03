"""Leitura estrutural do schema do provider aws (formato de 'terraform providers schema -json').

Guarda só o que o renderizador e o redator usam: tipo cty, required/optional/computed, sensitive, write_only
dos atributos; nesting_mode, min_items e max_items dos blocos. Descrições ficam de fora.

  python -I -m bo.harness.aws.schema excerpt TIPO [TIPO ...] --out ARQ   recorte do schema fixado (fixture)
  python -I -m bo.harness.aws.schema check-excerpt ARQ                   o recorte é igual ao do schema fixado
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from . import PROVIDER_SOURCE, pins

ATTR_KEYS = ("type", "required", "optional", "computed", "sensitive", "write_only")
BLOCK_KEYS = ("nesting_mode", "min_items", "max_items")


@dataclass
class Attr:
    name: str
    type: object
    required: bool = False
    optional: bool = False
    computed: bool = False
    sensitive: bool = False
    write_only: bool = False

    @property
    def configurable(self) -> bool:
        return self.required or self.optional


@dataclass
class Block:
    attributes: dict[str, Attr] = field(default_factory=dict)
    blocks: dict[str, "NestedBlock"] = field(default_factory=dict)

    @classmethod
    def from_json(cls, b: dict) -> "Block":
        out = cls()
        for n, a in (b.get("attributes") or {}).items():
            if "nested_type" in a and "type" not in a:
                raise ValueError(f"atributo {n} usa nested_type (protocolo 6), fora do que o harness renderiza")
            out.attributes[n] = Attr(n, a.get("type"), *(bool(a.get(k)) for k in ATTR_KEYS[1:]))
        for n, nb in (b.get("block_types") or {}).items():
            out.blocks[n] = NestedBlock(n, nb["nesting_mode"], int(nb.get("min_items") or 0),
                                        int(nb.get("max_items") or 0), Block.from_json(nb.get("block") or {}))
        return out

    def to_json(self) -> dict:
        d: dict = {}
        if self.attributes:
            d["attributes"] = {n: _attr_json(a) for n, a in sorted(self.attributes.items())}
        if self.blocks:
            d["block_types"] = {n: nb.to_json() for n, nb in sorted(self.blocks.items())}
        return d


def _attr_json(a: Attr) -> dict:
    d = {"type": a.type}
    for k in ATTR_KEYS[1:]:
        if getattr(a, k):
            d[k] = True
    return d


@dataclass
class NestedBlock:
    name: str
    nesting_mode: str
    min_items: int
    max_items: int
    block: Block

    def to_json(self) -> dict:
        d = {"nesting_mode": self.nesting_mode, "block": self.block.to_json()}
        if self.min_items:
            d["min_items"] = self.min_items
        if self.max_items:
            d["max_items"] = self.max_items
        return d


class ProviderSchema:
    def __init__(self, resource_schemas: dict, provider_version: str, sha256: str, origin: str):
        self._raw = resource_schemas
        self._cache: dict[str, Block] = {}
        self.provider_version = provider_version
        self.sha256 = sha256
        self.origin = origin

    def has(self, rtype: str) -> bool:
        return rtype in self._raw

    def resource(self, rtype: str) -> Block:
        if rtype not in self._cache:
            self._cache[rtype] = Block.from_json(self._raw[rtype]["block"])
        return self._cache[rtype]

    def types(self) -> list[str]:
        return sorted(self._raw)


def _from_doc(doc: dict, version: str, sha: str, origin: str) -> ProviderSchema:
    ps = doc["provider_schemas"][PROVIDER_SOURCE]
    return ProviderSchema(ps["resource_schemas"], version, sha, origin)


@lru_cache(maxsize=4)
def _load_cached(path: str, version: str, sha: str) -> ProviderSchema:
    return _from_doc(json.loads(Path(path).read_text(encoding="utf-8")), version, sha, path)


def load_pinned() -> ProviderSchema:
    """Schema completo da versão fixada; reprova se o arquivo não for o fixado (sha256)."""
    p, pin = pins.verified_schema_path()
    return _load_cached(str(p), pin.provider_version, pin.schema_sha256)


def load_excerpt(path: Path) -> ProviderSchema:
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    meta = doc.get("bo_excerpt") or {}
    return _from_doc(doc, meta.get("provider_version", "?"), meta.get("schema_sha256", "?"), str(path))


def load(schema_arg: str | None) -> ProviderSchema:
    if schema_arg:
        p = Path(schema_arg)
        doc_head = p.read_text(encoding="utf-8")[:4096]
        if '"bo_excerpt"' in doc_head:
            return load_excerpt(p)
        pin = pins.load_pin()
        sha = pins.sha256_file(p)
        if sha != pin.schema_sha256:
            raise pins.PinError(f"schema {p} não é o fixado (sha256 {sha[:12]}…)")
        return _load_cached(str(p), pin.provider_version, sha)
    return load_pinned()


def excerpt(full: ProviderSchema, types: list[str]) -> dict:
    missing = [t for t in types if not full.has(t)]
    if missing:
        raise KeyError(f"tipos fora do schema fixado: {missing}")
    return {
        "bo_excerpt": {"provider_version": full.provider_version, "schema_sha256": full.sha256,
                       "note": "recorte do schema fixado; só os campos estruturais (sem descrições)"},
        "format_version": "1.0",
        "provider_schemas": {PROVIDER_SOURCE: {"resource_schemas": {
            t: {"block": full.resource(t).to_json()} for t in sorted(types)}}},
    }


def dump(doc: dict) -> str:
    return json.dumps(doc, ensure_ascii=False, indent=1, sort_keys=True) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="bo.harness.aws.schema")
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("excerpt")
    e.add_argument("types", nargs="+")
    e.add_argument("--out", required=True)
    c = sub.add_parser("check-excerpt")
    c.add_argument("path")
    a = ap.parse_args(argv)
    full = load_pinned()
    if a.cmd == "excerpt":
        Path(a.out).write_text(dump(excerpt(full, a.types)), encoding="utf-8")
        print(f"recorte de {len(a.types)} tipo(s) do aws {full.provider_version} em {a.out}")
        return 0
    have = json.loads(Path(a.path).read_text(encoding="utf-8"))
    types = list(have["provider_schemas"][PROVIDER_SOURCE]["resource_schemas"])
    want = excerpt(full, types)
    if dump(have) != dump(want):
        print(f"recorte {a.path} difere do schema fixado aws {full.provider_version}")
        return 1
    print(f"recorte {a.path}: {len(types)} tipo(s) iguais ao schema fixado aws {full.provider_version}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
