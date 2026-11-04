"""Emissor HCL determinístico e mínimo para as fixtures (o terraform fmt fixado normaliza o alinhamento).

Valores aceitos em atributo: str (literal, `${` escapado), bool, int, float, list, dict (objeto), Ref
(expressão de referência), Var (var.<nome>), Tpl (template já escrito, com interpolação) e Json (jsonencode
de um objeto que pode conter Ref/Var/Tpl). Nenhum valor é acrescentado aqui: o que sai é o que o realizador
escreveu.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]*$")


@dataclass(frozen=True)
class Ref:
    expr: str

    def __str__(self):
        return self.expr


@dataclass(frozen=True)
class Var:
    name: str

    @property
    def expr(self):
        return f"var.{self.name}"


@dataclass(frozen=True)
class Tpl:
    text: str  # conteúdo entre aspas, com ${...} intencionais


@dataclass(frozen=True)
class Json:
    obj: object


@dataclass
class Block:
    name: str
    attrs: dict = field(default_factory=dict)
    blocks: list = field(default_factory=list)
    labels: tuple = ()


@dataclass
class Res:
    """Bloco resource ou data. address = <type>.<label> (data.<type>.<label> para data)."""
    type: str
    label: str
    attrs: dict = field(default_factory=dict)
    blocks: list = field(default_factory=list)
    kind: str = "resource"
    depends_on: list = field(default_factory=list)
    provider: str | None = None  # alias, ex. "aws.loc2"

    @property
    def address(self) -> str:
        a = f"{self.type}.{self.label}"
        return f"data.{a}" if self.kind == "data" else a

    def ref(self, attr: str = "id") -> Ref:
        return Ref(f"{self.address}.{attr}")


@dataclass
class VarDecl:
    name: str
    type: str = "string"
    description: str = ""
    sensitive: bool = False
    default: object = None
    has_default: bool = False


def _str(s: str) -> str:
    s = s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    s = s.replace("${", "$${").replace("%{", "%%{")
    return f'"{s}"'


def _key(k: str) -> str:
    return k if IDENT.match(k) else _str(k)


def value(v, indent: int = 0, json_mode: bool = False) -> str:
    pad = "  " * indent
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return repr(v)
    if v is None:
        return "null"
    if isinstance(v, str):
        return _str(v)
    if isinstance(v, Ref):
        return v.expr
    if isinstance(v, Var):
        return v.expr
    if isinstance(v, Tpl):
        return f'"{v.text}"'
    if isinstance(v, Json):
        return "jsonencode(" + value(v.obj, indent, json_mode=True) + ")"
    if isinstance(v, (list, tuple)):
        if not v:
            return "[]"
        items = [value(x, indent + 1, json_mode) for x in v]
        if all("\n" not in i for i in items) and sum(len(i) for i in items) < 80:
            return "[" + ", ".join(items) + "]"
        inner = "".join(f"{pad}  {i},\n" for i in items)
        return "[\n" + inner + pad + "]"
    if isinstance(v, dict):
        if not v:
            return "{}"
        lines = []
        for k, x in v.items():
            kk = _str(k) if json_mode and not IDENT.match(k) else _key(k)
            lines.append(f"{pad}  {kk} = {value(x, indent + 1, json_mode)}\n")
        return "{\n" + "".join(lines) + pad + "}"
    raise TypeError(f"valor HCL não suportado: {type(v).__name__}")


def _body(attrs: dict, blocks: list, indent: int) -> str:
    pad = "  " * indent
    out = []
    for k, v in attrs.items():
        out.append(f"{pad}{_key(k)} = {value(v, indent)}\n")
    for b in blocks:
        out.append(block(b, indent))
    return "".join(out)


def block(b: Block, indent: int = 0) -> str:
    pad = "  " * indent
    labels = "".join(f" {_str(x)}" for x in b.labels)
    return f"{pad}{b.name}{labels} {{\n" + _body(b.attrs, b.blocks, indent + 1) + f"{pad}}}\n"


def resource(r: Res) -> str:
    attrs = dict(r.attrs)
    head = f'{r.kind} "{r.type}" "{r.label}" {{\n'
    pre = ""
    if r.provider:
        pre += f"  provider = {r.provider}\n"
    body = _body(attrs, r.blocks, 1)
    post = ""
    if r.depends_on:
        post = "  depends_on = [" + ", ".join(r.depends_on) + "]\n"
    return head + pre + body + post + "}\n"


def variable(v: VarDecl) -> str:
    s = f'variable "{v.name}" {{\n  type = {v.type}\n'
    if v.description:
        s += f"  description = {_str(v.description)}\n"
    if v.sensitive:
        s += "  sensitive = true\n"
    if v.has_default:
        s += f"  default = {value(v.default, 1)}\n"
    return s + "}\n"
