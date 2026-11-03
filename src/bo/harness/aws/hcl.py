"""Escrita de HCL canônica: a saída já é a de 'terraform fmt' (os testes conferem com o binário fixado).

Regras de formatação reproduzidas: indentação de 2 espaços; atributos de uma linha consecutivos têm o '='
alinhado; atributo de várias linhas não entra no grupo e o encerra; chave de objeto que não é identificador
vai entre aspas; '${' e '%{' literais são escapados ('$${', '%%{').
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field

IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]*$")
TRAVERSAL = re.compile(r"^(var|local|data\.[a-z][a-z0-9_]*|[a-z][a-z0-9_]*)\.[A-Za-z_][A-Za-z0-9_-]*"
                       r"(\.[A-Za-z_][A-Za-z0-9_-]*)*$")


class Expr:
    def lines(self, indent: int) -> list[str]:  # primeira linha sem indentação; demais já indentadas
        raise NotImplementedError


@dataclass
class Lit(Expr):
    value: object

    def lines(self, indent):
        return [lit(self.value)]


@dataclass
class Ref(Expr):
    """Travessia (aws_vpc.x.id, var.y). Só aceita a forma de travessia, nunca expressão arbitrária."""
    path: str

    def __post_init__(self):
        if not TRAVERSAL.match(self.path):
            raise ValueError(f"referência fora da forma de travessia: {self.path!r}")

    def lines(self, indent):
        return [self.path]


@dataclass
class ListE(Expr):
    items: list

    def lines(self, indent):
        parts = [e.lines(indent + 2) for e in self.items]
        if all(len(p) == 1 for p in parts):
            return ["[" + ", ".join(p[0] for p in parts) + "]"]
        pad = " " * (indent + 2)
        out = ["["]
        for p in parts:
            out.append(pad + p[0])
            out.extend(p[1:])
            out[-1] += ","
        out.append(" " * indent + "]")
        return out


@dataclass
class ObjE(Expr):
    items: list  # [(chave, Expr)]

    def lines(self, indent):
        if not self.items:
            return ["{}"]
        out = ["{"]
        out.extend(_assignments([(key(k), v) for k, v in self.items], indent + 2))
        out.append(" " * indent + "}")
        return out


@dataclass
class Call(Expr):
    fn: str
    arg: Expr

    def lines(self, indent):
        inner = self.arg.lines(indent)
        inner[0] = f"{self.fn}({inner[0]}"
        inner[-1] += ")"
        return inner


@dataclass
class Attribute:
    name: str
    expr: Expr


@dataclass
class BlockN:
    type: str
    labels: list = field(default_factory=list)
    body: list = field(default_factory=list)  # Attribute | BlockN


def lit(v) -> str:
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        if not math.isfinite(v):
            raise ValueError("número não finito não tem forma HCL")
        return repr(int(v)) if v.is_integer() else repr(v)
    if isinstance(v, str):
        return quote(v)
    raise TypeError(f"literal escalar esperado, veio {type(v).__name__}")


def quote(s: str) -> str:
    body = json.dumps(s, ensure_ascii=False)[1:-1]
    body = body.replace("${", "$${").replace("%{", "%%{")
    return '"' + body + '"'


KEYWORDS = {"null", "true", "false", "for", "in", "if", "endfor", "endif"}


def key(k: str) -> str:
    return k if IDENT.match(k) and k not in KEYWORDS else quote(k)


def from_value(v) -> Expr:
    """Valor JSON (literal do plano) -> expressão HCL, sem tocar no conteúdo."""
    if isinstance(v, list):
        return ListE([from_value(x) for x in v])
    if isinstance(v, dict):
        return ObjE([(k, from_value(x)) for k, x in v.items()])
    return Lit(v)


def _assignments(pairs: list, indent: int) -> list[str]:
    pad = " " * indent
    rendered = [(k, v.lines(indent)) for k, v in pairs]
    out: list[str] = []
    i = 0
    while i < len(rendered):
        if len(rendered[i][1]) > 1:
            k, ls = rendered[i]
            out.append(f"{pad}{k} = {ls[0]}")
            out.extend(ls[1:])
            i += 1
            continue
        j = i
        while j < len(rendered) and len(rendered[j][1]) == 1:
            j += 1
        width = max(len(k) for k, _ in rendered[i:j])
        for k, ls in rendered[i:j]:
            out.append(f"{pad}{k.ljust(width)} = {ls[0]}")
        i = j
    return out


def body_lines(body: list, indent: int) -> list[str]:
    out: list[str] = []
    run: list = []

    def flush():
        if run:
            out.extend(_assignments([(a.name, a.expr) for a in run], indent))
            run.clear()

    for item in body:
        if isinstance(item, Attribute):
            run.append(item)
        else:
            flush()
            out.extend(block_lines(item, indent))
    flush()
    return out


def block_lines(b: BlockN, indent: int) -> list[str]:
    pad = " " * indent
    head = " ".join([b.type] + [quote(x) for x in b.labels])
    if not b.body:
        return [f"{pad}{head} {{", f"{pad}}}"]
    return [f"{pad}{head} {{"] + body_lines(b.body, indent + 2) + [f"{pad}}}"]


def render_file(blocks: list, header: list[str] | None = None) -> str:
    out: list[str] = [f"# {h}" if h else "#" for h in (header or [])]
    for i, b in enumerate(blocks):
        if out:
            out.append("")
        out.extend(block_lines(b, 0))
    return "\n".join(out) + "\n"
