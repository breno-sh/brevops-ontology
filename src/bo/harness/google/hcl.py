"""Emissor de HCL determinístico, já na forma canônica do 'terraform fmt' (conferida nos testes com o binário fixado).

Valores: str, int, float, bool, None, list, dict (literais) e Expr (expressão crua: referência a var, recurso ou
data source) e Template (string com interpolação). Regras do fmt reproduzidas:
  - indentação de 2 espaços; '=' alinhado numa sequência contígua de atributos de UMA linha;
  - atributo de várias linhas (mapa, lista de objetos) quebra a sequência e não é preenchido;
  - texto literal escapa '\\', '"', quebras de linha, tabulação, '${' -> '$${' e '%{' -> '%%{' (nada interpola).
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]*$")
_KEYWORDS = {"true", "false", "null", "for", "in", "if"}


@dataclass(frozen=True)
class Expr:
    """Expressão HCL crua, já validada por quem a cria (ex.: var.x, google_compute_network.lp_r2.id)."""
    text: str


@dataclass(frozen=True)
class Template:
    """String com interpolação: partes literais (str) e expressões (Expr)."""
    parts: tuple


def quote(s: str) -> str:
    out = ['"']
    i = 0
    while i < len(s):
        c = s[i]
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
        elif c in "$%" and s[i + 1:i + 2] == "{":
            out.append(c + c + "{")
            i += 1
        elif ord(c) < 0x20:
            out.append(f"\\u{ord(c):04x}")
        else:
            out.append(c)
        i += 1
    out.append('"')
    return "".join(out)


def template(t: Template) -> str:
    body = []
    for p in t.parts:
        if isinstance(p, Expr):
            body.append("${" + p.text + "}")
        else:
            body.append(quote(p)[1:-1])
    return '"' + "".join(body) + '"'


def key(k: str) -> str:
    return k if IDENT.match(k) and k not in _KEYWORDS else quote(k)


def number(v) -> str:
    if isinstance(v, bool):
        raise TypeError("booleano não é número")
    if isinstance(v, int):
        return str(v)
    if not math.isfinite(v):
        raise ValueError(f"número não finito não existe em HCL: {v!r}")
    if v == int(v) and abs(v) < 1e15:
        return str(int(v))
    return repr(v)


def is_multiline(v) -> bool:
    if isinstance(v, dict):
        return bool(v)
    if isinstance(v, list):
        return any(is_multiline(x) for x in v)
    return False


def inline(v) -> str:
    if isinstance(v, Expr):
        return v.text
    if isinstance(v, Template):
        return template(v)
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return number(v)
    if isinstance(v, str):
        return quote(v)
    if isinstance(v, list):
        return "[" + ", ".join(inline(x) for x in v) + "]"
    if isinstance(v, dict):
        if v:
            raise ValueError("mapa não vazio é sempre de várias linhas")
        return "{}"
    raise TypeError(f"valor sem forma HCL: {type(v).__name__}")


def value_lines(v, ind: int) -> list[str]:
    """Linhas do VALOR (a primeira sem indentação, para ir depois de 'nome = ')."""
    if not is_multiline(v):
        return [inline(v)]
    pad = "  " * (ind + 1)
    if isinstance(v, dict):
        lines = ["{"]
        lines += attr_lines([(key(k), v[k]) for k in v], ind + 1)
        lines.append("  " * ind + "}")
        return lines
    lines = ["["]
    for x in v:
        sub = value_lines(x, ind + 1)
        lines.append(pad + sub[0])
        lines += sub[1:]
        lines[-1] += ","
    lines.append("  " * ind + "]")
    return lines


def attr_lines(items: list[tuple[str, object]], ind: int) -> list[str]:
    """Atributos na ordem dada, com o alinhamento de '=' do fmt por sequência contígua de uma linha."""
    pad = "  " * ind
    out: list[str] = []
    run: list[tuple[str, str]] = []

    def flush():
        if run:
            w = max(len(k) for k, _ in run)
            out.extend(f"{pad}{k.ljust(w)} = {v}" for k, v in run)
            run.clear()

    for k, v in items:
        vl = value_lines(v, ind)
        if len(vl) == 1:
            run.append((k, vl[0]))
        else:
            flush()
            out.append(f"{pad}{k} = {vl[0]}")
            out.extend(vl[1:])
    flush()
    return out


@dataclass
class Body:
    """Corpo de bloco: atributos (ordem de inserção) e blocos aninhados (nome, Body)."""
    attrs: dict
    blocks: list

    @classmethod
    def new(cls):
        return cls({}, [])


def body_lines(b: Body, ind: int) -> list[str]:
    out = attr_lines(list(b.attrs.items()), ind)
    for name, sub in b.blocks:
        out += block_lines(name, [], sub, ind)
    return out


def block_lines(btype: str, labels: list[str], b: Body, ind: int) -> list[str]:
    pad = "  " * ind
    head = " ".join([btype] + [quote(lb) for lb in labels])
    inner = body_lines(b, ind + 1)
    if not inner:
        return [f"{pad}{head} {{", f"{pad}}}"]
    return [f"{pad}{head} {{"] + inner + [f"{pad}}}"]


def document(blocks: list[tuple[str, list[str], Body]], header: list[str] | None = None) -> str:
    """Arquivo .tf: blocos de topo separados por uma linha em branco; cabeçalho como comentários '#'."""
    parts = []
    if header:
        parts.append("\n".join(("# " + h).rstrip() for h in header))
    for btype, labels, b in blocks:
        parts.append("\n".join(block_lines(btype, labels, b, 0)))
    return "\n\n".join(parts) + "\n"
