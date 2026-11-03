"""Árvore Lark do python-hcl2 (parser LALR puro, nada é avaliado) -> AST neutra em tuplas.

AST de expressão (tuplas imutáveis, comparáveis com ==):
  ("num", v)  ("bool", v)  ("null",)
  ("str", parts)            parts: ("t", texto) | ("i", ast) | ("d", tipo, ast|None, nomes)
                            (aspas, heredoc e heredoc recuado viram o mesmo nó, já com escapes e recuo resolvidos)
  ("tuple", itens)  ("object", ((chave, valor), ...))
  ("trav", raiz, passos)    raiz: nome (str) ou ast; passos: ("a", nome) | ("i", ast) | ("as",) | ("fs",)
  ("call", nome, args, expand)
  ("bin", op, a, b)  ("un", op, a)  ("cond", c, a, b)
  ("fort", k, v, coleção, expr, cond)  ("foro", k, v, coleção, chave, valor, agrupa, cond)

Corpo: Body(attrs=[(nome, ast)], blocks=[Block(tipo, rótulos, Body)]) na ordem do arquivo.
"""

from __future__ import annotations

import json
import re
import signal
from dataclasses import dataclass, field

from lark import Token, Tree

from hcl2.api import parses_to_tree

BINOPS = {"DOUBLE_EQ": "==", "NEQ": "!=", "LT": "<", "GT": ">", "LEQ": "<=", "GEQ": ">=", "MINUS": "-",
          "ASTERISK": "*", "SLASH": "/", "PERCENT": "%", "DOUBLE_AMP": "&&", "DOUBLE_PIPE": "||", "PLUS": "+"}


class ParseTimeout(BaseException):
    pass


class AstError(Exception):
    pass


@dataclass
class Block:
    type: str
    labels: list
    body: "Body"
    line: int = 0


@dataclass
class Body:
    attrs: list = field(default_factory=list)
    blocks: list = field(default_factory=list)


def _is_nlc(x) -> bool:
    return isinstance(x, Tree) and x.data == "new_line_or_comment"


def _trees(children):
    return [c for c in children if isinstance(c, Tree) and not _is_nlc(c)]


# ------------------------------------------------------------------------------------------------ cadeias
_ESC = re.compile(r"\\(u[0-9A-Fa-f]{4}|U[0-9A-Fa-f]{8}|.)", re.S)
_SIMPLE = {"n": "\n", "r": "\r", "t": "\t", '"': '"', "\\": "\\"}


def unescape(raw: str) -> str:
    def rep(m):
        e = m.group(1)
        if e[0] in "uU" and len(e) > 1:
            try:
                return chr(int(e[1:], 16))
            except ValueError:
                return m.group(0)
        return _SIMPLE.get(e, m.group(0))
    return _ESC.sub(rep, raw) if "\\" in raw else raw


def _merge(parts: list) -> tuple:
    out = []
    for p in parts:
        if p[0] == "t":
            if not p[1]:
                continue
            if out and out[-1][0] == "t":
                out[-1] = ("t", out[-1][1] + p[1])
                continue
        out.append(p)
    return tuple(out)


_DIR = re.compile(r"^\s*~?\s*(if|else|endif|for|endfor)\b(.*?)~?\s*$", re.S)


def _directive(inner: str) -> tuple:
    m = _DIR.match(inner)
    if not m:
        raise AstError("diretiva de template ilegível")
    kind, rest = m.group(1), m.group(2).strip()
    if kind == "if":
        return ("d", "if", parse_expr(rest), ())
    if kind == "for":
        fm = re.match(r"^([A-Za-z_][\w-]*)\s*(?:,\s*([A-Za-z_][\w-]*))?\s+in\s+(.*)$", rest, re.S)
        if not fm:
            raise AstError("for de template ilegível")
        names = tuple(x for x in (fm.group(1), fm.group(2)) if x)
        return ("d", "for", parse_expr(fm.group(3)), names)
    return ("d", kind, None, ())


def _find_close(s: str, i: int) -> list:
    """Candidatos ao '}' que fecha a interpolação aberta em s[i:] (profundidade de chaves, aspas)."""
    cands, depth, j, n, q = [], 0, i, len(s), False
    while j < n:
        c = s[j]
        if q:
            if c == "\\":
                j += 2
                continue
            if c == '"':
                q = False
        elif c == '"':
            q = True
        elif c == "{":
            depth += 1
        elif c == "}":
            if depth == 0:
                cands.append(j)
                if len(cands) >= 4:
                    break
            else:
                depth -= 1
        j += 1
    if not cands:
        k = s.find("}", i)
        while k != -1 and len(cands) < 8:
            cands.append(k)
            k = s.find("}", k + 1)
    return cands


