"""Templates das sondas: deploy/probes/{tipo}/{provedor}/_templates/ = main.tf + side_case.tf + side_control.tf.

O lado (caso ou controle negativo) entra só pelo arquivo de lado, que define locals; o resto é idêntico. Para
conferir offline (sem terraform plan, sem credencial), este módulo:
  - lê o HCL com python-hcl2 e avalia o subconjunto de expressões que os templates usam (var, local, count.index,
    iterador de dynamic, lookup, substr, sha1, replace, lower, upper, tostring, condicional, template de string);
    expressão fora do subconjunto é recusada (fail-closed); referência a outro recurso vira valor desconhecido,
    como no plano de verdade;
  - monta um plano sintético no formato de `terraform show -json` (resource_changes, provider_config) para o
    plan_guard do SAFETY (bo.safety.plan_check), que dá os achados e o custo;
  - confere cada recurso contra o schema do provider fixado (tfschema): atributo e bloco existem, obrigatório
    presente, nada só-computado configurado;
  - confere que caso e controle só diferem nos atributos que realizam a sonda (SERVICE-EVIDENCE).
"""

from __future__ import annotations

import hashlib
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

import hcl2

from .common import ProbeError, deploy_dir

SIDES = ("case", "control")
SIDE_FILE = {"case": "side_case.tf", "control": "side_control.tf"}
TEMPLATE_FILES = ("main.tf", "side_case.tf", "side_control.tf")
META = {"count", "for_each", "depends_on", "lifecycle", "provider", "provisioner", "connection"}
PROVIDER_SOURCE = {"aws": "registry.terraform.io/hashicorp/aws", "google": "registry.terraform.io/hashicorp/google",
                   "azurerm": "registry.terraform.io/hashicorp/azurerm", "oci": "registry.terraform.io/oracle/oci"}


class Unknown:
    _inst = None

    def __new__(cls):
        if cls._inst is None:
            cls._inst = super().__new__(cls)
        return cls._inst

    def __repr__(self):
        return "<unknown>"


UNKNOWN = Unknown()


class ExprError(ProbeError):
    def __init__(self, msg):
        super().__init__(msg, "TEMPLATE_EXPR")


def template_dir(cell: str) -> Path:
    t, p = cell.split("/")
    return deploy_dir() / t / p / "_templates"


def has_template(cell: str) -> bool:
    d = template_dir(cell)
    return all((d / f).is_file() for f in TEMPLATE_FILES)


# =============================================================================================== expressões
TOK = re.compile(r"\s*(?:(?P<num>\d+(?:\.\d+)?)|(?P<id>[A-Za-z_][A-Za-z0-9_\-]*)|(?P<p>[()\[\],.?:{}])|(?P<q>\"))")


def _scan_string(s: str, i: int) -> int:
    """s[i] == '"'; devolve o índice depois da aspa que fecha (respeita escape e ${...} aninhado)."""
    j = i + 1
    while j < len(s):
        c = s[j]
        if c == "\\":
            j += 2
            continue
        if c == "$" and s[j:j + 2] == "${":
            j = _scan_interp(s, j + 2)
            continue
        if c == '"':
            return j + 1
        j += 1
    raise ExprError("string sem aspa de fechamento")


def _scan_interp(s: str, j: int) -> int:
    """j logo depois de '${'; devolve o índice depois da '}' que fecha."""
    depth = 1
    while j < len(s):
        c = s[j]
        if c == '"':
            j = _scan_string(s, j)
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return j + 1
        j += 1
    raise ExprError("interpolação sem '}'")


def tokenize(s: str) -> list[tuple[str, str]]:
    out, i = [], 0
    while i < len(s):
        if s[i].isspace():
            i += 1
            continue
        if s[i] == '"':
            j = _scan_string(s, i)
            out.append(("str", s[i + 1:j - 1]))
            i = j
            continue
        m = TOK.match(s, i)
        if not m or m.end() == i:
            raise ExprError(f"caractere fora do subconjunto: {s[i]!r}")
        kind = m.lastgroup
        out.append((kind, m.group(kind)))
        i = m.end()
    return out


