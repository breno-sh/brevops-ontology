"""Termo C06 -> texto HCL, com a tabela privada (símbolo -> texto) que só existe em memória no roundtrip.

Nada daqui é gravado: serve para provar que o termo guarda a estrutura inteira (nomes voltam pelo símbolo,
expressões, CIDRs e documentos voltam com a mesma árvore). Termo retido não tem volta (WithheldTerm).
"""

from __future__ import annotations

import json
import re

PLACE = "\u0002P{}\u0002"
TPL_DIRS = ("hcl_tif", "hcl_telse", "hcl_tendif", "hcl_tfor", "hcl_tendfor")
STRING_OPS = ("hcl_template", "cidr", "ip", "arn", "arn_partial")


class WithheldTerm(Exception):
    pass


class NotText(Exception):
    pass


def esc(s: str) -> str:
    """Conteúdo de cadeia HCL entre aspas: barra, aspas, controle e marcadores de template escapados."""
    out = s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\r", "\\r") \
        .replace("\t", "\\t")
    out = out.replace("${", "$${").replace("%{", "%%{")
    return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", lambda m: "\\u%04x" % ord(m.group(0)), out)


def esc_json(s: str) -> str:
    return json.dumps(s, ensure_ascii=False)[1:-1]


class Renderer:
    ATOMIC = {"hcl_getattr", "hcl_index", "hcl_splat", "hcl_splat_full", "hcl_attr", "hcl_provider_config", "hcl_tuple", "hcl_object"} | \
        set(STRING_OPS)

    def __init__(self, reveal: dict):
        self.reveal = reveal

    def name(self, sid: str) -> tuple:
        return self.reveal[sid]

    # ------------------------------------------------------------------------------------------ texto puro
    def is_text(self, t) -> bool:
        k = t["kind"]
        if k == "literal":
            return isinstance(t["value"], str)
        if k == "symbol":
            return self.name(t["symbol_id"])[0] in ("str", "path")
        if k == "document":
            return True
        if k == "expression" and t["op"] in ("cidr", "ip"):
            return True
        if k == "expression" and t["op"] in ("arn", "arn_resource", "arn_partial", "hcl_template"):
            return all(self.is_text(x) for x in t["args"])
        return False

    def to_text(self, t) -> str:
        """Texto de um termo que veio de cadeia sem interpolação (literal, símbolo, cidr, arn, documento)."""
        k = t["kind"]
        if k == "withheld":
            raise WithheldTerm()
        if k == "literal" and isinstance(t["value"], str):
            return t["value"]
        if k == "symbol" and self.name(t["symbol_id"])[0] in ("str", "path"):
            return self.name(t["symbol_id"])[1]
        if k == "document":
            tree, places = self.doc_tree(t)
            if places:
                raise NotText()
            return json.dumps(tree, ensure_ascii=False)
        if k == "expression":
            op, a = t["op"], t["args"]
            if op == "cidr":
                return f"{self.to_text(a[0])}/{a[1]['value']}"
            if op == "ip":
                return self.to_text(a[0])
            if op == "arn":
                return "arn:" + ":".join(self.to_text(x) for x in a[:4]) + ":" + self.to_text(a[4])
            if op in ("arn_resource", "arn_partial", "hcl_template"):
                return "".join(self.to_text(x) for x in a)
        raise NotText()

    # ------------------------------------------------------------------------------------------ documentos
    def doc_tree(self, t) -> tuple:
        """Árvore revelada; termos com interpolação viram marcadores (marcador -> termo)."""
        syms: dict = {}
        for e in t["symbolized"]:  # o mesmo caminho pode ter a chave e o valor simbolizados
            syms.setdefault(e["path"], set()).add(e["symbol_id"])
        places = {}

        def walk(x, path):
            if isinstance(x, dict):
                if set(x) == {"$term"}:
                    term = x["$term"]
                    if term["kind"] == "withheld":
                        raise WithheldTerm()
                    if self.is_text(term):
                        return self.to_text(term)
                    p = PLACE.format(len(places))
                    places[p] = term
                    return p
                out = {}
                for k, v in x.items():
                    kp = path + "/" + str(k).replace("~", "~0").replace("/", "~1")
                    if isinstance(v, dict) and set(v) == {"$key", "$value"}:
                        p = PLACE.format(len(places))
                        places[p] = v["$key"]
                        out[p] = walk(v["$value"], kp + "/$value")
                        continue
                    kk = self.name(k)[1] if k in syms.get(kp, ()) and k in self.reveal else k
                    out[kk] = walk(v, kp)
                return out
            if isinstance(x, list):
                return [walk(v, f"{path}/{i}") for i, v in enumerate(x)]
            if isinstance(x, str):
                if x in syms.get(path, ()) and x in self.reveal:
                    ns, txt = self.name(x)
                    return int(txt) if ns == "num" else txt
            return x
        return walk(t["tree"], ""), places

    def tpl_in_json(self, term) -> str:
        """Conteúdo HCL que, desescapado, dá o texto JSON (com ${...}) de uma cadeia JSON com interpolação."""
        parts = term["args"] if term["kind"] == "expression" and term["op"] == "hcl_template" else [term]
        out = []
        for x in parts:
            if self.is_text(x):
                out.append(esc(esc_json(self.to_text(x))))
            else:
                out.append("${" + self.expr(x) + "}")
        return "".join(out)

    # ------------------------------------------------------------------------------------------ cadeias
    def string_term(self, t) -> str:
        if t["kind"] == "document":
            tree, places = self.doc_tree(t)
            s = esc(json.dumps(tree, ensure_ascii=False))
            for p, term in places.items():
                s = s.replace(esc(esc_json(p)), self.tpl_in_json(term))
            return '"' + s + '"'
        if t["kind"] == "expression" and t["op"] == "hcl_template":
            return '"' + "".join(self.tpl_part(x) for x in t["args"]) + '"'
        return '"' + esc(self.to_text(t)) + '"'

    def tpl_part(self, x) -> str:
        if x["kind"] == "expression" and x["op"] in TPL_DIRS:
            op, a = x["op"], x["args"]
            if op == "hcl_tif":
                return "%{ if " + self.expr(a[0]) + " }"
            if op == "hcl_tfor":
                names = ", ".join(self.name(s["symbol_id"])[1] for s in a[:-1])
                return "%{ for " + names + " in " + self.expr(a[-1]) + " }"
            return "%{ " + op[5:] + " }"
        if self.is_text(x) and not (x["kind"] == "expression" and x["op"] == "hcl_template"):
            return esc(self.to_text(x))
        return "${" + self.expr(x) + "}"

    # ------------------------------------------------------------------------------------------ expressões
    def lit(self, v) -> str:
        if isinstance(v, bool):
            return "true" if v else "false"
        if v is None:
            return "null"
        if isinstance(v, (int, float)):
            return repr(v)
        if isinstance(v, str):
            return '"' + esc(v) + '"'
        if isinstance(v, list):
            return "[" + ", ".join(self.lit(x) for x in v) + "]"
        return "{" + ", ".join(f'"{esc(k)}" = {self.lit(x)}' for k, x in v.items()) + "}"

    def ref(self, t) -> str:
        m = re.match(r"^(data\.)?([a-z][a-z0-9_]*)\.(SYM-[0-9a-f]+)(\[(.+)\])?$", t["target_address"])
        out = (m.group(1) or "") + m.group(2) + "." + self.name(m.group(3))[1]
        if m.group(4):
            ix = m.group(5)
            out += ('["' + esc(self.name(ix.strip('"'))[1]) + '"]') if ix.startswith('"') else f"[{ix}]"
        if t.get("attribute"):
            for seg in t["attribute"].split("."):
                out += f"[{seg}]" if seg.isdigit() else f".{seg}"
        return out

    def sym(self, t) -> str:
        ns, txt = self.name(t["symbol_id"])
        if ns == "var":
            return f"var.{txt}"
        if ns == "local":
            return f"local.{txt}"
        if ns in ("modout", "module"):
            return f"module.{txt}"
        if ns in ("builtin", "iter", "ident", "num"):
            return txt
        if ns == "str":
            return '"' + esc(txt) + '"'
        raise ValueError(f"símbolo do espaço {ns} fora de expressão")

    def base(self, t) -> str:
        s = self.expr(t)
        if t["kind"] == "expression" and t["op"] not in self.ATOMIC and not self._is_call(t):
            return "(" + s + ")"
        if t["kind"] == "literal" and not isinstance(t["value"], (str, list, dict)):
            return "(" + s + ")"
        return s

    @staticmethod
    def _is_call(t) -> bool:
        return bool(re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", t["op"])) and not t["op"].startswith("hcl_") and \
            t["op"] not in ("cidr", "ip", "arn", "arn_resource", "arn_partial")

    def expr(self, t) -> str:  # noqa: C901
        k = t["kind"]
        if k == "withheld":
            raise WithheldTerm()
        if k == "literal":
            return self.lit(t["value"])
        if k == "symbol":
            return self.sym(t)
        if k == "reference":
            return self.ref(t)
        if k == "document":
            return self.string_term(t)
        op, a = t["op"], t["args"]
        if op in STRING_OPS:
            return self.string_term(t)
        if op == "hcl_getattr":
            f = a[1]
            name = f["value"] if f["kind"] == "literal" else self.name(f["symbol_id"])[1]
            return self.base(a[0]) + "." + name
        if op == "hcl_index":
            return self.base(a[0]) + "[" + self.expr(a[1]) + "]"
        if op == "hcl_splat":
            return self.base(a[0]) + ".*"
        if op == "hcl_splat_full":
            return self.base(a[0]) + "[*]"
        if op == "hcl_attr":
            return a[0]["value"]
        if op == "hcl_provider_config":
            return a[0]["value"] + ("." + self.name(a[1]["symbol_id"])[1] if len(a) > 1 else "")
        if op == "hcl_tuple":
            return "[" + ", ".join(self.expr(x) for x in a) + "]"
        if op == "hcl_object":
            items = []
            for i in range(0, len(a), 2):
                kt, vt = a[i], a[i + 1]
                if self.is_text(kt) and kt["kind"] in ("literal", "symbol"):
                    ks = '"' + esc(self.to_text(kt)) + '"'
                elif kt["kind"] == "document" or (kt["kind"] == "expression" and kt["op"] in STRING_OPS):
                    ks = self.string_term(kt)
                else:
                    ks = "(" + self.expr(kt) + ")"
                items.append(f"{ks} = {self.expr(vt)}")
            return "{" + ", ".join(items) + "}"
        if op == "?:":
            return f"({self.expr(a[0])} ? {self.expr(a[1])} : {self.expr(a[2])})"
        if op in ("!", "-") and len(a) == 1:
            return f"{op}({self.expr(a[0])})"
        if len(a) == 2 and re.match(r"^[-+*/%<>=!&|]{1,2}$", op):
            return f"({self.expr(a[0])} {op} {self.expr(a[1])})"
        if op in ("hcl_for_tuple", "hcl_for_object"):
            kv, vv, coll = a[0], a[1], a[2]
            names = (self.name(kv["symbol_id"])[1] + ", " if kv["kind"] == "symbol" else "") + \
                self.name(vv["symbol_id"])[1]
            cond = a[-1]
            c = "" if (cond["kind"] == "literal" and cond["value"] is None) else f" if {self.expr(cond)}"
            if op == "hcl_for_tuple":
                return f"[for {names} in {self.expr(coll)} : {self.expr(a[3])}{c}]"
            g = "..." if a[5]["value"] else ""
            return f"{{for {names} in {self.expr(coll)} : {self.expr(a[3])} => {self.expr(a[4])}{g}{c}}}"
        if op == "hcl_provider_function":
            return a[0]["value"] + "(" + ", ".join(self.expr(x) for x in a[1:]) + ")"
        if op == "hcl_expand":
            return self.expr(a[0]) + "..."
        return op + "(" + ", ".join(self.expr(x) for x in a) + ")"