def template_parts(text: str) -> tuple:
    """Texto de heredoc (sem escapes de barra) -> partes com interpolações e diretivas."""
    parts, buf, i, n = [], [], 0, len(text)
    while i < n:
        if text.startswith("$${", i):
            buf.append("${")
            i += 3
        elif text.startswith("%%{", i):
            buf.append("%{")
            i += 3
        elif text.startswith("${", i) or text.startswith("%{", i):
            is_dir = text[i] == "%"
            ok = False
            for j in _find_close(text, i + 2):
                inner = text[i + 2:j]
                try:
                    if is_dir:
                        node = _directive(inner)
                    else:
                        e = inner.strip()
                        if e.startswith("~"):
                            e = e[1:]
                        if e.endswith("~"):
                            e = e[:-1]
                        node = ("i", parse_expr(e))
                except (AstError, Exception):  # noqa: BLE001 - candidato errado; tenta o próximo '}'
                    continue
                if buf:
                    parts.append(("t", "".join(buf)))
                    buf = []
                parts.append(node)
                i = j + 1
                ok = True
                break
            if not ok:
                buf.append(text[i])
                i += 1
        else:
            buf.append(text[i])
            i += 1
    if buf:
        parts.append(("t", "".join(buf)))
    return _merge(parts)


def _heredoc(tok: str, trim: bool) -> tuple:
    m = re.match(r"<<-?([A-Za-z][A-Za-z0-9._-]*)\r?\n", tok)
    if not m:
        raise AstError("heredoc ilegível")
    body = tok[m.end():]
    body = re.sub(r"[ \t]*" + re.escape(m.group(1)) + r"\r?\n?$", "", body)
    body = body.replace("\r\n", "\n")
    if trim:
        lines = body.split("\n")
        ind = [len(ln) - len(ln.lstrip(" \t")) for ln in lines if ln.strip()]
        k = min(ind) if ind else 0
        body = "\n".join(ln[k:] if len(ln) >= k else ln.lstrip(" \t") for ln in lines)
    return _str_node(template_parts(body))


def _string(node: Tree) -> tuple:
    parts = []
    for sp in node.children:
        if isinstance(sp, Token):
            continue  # DBLQUOTE
        for c in sp.children:
            if isinstance(c, Token):
                if c.type == "STRING_CHARS":
                    parts.append(("t", unescape(str(c))))
                elif c.type == "ESCAPED_INTERPOLATION":
                    parts.append(("t", str(c)[1:]))
                elif c.type == "ESCAPED_DIRECTIVE":
                    parts.append(("t", str(c)[1:]))
                else:
                    parts.append(("t", str(c)))
            elif c.data == "interpolation":
                parts.append(("i", expr(_trees(c.children)[0])))
            elif c.data == "template_if_start":
                parts.append(("d", "if", expr(_trees(c.children)[0]), ()))
            elif c.data == "template_else":
                parts.append(("d", "else", None, ()))
            elif c.data == "template_endif":
                parts.append(("d", "endif", None, ()))
            elif c.data == "template_for_start":
                ts = _trees(c.children)
                names = tuple(str(t.children[0]) for t in ts if t.data == "identifier")
                parts.append(("d", "for", expr(ts[-1]), names))
            elif c.data == "template_endfor":
                parts.append(("d", "endfor", None, ()))
            else:
                raise AstError(f"parte de cadeia desconhecida: {c.data}")
    return _str_node(_merge(parts))


def _str_node(parts: tuple) -> tuple:
    """"${x}" sozinho é x (semântica do Terraform: o tipo de x é preservado)."""
    if len(parts) == 1 and parts[0][0] == "i":
        return parts[0][1]
    return ("str", parts)


def _name(node) -> str:
    if isinstance(node, Token):
        return str(node)
    if node.data in ("identifier", "keyword", "literal_value"):
        return str(node.children[0])
    if node.data == "string":
        s = _string(node)
        return "".join(p[1] for p in s[1] if p[0] == "t")
    raise AstError(f"nome inesperado: {node.data}")


