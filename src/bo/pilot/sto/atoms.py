"""Átomos C01 (SCHEMA-*) dos tipos da fatia: campos obrigatórios e quais caminhos são blocos (para o lowering)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import lru_cache

from . import common as C

EXTRA_TYPES = {"azurerm": ("azurerm_resource_group",)}


@dataclass
class TypeAtoms:
    rtype: str
    atoms: dict = field(default_factory=dict)        # caminho -> registro C01
    blocks: dict = field(default_factory=dict)       # caminho do bloco -> {nesting_mode, min_items, max_items}

    def required_top(self) -> list[str]:
        return sorted(p for p, a in self.atoms.items()
                      if not a.get("block_path") and a.get("required"))

    def required_in(self, block: str) -> list[str]:
        out = []
        for p, a in self.atoms.items():
            if _bp(a) == block and a.get("required"):
                out.append(p)
        return sorted(out)

    def required_blocks(self, parent: str) -> list[str]:
        """Blocos filhos diretos de parent ('' = raiz) com min_items >= 1."""
        out = []
        for b, d in self.blocks.items():
            par = b.rsplit(".", 1)[0] if "." in b else ""
            if par == parent and (d.get("min_items") or 0) >= 1:
                out.append(b)
        return sorted(out)

    def is_block(self, path: str) -> bool:
        return path in self.blocks


@lru_cache(maxsize=1)
def load() -> dict[str, TypeAtoms]:
    out: dict[str, TypeAtoms] = {}
    for prov, d in C.SCHEMA_DIR.items():
        types = set(C.SLICE_TYPES[prov]) | set(EXTRA_TYPES.get(prov, ()))
        needles = tuple(f'"resource_type": "{t}"' for t in types)
        p = C.data_root() / d / "atoms.jsonl"
        with open(p, encoding="utf-8") as fh:
            for line in fh:
                if not any(n in line for n in needles):
                    continue
                a = json.loads(line)
                rt = a.get("resource_type")
                if rt not in types:
                    continue
                ta = out.setdefault(rt, TypeAtoms(rt))
                ta.atoms[a["path"]] = a
                bp = a.get("block_path") or []
                for i in range(1, len(bp) + 1):
                    b = bp[i - 1]
                    ta.blocks.setdefault(".".join(x["block"] for x in bp[:i]),
                                         {"nesting_mode": b.get("nesting_mode"), "min_items": b.get("min_items") or 0,
                                          "max_items": b.get("max_items")})
    return out


def _bp(a: dict) -> str:
    return ".".join(x["block"] for x in (a.get("block_path") or []))


def sources() -> list[dict]:
    out = []
    for prov, d in sorted(C.SCHEMA_DIR.items()):
        p = C.data_root() / d / "atoms.jsonl"
        out.append({"path": C.portable(p), "sha256": C.sha256_file(p)})
    return out
