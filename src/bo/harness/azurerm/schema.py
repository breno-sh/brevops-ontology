"""Índice compacto do schema fixado do azurerm (deploy/fixtures/azurerm/_templates/schema_index.jsonl).

No arquivo, o nó é {"a": [[atributo, marcas, tipo]], "b": [[bloco, modo, min, max, nó]]}; ao carregar vira
{"a": {atributo: [marcas, tipo cty]}, "b": {bloco: [nesting_mode, min_items, max_items, nó]}}, com o tipo
objeto do cty de volta como ["object", {nome: tipo}].
Marcas: r required, o optional, c computed, s sensitive, w write_only.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from ._common import HarnessError, templates_dir


@dataclass(frozen=True)
class AttrInfo:
    flags: str
    type: object

    @property
    def required(self) -> bool:
        return "r" in self.flags

    @property
    def configurable(self) -> bool:
        return "r" in self.flags or "o" in self.flags

    @property
    def sensitive(self) -> bool:
        return "s" in self.flags

    @property
    def write_only(self) -> bool:
        return "w" in self.flags


@dataclass(frozen=True)
class BlockInfo:
    mode: str
    min_items: int
    max_items: int
    node: dict


class Schema:
    def __init__(self, header: dict, resources: dict, data: dict, path: Path):
        self.header = header
        self.resources = resources
        self.data = data
        self.path = path

    @property
    def version(self) -> str:
        return self.header["version"]

    def node(self, kind: str, rtype: str) -> dict | None:
        return (self.resources if kind == "resource" else self.data).get(rtype)


def attrs(node: dict) -> dict[str, AttrInfo]:
    return {k: AttrInfo(v[0], v[1]) for k, v in node.get("a", {}).items()}


def blocks(node: dict) -> dict[str, BlockInfo]:
    return {k: BlockInfo(v[0], v[1], v[2], v[3]) for k, v in node.get("b", {}).items()}


def _dec_type(t):
    if isinstance(t, list) and t and t[0] == "object" and len(t) > 1 and isinstance(t[1], list):
        out = ["object", {k: _dec_type(v) for k, v in t[1]}]
        return out + t[2:]
    if isinstance(t, list):
        return [_dec_type(x) for x in t]
    return t


def _dec(node: dict) -> dict:
    out = {}
    if "a" in node:
        out["a"] = {n: [f, _dec_type(t)] for n, f, t in node["a"]}
    if "b" in node:
        out["b"] = {n: [m, lo, hi, _dec(sub)] for n, m, lo, hi, sub in node["b"]}
    return out


@lru_cache(maxsize=4)
def _load(path: str) -> Schema:
    p = Path(path)
    if not p.is_file():
        raise HarnessError(f"índice do schema ausente: {p} (rode bo.harness.azurerm.build_templates)")
    res, data, header = {}, {}, None
    with open(p, encoding="utf-8") as f:
        for i, line in enumerate(f):
            o = json.loads(line)
            if i == 0:
                header = o
                if o.get("schema") != "bo.harness_azurerm.schema_index/1":
                    raise HarnessError(f"{p}: cabeçalho inesperado")
                continue
            (res if o["kind"] == "resource" else data)[o["type"]] = _dec(o["block"])
    return Schema(header, res, data, p)


def load(tdir: Path | None = None) -> Schema:
    return _load(str((tdir or templates_dir()) / "schema_index.jsonl"))


def templates_manifest(tdir: Path | None = None) -> dict:
    p = (tdir or templates_dir()) / "TEMPLATES.json"
    if not p.is_file():
        raise HarnessError(f"TEMPLATES.json ausente em {p.parent}")
    return json.loads(p.read_text(encoding="utf-8"))