def _step(node: Tree) -> tuple:
    if node.data == "get_attr":
        return ("a", _name(_trees(node.children)[0] if _trees(node.children) else node.children[-1]))
    if node.data == "braces_index":
        return ("i", expr(_trees(node.children)[0]))
    if node.data == "short_index":
        return ("i", ("num", int(str(node.children[-1]))))
    raise AstError(f"passo desconhecido: {node.data}")


def _with_steps(base, steps: list) -> tuple:
    if base[0] == "trav":
        return ("trav", base[1], base[2] + tuple(steps))
    return ("trav", base, tuple(steps))


def _num(tok: str):
    t = str(tok)
    if re.fullmatch(r"-?\d+", t):
        return int(t)
    return float(t)


def _for_intro(node: Tree):
    ids = [str(t.children[0]) for t in _trees(node.children) if t.data == "identifier"]
    coll = [t for t in _trees(node.children) if t.data != "identifier"]
    k, v = (ids[0], ids[1]) if len(ids) == 2 else (None, ids[0])
    return k, v, expr(coll[0])


def expr(node) -> tuple:  # noqa: C901 - um despacho por regra da gramática
    if isinstance(node, Token):
        if node.type == "NAME":
            return ("trav", str(node), ())
        raise AstError(f"token solto: {node.type}")
    d = node.data
    ch = node.children
    if d == "expr_term":
        ts = _trees(ch)
        if len(ts) != 1:
            raise AstError("expr_term com filhos inesperados")
        return expr(ts[0])
    if d in ("int_lit", "float_lit"):
        return ("num", _num(ch[0]))
    if d == "literal_value":
        v = str(ch[0])
        return ("null",) if v == "null" else ("bool", v == "true")
    if d == "identifier":
        return ("trav", str(ch[0]), ())
    if d == "keyword":
        return ("trav", str(ch[0]), ())
    if d == "string":
        return _string(node)
    if d == "template_string":
        raw = str(ch[0])
        return ("str", _merge([("t", unescape(raw[2:-2]))]))
    if d == "heredoc_template":
        return _heredoc(str(ch[0]), False)
    if d == "heredoc_template_trim":
        return _heredoc(str(ch[0]), True)
    if d == "tuple":
        return ("tuple", tuple(expr(t) for t in _trees(ch)))
    if d == "object":
        items = []
        for el in _trees(ch):
            k_node, v_node = _trees(el.children)
            kt = _trees(k_node.children)
            if kt and kt[0].data == "keyword":
                key = ("str", (("t", str(kt[0].children[0])),))
            else:
                key = expr(kt[0]) if kt else ("str", (("t", str(k_node.children[0])),))
                if key[0] == "trav" and isinstance(key[1], str) and not key[2]:
                    key = ("str", (("t", key[1]),))  # chave identificador nu = cadeia literal
            items.append((key, expr(v_node)))
        return ("object", tuple(items))
    if d == "function_call":
        ids = [t for t in _trees(ch) if t.data == "identifier"]
        name = "::".join(str(t.children[0]) for t in ids)
        args_n = [t for t in _trees(ch) if t.data == "arguments"]
        args, expand = (), False
        if args_n:
            a = args_n[0]
            args = tuple(expr(t) for t in _trees(a.children))
            expand = any(isinstance(t, Token) and t.type == "ELLIPSIS" for t in a.children)
        return ("call", name, args, expand)
    if d == "conditional":
        c, a, b = _trees(ch)
        return ("cond", expr(c), expr(a), expr(b))
    if d == "binary_op":
        ts = _trees(ch)
        left, term = ts[0], ts[1]
        tt = _trees(term.children)
        op_tok = tt[0].children[0]
        return ("bin", BINOPS[op_tok.type], expr(left), expr(tt[1]))
    if d == "unary_op":
        op = str(ch[0]).strip()
        return ("un", op, expr(_trees(ch)[0]))
    if d == "index_expr_term":
        base, idx = _trees(ch)
        return _with_steps(expr(base), [_step(idx)])
    if d == "get_attr_expr_term":
        base, ga = _trees(ch)
        return _with_steps(expr(base), [_step(ga)])
    if d in ("attr_splat_expr_term", "full_splat_expr_term"):
        base, sp = _trees(ch)
        mark = ("as",) if d == "attr_splat_expr_term" else ("fs",)
        return _with_steps(expr(base), [mark] + [_step(s) for s in _trees(sp.children)])
    if d == "for_tuple_expr":
        ts = _trees(ch)
        intro = [t for t in ts if t.data == "for_intro"][0]
        cond = [t for t in ts if t.data == "for_cond"]
        body = [t for t in ts if t.data not in ("for_intro", "for_cond")]
        k, v, coll = _for_intro(intro)
        c = expr(_trees(cond[0].children)[0]) if cond else None
        return ("fort", k, v, coll, expr(body[0]), c)
    if d == "for_object_expr":
        ts = _trees(ch)
        intro = [t for t in ts if t.data == "for_intro"][0]
        cond = [t for t in ts if t.data == "for_cond"]
        body = [t for t in ts if t.data not in ("for_intro", "for_cond")]
        k, v, coll = _for_intro(intro)
        c = expr(_trees(cond[0].children)[0]) if cond else None
        group = any(isinstance(t, Token) and t.type == "ELLIPSIS" for t in ch)
        return ("foro", k, v, coll, expr(body[0]), expr(body[1]), group, c)
    raise AstError(f"regra de expressão desconhecida: {d}")


