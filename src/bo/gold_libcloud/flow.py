"""Interpretador abstrato, intraprocedural, sobre o ast de um driver do Libcloud (o código nunca é importado).

Pergunta que ele responde: num ponto do código em que um objeto normalizado é construído (Node(...),
Object(...), Record(...), ...), de que campo da resposta da API vem cada argumento.

Domínio abstrato: um valor (V) é um conjunto de origens (O) mais, opcionalmente, as chaves de um dicionário
montado no código (extra = {...}; extra["k"] = ...) e uma constante do código-fonte (tabelas de estado,
mapas de atributos). Uma origem é:
  field   leitura de campo da API: raiz (parâmetro da função ou corpo/cabeçalho de resposta) + caminho
          de chaves (subscrito, .get, findtext/findattr/findall com xpath, .find/.findtext do ElementTree);
          '*' no caminho = item de lista;
  const   literal ou constante do código;
  ctx     objeto Python do próprio Libcloud (parâmetro usado por atributo, self.X, NodeState.X): não é API;
  opaque  resultado de chamada que o interpretador não segue.
Cada origem carrega a sequência de operações aplicadas (ops): cast:int, enum:<tabela>, call:<f>, expr, ...

Fluxo: sensível à ordem em código reto (atribuição simples substitui), fraco em ramos (if/try/for/while
juntam os dois lados). Métodos do próprio arquivo (self.m(...), funções do módulo) são seguidos com os
argumentos ligados até a profundidade MAX_DEPTH, sem registrar construções (cada função também é analisada
sozinha, com os parâmetros como raízes). As regras de cada caso estão nas funções abaixo, sem heurística
escondida: o que não está aqui vira opaque.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, replace

MAX_OPS = 8
MAX_ORIGINS = 100_000   # sem corte na prática (medido em 03/11: com 64 o SSSOM mudava)
MAX_DEPTH = 2

CASTS = {"int": "int", "float": "float", "str": "str", "bool": "bool", "long": "int", "Decimal": "decimal"}
DATE_FNS = {"parse_date", "parse_date_allow_empty", "parse_iso_date", "_to_datetime", "_parse_date",
            "iso8601", "fromisoformat", "strptime", "parse"}
XML_FNS = {"findtext", "findattr", "find", "findall", "findall_ignore_namespace", "findtext_ignore_namespace"}
LIST_FNS = {"list", "tuple", "set", "sorted", "frozenset"}
SIDE_ADD = {"append", "add", "insert", "extend"}
RESPONSE_PARTS = {"object", "headers", "body", "parse_body", "json"}
# operações que não mudam o valor lido (só embrulham em lista, iteram ou dão valor na ausência)
NEUTRAL_OPS = {"list", "append", "default", "text", "attrmap"}  # e via:<helper>


class Sym(str):
    """Nome simbólico vindo do código (NodeState.RUNNING, str, parse_date)."""


NOCONST = object()
ITEM = "\x00item"   # chave interna: dicionário acrescentado a uma lista


@dataclass(frozen=True)
class O:
    kind: str
    root: str = ""
    path: tuple = ()
    ops: tuple = ()
    line: int = 0
    note: str = ""

    def op(self, *ops: str) -> "O":
        return replace(self, ops=(self.ops + tuple(ops))[:MAX_OPS])

    def navigable(self) -> bool:
        """Depois de uma operação que muda o valor (chamada, expressão, cast...), o caminho não continua."""
        return all(op in NEUTRAL_OPS or op.startswith("via:") for op in self.ops)

    def child(self, keys, line: int) -> "O":
        if self.kind != "field":
            return self
        if not self.navigable():
            return self.op("sub")
        keys = tuple(re.sub(r"^\{[^}]*\}", "", str(k)) or "?" for k in keys)
        if keys == ("*",) and self.path and self.path[-1] == "*":
            return self   # item de um findall já é item: não aninha
        named = any(k != "*" for k in keys)   # a linha registrada é a do último segmento com nome
        return replace(self, path=self.path + keys, line=(line or self.line) if named else self.line)


class V:
    __slots__ = ("o", "keys", "cv", "cname")

    def __init__(self, o=frozenset(), keys=None, cv=NOCONST, cname=""):
        # corte determinístico (independe da ordem de hash do processo): as MAX_ORIGINS menores por repr
        self.o = frozenset(sorted(o, key=repr)[:MAX_ORIGINS]) if len(o) > MAX_ORIGINS else frozenset(o)
        self.keys = keys
        self.cv = cv
        self.cname = cname

    def op(self, *ops: str) -> "V":
        keys = None if self.keys is None else {k: v.op(*ops) for k, v in self.keys.items()}
        return V({x.op(*ops) for x in self.o}, keys)

    def child(self, keys, line: int) -> "V":
        return V({x.child(keys, line) for x in self.o})

    def fields(self):
        return [x for x in self.o if x.kind == "field"]

    def all_origins(self):
        out = set(self.o)
        for v in (self.keys or {}).values():
            out |= v.all_origins()
        return out


EMPTY = V()


def join(*vs: V) -> V:
    vs = [v for v in vs if v is not None]
    if not vs:
        return EMPTY
    o = set()
    keys = None
    for v in vs:
        o |= v.o
        if v.keys is not None:
            keys = dict(keys or {})
            for k, kv in v.keys.items():
                keys[k] = join(keys[k], kv) if k in keys else kv
    cvs = [v.cv for v in vs if v.cv is not NOCONST]
    cv = cvs[0] if len(cvs) == len(vs) and all(c == cvs[0] for c in cvs) else NOCONST
    return V(o, keys, cv, vs[0].cname if cv is not NOCONST else "")


def const(node_or_value, line: int = 0, note: str = "") -> V:
    return V({O("const", line=line, note=note[:60])}, cv=node_or_value)


def ctx(note: str, line: int = 0) -> V:
    return V({O("ctx", line=line, note=note[:80])})


def opaque(note: str, line: int = 0) -> V:
    return V({O("opaque", line=line, note=note[:80])})


def flow_name(n: ast.AST) -> str:
    return dotted(n).split(".")[-1] if dotted(n) else "?"


def dotted(n: ast.AST) -> str:
    if isinstance(n, ast.Name):
        return n.id
    if isinstance(n, ast.Attribute):
        d = dotted(n.value)
        return f"{d}.{n.attr}" if d else ""
    return ""


def const_eval(n: ast.AST, consts: dict | None = None):
    """Constante do código como estrutura Python; nomes viram Sym. NOCONST se não é constante."""
    consts = consts or {}
    if isinstance(n, ast.Constant):
        return n.value
    if isinstance(n, (ast.Name, ast.Attribute)):
        d = dotted(n)
        if isinstance(n, ast.Name) and d in consts:
            return consts[d]
        return Sym(d) if d else NOCONST
    if isinstance(n, ast.Dict):
        out = {}
        for k, v in zip(n.keys, n.values):
            if k is None:
                return NOCONST
            kk, vv = const_eval(k, consts), const_eval(v, consts)
            if kk is NOCONST or vv is NOCONST or isinstance(kk, (dict, list)):
                return NOCONST
            out[kk] = vv
        return out
    if isinstance(n, (ast.List, ast.Tuple, ast.Set)):
        out = [const_eval(e, consts) for e in n.elts]
        return NOCONST if any(x is NOCONST for x in out) else out
    if isinstance(n, ast.Call):
        d = dotted(n.func)
        return Sym("call:" + d) if d else NOCONST
    if isinstance(n, ast.UnaryOp) and isinstance(n.op, ast.USub) and isinstance(n.operand, ast.Constant):
        return -n.operand.value
    return NOCONST


def xpath_parts(x) -> list[str]:
    if not isinstance(x, str):
        return ["?"]
    x = re.sub(r"\{[^}]*\}", "", x)   # namespace XML em notação de Clark
    parts = [p for p in x.strip("/").split("/") if p not in ("", ".")]
    return [p.split(":", 1)[-1] if ":" in p and not p.startswith("@") else p for p in parts] or ["?"]


class Interp:
    """Executa uma função abstratamente. sink(callnode, cls, args_V, env) recebe cada construção-alvo."""

    def __init__(self, mod, cls, fn: ast.FunctionDef, bind: dict | None = None, depth: int = 0,
                 sink=None, stack: tuple = ()):
        self.mod, self.cls, self.fn, self.depth, self.sink = mod, cls, fn, depth, sink
        self.stack = stack + (fn.name,)
        self.returns = EMPTY
        self.env: dict[str, V] = {}
        params = [a.arg for a in fn.args.posonlyargs + fn.args.args + fn.args.kwonlyargs]
        if fn.args.vararg:
            params.append(fn.args.vararg.arg)
        if fn.args.kwarg:
            params.append(fn.args.kwarg.arg)
        for p in params:
            if p in ("self", "cls"):
                continue
            if bind is not None:
                self.env[p] = bind.get(p, ctx(f"param-ausente:{p}", fn.lineno))
            else:
                self.env[p] = V({O("field", root=p, line=fn.lineno)})

    # ------------------------------------------------------------------ execução
    def run(self) -> V:
        self.env = self.block(self.fn.body, self.env)
        return self.returns

    def block(self, stmts, env: dict) -> dict:
        for s in stmts:
            env = self.stmt(s, env)
        return env

    @staticmethod
    def merge(*envs: dict) -> dict:
        out = {}
        for e in envs:
            for k, v in e.items():
                out[k] = join(out[k], v) if k in out else v
        return out

    def stmt(self, s, env: dict) -> dict:
        if isinstance(s, ast.Assign):
            v = self.ev(s.value, env)
            for t in s.targets:
                self.assign(t, v, env)
        elif isinstance(s, ast.AnnAssign) and s.value is not None:
            self.assign(s.target, self.ev(s.value, env), env)
        elif isinstance(s, ast.AugAssign):
            cur = self.ev(s.target, env) if not isinstance(s.target, ast.Subscript) else EMPTY
            self.assign(s.target, join(cur, self.ev(s.value, env)).op("expr"), env)
        elif isinstance(s, ast.Expr):
            self.ev(s.value, env)
        elif isinstance(s, ast.Return):
            if s.value is not None:
                self.returns = join(self.returns, self.ev(s.value, env))
        elif isinstance(s, ast.If):
            self.ev(s.test, env)
            a = self.block(s.body, dict(env))
            b = self.block(s.orelse, dict(env))
            env = self.merge(a, b)
        elif isinstance(s, (ast.For, ast.AsyncFor)):
            it = self.iterate(self.ev(s.iter, env), s.lineno)
            e1 = dict(env)
            self.assign(s.target, it, e1)
            e1 = self.block(s.body, e1)
            e2 = self.merge(env, e1)
            self.assign(s.target, it, e2)
            e2 = self.block(s.body, e2)
            env = self.merge(env, e2)
            env = self.merge(env, self.block(s.orelse, dict(env)))
        elif isinstance(s, ast.While):
            self.ev(s.test, env)
            e1 = self.block(s.body, dict(env))
            e2 = self.block(s.body, self.merge(env, e1))
            env = self.merge(env, e2)
        elif isinstance(s, (ast.Try, getattr(ast, "TryStar", ast.Try))):
            eb = self.block(s.body, dict(env))
            eb = self.block(s.orelse, eb)
            outs = [eb]
            for h in s.handlers:
                outs.append(self.block(h.body, self.merge(env, eb)))
            env = self.merge(*outs)
            env = self.block(s.finalbody, env)
        elif isinstance(s, (ast.With, ast.AsyncWith)):
            for item in s.items:
                v = self.ev(item.context_expr, env)
                if item.optional_vars is not None:
                    self.assign(item.optional_vars, v, env)
            env = self.block(s.body, env)
        elif isinstance(s, ast.Match):
            self.ev(s.subject, env)
            env = self.merge(env, *[self.block(c.body, dict(env)) for c in s.cases])
        # FunctionDef/ClassDef aninhados, Raise, Pass, Break, Continue, Assert, Delete, Global: sem efeito
        return env

    def assign(self, t, v: V, env: dict) -> None:
        if isinstance(t, ast.Name):
            env[t.id] = v
        elif isinstance(t, (ast.Tuple, ast.List)):
            for e in t.elts:
                self.assign(e.value if isinstance(e, ast.Starred) else e, v.op("unpack"), env)
        elif isinstance(t, ast.Subscript) and isinstance(t.value, ast.Name):
            k = const_eval(t.slice)
            name = t.value.id
            cur = env.get(name, EMPTY)
            if isinstance(k, (str, int)) and not isinstance(k, Sym):
                keys = dict(cur.keys or {})
                keys[str(k)] = v
                env[name] = V(cur.o, keys)
            else:   # chave calculada: o valor entra no dicionário sem chave conhecida
                env[name] = V(join(cur, v.op("dyn")).o, cur.keys)
        elif isinstance(t, ast.Starred):
            self.assign(t.value, v, env)
        # atributo (obj.x = ...) e subscrito aninhado: fora do domínio

    def iterate(self, v: V, line: int) -> V:
        """Item de uma iteração: filho '*' dos campos; o dicionário acrescentado a uma lista (ITEM); iterar um
        dicionário dá as chaves (constantes), não os valores (esses só por .values())."""
        parts = [v.child(["*"], line)]
        if v.keys and ITEM in v.keys:
            parts.append(v.keys[ITEM])
        if isinstance(v.cv, (list, tuple)):
            parts.append(const(v.cv[0] if v.cv else None, line))
        return join(*parts)

    # ------------------------------------------------------------------ expressões
    def ev(self, n, env: dict) -> V:
        line = getattr(n, "lineno", 0)
        if n is None:
            return EMPTY
        if isinstance(n, ast.Constant):
            return const(n.value, line, repr(n.value))
        if isinstance(n, ast.Name):
            if n.id in env:
                return env[n.id]
            if n.id in self.mod.consts:
                return V({O("const", line=line, note=n.id)}, cv=self.mod.consts[n.id], cname=n.id)
            if n.id[:1].isupper():
                return V({O("const", line=line, note=n.id)}, cv=Sym(n.id))
            return ctx(n.id, line)
        if isinstance(n, ast.Attribute):
            return self.ev_attr(n, env, line)
        if isinstance(n, ast.Subscript):
            return self.ev_sub(n, env, line)
        if isinstance(n, ast.Call):
            return self.ev_call(n, env, line)
        if isinstance(n, ast.Dict):
            keys, rest = {}, []
            for k, v in zip(n.keys, n.values):
                kk = const_eval(k) if k is not None else NOCONST
                vv = self.ev(v, env)
                if isinstance(kk, (str, int)) and not isinstance(kk, Sym):
                    keys[str(kk)] = vv
                else:
                    rest.append(vv.op("dyn"))
            out = V(join(*rest).o if rest else frozenset(), keys)
            cv = const_eval(n, self.mod.consts)
            if cv is not NOCONST:
                out.cv = cv
            return out
        if isinstance(n, (ast.List, ast.Tuple, ast.Set)):
            elts = [self.ev(e.value if isinstance(e, ast.Starred) else e, env) for e in n.elts]
            out = join(*elts).op("list") if elts else const([], line, "[]")
            cv = const_eval(n, self.mod.consts)
            if cv is not NOCONST:
                out.cv = cv
            return out
        if isinstance(n, (ast.ListComp, ast.SetComp, ast.GeneratorExp)):
            e2 = dict(env)
            for g in n.generators:
                self.assign(g.target, self.iterate(self.ev(g.iter, e2), line), e2)
                for c in g.ifs:
                    self.ev(c, e2)
            return self.ev(n.elt, e2).op("list")
        if isinstance(n, ast.DictComp):
            e2 = dict(env)
            for g in n.generators:
                self.assign(g.target, self.iterate(self.ev(g.iter, e2), line), e2)
            return join(self.ev(n.key, e2), self.ev(n.value, e2)).op("dyn")
        if isinstance(n, ast.IfExp):
            self.ev(n.test, env)
            return join(self.ev(n.body, env), self.ev(n.orelse, env))
        if isinstance(n, ast.BoolOp):
            if isinstance(n.op, ast.Or):
                return join(*[self.ev(v, env) for v in n.values])
            return join(*[self.ev(v, env) for v in n.values]).op("expr")
        if isinstance(n, (ast.BinOp,)):
            return join(self.ev(n.left, env), self.ev(n.right, env)).op("expr")
        if isinstance(n, ast.UnaryOp):
            return self.ev(n.operand, env).op("expr")
        if isinstance(n, ast.Compare):
            return join(self.ev(n.left, env), *[self.ev(c, env) for c in n.comparators]).op("bool")
        if isinstance(n, ast.JoinedStr):
            return join(*[self.ev(v.value, env) for v in n.values if isinstance(v, ast.FormattedValue)],
                        const("", line)).op("expr")
        if isinstance(n, ast.NamedExpr):
            v = self.ev(n.value, env)
            self.assign(n.target, v, env)
            return v
        if isinstance(n, (ast.Await, ast.Starred)):
            return self.ev(n.value, env)
        if isinstance(n, ast.Lambda):
            return opaque("lambda", line)
        return opaque(type(n).__name__, line)

    def ev_attr(self, n: ast.Attribute, env: dict, line: int) -> V:
        if isinstance(n.value, ast.Name) and n.value.id == "self":
            cv = self.mod.class_const(self.cls, n.attr)
            if cv is not NOCONST:
                return V({O("const", line=line, note="self." + n.attr)}, cv=cv, cname=n.attr)
            return ctx("self." + n.attr, line)
        base = self.ev(n.value, env)
        if isinstance(base.cv, Sym) and not base.fields():
            d = f"{base.cv}.{n.attr}"
            return V({O("const", line=line, note=d)}, cv=Sym(d))
        if n.attr in ("text", "tail"):
            return V({o.op("text") if o.kind == "field" else o for o in base.o})
        if n.attr == "attrib":
            return base
        if base.keys is not None and n.attr in base.keys and not base.fields():
            return base.keys[n.attr]
        out = set()
        for o in base.o:
            if o.kind == "field" and not o.path:
                if o.root.startswith("response") and n.attr in RESPONSE_PARTS and "." not in o.root:
                    out.add(O("field", root=f"response.{n.attr}", line=line))
                else:
                    out.add(O("ctx", line=line, note=f"{o.root}.{n.attr}"))
            elif o.kind == "field":
                out.add(o.op("attr:" + n.attr))
            elif o.kind == "ctx":
                out.add(replace(o, note=(o.note + "." + n.attr)[:80], line=line))
            else:
                out.add(o)
        return V(out)

    def table_lookup(self, table: V, key: V, line: int) -> V:
        name = table.cname or "tabela"
        self.mod.tables[name] = table.cv
        return key.op("enum:" + name)

    def ev_sub(self, n: ast.Subscript, env: dict, line: int) -> V:
        base = self.ev(n.value, env)
        if isinstance(n.slice, ast.Slice):
            return base.op("slice")
        k = const_eval(n.slice)
        if isinstance(k, (str, int)) and not isinstance(k, Sym):
            if base.keys is not None and str(k) in base.keys:
                return base.keys[str(k)]
            if isinstance(k, int) and base.keys and ITEM in base.keys:
                return join(base.child(["*"], line), base.keys[ITEM])
            if isinstance(base.cv, dict):
                if k in base.cv:
                    return V({O("const", line=line, note=f"{base.cname}[{k!r}]")}, cv=base.cv[k],
                             cname=f"{base.cname}[{k!r}]")
                return const(None, line, "chave-ausente")
            if isinstance(base.cv, (list, tuple)):
                return const(None, line, "item")
            return base.child([str(k) if isinstance(k, str) else "*"], line)
        key = self.ev(n.slice, env)
        if isinstance(base.cv, dict) and base.cv:
            return self.table_lookup(base, key, line)
        if base.keys and ITEM in base.keys:
            return join(base.child(["*"], line), base.keys[ITEM])
        return base.child(["*"], line)

    # ------------------------------------------------------------------ chamadas
    def args_of(self, n: ast.Call, env: dict):
        pos = [self.ev(a.value if isinstance(a, ast.Starred) else a, env) for a in n.args]
        kw = {k.arg: self.ev(k.value, env) for k in n.keywords if k.arg}
        star = [self.ev(k.value, env) for k in n.keywords if not k.arg]
        return pos, kw, star

    def xml_call(self, fname: str, n: ast.Call, env: dict, line: int, base: V | None = None) -> V:
        kw = {k.arg: k.value for k in n.keywords if k.arg}
        args = list(n.args)
        if base is None:
            el = kw.get("element") or (args.pop(0) if args else None)
            base = self.ev(el, env) if el is not None else EMPTY
        xp = kw.get("xpath") or (args[0] if args else None)
        xv = self.ev(xp, env) if xp is not None else EMPTY
        x = xv.cv if isinstance(xv.cv, str) and not isinstance(xv.cv, Sym) else None
        parts = xpath_parts(x)
        out = base.child(parts, line)
        if fname.startswith("findall") or fname == "iter":
            out = out.child(["*"], line)
        return out

    def ev_call(self, n: ast.Call, env: dict, line: int) -> V:
        f = n.func
        # construção-alvo?
        tgt = self.mod.target_of(f)
        if tgt is not None:
            pos, kw, _ = self.args_of(n, env)
            if self.sink is not None:
                self.sink(n, tgt, pos, kw, self)
            return ctx("obj:" + tgt[0], line)
        attrs = self.mod.plain_class_attrs(f)
        if attrs is not None:   # objeto de classe auxiliar do Libcloud: atributo = parâmetro do __init__
            params, amap = attrs
            pos, kw, _ = self.args_of(n, env)
            bound = dict(zip(params, pos))
            bound.update({k: v for k, v in kw.items() if k in params})
            return V(frozenset({O("ctx", line=line, note="obj:" + flow_name(f))}),
                     {a: bound[p] for a, p in amap.items() if p in bound})
        if isinstance(f, ast.Name):
            name = f.id
            if name in CASTS and n.args:
                return self.ev(n.args[0], env).op("cast:" + CASTS[name])
            if name in DATE_FNS and n.args:
                return join(*self.args_of(n, env)[0][:1]).op("cast:datetime")
            if name in XML_FNS:
                return self.xml_call(name, n, env, line)
            if name == "fixxpath":   # fixxpath(xpath=, namespace=) do libcloud.utils.xml ou fixxpath(raiz, tag) local
                kw = {k.arg: k.value for k in n.keywords if k.arg}
                cands = [kw["xpath"]] if "xpath" in kw else list(n.args)
                xs = [const_eval(c) for c in cands]
                x = next((c for c in xs if isinstance(c, str) and not isinstance(c, Sym)), None)
                return const(x, line, "xpath")
            if name in LIST_FNS:
                pos, _, _ = self.args_of(n, env)
                return join(*pos).op("list") if pos else const([], line)
            if name == "dict":
                pos, kw, _ = self.args_of(n, env)
                return join(*pos, V(frozenset(), dict(kw)))
            if name in self.mod.functions and self.depth < MAX_DEPTH and name not in self.stack:
                return self.inline(None, self.mod.functions[name], n, env, line)
            pos, kw, star = self.args_of(n, env)
            return join(*pos, *kw.values(), *star, opaque("call:" + name, line)).op("call:" + name)
        if isinstance(f, ast.Attribute):
            attr = f.attr
            owner = f.value
            if isinstance(owner, ast.Name) and owner.id == "self":
                meth = self.mod.method(self.cls, attr)
                if meth is not None and self.depth < MAX_DEPTH and attr not in self.stack:
                    return self.inline(meth[0], meth[1], n, env, line, is_method=True)
                if attr in DATE_FNS:
                    return join(*self.args_of(n, env)[0][:1]).op("cast:datetime")
                if "request" in attr:   # requisição herdada (ex. _sync_request de um mixin de outro arquivo)
                    self.args_of(n, env)
                    return V({O("field", root="response", line=line)})
                pos, kw, star = self.args_of(n, env)
                return join(*pos, *kw.values(), *star, opaque("call:self." + attr, line)).op("call:" + attr)
            # efeitos colaterais em variáveis locais
            if isinstance(owner, ast.Name) and owner.id in env and attr in SIDE_ADD | {"update", "setdefault"}:
                pos, kw, _ = self.args_of(n, env)
                cur = env[owner.id]
                if attr in SIDE_ADD:
                    add = pos[-1] if pos else EMPTY
                    if attr == "extend":
                        add = self.iterate(add, line)
                    if add.keys is not None:   # lista de dicionários: o item guarda as chaves
                        keys = dict(cur.keys or {})
                        keys[ITEM] = join(keys[ITEM], add) if ITEM in keys else add
                        env[owner.id] = V(join(cur, V(add.o).op("append")).o, keys)
                    else:
                        env[owner.id] = join(cur, add.op("append"))
                elif attr == "update":
                    keys = dict(cur.keys or {})
                    for p in pos:
                        for k, v in (p.keys or {}).items():
                            keys[k] = v
                    for k, v in kw.items():
                        keys[k] = v
                    rest = [p for p in pos if not p.keys]
                    env[owner.id] = V(join(cur, *[r.op("dyn") for r in rest]).o, keys)
                elif attr == "setdefault" and n.args:
                    k = const_eval(n.args[0])
                    if isinstance(k, str) and not isinstance(k, Sym):
                        keys = dict(cur.keys or {})
                        if k not in keys and len(pos) > 1:
                            keys[k] = pos[1]
                        env[owner.id] = V(cur.o, keys)
                        return keys.get(k, EMPTY)
                return const(None, line, attr)
            base = self.ev(owner, env)
            if attr == "get" and n.args:
                k = const_eval(n.args[0])
                dflt = self.ev(n.args[1], env) if len(n.args) > 1 else const(None, line, "None")
                if isinstance(base.cv, dict) and base.cv:
                    if isinstance(k, (str, int)) and not isinstance(k, Sym):
                        return join(const(base.cv.get(k), line), dflt)
                    return join(self.table_lookup(base, self.ev(n.args[0], env), line), dflt.op("default"))
                if isinstance(k, (str, int)) and not isinstance(k, Sym):
                    if base.keys is not None and str(k) in base.keys:
                        return join(base.keys[str(k)], dflt)
                    return join(base.child([str(k)], line), dflt.op("default"))
                return join(base.child(["*"], line), dflt.op("default")).op("dyn")
            if attr in ("findtext", "find", "findall", "iter", "iterfind"):
                return self.xml_call(attr if attr != "iterfind" else "findall", n, env, line, base=base)
            if attr == "values" and not n.args:
                return join(self.iterate(base, line), *[v for k, v in (base.keys or {}).items() if k != ITEM])
            if attr in ("items", "keys") and not n.args:
                return self.iterate(base, line).op("dyn")
            if attr == "copy" and not n.args:
                return base
            if attr == "request" or attr.startswith("request_") or attr.endswith("_request"):
                self.args_of(n, env)
                return V({O("field", root="response", line=line)})
            if attr in DATE_FNS:
                return join(*self.args_of(n, env)[0][:1]).op("cast:datetime")
            if attr in RESPONSE_PARTS and any(o.kind == "field" and o.root == "response" and not o.path
                                              for o in base.o):
                self.args_of(n, env)
                return V({O("field", root=f"response.{attr}", line=line)})
            # método de string/objeto sobre um valor: derivado
            pos, kw, star = self.args_of(n, env)
            return join(base, *pos, *kw.values(), *star).op("call:" + attr)
        pos, kw, star = self.args_of(n, env)
        return join(self.ev(f, env), *pos, *kw.values(), *star).op("call")

    @staticmethod
    def attr_map_idiom(pos: list, kw: dict, line: int) -> V | None:
        """Idioma dos drivers AWS-like: helper(elemento, MAPA) com MAPA = {chave_extra: {'xpath': x,
        'transform_func': f}} constante. Vira um dicionário {chave_extra: campo xpath com cast:f}."""
        vals = pos + list(kw.values())
        amap = next((v.cv for v in vals if isinstance(v.cv, dict) and v.cv
                     and all(isinstance(x, dict) and "xpath" in x for x in v.cv.values())), None)
        el = next((v for v in vals if v.fields()), None)
        if amap is None or el is None:
            return None
        keys = {}
        for k, spec in amap.items():
            out = el.child(xpath_parts(spec.get("xpath")), line)
            tf = spec.get("transform_func")
            tf = str(tf) if tf is not None else ""
            if tf in CASTS:
                out = out.op("cast:" + CASTS[tf])
            elif tf.split(".")[-1] in DATE_FNS:
                out = out.op("cast:datetime")
            elif tf:
                out = out.op("call:" + tf.split(".")[-1])
            keys[str(k)] = out.op("attrmap")
        return V(frozenset(), keys)

    def inline(self, cls, fn: ast.FunctionDef, n: ast.Call, env: dict, line: int, is_method: bool = False) -> V:
        pos, kw, _ = self.args_of(n, env)
        idiom = self.attr_map_idiom(pos, kw, line)
        if idiom is not None:
            return idiom
        params = [a.arg for a in fn.args.posonlyargs + fn.args.args]
        if is_method and params and params[0] in ("self", "cls"):
            params = params[1:]
        bind = {}
        for p, v in zip(params, pos):
            bind[p] = v
        defaults = fn.args.defaults
        for p, d in zip(params[len(params) - len(defaults):], defaults):
            bind.setdefault(p, const(const_eval(d), line, "default"))
        for k, d in zip(fn.args.kwonlyargs, fn.args.kw_defaults):
            if d is not None:
                bind.setdefault(k.arg, const(const_eval(d), line, "default"))
        bind.update(kw)
        if self.depth == 0 and self.sink is not None:   # sítio de chamada para a análise de raízes da API
            caller = (self.cls or "_module", self.fn.name)
            callee = ((cls if is_method else None) or "_module", fn.name)
            self.mod.callsites.append((caller, callee, dict(bind)))
        sub = Interp(self.mod, cls if cls is not None else self.cls, fn, bind=bind, depth=self.depth + 1,
                     sink=None, stack=self.stack)
        try:
            ret = sub.run()
        except RecursionError:
            return opaque("call:" + fn.name, line)
        if not ret.o and ret.keys is None:
            return opaque("call:" + fn.name, line)
        return ret.op("via:" + fn.name)
