"""Escritor de HCL na forma canônica do `terraform fmt` (o gate confere com `terraform fmt -check`).

Regras do fmt que importam aqui: indentação de 2 espaços; numa sequência de atributos de uma linha só, os '=' ficam
alinhados (o nome é preenchido até o maior da sequência); um bloco interrompe a sequência. Todo valor é escrito numa
linha só (listas e objetos inline), então todos os atributos de um corpo formam uma sequência só, antes dos blocos.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]*$")


class HclError(ValueError):
    pass


# ------------------------------------------------------------------------------------------- expressões
def string(s: str) -> str:
    out = []
    i = 0
    while i < len(s):
        ch = s[i]
        nxt = s[i + 1] if i + 1 < len(s) else ""
        if ch == "\\":
            out.append("\\\\")
        elif ch == '"':
            out.append('\\"')
        elif ch == "\n":
            out.append("\\n")
        elif ch == "\r":
            out.append("\\r")
        elif ch == "\t":
            out.append("\\t")
        elif ch in "$%" and nxt == "{":
            out.append(ch + ch)       # $${ e %%{ escapam a interpolação e a diretiva
        elif ord(ch) < 0x20 or ord(ch) == 0x7F:
            out.append(f"\\u{ord(ch):04x}")
        else:
            out.append(ch)
        i += 1
    return '"' + "".join(out) + '"'


def number(v) -> str:
    if isinstance(v, bool):
        raise HclError("booleano não é número")
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        if math.isnan(v) or math.isinf(v):
            raise HclError(f"número não finito: {v!r}")
        if v.is_integer() and abs(v) < 1e16:
            return str(int(v))
        return repr(v)
    raise HclError(f"não é número: {v!r}")


def literal(v) -> str:
    """Valor JSON -> expressão HCL literal (uma linha)."""
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return number(v)
    if isinstance(v, str):
        return string(v)
    if isinstance(v, list):
        return "[" + ", ".join(literal(x) for x in v) + "]"
    if isinstance(v, dict):
        if not v:
            return "{}"
        return "{ " + ", ".join(f"{string(str(k))} = {literal(v[k])}" for k in sorted(v)) + " }"
    raise HclError(f"valor sem forma HCL: {type(v).__name__}")


def traversal(*parts: str) -> str:
    for p in parts:
        if not IDENT.match(p):
            raise HclError(f"nome inválido numa referência: {p!r}")
    return ".".join(parts)


# ------------------------------------------------------------------------------------------- corpo
@dataclass
class Attribute:
    name: str
    expr: str


@dataclass
class Block:
    type: str
    labels: list[str] = field(default_factory=list)
    body: list = field(default_factory=list)   # Attribute | Block, na ordem de escrita

    def attr(self, name: str, expr: str) -> "Block":
        self.body.append(Attribute(name, expr))
        return self

    def block(self, b: "Block") -> "Block":
        self.body.append(b)
        return b


def _name(n: str) -> str:
    if not IDENT.match(n):
        raise HclError(f"nome de atributo ou bloco inválido: {n!r}")
    return n


def _write_body(items: list, indent: int, out: list[str]) -> None:
    pad = "  " * indent
    i = 0
    while i < len(items):
        if isinstance(items[i], Attribute):
            j = i
            while j < len(items) and isinstance(items[j], Attribute):
                j += 1
            run = items[i:j]
            width = max(len(_name(a.name)) for a in run)
            for a in run:
                if "\n" in a.expr:
                    raise HclError(f"expressão de {a.name} tem quebra de linha")
                out.append(f"{pad}{a.name.ljust(width)} = {a.expr}")
            i = j
        else:
            _write_block(items[i], indent, out)
            i += 1


def _write_block(b: Block, indent: int, out: list[str]) -> None:
    pad = "  " * indent
    head = " ".join([_name(b.type)] + [string(lab) for lab in b.labels])
    if not b.body:
        out.append(f"{pad}{head} {{")
        out.append(f"{pad}}}")
        return
    out.append(f"{pad}{head} {{")
    _write_body(b.body, indent + 1, out)
    out.append(f"{pad}}}")


def write_file(blocks: list[Block], header_comment: list[str] | None = None) -> str:
    out: list[str] = []
    for c in header_comment or []:
        out.append(f"# {c}" if c else "#")
    if header_comment:
        out.append("")
    for k, b in enumerate(blocks):
        if k:
            out.append("")
        _write_block(b, 0, out)
    return "\n".join(out) + "\n"
