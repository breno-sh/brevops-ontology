"""Escritor de HCL na forma canônica do `terraform fmt` (subconjunto que o renderizador usa).

Modelo: Body = itens Attr(nome, expr) e Block(tipo, rótulos, Body). Expressões: Lit (valor JSON), Ref
(travessia como `azurerm_x.r1.name` ou `var.sym_x`), Tmpl (string com interpolações), ListE, ObjE, Call, BinOp.
Regras de forma (conferidas contra o próprio `terraform fmt` nos testes):
  - indentação de 2 espaços; atributos de uma linha seguidos têm o `=` alinhado (como o fmt);
  - atributo de várias linhas e bloco aninhado ficam separados por linha em branco, o que quebra o grupo de
    alinhamento sem depender de regra fina do fmt;
  - string com `${` ou `%{` literal sai escapada (`$${`, `%%{`), para nunca virar interpolação.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field

IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]*$")


# ------------------------------------------------------------------------------------------------ expressões
@dataclass(frozen=True)
class Lit:
    value: object


@dataclass(frozen=True)
class Ref:
    traversal: str  # ex.: azurerm_resource_group.r1.name, var.sym_0a1b, data.azurerm_client_config.r9.tenant_id


@dataclass(frozen=True)
class Tmpl:
    parts: tuple  # str literal ou Ref


@dataclass(frozen=True)
class ListE:
    items: tuple


@dataclass(frozen=True)
class ObjE:
    items: tuple  # ((chave, expr), ...)


@dataclass(frozen=True)
class Call:
    name: str
    args: tuple


@dataclass(frozen=True)
class BinOp:
    op: str
    left: object
    right: object


@dataclass(frozen=True)
class UnOp:
    op: str
    arg: object


# ------------------------------------------------------------------------------------------------ corpo
@dataclass
class Attr:
    name: str
    expr: object


@dataclass
class Block:
    type: str
    labels: tuple = ()
    body: list = field(default_factory=list)


def escape(s: str) -> str:
    out = []
    i = 0
    while i < len(s):
        c = s[i]
        nxt = s[i + 1] if i + 1 < len(s) else ""
        if c == "\\":
            out.append("\\\\")
        elif c == '"':
            out.append('\\"')
        elif c == "\n":
            out.append("\\n")
        elif c == "\r":
            out.append("\\r")
        elif c == "\t":
            out.append("\\t")
        elif c in "$%" and nxt == "{":
            out.append(c + c + "{")
            i += 2
            continue
        elif ord(c) < 0x20 or ord(c) == 0x7F:
            out.append(f"\\u{ord(c):04x}")
        else:
            out.append(c)
        i += 1
    return "".join(out)


def key_text(k: str) -> str:
    return k if IDENT.match(k) and k not in ("true", "false", "null") else '"' + escape(k) + '"'


def _num(v) -> str:
    if isinstance(v, bool):
        raise TypeError("bool não é número")
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        if math.isnan(v) or math.isinf(v):
            raise ValueError("número não finito não tem literal HCL")
        if v.is_integer() and abs(v) < 1e15:
            return str(int(v))
        return json.dumps(v)
    raise TypeError(f"não é número: {v!r}")


def _lit_expr(v):
    """Converte valor JSON em expressão (listas e mapas viram ListE/ObjE)."""
    if isinstance(v, list):
        return ListE(tuple(_lit_expr(x) for x in v))
    if isinstance(v, dict):
        return ObjE(tuple((str(k), _lit_expr(x)) for k, x in v.items()))
    return Lit(v)


def is_single_line(e) -> bool:
    if isinstance(e, Lit):
        if isinstance(e.value, (list, dict)):
            return is_single_line(_lit_expr(e.value))
        return True
    if isinstance(e, (Ref, Tmpl)):
        return True
    if isinstance(e, ListE):
        return all(is_single_line(x) and not isinstance(x, (ListE, ObjE)) for x in e.items)
    if isinstance(e, ObjE):
        return not e.items
    if isinstance(e, Call):
        return all(is_single_line(a) for a in e.args)
    if isinstance(e, BinOp):
        return is_single_line(e.left) and is_single_line(e.right)
    if isinstance(e, UnOp):
        return is_single_line(e.arg)
    raise TypeError(f"expressão desconhecida: {e!r}")


def expr_text(e, indent: int = 0) -> str:
    pad = "  " * indent
    if isinstance(e, Lit):
        v = e.value
        if isinstance(v, (list, dict)):
            return expr_text(_lit_expr(v), indent)
        if v is None:
            return "null"
        if isinstance(v, bool):
            return "true" if v else "false"
        if isinstance(v, (int, float)):
            return _num(v)
        if isinstance(v, str):
            return '"' + escape(v) + '"'
        raise TypeError(f"literal sem forma HCL: {v!r}")
    if isinstance(e, Ref):
        return e.traversal
    if isinstance(e, Tmpl):
        s = []
        for p in e.parts:
            s.append("${" + p.traversal + "}" if isinstance(p, Ref) else escape(p))
        return '"' + "".join(s) + '"'
    if isinstance(e, ListE):
        if is_single_line(e):
            return "[" + ", ".join(expr_text(x, indent) for x in e.items) + "]"
        lines = ["["]
        for x in e.items:
            lines.append(pad + "  " + expr_text(x, indent + 1) + ",")
        lines.append(pad + "]")
        return "\n".join(lines)
    if isinstance(e, ObjE):
        if not e.items:
            return "{}"
        lines = ["{"]
        lines += _attr_lines([(key_text(k), v) for k, v in e.items], indent + 1)
        lines.append(pad + "}")
        return "\n".join(lines)
    if isinstance(e, Call):
        return e.name + "(" + ", ".join(expr_text(a, indent) for a in e.args) + ")"
    if isinstance(e, BinOp):
        return "(" + expr_text(e.left, indent) + " " + e.op + " " + expr_text(e.right, indent) + ")"
    if isinstance(e, UnOp):
        return e.op + expr_text(e.arg, indent)
    raise TypeError(f"expressão desconhecida: {e!r}")


def _attr_lines(pairs: list, indent: int) -> list[str]:
    """Pares (texto da chave, expr): uma linha alinhada por grupo; multi-linha isolada por linha em branco."""
    pad = "  " * indent
    singles = [(k, v) for k, v in pairs if is_single_line(v)]
    multis = [(k, v) for k, v in pairs if not is_single_line(v)]
    out = []
    if singles:
        w = max(len(k) for k, _ in singles)
        for k, v in singles:
            out.append(f"{pad}{k.ljust(w)} = {expr_text(v, indent)}")
    for k, v in multis:
        if out:
            out.append("")
        out.append(f"{pad}{k} = {expr_text(v, indent)}")
    return out


def body_lines(body: list, indent: int) -> list[str]:
    pad = "  " * indent
    attrs = [b for b in body if isinstance(b, Attr) and b.name != "depends_on"]
    deps = [b for b in body if isinstance(b, Attr) and b.name == "depends_on"]
    blocks = [b for b in body if isinstance(b, Block)]
    out = _attr_lines([(a.name, a.expr) for a in attrs], indent)
    for b in blocks:
        if out:
            out.append("")
        out += block_lines(b, indent)
    if deps:
        if out:
            out.append("")
        out += _attr_lines([(d.name, d.expr) for d in deps], indent)
    return out


def block_lines(b: Block, indent: int) -> list[str]:
    pad = "  " * indent
    head = pad + b.type + "".join(' "' + escape(lbl) + '"' for lbl in b.labels)
    inner = body_lines(b.body, indent + 1)
    if not inner:
        return [head + " {}"]
    return [head + " {"] + inner + [pad + "}"]


def file_text(blocks: list[Block]) -> str:
    out = []
    for b in blocks:
        if out:
            out.append("")
        out += block_lines(b, 0)
    return "\n".join(out) + "\n"
