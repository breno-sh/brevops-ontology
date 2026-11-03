"""Leitor mínimo de HCL para os arquivos .pp/.sp dos mods do Steampipe/Powerpipe (lidos como DADO).

Nada é avaliado nem executado: o leitor só reconhece blocos `tipo "rótulo" { ... }`, `locals { ... }`,
atributos `chave = expressão` e, dentro das expressões que interessam, literais de texto, listas de
referências (`children = [control.x, benchmark.y]`), `merge(local.x, { k = "v" })` e `file("...")`.
Qualquer construção fora disso é guardada como texto bruto e marcada; o extrator decide se reprova.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_\-]*")


class HclError(ValueError):
    pass


@dataclass
class Token:
    kind: str  # ident, string, num, punct, heredoc
    value: str
    line: int


@dataclass
class Block:
    type: str
    labels: list[str]
    attrs: dict[str, "Expr"]
    line: int
    file: str = ""
    blocks: list["Block"] = field(default_factory=list)


@dataclass
class Expr:
    kind: str  # string, ref, list, object, call, number, raw
    value: object
    line: int


def tokenize(text: str) -> list[Token]:
    toks: list[Token] = []
    i, n, line = 0, len(text), 1
    while i < n:
        c = text[i]
        if c == "\n":
            toks.append(Token("nl", "\n", line))
            line += 1
            i += 1
        elif c in " \t\r":
            i += 1
        elif c == "#" or text.startswith("//", i):
            while i < n and text[i] != "\n":
                i += 1
        elif text.startswith("/*", i):
            j = text.find("*/", i + 2)
            if j < 0:
                raise HclError(f"linha {line}: comentário /* sem fim")
            line += text.count("\n", i, j)
            i = j + 2
        elif c == '"':
            j, buf = i + 1, []
            while True:
                if j >= n:
                    raise HclError(f"linha {line}: texto sem fim")
                d = text[j]
                if d == "\\" and j + 1 < n:
                    e = text[j + 1]
                    buf.append({"n": "\n", "t": "\t", '"': '"', "\\": "\\"}.get(e, "\\" + e))
                    j += 2
                    continue
                if d == '"':
                    break
                if d == "\n":
                    raise HclError(f"linha {line}: quebra de linha dentro de texto")
                buf.append(d)
                j += 1
            toks.append(Token("string", "".join(buf), line))
            i = j + 1
        elif text.startswith("<<", i):
            m = re.match(r"<<-?([A-Za-z_][A-Za-z0-9_]*)\n", text[i:])
            if not m:
                raise HclError(f"linha {line}: heredoc malformado")
            tag = m.group(1)
            body_start = i + m.end()
            end = re.compile(r"^[ \t]*" + re.escape(tag) + r"[ \t]*$", re.M)
            mm = end.search(text, body_start)
            if not mm:
                raise HclError(f"linha {line}: heredoc {tag} sem fim")
            body = text[body_start:mm.start()]
            toks.append(Token("heredoc", body, line))
            line += text.count("\n", i, mm.end())
            i = mm.end()
        elif c.isdigit():
            m = re.match(r"[0-9]+(\.[0-9]+)?", text[i:])
            toks.append(Token("num", m.group(0), line))
            i += m.end()
        elif _IDENT.match(text, i):
            m = _IDENT.match(text, i)
            toks.append(Token("ident", m.group(0), line))
            i = m.end()
        elif c in "{}[](),=.:?!<>+-*/%&|":
            toks.append(Token("punct", c, line))
            i += 1
        else:
            raise HclError(f"linha {line}: caractere inesperado {c!r}")
    toks.append(Token("eof", "", line))
    return toks


class _Parser:
    def __init__(self, toks: list[Token], fname: str):
        self.t, self.p, self.f = toks, 0, fname

    def peek(self, skip_nl: bool = True) -> Token:
        q = self.p
        while skip_nl and self.t[q].kind == "nl":
            q += 1
        return self.t[q]

    def next(self, skip_nl: bool = True) -> Token:
        while skip_nl and self.t[self.p].kind == "nl":
            self.p += 1
        tok = self.t[self.p]
        self.p += 1
        return tok

    def expect(self, kind: str, value: str | None = None) -> Token:
        tok = self.next()
        if tok.kind != kind or (value is not None and tok.value != value):
            raise HclError(f"{self.f}:{tok.line}: esperado {value or kind}, achado {tok.value!r}")
        return tok

    def body(self, closing: str | None) -> tuple[dict[str, Expr], list[Block]]:
        attrs: dict[str, Expr] = {}
        blocks: list[Block] = []
        while True:
            tok = self.peek()
            if tok.kind == "eof":
                if closing:
                    raise HclError(f"{self.f}:{tok.line}: fim de arquivo antes de '{closing}'")
                return attrs, blocks
            if tok.kind == "punct" and tok.value == closing:
                self.next()
                return attrs, blocks
            name = self.expect("ident")
            nxt = self.peek()
            if nxt.kind == "punct" and nxt.value == "=":
                self.next()
                if name.value in attrs:
                    raise HclError(f"{self.f}:{name.line}: atributo {name.value} repetido")
                attrs[name.value] = self.expr()
                continue
            labels = []
            while self.peek().kind == "string":
                labels.append(self.next().value)
            self.expect("punct", "{")
            a, b = self.body("}")
            blocks.append(Block(name.value, labels, a, name.line, self.f, b))

    def expr(self) -> Expr:
        tok = self.next()
        if tok.kind in ("string", "heredoc"):
            e = Expr("string", tok.value, tok.line)
            return self._tail(e)
        if tok.kind == "num":
            return Expr("number", tok.value, tok.line)
        if tok.kind == "punct" and tok.value == "[":
            items = []
            while True:
                if self.peek().kind == "punct" and self.peek().value == "]":
                    self.next()
                    break
                items.append(self.expr())
                if self.peek().kind == "punct" and self.peek().value == ",":
                    self.next()
            return Expr("list", items, tok.line)
        if tok.kind == "punct" and tok.value == "{":
            obj: dict[str, Expr] = {}
            while True:
                k = self.next()
                if k.kind == "punct" and k.value == "}":
                    break
                if k.kind not in ("ident", "string"):
                    raise HclError(f"{self.f}:{k.line}: chave de objeto inválida {k.value!r}")
                sep = self.next()
                if not (sep.kind == "punct" and sep.value in "=:"):
                    raise HclError(f"{self.f}:{sep.line}: esperado '=' no objeto")
                obj[k.value] = self.expr()
                if self.peek().kind == "punct" and self.peek().value == ",":
                    self.next()
            return Expr("object", obj, tok.line)
        if tok.kind == "ident":
            if tok.value in ("true", "false", "null"):
                return Expr("raw", tok.value, tok.line)
            nxt = self.peek(skip_nl=False)
            if nxt.kind == "punct" and nxt.value == "(":
                self.next()
                args = []
                while True:
                    if self.peek().kind == "punct" and self.peek().value == ")":
                        self.next()
                        break
                    args.append(self.expr())
                    if self.peek().kind == "punct" and self.peek().value == ",":
                        self.next()
                return Expr("call", (tok.value, args), tok.line)
            parts = [tok.value]
            while True:
                nxt = self.peek(skip_nl=False)
                if nxt.kind == "punct" and nxt.value == ".":
                    self.next(skip_nl=False)
                    parts.append(self.expect("ident").value)
                else:
                    break
            return Expr("ref", ".".join(parts), tok.line)
        raise HclError(f"{self.f}:{tok.line}: expressão não reconhecida começando em {tok.value!r}")

    def _tail(self, e: Expr) -> Expr:
        # Texto seguido de operador (ex. concatenação) não é usado nos arquivos de CIS: marcar como bruto.
        nxt = self.peek(skip_nl=False)
        if nxt.kind == "punct" and nxt.value not in ",)]}":
            raise HclError(f"{self.f}:{e.line}: operador após texto não suportado ({nxt.value!r})")
        return e


def parse(text: str, fname: str = "") -> list[Block]:
    attrs, blocks = _Parser(tokenize(text), fname).body(None)
    if attrs:
        raise HclError(f"{fname}: atributo solto no topo: {sorted(attrs)}")
    return blocks
