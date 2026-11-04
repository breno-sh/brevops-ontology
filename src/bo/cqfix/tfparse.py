"""Leitura do main.tf com python-hcl2 (versão do requirements.lock), normalizada: chaves sem aspas, literal de
texto como str, expressão como Expr. Usada pelo plan_guard_offline e pelo fixture_check (nada é executado)."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import hcl2


@dataclass(frozen=True)
class Expr:
    text: str


def _key(k: str) -> str:
    return k[1:-1] if len(k) >= 2 and k[0] == '"' and k[-1] == '"' else k


def norm(v):
    if isinstance(v, dict):
        return {_key(k): norm(x) for k, x in v.items() if k not in ("__is_block__", "__comments__")}
    if isinstance(v, list):
        return [norm(x) for x in v]
    if isinstance(v, str):
        if len(v) >= 2 and v[0] == '"' and v[-1] == '"' and "${" not in v:
            return v[1:-1]
        return Expr(v)
    return v


@dataclass
class Block:
    kind: str  # resource | data
    type: str
    label: str
    body: dict

    @property
    def address(self) -> str:
        a = f"{self.type}.{self.label}"
        return f"data.{a}" if self.kind == "data" else a

    @property
    def type_key(self) -> str:
        return f"data.{self.type}" if self.kind == "data" else self.type


def load(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        raw = hcl2.load(f)
    blocks = []
    for kind in ("resource", "data"):
        for entry in raw.get(kind, []):
            for t, labels in entry.items():
                for lab, body in labels.items():
                    blocks.append(Block(kind, _key(t), _key(lab), norm(body)))
    return {"blocks": blocks, "provider": norm(raw.get("provider", [])), "terraform": norm(raw.get("terraform", [])),
            "variable": norm(raw.get("variable", [])), "raw_keys": sorted(k for k in raw if k != "__comments__")}


def get_path(body: dict, path: str):
    """Valores no caminho pontuado (blocos são listas): devolve lista de valores encontrados."""
    cur = [body]
    for part in path.split("."):
        nxt = []
        for c in cur:
            if isinstance(c, list):
                for x in c:
                    if isinstance(x, dict) and part in x:
                        nxt.append(x[part])
            elif isinstance(c, dict) and part in c:
                nxt.append(c[part])
        cur = nxt
    out = []
    for c in cur:
        if isinstance(c, list) and c and all(isinstance(x, dict) for x in c):
            out.extend(c)
        else:
            out.append(c)
    return out


def walk_keys(v, prefix=""):
    if isinstance(v, dict):
        for k, x in v.items():
            p = f"{prefix}.{k}" if prefix else k
            yield p, x
            yield from walk_keys(x, p)
    elif isinstance(v, list):
        for x in v:
            yield from walk_keys(x, prefix)