FUNCS = {
    "lookup": lambda m, k, d: (m.get(k, d) if isinstance(m, dict) else UNKNOWN),
    "substr": lambda s, o, n: s[int(o):int(o) + int(n)],
    "sha1": lambda s: hashlib.sha1(s.encode()).hexdigest(),
    "replace": lambda s, a, b: s.replace(a, b),
    "lower": lambda s: s.lower(),
    "upper": lambda s: s.upper(),
    "tostring": lambda x: str(x).lower() if isinstance(x, bool) else str(x),
}


class Scope:
    def __init__(self, vars_: dict, locals_: dict | None = None, iters: dict | None = None, count_index=None):
        self.vars, self.iters, self.count_index = vars_, iters or {}, count_index
        self.locals = locals_ if locals_ is not None else {}

    def child(self, **kw):
        s = Scope(self.vars, self.locals, dict(self.iters), self.count_index)
        for k, v in kw.items():
            if k == "iters":
                s.iters.update(v)
            else:
                setattr(s, k, v)
        return s


class Parser:
    def __init__(self, toks, scope: Scope):
        self.t, self.i, self.sc = toks, 0, scope

    def peek(self, v=None):
        if self.i >= len(self.t):
            return None
        tok = self.t[self.i]
        return tok if v is None or tok[1] == v else None

    def take(self, v=None):
        tok = self.peek(v)
        if tok is None:
            raise ExprError(f"esperado {v!r}" if v else "expressão incompleta")
        self.i += 1
        return tok

    def parse(self):
        v = self.cond()
        if self.i != len(self.t):
            raise ExprError(f"sobra na expressão: {self.t[self.i][1]!r}")
        return v

    def cond(self):
        c = self.primary()
        if self.peek("?"):
            self.take("?")
            a = self.cond()
            self.take(":")
            b = self.cond()
            if c is UNKNOWN:
                return UNKNOWN
            if not isinstance(c, bool):
                raise ExprError("condição não booleana")
            return a if c else b
        return c

    def primary(self):
        kind, val = self.take()
        if kind == "num":
            return float(val) if "." in val else int(val)
        if kind == "str":
            return interpolate(val, self.sc)
        if kind == "p" and val == "(":
            v = self.cond()
            self.take(")")
            return v
        if kind == "p" and val == "[":
            items = []
            while not self.peek("]"):
                items.append(self.cond())
                if not self.peek("]"):
                    self.take(",")
            self.take("]")
            return items
        if kind == "id":
            if val in ("true", "false"):
                return val == "true"
            if val == "null":
                return None
            if self.peek("("):
                return self.call(val)
            return self.ref(val)
        raise ExprError(f"token inesperado {val!r}")

    def call(self, name):
        if name not in FUNCS:
            raise ExprError(f"função fora do subconjunto: {name}")
        self.take("(")
        args = []
        while not self.peek(")"):
            args.append(self.cond())
            if not self.peek(")"):
                self.take(",")
        self.take(")")
        if any(a is UNKNOWN for a in args):
            return UNKNOWN
        try:
            return FUNCS[name](*args)
        except (TypeError, ValueError, AttributeError) as e:
            raise ExprError(f"{name}: {e}") from None

    def ref(self, head):
        parts = [head]
        while True:
            if self.peek("."):
                self.take(".")
                parts.append(self.take()[1])
            elif self.peek("["):
                self.take("[")
                parts.append(self.cond())
                self.take("]")
            else:
                break
        return resolve(parts, self.sc)


def resolve(parts, sc: Scope):
    head = parts[0]
    if head == "var":
        if parts[1] not in sc.vars:
            raise ExprError(f"variável sem valor: var.{parts[1]}")
        v = sc.vars[parts[1]]
        return _index(v, parts[2:])
    if head == "local":
        if parts[1] not in sc.locals:
            raise ExprError(f"local indefinido: local.{parts[1]}")
        return _index(sc.locals[parts[1]], parts[2:])
    if head == "count":
        if sc.count_index is None or parts[1:] != ["index"]:
            raise ExprError("count.index fora de recurso com count")
        return sc.count_index
    if head in sc.iters:
        if parts[1:2] == ["value"]:
            return _index(sc.iters[head], parts[2:])
        raise ExprError(f"iterador {head} sem .value")
    return UNKNOWN  # data.*, recurso.* e afins: conhecidos só depois do apply


def _index(v, rest):
    for p in rest:
        if v is UNKNOWN:
            return UNKNOWN
        if isinstance(v, dict) and p in v:
            v = v[p]
        elif isinstance(v, list) and isinstance(p, int) and p < len(v):
            v = v[p]
        else:
            raise ExprError(f"índice {p!r} inexistente")
    return v


