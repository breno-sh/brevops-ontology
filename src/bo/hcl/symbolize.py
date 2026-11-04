"""AST neutra -> termos C06, por repositório.

Símbolo (C06-SYM): SYM-<hex> que depende só do repo_id e da ordem da primeira ocorrência de (espaço, texto) na
travessia canônica (arquivos em ordem, documento em ordem). O texto nunca é gravado nem resumido em hash.
O mesmo texto no mesmo espaço do mesmo repositório dá o mesmo símbolo; textos diferentes dão símbolos diferentes.

Vocabulário: na 1ª passada (collect) cada cadeia candidata registra (contexto, valor) só como chave de 64 bits;
na 2ª (apply) a cadeia fica literal se a chave está no conjunto mantido e o valor passa no privacy_lint.
O contexto depende só da AST (nunca do vocabulário), então as duas passadas percorrem a mesma coisa.
"""

from __future__ import annotations

import json
import re

from bo.contracts.rules import LEAK as CONTRACT_LEAK  # regra C06 do validador: nenhum literal com e-mail, ARN...
from bo.repo import privacy

from . import classify as C
from .common import key64, sym_id

OP_RX = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
RES_ROOT = re.compile(r"^[a-z][a-z0-9]*_[a-z0-9_]+$")
SCHEMA_ATTR = re.compile(r"^[A-Za-z0-9_]+$")
SKIP_BLOCKS = {"lifecycle_never"}  # nada é pulado: lifecycle, dynamic, provisioner entram (provisioner retido)


def lit(v, dt=None):
    if dt is None:
        dt = ("bool" if isinstance(v, bool) else "null" if v is None else "number" if isinstance(v, (int, float))
              else "string" if isinstance(v, str) else "list" if isinstance(v, list) else "map")
    return {"kind": "literal", "datatype": dt, "value": v}


def ex(op, *args):
    return {"kind": "expression", "op": op, "args": list(args)}


def is_lit(t):
    return t.get("kind") == "literal"


class SymTab:
    def __init__(self, rid: str, reveal: bool = False):
        self.rid = rid
        self.ids: dict = {}
        self.reveal = {} if reveal else None
        self.n = 0
        self.used: set = set()

    def get(self, ns: str, text: str) -> str:
        k = (ns, text)
        s = self.ids.get(k)
        if s is None:
            s = sym_id(self.rid, self.n)
            self.n += 1
            while s in self.used:  # colisão de 48 bits no mesmo repositório: próxima ordem (determinístico)
                s = sym_id(self.rid, self.n)
                self.n += 1
            self.used.add(s)
            self.ids[k] = s
            if self.reveal is not None:
                self.reveal[s] = k
        return s


class Vocab:
    """collect: registra chaves; apply: decide literal pelo conjunto mantido."""

    def __init__(self, keep=None):
        self.keep = keep
        self.seen: set = set()
        self._priv: dict = {}

    @property
    def collecting(self) -> bool:
        return self.keep is None

    def literal_ok(self, ctx: str, text: str) -> bool:
        k = key64(ctx, text)
        if self.keep is None:
            self.seen.add((key64(ctx), k))
            return False
        if k not in self.keep:
            return False
        ok = self._priv.get(text)
        if ok is None:
            ok = not privacy.scan_text(text, "v") and not any(rx.search(text) for _, rx in CONTRACT_LEAK) \
                and ("\n" not in text) and len(text) <= 256
            self._priv[text] = ok
        return ok


def norm_ctx(path: str) -> str:
    return re.sub(r"\[\d+\]", "", path)


def jp(seg) -> str:
    return "/" + str(seg).replace("~", "~0").replace("/", "~1")


