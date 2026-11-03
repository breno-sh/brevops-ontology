"""Leitura da tabela compacta do schema do oci fixado e resolução de caminhos de campo do C26.

Um caminho de valor do C26 (`a.b.c`, só [A-Za-z0-9_] e pontos) é resolvido contra o schema assim:
  - segmento que é atributo do bloco corrente -> atributo; segmentos seguintes só se o tipo do atributo for
    map (chave livre) ou object (chave tem de ser atributo do objeto);
  - segmento que é bloco aninhado -> bloco; com modo list ou set, o segmento seguinte pode ser um índice de
    ocorrência só com dígitos (0, 1, ...); sem índice, é a ocorrência 0 (um bloco só);
  - qualquer outro segmento -> FIELD_NOT_IN_SCHEMA (o renderizador não adivinha).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from . import PROVIDER_VERSION, SCHEMA_SHA256, SCHEMA_TABLE


@dataclass(frozen=True)
class Attr:
    name: str
    type: object
    flags: str

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

    @property
    def deprecated(self) -> bool:
        return "d" in self.flags


@dataclass
class Block:
    attrs: dict = field(default_factory=dict)
    blocks: dict = field(default_factory=dict)   # nome -> BlockType


@dataclass
class BlockType:
    name: str
    mode: str          # single | list | set | map | group
    min_items: int
    max_items: int     # 0 = sem limite
    deprecated: bool
    block: Block

    @property
    def repeatable(self) -> bool:
        return self.mode in ("list", "set")


def parse_block(raw: dict) -> Block:
    b = Block()
    for name, typ, flags in raw.get("a", []):
        b.attrs[name] = Attr(name, typ, flags)
    for name, mode, mn, mx, dep, sub in raw.get("b", []):
        b.blocks[name] = BlockType(name, mode, int(mn), int(mx), bool(dep), parse_block(sub))
    return b


class SchemaTable:
    def __init__(self, path: Path = SCHEMA_TABLE):
        lines = path.read_text(encoding="utf-8").splitlines()
        self.header = json.loads(lines[0])
        if self.header.get("schema_sha256") != SCHEMA_SHA256 or self.header.get("version") != PROVIDER_VERSION:
            raise ValueError(f"tabela de schema {path.name} não é do oci {PROVIDER_VERSION} fixado")
        self._raw = {}
        for ln in lines[1:]:
            rec = json.loads(ln)
            self._raw[(rec["kind"], rec["type"])] = rec["block"]
        self._parsed: dict = {}
        self.provider_block = parse_block(self.header["provider_block"])

    def has(self, kind: str, rtype: str) -> bool:
        return (kind, rtype) in self._raw

    def block(self, kind: str, rtype: str) -> Block:
        key = (kind, rtype)
        if key not in self._parsed:
            self._parsed[key] = parse_block(self._raw[key])
        return self._parsed[key]

    def types(self, kind: str) -> list[str]:
        return sorted(t for k, t in self._raw if k == kind)


@lru_cache(maxsize=1)
def table() -> SchemaTable:
    return SchemaTable()


class PathError(ValueError):
    def __init__(self, code: str, msg: str):
        super().__init__(msg)
        self.code = code


@dataclass(frozen=True)
class Token:
    kind: str          # block | attr | key
    name: str
    index: int = 0     # ocorrência do bloco (0 se não repetível)


def resolve(block: Block, field_path: str) -> tuple[tuple[Token, ...], object]:
    """Resolve um caminho do C26 contra o bloco. Devolve (tokens, alvo) onde alvo é o Attr da folha.

    Erros: FIELD_NOT_IN_SCHEMA, FIELD_NOT_CONFIGURABLE, PATH_ENDS_AT_BLOCK, INDEX_NOT_ALLOWED, KEY_NOT_ALLOWED.
    """
    segs = field_path.split(".")
    toks: list[Token] = []
    cur = block
    i = 0
    while i < len(segs):
        s = segs[i]
        if s in cur.attrs:
            a = cur.attrs[s]
            if not a.configurable:
                raise PathError("FIELD_NOT_CONFIGURABLE", f"{field_path}: '{s}' é só computado no schema")
            toks.append(Token("attr", s))
            rest = segs[i + 1:]
            typ = a.type
            for k in rest:
                if isinstance(typ, list) and typ[0] == "map":
                    toks.append(Token("key", k))
                    typ = typ[1]
                elif isinstance(typ, list) and typ[0] == "object":
                    names = dict((n, t) for n, t in typ[1])
                    if k not in names:
                        raise PathError("FIELD_NOT_IN_SCHEMA", f"{field_path}: '{k}' não é atributo do objeto '{s}'")
                    toks.append(Token("key", k))
                    typ = names[k]
                else:
                    raise PathError("KEY_NOT_ALLOWED", f"{field_path}: '{s}' não é map nem object; '{k}' não cabe")
            return tuple(toks), a
        if s in cur.blocks:
            bt = cur.blocks[s]
            idx = 0
            if i + 1 < len(segs) and segs[i + 1].isdigit():
                if not bt.repeatable:
                    raise PathError("INDEX_NOT_ALLOWED", f"{field_path}: bloco '{s}' ({bt.mode}) não tem ocorrências")
                idx = int(segs[i + 1])
                i += 1
            toks.append(Token("block", s, idx))
            cur = bt.block
            i += 1
            continue
        raise PathError("FIELD_NOT_IN_SCHEMA", f"{field_path}: '{s}' não existe no schema do oci {PROVIDER_VERSION}")
    raise PathError("PATH_ENDS_AT_BLOCK", f"{field_path}: termina num bloco; o plano tem de dar os campos-folha")


def leaf_type(attr: Attr, toks: tuple[Token, ...]):
    """Tipo cty do valor na folha (desce por chaves de map/object)."""
    typ = attr.type
    for t in toks:
        if t.kind != "key":
            continue
        if isinstance(typ, list) and typ[0] == "map":
            typ = typ[1]
        elif isinstance(typ, list) and typ[0] == "object":
            typ = dict((n, x) for n, x in typ[1])[t.name]
    return typ
