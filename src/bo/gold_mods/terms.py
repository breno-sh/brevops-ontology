"""Leitura dos termos simbólicos do C06: onde uma variável do módulo chega num atributo.

Duas funções puras, sem estado, usadas pela varredura (scan), pelo gate de resolução e pelos testes:

  var_uses(term)       -> [(pivô, ops)]: cada ocorrência de var.<x> (com a cadeia de getattr/índice literal que
                          sai dela) e a pilha de operações entre a raiz do termo e essa ocorrência.
                          ops == () quer dizer que o valor do atributo É a variável (transporte direto);
  norm_attr(attr_path) -> (categoria, caminho do átomo | None): tira índices de posição, abre blocos dynamic e
                          separa meta-argumentos (count, for_each, depends_on, lifecycle, provider, ...).

Regra fixada antes de olhar os números: só ops == () é identidade. Qualquer função, template, operador,
objeto ou condicional entre a variável e o atributo faz a ocorrência ser 'expr' (transporte não provado).
"""
from __future__ import annotations

import re

# meta-argumentos do Terraform e blocos de ciclo de vida: não são atributos do provider
META_TOP = {"count", "for_each", "depends_on", "provider", "lifecycle", "provisioner", "connection", "timeouts"}
SEG = re.compile(r'([A-Za-z0-9_]+)|\[([0-9]+)\]|\["((?:[^"\\]|\\.)*)"\]')
ATOM_SEG = re.compile(r"^[A-Za-z0-9_]+$")
SYM = re.compile(r"^SYM-[0-9a-f]{8,16}$")


def _segments(path: str):
    out, pos = [], 0
    while pos < len(path):
        if path[pos] == ".":
            pos += 1
            continue
        m = SEG.match(path, pos)
        if not m:
            return None
        if m.group(1) is not None:
            out.append(("name", m.group(1)))
        elif m.group(2) is not None:
            out.append(("idx", int(m.group(2))))
        else:
            out.append(("key", m.group(3)))
        pos = m.end()
    return out


def norm_attr(attr_path: str) -> tuple[str, str | None]:
    """Categoria e caminho de átomo de um attr_path do C06.

    Categorias: 'attribute' (vira átomo), 'meta' (meta-argumento ou ciclo de vida), 'dynamic_iter' (for_each ou
    iterator de um bloco dynamic: a coleção que gera o bloco, não um atributo), 'unresolved' (chave de mapa,
    rótulo dynamic simbolizado ou caminho fora da gramática).
    """
    segs = _segments(attr_path)
    if not segs or segs[0][0] != "name":
        return "unresolved", None
    if segs[0][1] in META_TOP:
        return "meta", None
    names: list[str] = []
    i = 0
    while i < len(segs):
        kind, v = segs[i]
        if kind == "name" and v == "dynamic" and i + 1 < len(segs) and segs[i + 1][0] == "key":
            label = segs[i + 1][1]
            if SYM.match(label) or not ATOM_SEG.match(label):
                return "unresolved", None
            j = i + 2
            while j < len(segs) and segs[j][0] == "idx":
                j += 1
            if j >= len(segs):
                return "unresolved", None
            nxt = segs[j]
            if nxt == ("name", "content"):
                names.append(label)
                i = j + 1
                continue
            if nxt[0] == "name" and nxt[1] in ("for_each", "iterator", "labels"):
                return "dynamic_iter", None
            return "unresolved", None
        if kind == "name":
            if SYM.match(v):
                return "unresolved", None
            names.append(v)
        elif kind == "key":
            return "unresolved", None
        i += 1
    if not names:
        return "unresolved", None
    if names[-1] in META_TOP or names[0] in META_TOP:
        return "meta", None
    return "attribute", ".".join(names)


# ------------------------------------------------------------------------------------------------ termos
def _is_var(t) -> bool:
    return isinstance(t, dict) and t.get("kind") == "symbol" and t.get("name_class") == "variable"


def _pivot_chain(t):
    """Se t é var.<x> seguido só de getattr (campo simbólico ou literal) e índice literal, devolve o pivô."""
    suffix = []
    cur = t
    while isinstance(cur, dict) and cur.get("kind") == "expression" and cur.get("op") in ("hcl_getattr", "hcl_index") \
            and len(cur.get("args") or []) == 2:
        base, key = cur["args"]
        if cur["op"] == "hcl_getattr":
            if key.get("kind") == "symbol":
                suffix.append("." + key["symbol_id"])
            elif key.get("kind") == "literal" and isinstance(key.get("value"), str):
                suffix.append("." + key["value"])
            else:
                return None
        else:
            if key.get("kind") == "literal" and isinstance(key.get("value"), (int, float)) \
                    and not isinstance(key.get("value"), bool):
                suffix.append(f"[{int(key['value'])}]")
            elif key.get("kind") == "literal" and isinstance(key.get("value"), str):
                suffix.append(f'["{key["value"]}"]')
            elif key.get("kind") == "symbol":
                suffix.append(f'["{key["symbol_id"]}"]')
            else:
                return None
        cur = base
    if _is_var(cur):
        return cur["symbol_id"] + "".join(reversed(suffix))
    return None


def var_uses(term) -> list[tuple[str, tuple[str, ...]]]:
    """Toda ocorrência de variável no termo: (pivô, ops da raiz até a ocorrência)."""
    out: list[tuple[str, tuple[str, ...]]] = []

    def walk(t, ops):
        if isinstance(t, list):
            for x in t:
                walk(x, ops)
            return
        if not isinstance(t, dict):
            return
        if _is_var(t):
            out.append((t["symbol_id"], ops))
            return
        kind = t.get("kind")
        if kind == "expression":
            piv = _pivot_chain(t)
            if piv is not None:
                out.append((piv, ops))
                # o índice/campo não variável (ex.: var.m[var.k]) não existe em _pivot_chain; nada a descer
                return
            op = t.get("op") or "?"
            for a in t.get("args") or []:
                walk(a, ops + (op,))
            return
        if kind in ("literal", "symbol", "reference", "withheld"):
            return
        # documento parseado (política JSON) ou outro termo composto: desce em tudo, marcando o tipo
        tag = kind or "?"
        for k in sorted(t):
            if k in ("kind",):
                continue
            walk(t[k], ops + (tag,))

    walk(term, ())
    return out


def mode_of(ops: tuple[str, ...]) -> str:
    return "identity" if not ops else "expr"