def body(node: Tree) -> Body:
    out = Body()
    for c in _trees(node.children):
        if c.data == "attribute":
            ts = _trees(c.children)
            out.attrs.append((_name(ts[0]), expr(ts[1])))
        elif c.data == "block":
            ts = [t for t in c.children if isinstance(t, Tree) and not _is_nlc(t)]
            b = [t for t in ts if t.data == "body"][0]
            names = [t for t in ts if t.data != "body"]
            line = getattr(c.meta, "line", 0) if hasattr(c, "meta") else 0
            out.blocks.append(Block(_name(names[0]), [_name(t) for t in names[1:]], body(b), line))
    return out


def parse_expr(text: str) -> tuple:
    """Uma expressão isolada (interpolação de heredoc, roundtrip): embrulha em atributo."""
    t = parses_to_tree("x = " + text.strip())
    b = body(_trees(t.children)[0])
    if len(b.attrs) != 1 or b.blocks:
        raise AstError("expressão isolada inválida")
    return b.attrs[0][1]


def _alarm(_sig, _frm):
    raise ParseTimeout()


def parse_file(text: str, timeout_s: int = 20) -> Body:
    """Arquivo .tf inteiro, com tempo-limite (SIGALRM; só no processo principal de cada worker)."""
    old = signal.signal(signal.SIGALRM, _alarm)
    signal.setitimer(signal.ITIMER_REAL, timeout_s)
    try:
        t = parses_to_tree(text)
        return body(_trees(t.children)[0])
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, old)


# ------------------------------------------------------------------------------------------------ .tf.json
def _json_value(v) -> tuple:
    if isinstance(v, bool):
        return ("bool", v)
    if v is None:
        return ("null",)
    if isinstance(v, (int, float)):
        return ("num", v)
    if isinstance(v, str):
        return _str_node(template_parts(v))
    if isinstance(v, list):
        return ("tuple", tuple(_json_value(x) for x in v))
    if isinstance(v, dict):
        return ("object", tuple((("str", (("t", k),)), _json_value(x)) for k, x in v.items()))
    raise AstError("valor JSON inesperado")


def _json_body(obj: dict) -> Body:
    """Sintaxe JSON do Terraform: sem schema, objeto aninhado é atributo de mapa (nunca bloco)."""
    out = Body()
    for k, v in obj.items():
        out.attrs.append((k, _json_value(v)))
    return out


def parse_json_file(text: str) -> Body:
    doc = json.loads(text)
    out = Body()
    if not isinstance(doc, dict):
        raise AstError("raiz de .tf.json não é objeto")
    for btype in ("resource", "data"):
        sect = doc.get(btype) or {}
        sect_list = sect if isinstance(sect, list) else [sect]
        for s in sect_list:
            for rtype, named in (s or {}).items():
                for named_d in (named if isinstance(named, list) else [named]):
                    for rname, cfg in (named_d or {}).items():
                        for c in (cfg if isinstance(cfg, list) else [cfg]):
                            out.blocks.append(Block(btype, [rtype, rname], _json_body(c or {}), 0))
    mods = doc.get("module") or {}
    for m in (mods if isinstance(mods, list) else [mods]):
        for mname, cfg in (m or {}).items():
            for c in (cfg if isinstance(cfg, list) else [cfg]):
                out.blocks.append(Block("module", [mname], _json_body(c or {}), 0))
    return out