class Symbolizer:
    def __init__(self, rid: str, vocab: Vocab, reveal: bool = False):
        self.tab = SymTab(rid, reveal)
        self.vocab = vocab
        self.scope: list = []  # pilhas de nomes de iteração (for, dynamic)
        self.counts = {"withheld": {}, "symbol_str": 0, "literal_str": 0, "documents": 0, "cidr": 0, "arn": 0}
        self.ast_log = [] if reveal else None  # (attr_path, contexto, modo, ast) só no roundtrip

    # -------------------------------------------------------------------------------------------- símbolos
    def sym(self, ns: str, text: str, cls: str = "unknown") -> dict:
        return {"kind": "symbol", "symbol_id": self.tab.get(ns, text), "name_class": cls, "scope": "repo"}

    def withheld(self, reason: str) -> dict:
        self.counts["withheld"][reason] = self.counts["withheld"].get(reason, 0) + 1
        return {"kind": "withheld", "reason": reason}

    # -------------------------------------------------------------------------------------------- cadeias
    def text(self, s: str, ctx: str) -> dict:
        if s == "":
            return lit("")
        if C.looks_json(s):
            try:
                tree = json.loads(s)
            except ValueError:
                tree = None
            if isinstance(tree, (dict, list)):
                return self.document(tree, "policy_json" if C.is_policy(tree) else "json", {})
        cid = C.parse_cidr(s)
        if cid:
            self.counts["cidr"] += 1
            addr, pfx, cls = cid
            a = self.sym("str", addr) if cls == "public" else lit(addr)
            return ex("cidr", a, lit(pfx), lit(cls))
        ip = C.parse_ip(s)
        if ip:
            addr, cls = ip
            return ex("ip", self.sym("str", addr) if cls == "public" else lit(addr), lit(cls))
        if s.startswith(C.ARN_PREFIX):
            return self.arn(s) or self.arn_partial(s)
        if C.ACCOUNT_LIKE.match(s):
            return self.sym("str", s)
        if C.is_numeric_text(s) and len(s) < 12:
            return lit(s)
        if self.vocab.literal_ok(ctx, s):
            self.counts["literal_str"] += 1
            return lit(s)
        self.counts["symbol_str"] += 1
        return self.sym("str", s)

    def arn(self, s: str):
        p = C.split_arn(s)
        if not p:
            return None
        self.counts["arn"] += 1
        part, svc, reg, acct, res = p
        ctx = f"arn:{svc}"
        args = [self.text(part, "arn:partition") if part else lit(""),
                self.text(svc, "arn:service") if svc else lit(""),
                self.text(reg, "arn:region") if reg else lit("")]
        if acct in ("", "*", "aws"):
            args.append(lit(acct))
        else:
            args.append(self.sym("str", acct))
        segs = []
        for i, sg in enumerate(C.arn_resource_segments(res)):
            if sg in ("/", ":", "*", ""):
                segs.append(lit(sg))
            else:
                segs.append(self.text(sg, f"{ctx}:seg{min(i, 6)}"))
        args.append(ex("arn_resource", *segs))
        return ex("arn", *args)

    def arn_partial(self, s: str) -> dict:
        """Pedaço de ARN (o prefixo de um template com a conta interpolada): segmentos e separadores, sem perder a forma."""
        self.counts["arn"] += 1
        segs = []
        for i, sg in enumerate(C.arn_resource_segments(s)):
            if sg in ("/", ":", "*", "") or (i == 0 and sg == "arn"):
                segs.append(lit(sg))
            else:
                segs.append(self.text(sg, f"arnpart:seg{min(i, 12)}"))
        return ex("arn_partial", *segs)

    # -------------------------------------------------------------------------------------------- documentos
    def document(self, tree, fmt: str, interps: dict) -> dict:
        """Árvore JSON com principais e identificadores simbolizados (C06-DOC).

        interps: marcador -> termo de interpolação (heredoc/template com ${...} dentro do JSON)."""
        self.counts["documents"] += 1
        symbolized = []
        out = self._doc(tree, "", "", "identifier", interps, symbolized)
        return {"kind": "document", "format": fmt, "tree": out, "symbolized": symbolized}

    def _interp_term(self, s, npath, interps):
        """Cadeia JSON com marcadores de interpolação -> termo (a interpolação sozinha ou um template)."""
        parts = []
        rx = re.compile("|".join(re.escape(m) for m in interps))
        last = 0
        for m in rx.finditer(s):
            if m.start() > last:
                parts.append(("t", s[last:m.start()]))
            parts.append(("m", m.group(0)))
            last = m.end()
        if last < len(s):
            parts.append(("t", s[last:]))
        if len(parts) == 1:
            return interps[parts[0][1]]
        args = [interps[p[1]] if p[0] == "m" else self.text(p[1], "doc" + npath + "#frag") for p in parts]
        return ex("hcl_template", *args)

    def _doc_str(self, s, path, npath, role, interps, symbolized):
        if interps and any(m in s for m in interps):
            t = self._interp_term(s, npath, interps)
            self._collect_syms(t, path + "/$term", role, symbolized)
            return {"$term": t}
        t = self.text(s, "doc" + npath)
        if t["kind"] == "literal":
            return t["value"]
        if t["kind"] == "symbol":
            symbolized.append({"path": path, "symbol_id": t["symbol_id"],
                               "role": "account" if C.ACCOUNT_LIKE.match(s) else role})
            return t["symbol_id"]
        self._collect_syms(t, path + "/$term", role, symbolized)
        return {"$term": t}

    def _collect_syms(self, t, path, role, symbolized):
        k = t.get("kind")
        if k == "symbol":
            symbolized.append({"path": path, "symbol_id": t["symbol_id"], "role": role})
        elif k == "reference":
            pass
        elif k == "expression":
            arn_acct = t["op"] == "arn"
            for i, a in enumerate(t["args"]):
                r = "account" if (arn_acct and i == 3) else role
                self._collect_syms(a, f"{path}/args/{i}", r, symbolized)
        elif k == "document":
            for e in t["symbolized"]:
                symbolized.append({"path": path + "/tree" + e["path"], "symbol_id": e["symbol_id"],
                                   "role": e["role"]})

    def _doc(self, x, path, npath, role, interps, symbolized):
        if isinstance(x, dict):
            out = {}
            for k, v in x.items():
                r = role
                if k in ("Principal", "NotPrincipal", "principal", "principals"):
                    r = "principal"
                elif k in ("Resource", "NotResource", "resource", "resources"):
                    r = "identifier"
                reason = C.withheld_reason(k, "", value_is_scalar=not isinstance(v, (dict, list)))
                kk = k
                if interps and any(m in k for m in interps):
                    # chave com interpolação: a chave vira símbolo e o membro guarda {"$key": termo, "$value": ...}
                    kterm = self._interp_term(k, npath + "#key", interps)
                    kk = self.tab.get("dockey", json.dumps(kterm, sort_keys=True))
                    symbolized.append({"path": path + jp(kk), "symbol_id": kk, "role": "resource_name"})
                    self._collect_syms(kterm, path + jp(kk) + "/$key", "identifier", symbolized)
                    out[kk] = {"$key": kterm, "$value": self._doc(v, path + jp(kk) + "/$value", npath + "/*", r,
                                                                  interps, symbolized)}
                    continue
                else:
                    kt = self.text(k, "dockey" + npath) if k else lit("")
                    if kt["kind"] == "literal" and isinstance(kt["value"], str):
                        kk = kt["value"]
                    else:
                        kk = self.tab.get("str", k)
                        symbolized.append({"path": path + jp(kk), "symbol_id": kk, "role": "resource_name"})
                if reason and not (reason == "secret" and isinstance(v, bool)):
                    out[kk] = {"$term": self.withheld(reason)}
                    continue
                out[kk] = self._doc(v, path + jp(kk), npath + jp(k if kt_is_schema(k) else "*"), r,
                                    interps, symbolized)
            return out
        if isinstance(x, list):
            return [self._doc(v, path + jp(i), npath + "/*", role, interps, symbolized) for i, v in enumerate(x)]
        if isinstance(x, str):
            return self._doc_str(x, path, npath, role, interps, symbolized)
        if isinstance(x, bool) or x is None:
            return x
        if isinstance(x, int) and C.ACCOUNT_LIKE.match(str(abs(x))):
            s = self.tab.get("num", str(x))
            symbolized.append({"path": path, "symbol_id": s, "role": "account"})
            return s
        return x

    # -------------------------------------------------------------------------------------------- expressões
    def in_scope(self, name: str) -> bool:
        return any(name in fr for fr in self.scope)

    def steps(self, base: dict, steps, schema: bool, ctx: str) -> dict:
        t = base
        for st in steps:
            if st[0] == "a":
                t = ex("hcl_getattr", t, lit(st[1]) if schema else self.sym("field", st[1]))
            elif st[0] == "i":
                t = ex("hcl_index", t, self.term(st[1], ctx + "#idx"))
            elif st[0] == "as":
                t = ex("hcl_splat", t)
                schema = schema
            elif st[0] == "fs":
                t = ex("hcl_splat_full", t)
        return t

    def trav(self, node, ctx: str) -> dict:  # noqa: C901
        root, steps = node[1], list(node[2])
        if not isinstance(root, str):
            return self.steps(self.term(root, ctx), steps, False, ctx)
        a0 = steps[0][1] if steps and steps[0][0] == "a" else None
        if self.in_scope(root):
            base = self.sym("iter", root, "each_key" if self.is_dynamic_iter(root) else "unknown")
            if self.is_dynamic_iter(root) and a0 in ("key", "value"):
                return self.steps(ex("hcl_getattr", base, lit(a0)), steps[1:], False, ctx)
            return self.steps(base, steps, False, ctx)
        if root == "var" and a0 is not None:
            return self.steps(self.sym("var", a0, "variable"), steps[1:], False, ctx)
        if root == "local" and a0 is not None:
            return self.steps(self.sym("local", a0, "local"), steps[1:], False, ctx)
        if root == "module" and a0 is not None:
            if len(steps) > 1 and steps[1][0] == "a":
                return self.steps(self.sym("modout", f"{a0}.{steps[1][1]}", "module_output"), steps[2:], False, ctx)
            return self.steps(self.sym("module", a0, "module_output"), steps[1:], False, ctx)
        if root == "count" and a0 == "index":
            return self.steps(self.sym("builtin", "count.index", "count_index"), steps[1:], True, ctx)
        if root == "each" and a0 in ("key", "value"):
            return self.steps(self.sym("builtin", f"each.{a0}", "each_key"), steps[1:], False, ctx)
        if root == "path" and a0 is not None:
            return self.steps(self.sym("builtin", f"path.{a0}", "path"), steps[1:], True, ctx)
        if root == "terraform" and a0 is not None:
            cls = "workspace" if a0 == "workspace" else "unknown"
            return self.steps(self.sym("builtin", f"terraform.{a0}", cls), steps[1:], True, ctx)
        if root == "self":
            return self.steps(self.sym("builtin", "self", "resource_attribute"), steps, True, ctx)
        if root == "data" and len(steps) >= 2 and steps[0][0] == "a" and steps[1][0] == "a" \
                and RES_ROOT.match(steps[0][1]):
            return self.reference("data." + steps[0][1], steps[0][1], steps[1][1], steps[2:], ctx)
        if a0 is not None and RES_ROOT.match(root):
            return self.reference(root, root, a0, steps[1:], ctx)
        if not steps:
            return self.sym("ident", root, "unknown")
        return self.steps(self.sym("ident", root, "unknown"), steps, False, ctx)

    def reference(self, prefix: str, rtype: str, name: str, rest, ctx: str) -> dict:
        addr = f"{prefix}.{self.tab.get('res', name)}"
        rest = list(rest)
        if rest and rest[0][0] == "i":
            ix = rest[0][1]
            if ix[0] == "num" and isinstance(ix[1], int) and ix[1] >= 0:
                addr += f"[{ix[1]}]"
                rest = rest[1:]
            elif ix[0] == "str" and len(ix[1]) == 1 and ix[1][0][0] == "t" and "]" not in ix[1][0][1]:
                addr += f'["{self.tab.get("str", ix[1][0][1])}"]'
                rest = rest[1:]
        attr = []
        while rest:
            st = rest[0]
            if st[0] == "a" and SCHEMA_ATTR.match(st[1]):
                attr.append(st[1])
            elif st[0] == "i" and st[1][0] == "num" and isinstance(st[1][1], int) and st[1][1] >= 0 and attr:
                attr.append(str(st[1][1]))
            else:
                break
            rest = rest[1:]
        t = {"kind": "reference", "target_type": rtype, "target_address": addr}
        if attr:
            t["attribute"] = ".".join(attr)
        return self.steps(t, rest, True, ctx) if rest else t

    def is_dynamic_iter(self, name: str) -> bool:
        return any(fr.get(name) == "dyn" for fr in self.scope)

    def strterm(self, parts, ctx: str) -> dict:
        if all(p[0] == "t" for p in parts):
            return self.text("".join(p[1] for p in parts), ctx)
        if not any(p[0] == "d" for p in parts):
            doc = self.template_document(parts, ctx)
            if doc is not None:
                return doc
        args = []
        for p in parts:
            if p[0] == "t":
                args.append(self.text(p[1], ctx + "#frag"))
            elif p[0] == "i":
                args.append(self.term(p[1], ctx + "#interp"))
            else:
                kind = p[1]
                if kind == "if":
                    args.append(ex("hcl_tif", self.term(p[2], ctx + "#interp")))
                elif kind == "for":
                    names = [self.sym("iter", n) for n in p[3]]
                    args.append(ex("hcl_tfor", *names, self.term(p[2], ctx + "#interp")))
                    self.scope.append({n: "for" for n in p[3]})
                elif kind == "endfor":
                    if self.scope:
                        self.scope.pop()
                    args.append(ex("hcl_tendfor"))
                else:
                    args.append(ex("hcl_t" + kind))
        return ex("hcl_template", *args)

    def template_document(self, parts, ctx: str):
        """Heredoc/template cujo texto, com marcadores no lugar das interpolações, é JSON."""
        text = "".join(p[1] if p[0] == "t" else f"\ue000I{i}\ue000" for i, p in enumerate(parts))
        if not C.looks_json(text):
            return None
        try:
            tree = json.loads(text)
        except ValueError:
            return None
        if not isinstance(tree, (dict, list)):
            return None
        interps = {f"\ue000I{i}\ue000": self.term(p[1], ctx + "#interp") for i, p in enumerate(parts) if p[0] == "i"}
        return self.document(tree, "policy_json" if C.is_policy(tree) else "json", interps)

    def term(self, n, ctx: str) -> dict:  # noqa: C901
        k = n[0]
        if k == "num":
            v = n[1]
            if isinstance(v, int) and C.ACCOUNT_LIKE.match(str(abs(v))):
                return self.sym("num", str(v))
            return lit(v, "number")
        if k == "bool":
            return lit(n[1], "bool")
        if k == "null":
            return lit(None, "null")
        if k == "str":
            return self.strterm(n[1], ctx)
        if k == "tuple":
            items = [self.term(x, ctx) for x in n[1]]
            if all(is_lit(t) for t in items):
                return lit([t["value"] for t in items], "list")
            return ex("hcl_tuple", *items)
        if k == "object":
            args, all_lit, val = [], True, {}
            for key, v in n[1]:
                if key[0] == "str" and all(p[0] == "t" for p in key[1]):
                    ktext = "".join(p[1] for p in key[1])
                    kt = self.text(ktext, ctx + "#key")
                    vctx = f"{ctx}[{ktext}]"
                    reason = C.withheld_reason(ktext, "", value_is_scalar=v[0] in ("str", "num", "bool", "null"))
                    if reason and not (reason == "secret" and v[0] in ("bool", "null")):
                        vt = self.withheld(reason)
                    else:
                        vt = self.term(v, vctx)
                else:
                    kt = self.term(key, ctx + "#key")
                    vt = self.term(v, ctx + "#val")
                args += [kt, vt]
                if is_lit(kt) and isinstance(kt["value"], str) and is_lit(vt) and kt["value"] not in val:
                    val[kt["value"]] = vt["value"]
                else:
                    all_lit = False
            if all_lit:
                return lit(val, "map")
            return ex("hcl_object", *args)
        if k == "trav":
            return self.trav(n, ctx)
        if k == "call":
            name, args, expand = n[1], n[2], n[3]
            ts = [self.term(a, f"{ctx}#fn:{name}:{i}") for i, a in enumerate(args)]
            if expand and ts:
                ts[-1] = ex("hcl_expand", ts[-1])
            if OP_RX.match(name):
                return ex(name, *ts)
            return ex("hcl_provider_function", lit(name), *ts)
        if k == "bin":
            return ex(n[1], self.term(n[2], ctx), self.term(n[3], ctx))
        if k == "un":
            return ex(n[1], self.term(n[2], ctx))
        if k == "cond":
            return ex("?:", self.term(n[1], ctx), self.term(n[2], ctx), self.term(n[3], ctx))
        if k == "fort":
            _, kv, vv, coll, body, cond = n
            c = self.term(coll, ctx)
            self.scope.append({x: "for" for x in (kv, vv) if x})
            try:
                args = [self.sym("iter", kv) if kv else lit(None), self.sym("iter", vv), c, self.term(body, ctx),
                        self.term(cond, ctx) if cond is not None else lit(None)]
            finally:
                self.scope.pop()
            return ex("hcl_for_tuple", *args)
        if k == "foro":
            _, kv, vv, coll, kb, vb, group, cond = n
            c = self.term(coll, ctx)
            self.scope.append({x: "for" for x in (kv, vv) if x})
            try:
                args = [self.sym("iter", kv) if kv else lit(None), self.sym("iter", vv), c, self.term(kb, ctx),
                        self.term(vb, ctx), lit(bool(group)),
                        self.term(cond, ctx) if cond is not None else lit(None)]
            finally:
                self.scope.pop()
            return ex("hcl_for_object", *args)
        raise ValueError(f"nó desconhecido {k}")

    # -------------------------------------------------------------------------------------------- recursos
    def resource_records(self, rtype: str, body, prefix: str = "", out=None) -> list:
        """(attr_path, termo) de cada valor configurado, blocos aninhados com índice por tipo de bloco."""
        out = [] if out is None else out
        ctxbase = rtype + ":"
        for name, val in body.attrs:
            if not SCHEMA_ATTR.match(name):
                self.counts["invalid_attr_name"] = self.counts.get("invalid_attr_name", 0) + 1
                continue  # nome que nenhum schema de provider usa (ex.: com hífen): fora do C06
            path = f"{prefix}{name}"
            ctx = ctxbase + norm_ctx(path)
            if prefix == "" and name == "provider" and val[0] == "trav":
                self._log(path, ctx, "provider", val)
                out.append((path, self.provider_ref(val)))
                continue
            if prefix.startswith("lifecycle") and name in ("ignore_changes", "replace_triggered_by"):
                self._log(path, ctx, "attrlist", val)
                out.append((path, self.attr_list(val, ctx)))
                continue
            reason = C.withheld_reason(name, rtype, value_is_scalar=val[0] in ("str", "num", "bool", "null"))
            if reason and not (reason == "secret" and val[0] in ("bool", "null")):
                self._log(path, ctx, "withheld", None)
                out.append((path, self.withheld(reason)))
                continue
            self._log(path, ctx, "term", val)
            out.append((path, self.term(val, ctx)))
        seen: dict = {}
        for b in body.blocks:
            if b.type == "dynamic" and b.labels:
                label = b.labels[0]
                if not SCHEMA_ATTR.match(label):
                    self.counts["invalid_attr_name"] = self.counts.get("invalid_attr_name", 0) + 1
                    continue  # rótulo de dynamic que não é nome de bloco (ex.: vazio): fora do C06
                i = seen.get(("dyn", label), 0)
                seen[("dyn", label)] = i + 1
                p = f'{prefix}dynamic["{label}"][{i}].'
                reason = C.withheld_reason(label, rtype)
                if reason or label in C.WITHHELD_BLOCKS:
                    self._log(p + "content", "", "withheld", None)
                    out.append((p + "content", self.withheld(reason or C.WITHHELD_BLOCKS[label])))
                    continue
                it = label
                for an, av in b.body.attrs:
                    if an == "iterator" and av[0] == "trav" and not av[2] and isinstance(av[1], str):
                        it = av[1]
                attrs_wo_it = [(an, av) for an, av in b.body.attrs if an != "iterator"]
                for an, av in attrs_wo_it:
                    c2 = ctxbase + norm_ctx(f"{prefix}{label}") + "#" + an
                    self._log(p + an, c2, "term", av)
                    out.append((p + an, self.term(av, c2)))
                for an, av in b.body.attrs:
                    if an == "iterator":
                        self._log(p + "iterator", "", "iterator", av)
                        out.append((p + "iterator", self.sym("iter", it, "each_key")))
                self.scope.append({it: "dyn"})
                try:
                    for cb in b.body.blocks:
                        if cb.type == "content":
                            self.resource_records(rtype, cb.body, p + "content.", out)
                finally:
                    self.scope.pop()
                continue
            if not SCHEMA_ATTR.match(b.type):
                self.counts["invalid_attr_name"] = self.counts.get("invalid_attr_name", 0) + 1
                continue
            if b.type in C.WITHHELD_BLOCKS:
                i = seen.get(b.type, 0)
                seen[b.type] = i + 1
                self._log(f"{prefix}{b.type}[{i}]", "", "withheld", None)
                out.append((f"{prefix}{b.type}[{i}]", self.withheld(C.WITHHELD_BLOCKS[b.type])))
                continue
            reason = C.withheld_reason(b.type, rtype)
            i = seen.get(b.type, 0)
            seen[b.type] = i + 1
            if reason:
                self._log(f"{prefix}{b.type}[{i}]", "", "withheld", None)
                out.append((f"{prefix}{b.type}[{i}]", self.withheld(reason)))
                continue
            self.resource_records(rtype, b.body, f"{prefix}{b.type}[{i}].", out)
        return out

    def _log(self, path, ctx, mode, val):
        if self.ast_log is not None:
            self.ast_log.append((path, ctx, mode, val, [dict(fr) for fr in self.scope]))

    def provider_ref(self, val) -> dict:
        root, steps = val[1], val[2]
        if isinstance(root, str) and steps and steps[0][0] == "a" and len(steps) == 1:
            return ex("hcl_provider_config", lit(root), self.sym("provider_alias", steps[0][1]))
        if isinstance(root, str) and not steps:
            return ex("hcl_provider_config", lit(root))
        return self.term(val, "provider")

    def attr_list(self, val, ctx) -> dict:
        def one(n):
            if n[0] == "trav" and isinstance(n[1], str) and not self.in_scope(n[1]):
                if RES_ROOT.match(n[1]) and n[2] and n[2][0][0] == "a":
                    return self.term(n, ctx)
                t = ex("hcl_attr", lit(n[1]))
                return self.steps(t, n[2], True, ctx)
            return self.term(n, ctx)
        if val[0] == "tuple":
            return ex("hcl_tuple", *[one(x) for x in val[1]])
        return one(val)


def kt_is_schema(k: str) -> bool:
    """Chave de documento que entra no contexto como nome (estrutura comum); o resto vira '*'."""
    return bool(re.match(r"^[A-Za-z][A-Za-z0-9_:.-]{0,40}$", k))