def interpolate(content: str, sc: Scope):
    """Corpo de string HCL (sem as aspas): escapes e ${...}. Uma interpolação sozinha devolve o valor cru."""
    parts, i, buf = [], 0, []
    while i < len(content):
        c = content[i]
        if c == "\\" and i + 1 < len(content):
            buf.append({"n": "\n", "t": "\t", '"': '"', "\\": "\\"}.get(content[i + 1], content[i + 1]))
            i += 2
            continue
        if content.startswith("${", i):
            j = _scan_interp(content, i + 2)
            if buf:
                parts.append("".join(buf))
                buf = []
            parts.append(("expr", eval_expr(content[i + 2:j - 1], sc)))
            i = j
            continue
        buf.append(c)
        i += 1
    if buf:
        parts.append("".join(buf))
    if len(parts) == 1 and isinstance(parts[0], tuple):
        return parts[0][1]
    out = []
    for p in parts:
        if isinstance(p, tuple):
            if p[1] is UNKNOWN:
                return UNKNOWN
            out.append(str(p[1]).lower() if isinstance(p[1], bool) else str(p[1]))
        else:
            out.append(p)
    return "".join(out)


def eval_expr(src: str, sc: Scope):
    return Parser(tokenize(src), sc).parse()


def eval_value(v, sc: Scope):
    if v is None or isinstance(v, (bool, int, float)):
        return v
    if isinstance(v, str):
        s = v.strip()
        if s.startswith('"') and s.endswith('"') and _scan_string(s, 0) == len(s):
            return interpolate(s[1:-1], sc)
        if s.startswith("${") and _scan_interp(s, 2) == len(s):
            return eval_expr(s[2:-1], sc)
        return eval_expr(s, sc)
    if isinstance(v, list):
        return [eval_value(x, sc) for x in v]
    if isinstance(v, dict):
        return {unq(k): eval_value(x, sc) for k, x in v.items() if k != "__is_block__"}
    raise ExprError(f"valor HCL inesperado: {type(v).__name__}")


def unq(k: str) -> str:
    return k[1:-1] if len(k) >= 2 and k[0] == '"' and k[-1] == '"' else k


# =============================================================================================== documento
@dataclass
class Instance:
    address: str
    type: str
    name: str
    index: int | None
    config: dict        # atributos e blocos já avaliados (blocos = lista de dicts)
    raw_keys: dict      # mesma árvore com os nomes configurados (para o schema)


def _is_block(v) -> bool:
    return isinstance(v, list) and v and all(isinstance(x, dict) and x.get("__is_block__") for x in v)


def load_doc(d: Path, side: str) -> dict:
    if side not in SIDES:
        raise ProbeError(f"lado inválido: {side}", "SIDE")
    merged: dict = {}
    for f in ("main.tf", SIDE_FILE[side]):
        doc = hcl2.load(open(Path(d) / f, encoding="utf-8"))
        for k, v in doc.items():
            merged.setdefault(k, []).extend(v)
    return merged


def eval_block(body: dict, sc: Scope) -> dict:
    """Corpo de bloco (atributos e blocos aninhados, com dynamic expandido) avaliado."""
    out: dict = {}
    for k, v in body.items():
        if k == "__is_block__" or k in META:
            continue
        if k == "dynamic":
            for dyn in v:
                for label, spec in dyn.items():
                    name = unq(label)
                    fe = eval_value(spec["for_each"], sc)
                    if fe is UNKNOWN:
                        raise ExprError(f"dynamic {name} com for_each desconhecido no plano")
                    contents = spec.get("content") or [{}]
                    for item in (fe if isinstance(fe, list) else list(fe.values())):
                        out.setdefault(name, []).append(eval_block(contents[0], sc.child(iters={name: item})))
            continue
        if _is_block(v):
            out[k] = [eval_block(b, sc) for b in v]
        else:
            out[k] = eval_value(v, sc)
    return out


