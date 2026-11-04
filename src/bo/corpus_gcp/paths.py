"""attr_path do C06 (HCL) -> caminho de átomo do C01 (SCHEMA-GCP).

O HCL grava blocos aninhados com índice por tipo de bloco (`boot_disk[0].initialize_params[0].image`) e blocos
dynamic como `dynamic["rotulo"][i].content.<attr>` (com for_each/iterator/labels do próprio dynamic ao lado do
content). O átomo do schema é o caminho de blocos sem índice (`boot_disk.initialize_params.image`).

classify_path devolve (categoria, caminho):
  ("path", "a.b.c")        caminho candidato a átomo (ainda sem conferir o schema)
  ("block", "a.b")         o registro é o bloco inteiro (só acontece com termo retido: bloco Withheld)
  ("meta", None)           meta-argumento do Terraform ou do dynamic (não é átomo)
  ("malformed", None)      attr_path fora da gramática do C06
"""

from __future__ import annotations

import re

from .common import META_DYNAMIC, META_TOP

_TOKEN = re.compile(r'\.?([A-Za-z0-9_]+)|\[([0-9]+)\]|\["([^"]+)"\]')


def tokens(attr_path: str) -> list[tuple[str, str]] | None:
    """[('name', x) | ('index', n) | ('label', s)], ou None se sobrar texto fora da gramática."""
    out, pos = [], 0
    while pos < len(attr_path):
        m = _TOKEN.match(attr_path, pos)
        if not m or m.end() == pos:
            return None
        if m.group(1) is not None:
            if pos > 0 and not attr_path.startswith(".", pos):
                return None
            if pos == 0 and attr_path.startswith("."):
                return None
            out.append(("name", m.group(1)))
        elif m.group(2) is not None:
            out.append(("index", m.group(2)))
        else:
            out.append(("label", m.group(3)))
        pos = m.end()
    return out


def classify_path(attr_path: str) -> tuple[str, str | None]:
    toks = tokens(attr_path)
    if not toks or toks[0][0] != "name":
        return "malformed", None
    if toks[0][1] in META_TOP:
        return "meta", None
    segs: list[str] = []
    i, n = 0, len(toks)
    ends_in_block = False
    while i < n:
        kind, val = toks[i]
        if kind == "name" and val == "dynamic" and i + 1 < n and toks[i + 1][0] == "label":
            segs.append(toks[i + 1][1])
            i += 2
            if i < n and toks[i][0] == "index":
                i += 1
            if i >= n:
                ends_in_block = True
                break
            kind2, val2 = toks[i]
            if kind2 != "name":
                return "malformed", None
            if val2 == "content":
                i += 1
                if i >= n:
                    ends_in_block = True  # dynamic["x"][i].content retido inteiro
                continue
            if val2 in META_DYNAMIC and i + 1 == n:
                return "meta", None
            return "malformed", None
        if kind == "name":
            segs.append(val)
            ends_in_block = False
        elif kind == "index":
            ends_in_block = True  # bloco[i] sem atributo depois: o registro é o bloco
        else:
            return "malformed", None
        i += 1
    if not segs:
        return "malformed", None
    return ("block" if ends_in_block else "path"), ".".join(segs)