def instances(doc: dict, vars_: dict) -> tuple[list[Instance], dict, Scope]:
    locals_: dict = {}
    sc = Scope(vars_, locals_)
    for blk in doc.get("locals", []):
        for k, v in blk.items():
            if k != "__is_block__":
                if k in locals_:
                    raise ExprError(f"local duplicado: {k}")
                locals_[k] = eval_value(v, sc)
    out = []
    for blk in doc.get("resource", []):
        for tlabel, named in blk.items():
            rtype = unq(tlabel)
            for nlabel, body in named.items():
                name = unq(nlabel)
                count = eval_value(body["count"], sc) if "count" in body else None
                if count is UNKNOWN or (count is not None and not isinstance(count, int)):
                    raise ExprError(f"{rtype}.{name}: count desconhecido ou não inteiro")
                idxs = [None] if count is None else list(range(count))
                for i in idxs:
                    isc = sc.child(count_index=i)
                    addr = f"{rtype}.{name}" + (f"[{i}]" if i is not None else "")
                    out.append(Instance(addr, rtype, name, i, eval_block(body, isc), body))
    providers = {}
    for blk in doc.get("provider", []):
        for label, body in blk.items():
            providers[unq(label)] = body
    return out, providers, sc


def _split_unknown(v):
    """(after, after_unknown) como no plano JSON do Terraform."""
    if v is UNKNOWN:
        return None, True
    if isinstance(v, dict):
        a, u = {}, {}
        for k, x in v.items():
            ax, ux = _split_unknown(x)
            if ux is True:
                u[k] = True
            else:
                a[k] = ax
                if ux:
                    u[k] = ux
        return a, u
    if isinstance(v, list):
        pairs = [_split_unknown(x) for x in v]
        unk = [p[1] or False for p in pairs]
        return [p[0] for p in pairs], (unk if any(unk) else False)
    return v, False


def _provider_expr(body: dict, sc: Scope) -> dict:
    ex = {}
    for k, v in body.items():
        if k == "__is_block__":
            continue
        if _is_block(v):
            ex[k] = [_provider_expr(b, sc) for b in v]
            continue
        if isinstance(v, str) and ("var." in v or "local." in v):
            refs = sorted(set(re.findall(r"\b(var\.[A-Za-z0-9_]+|local\.[A-Za-z0-9_]+)", v)))
            ex[k] = {"references": refs}
        else:
            ex[k] = {"constant_value": eval_value(v, sc)}
    return ex


def synthetic_plan(cell: str, side: str, vars_: dict, tdir: Path | None = None) -> tuple[dict, list[Instance]]:
    """Plano no formato de `terraform show -json` com só o que o plan_guard lê. Nunca vai para o disco."""
    provider = cell.split("/")[1]
    doc = load_doc(tdir or template_dir(cell), side)
    insts, providers, sc = instances(doc, vars_)
    rcs = []
    for it in insts:
        after, unk = _split_unknown(it.config)
        rc = {"address": it.address, "mode": "managed", "type": it.type, "name": it.name,
              "provider_name": PROVIDER_SOURCE[provider],
              "change": {"actions": ["create"], "after": after, "after_unknown": unk or {}}}
        if it.index is not None:
            rc["index"] = it.index
        rcs.append(rc)
    pc = {name: {"name": name, "full_name": PROVIDER_SOURCE.get(name, name), "expressions": _provider_expr(body, sc)}
          for name, body in providers.items()}
    backend = [t for t in doc.get("terraform", []) if "backend" in t or "cloud" in t]
    if backend:
        raise ProbeError(f"{cell}: backend/cloud no template", "TEMPLATE")
    return {"format_version": "1.2", "resource_changes": rcs, "configuration": {"provider_config": pc}}, insts


def synthetic_vars(cell: str, run_tag: str, names: dict, region: str, runner_inputs=()) -> dict:
    v = {"bo_region": region, "bo_run_id": run_tag, "bo_names": dict(names)}
    for k in runner_inputs:
        v[k] = UNKNOWN  # entregue pelo runner pelo ambiente; sensível; nunca avaliado nem gravado
    return v


# =============================================================================================== schema
def schema_findings(insts: list[Instance], schema_of) -> list[str]:
    """schema_of(tipo) -> bloco do schema fixado (ou None). Confere atributos, blocos e obrigatórios."""
    out = []
    for it in insts:
        blk = schema_of(it.type)
        if blk is None:
            out.append(f"{it.address}: tipo fora do schema fixado")
            continue
        out += _check_block(it.address, it.config, blk)
    return out


def _check_block(where: str, cfg: dict, blk: dict) -> list[str]:
    out = []
    attrs, btypes = blk.get("attributes") or {}, blk.get("block_types") or {}
    for k, v in cfg.items():
        if k in attrs:
            a = attrs[k]
            if a.get("computed") and not a.get("optional") and not a.get("required"):
                out.append(f"{where}.{k}: atributo só computado configurado")
        elif k in btypes:
            bt = btypes[k]
            items = v if isinstance(v, list) else [v]
            mx = bt.get("max_items")
            if mx and len(items) > mx:
                out.append(f"{where}.{k}: {len(items)} blocos (máximo {mx})")
            for n, b in enumerate(items):
                if not isinstance(b, dict):
                    out.append(f"{where}.{k}: bloco esperado")
                    continue
                out += _check_block(f"{where}.{k}[{n}]", b, bt.get("block") or {})
        else:
            out.append(f"{where}.{k}: atributo ou bloco inexistente no schema fixado")
    for k, a in attrs.items():
        if a.get("required") and k not in cfg:
            out.append(f"{where}.{k}: obrigatório ausente")
    for k, bt in btypes.items():
        mn = bt.get("min_items") or 0
        if mn and len(cfg.get(k) or []) < mn:
            out.append(f"{where}.{k}: exige ao menos {mn} bloco(s)")
    return out


# =============================================================================================== diferenças
def flatten(v, prefix="") -> dict:
    out = {}
    if isinstance(v, dict):
        for k, x in v.items():
            out.update(flatten(x, f"{prefix}.{k}" if prefix else k))
    elif isinstance(v, list) and v and all(isinstance(x, dict) for x in v):
        for i, x in enumerate(v):
            out.update(flatten(x, f"{prefix}.{i}"))
        if not v:
            out[prefix] = []
    else:
        out[prefix] = repr(v)
    return out


def strip_index(path: str) -> str:
    return ".".join(p for p in path.split(".") if not p.isdigit())


def side_diff(case: list[Instance], control: list[Instance]) -> dict:
    """Endereços só num lado e caminhos com valor diferente nos endereços comuns."""
    a = {i.address: i for i in case}
    b = {i.address: i for i in control}
    diff = {"only_case": sorted(set(a) - set(b)), "only_control": sorted(set(b) - set(a)), "changed": []}
    for addr in sorted(set(a) & set(b)):
        fa, fb = flatten(a[addr].config), flatten(b[addr].config)
        for p in sorted(set(fa) | set(fb)):
            if fa.get(p) != fb.get(p):
                diff["changed"].append((addr, a[addr].type, p))
    return diff


def diff_findings(diff: dict, se_type: str, se_attrs: list[str], types_of: dict) -> list[str]:
    """Caso e controle só podem diferir no tipo e nos atributos que realizam a sonda."""
    roots = {a.split(".")[0] for a in se_attrs}
    out = []
    for addr in diff["only_control"]:
        out.append(f"{addr}: recurso só no controle")
    for addr in diff["only_case"]:
        if types_of.get(addr) != se_type:
            out.append(f"{addr}: recurso só no caso e não é do tipo da sonda ({se_type})")
    for addr, rtype, path in diff["changed"]:
        if rtype != se_type or strip_index(path).split(".")[0] not in roots:
            out.append(f"{addr}.{path}: caso e controle diferem fora dos atributos da sonda")
    if not (diff["only_case"] or diff["changed"]):
        out.append("caso e controle idênticos: o controle negativo não desliga nada")
    return out


def has_attr_path(cfg: dict, path: str) -> bool:
    cur = [cfg]
    for part in path.split("."):
        nxt = []
        for c in cur:
            if isinstance(c, dict) and part in c:
                v = c[part]
                nxt += v if isinstance(v, list) and v and all(isinstance(x, dict) for x in v) else [v]
        if not nxt:
            return False
        cur = nxt
    return True


def get_path(cfg: dict, path: str):
    cur = cfg
    for part in path.split("."):
        if isinstance(cur, list):
            cur = cur[int(part)] if part.isdigit() and int(part) < len(cur) else None
        elif isinstance(cur, dict):
            cur = cur.get(part)
        else:
            return None
    return cur


def render_run_dir(cell: str, side: str, out_dir: Path) -> Path:
    """Diretório de trabalho de um lado (o tf_dir do SafeRun): main.tf + o arquivo de lado como side.tf."""
    src = template_dir(cell)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src / "main.tf", out / "main.tf")
    shutil.copy2(src / SIDE_FILE[side], out / "side.tf")
    return out
