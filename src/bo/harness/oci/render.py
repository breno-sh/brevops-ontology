"""Renderizador de HCL do OCI a partir de um plano de lowering (C26), sem inserção silenciosa.

  python -I -m bo.harness.oci.render PLANO.jsonl --out DIR [--graph-ir GIR.jsonl] [--bindings B.json]
                                     [--plan-id LP-x ...]

Entrada: um arquivo C26:lowering_plan (validado pelo validador único antes de qualquer coisa); o graph_ir irmão
(graph_ir.jsonl na mesma pasta, como no C26) quando existe; um arquivo de bindings opcional que liga symbol_id a
chaves de contexto da execução (deploy/fixtures/oci/_templates/context_bindings.json).

Saída em DIR (só dentro de $BO_TMP ou da pasta de moldes do módulo):
  main.tf               raiz: bloco terraform (versões fixadas), provider oci, variáveis da raiz e um module por plano
                        renderizado
  <plano>/main.tf       um módulo por plano RENDERED: required_providers, variáveis e um resource/data por passo
  render_report.json    situação de cada plano (RENDERED | UNKNOWN_INPUT | INVALID_PLAN | NOT_APPLICABLE), problemas
                        com código, a origem de cada atributo escrito e os sha256 dos arquivos

O que vira HCL, e só isso: cada valor do passo (carried, synthesized ou default_declared, como o plano marca) no
caminho que ele declara. Campo obrigatório do schema do oci fixado que o plano não traz, escolha sem seleção,
símbolo sem binding, referência sem alvo no plano, segredo carried e fecho de dependências aberto: o plano sai
UNKNOWN_INPUT e nenhum HCL dele é escrito. Plano para outro provedor: NOT_APPLICABLE.

Saída 0 quando a entrada confere com o C26 e todo plano recebeu situação; 2 para entrada inválida ou uso errado.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import MODULE_ID, PROVIDER, PROVIDER_VERSION, SCHEMA_SHA256, SCHEMA_TABLE, hcl, templates_dir, tmp_root
from . import schema as S

TZ = timezone(timedelta(hours=-3))
REPORT_NAME = "render_report.json"
REPORT_SCHEMA = "bo.harness.oci.render_report/1"

UNKNOWN_CODES = {"MISSING_REQUIRED_FIELD", "MISSING_REQUIRED_BLOCK", "UNRESOLVED_CHOICE", "UNKNOWN_SYMBOLIC_INPUT",
                 "WITHHELD_NOT_AVAILABLE", "OPEN_DEPENDENCY_CLOSURE", "REFERENCE_UNRESOLVED", "NO_GRAPH_IR"}
INVALID_CODES = {"RESOURCE_TYPE_NOT_IN_PIN", "FIELD_NOT_IN_SCHEMA", "FIELD_NOT_CONFIGURABLE", "PATH_ENDS_AT_BLOCK",
                 "INDEX_NOT_ALLOWED", "KEY_NOT_ALLOWED", "TYPE_MISMATCH", "TERM_DATATYPE_MISMATCH",
                 "DUPLICATE_FIELD", "MIXED_INDEXING", "INDEX_GAP", "MAX_ITEMS_EXCEEDED", "AMBIGUOUS_TARGET",
                 "REFERENCE_NOT_IN_DEPENDS_ON", "UNSUPPORTED_TERM", "UNKNOWN_BINDING_KEY"}
STATUS = ("RENDERED", "UNKNOWN_INPUT", "INVALID_PLAN", "NOT_APPLICABLE")

# expressões do C00 que o renderizador sabe escrever: operadores do HCL e funções puras do Terraform
BINARY_OPS = {"+", "-", "*", "/", "%", "==", "!=", "<", ">", "<=", ">=", "&&", "||"}
UNARY_OPS = {"!", "-"}
FUNCTIONS = {"format", "join", "lower", "upper", "cidrsubnet", "cidrhost", "tostring", "tonumber", "tobool",
             "tolist", "toset", "concat", "merge", "jsonencode", "min", "max"}
ADDR = re.compile(r"^(data\.)?([a-z][a-z0-9_]*)\.(SYM-[0-9a-f]{8,16})(\[[^\]]+\])?$")


def now_iso() -> str:
    return datetime.now(TZ).replace(microsecond=0).isoformat()


def sha256_file(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


# ------------------------------------------------------------------------------------------- moldes
@dataclass
class Templates:
    root: dict
    bindings: dict      # chave -> definição

    @classmethod
    def load(cls, d: Path | None = None) -> "Templates":
        d = d or templates_dir()
        root = json.loads((d / "root_template.json").read_text(encoding="utf-8"))
        b = json.loads((d / "context_bindings.json").read_text(encoding="utf-8"))
        return cls(root, {x["key"]: x for x in b["bindings"]})

    def binding_var(self, key: str) -> str:
        return self.root["variable_prefixes"]["binding"] + key

    def withheld_var(self, label: str, field_path: str) -> str:
        return self.root["variable_prefixes"]["withheld"] + label + "_" + field_path.replace(".", "_")


# ------------------------------------------------------------------------------------------- estruturas
@dataclass
class Issue:
    code: str
    order: int | None
    node_id: str | None
    field: str | None
    detail: str

    @property
    def cls(self) -> str:
        return "invalid" if self.code in INVALID_CODES else "unknown"

    def as_dict(self) -> dict:
        return {"code": self.code, "class": self.cls, "order": self.order, "node_id": self.node_id,
                "field": self.field, "detail": self.detail}


class TermError(Exception):
    def __init__(self, code: str, detail: str):
        super().__init__(detail)
        self.code = code
        self.detail = detail


@dataclass
class Var:
    name: str
    type: str
    sensitive: bool
    source: str        # binding:<chave> | withheld:<motivo>


@dataclass
class Written:
    """Um atributo escrito no HCL e de onde ele veio (para o relatório e o no_silent_insert)."""
    label: str
    resource_type: str
    kind: str              # resource | data
    field: str             # caminho do C26
    hcl_path: str          # caminho com ocorrências: a[0].b.c
    origin: str            # carried | synthesized | default_declared | derived_name
    marked: bool
    term_kind: str
    expr: str
    source: str            # plan | binding:<chave> | withheld:<motivo> | derived_name
    node_id: str = ""
    derived_value: str | None = None   # só para origin derived_name: o nome já montado do template


@dataclass
class PlanRender:
    plan_id: str
    graph_id: str
    target_provider: str
    status: str = "RENDERED"
    module: str | None = None
    issues: list = field(default_factory=list)
    written: list = field(default_factory=list)
    variables: dict = field(default_factory=dict)     # nome -> Var
    blocks: list = field(default_factory=list)        # hcl.Block por passo
    labels: dict = field(default_factory=dict)        # order -> label
    notes: list = field(default_factory=list)
    losses: list = field(default_factory=list)
    choices: list = field(default_factory=list)

    def report(self) -> dict:
        return {
            "plan_id": self.plan_id, "graph_id": self.graph_id, "target_provider": self.target_provider,
            "status": self.status, "module": self.module,
            "issues": [i.as_dict() for i in self.issues],
            "labels": {str(k): v for k, v in sorted(self.labels.items())},
            "written": [w.__dict__ for w in self.written],
            "variables": [v.__dict__ for v in sorted(self.variables.values(), key=lambda v: v.name)],
            "losses": self.losses, "choices": self.choices, "notes": self.notes,
        }


def module_name(plan_id: str) -> str:
    return re.sub(r"[^a-z0-9_]", "_", plan_id.lower())


# ------------------------------------------------------------------------------------------- tipos
def check_type(v, typ, where: str) -> None:
    """Confere um literal JSON contra um tipo cty do schema. Nada é convertido: diferença é TYPE_MISMATCH."""
    if v is None or typ == "dynamic":
        return
    bad = TermError("TYPE_MISMATCH", f"{where}: valor {type(v).__name__} não é {json.dumps(typ)}")
    if typ == "string":
        if not isinstance(v, str):
            raise bad
    elif typ == "number":
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            raise bad
    elif typ == "bool":
        if not isinstance(v, bool):
            raise bad
    elif isinstance(typ, list) and typ[0] in ("list", "set"):
        if not isinstance(v, list):
            raise bad
        for k, x in enumerate(v):
            check_type(x, typ[1], f"{where}[{k}]")
    elif isinstance(typ, list) and typ[0] == "map":
        if not isinstance(v, dict):
            raise bad
        for k, x in v.items():
            check_type(x, typ[1], f"{where}.{k}")
    elif isinstance(typ, list) and typ[0] == "object":
        if not isinstance(v, dict):
            raise bad
        names = dict((n, t) for n, t in typ[1])
        extra = sorted(set(v) - set(names))
        if extra:
            raise TermError("TYPE_MISMATCH", f"{where}: chaves fora do objeto: {extra}")
        missing = sorted(set(names) - set(v))
        if missing:
            raise TermError("MISSING_REQUIRED_FIELD", f"{where}: objeto sem {missing}")
        for k, x in v.items():
            check_type(x, names[k], f"{where}.{k}")
    elif isinstance(typ, list) and typ[0] == "tuple":
        if not isinstance(v, list) or len(v) != len(typ[1]):
            raise bad
        for k, (x, t) in enumerate(zip(v, typ[1])):
            check_type(x, t, f"{where}[{k}]")
    else:
        raise TermError("TYPE_MISMATCH", f"{where}: tipo do schema não reconhecido {json.dumps(typ)}")


def check_datatype(term: dict, where: str) -> None:
    dt, v = term["datatype"], term["value"]
    ok = {"string": isinstance(v, str), "number": isinstance(v, (int, float)) and not isinstance(v, bool),
          "bool": isinstance(v, bool), "null": v is None, "list": isinstance(v, list),
          "map": isinstance(v, dict)}[dt]
    if not ok:
        raise TermError("TERM_DATATYPE_MISMATCH", f"{where}: datatype {dt} com valor {type(v).__name__}")


# ------------------------------------------------------------------------------------------- contexto do plano
class PlanCtx:
    def __init__(self, plan: dict, graph: dict | None, bindings: dict, tpl: Templates, table: S.SchemaTable):
        self.plan, self.graph, self.bindings, self.tpl, self.table = plan, graph, bindings, tpl, table
        self.steps = {s["order"]: s for s in plan["steps"]}
        self.terms = {t["term_id"]: t["term"] for t in (graph or {}).get("terms", [])}
        count: dict = {}
        for s in plan["steps"]:
            count[s["node_id"]] = count.get(s["node_id"], 0) + 1
        self.labels = {s["order"]: (s["node_id"] if count[s["node_id"]] == 1 else f"{s['node_id']}_s{s['order']}")
                       for s in plan["steps"]}

    @staticmethod
    def kind_of(step: dict) -> str:
        return "data" if step["action"] == "reference" else "resource"

    def step_symbols(self, step: dict) -> set:
        out = set()
        for tid in (step.get("derived_name") or {}).get("from_terms", []):
            t = self.terms.get(tid)
            if t and t.get("kind") == "symbol":
                out.add(t["symbol_id"])
        return out

    def ancestors(self, order: int) -> set:
        """Passos de que o passo depende, direta ou indiretamente (C26-TARGET)."""
        seen, todo = set(), list(self.steps[order]["depends_on"])
        while todo:
            o = todo.pop()
            if o in seen or o not in self.steps:
                continue
            seen.add(o)
            todo += self.steps[o]["depends_on"]
        return seen

    def resolve_reference(self, step: dict, term: dict) -> str:
        m = ADDR.match(term["target_address"])
        if not m:
            raise TermError("UNSUPPORTED_TERM", f"endereço de referência fora da forma tipo.SYM: {term['target_address']}")
        is_data, rtype, sym, idx = bool(m.group(1)), m.group(2), m.group(3), m.group(4)
        if idx:
            raise TermError("UNSUPPORTED_TERM", "referência com índice (count/for_each) não é renderizada")
        if rtype != term["target_type"]:
            raise TermError("UNSUPPORTED_TERM", f"target_type {term['target_type']} difere do endereço {rtype}")
        if term.get("target_node"):
            # C00 3.0.1: a referência pode citar o nó do grafo direto
            cands = [o for o, s in self.steps.items() if s["node_id"] == term["target_node"]
                     and s["resource_type"] == rtype and (self.kind_of(s) == "data") == is_data]
        else:
            if self.graph is None:
                raise TermError("NO_GRAPH_IR", "referência por símbolo sem o graph_ir irmão para resolver o nó")
            cands = [o for o, s in self.steps.items() if s["resource_type"] == rtype
                     and (self.kind_of(s) == "data") == is_data and sym in self.step_symbols(s)]
        cands = [o for o in cands if o != step["order"]]
        if not cands:
            raise TermError("REFERENCE_UNRESOLVED",
                            f"nenhum passo do plano cria {rtype} com o nó ou símbolo do endereço (alvo fora do plano)")
        if len(cands) > 1:
            raise TermError("AMBIGUOUS_TARGET", f"{len(cands)} passos casam com {term['target_address']}")
        tgt = self.steps[cands[0]]
        if tgt["order"] not in self.ancestors(step["order"]):
            raise TermError("REFERENCE_NOT_IN_DEPENDS_ON",
                            f"passo {step['order']} referencia o passo {tgt['order']} sem depender dele")
        attr = term.get("attribute")
        if not attr:
            raise TermError("REFERENCE_UNRESOLVED", "referência sem atributo: o renderizador não escolhe um (ex. id)")
        tblock = self.table.block(self.kind_of(tgt), rtype)
        first = attr.split(".")[0]
        if first not in tblock.attrs and first not in tblock.blocks:
            raise TermError("FIELD_NOT_IN_SCHEMA", f"atributo {attr} não existe em {rtype}")
        parts = (["data"] if is_data else []) + [rtype, self.labels[tgt["order"]]] + attr.split(".")
        return hcl.traversal(*parts)


# ------------------------------------------------------------------------------------------- termos -> expressão
def term_expr(ctx: PlanCtx, step: dict, value: dict, typ, where: str, pr: PlanRender, label: str) -> tuple[str, str]:
    """Devolve (expressão HCL, fonte). Fonte: plan | binding:<chave> | withheld:<motivo>."""
    term = value["term"]
    return _term(ctx, step, value, term, typ, where, pr, label, top=True)


def _term(ctx, step, value, term, typ, where, pr, label, top=False):
    k = term["kind"]
    if k == "literal":
        check_datatype(term, where)
        if typ is not None:
            check_type(term["value"], typ, where)
        return hcl.literal(term["value"]), "plan"
    if k == "reference":
        return ctx.resolve_reference(step, term), "plan"
    if k == "symbol":
        sym = term["symbol_id"]
        unknown = {u["term_id"] for u in step["symbolic_unknowns"]}
        ref_terms = {tid for tid, t in ctx.terms.items() if t.get("kind") == "symbol" and t.get("symbol_id") == sym}
        key = ctx.bindings.get(sym)
        if key is None:
            why = "listado em symbolic_unknowns" if ref_terms & unknown else "sem binding de contexto"
            raise TermError("UNKNOWN_SYMBOLIC_INPUT", f"{where}: símbolo {sym} ({term['name_class']}) {why}")
        if key not in ctx.tpl.bindings:
            raise TermError("UNKNOWN_BINDING_KEY", f"{where}: chave de binding {key!r} fora de context_bindings.json")
        if typ is not None and ctx.tpl.bindings[key]["type"] != typ:
            raise TermError("TYPE_MISMATCH", f"{where}: binding {key} é {ctx.tpl.bindings[key]['type']}, campo é {typ}")
        name = ctx.tpl.binding_var(key)
        pr.variables[name] = Var(name, ctx.tpl.bindings[key]["type"], False, f"binding:{key}")
        return hcl.traversal("var", name), f"binding:{key}"
    if k == "withheld":
        if value["origin"] == "carried" or not top:
            raise TermError("WITHHELD_NOT_AVAILABLE",
                            f"{where}: valor retido na origem ({term['reason']}) não existe para transportar")
        name = ctx.tpl.withheld_var(label, value["field"])
        if not hcl.IDENT.match(name):
            raise TermError("UNSUPPORTED_TERM", f"{where}: nome de variável inválido para o valor retido")
        pr.variables[name] = Var(name, "string" if typ in (None, "string") else json.dumps(typ), True,
                                 f"withheld:{term['reason']}")
        return hcl.traversal("var", name), f"withheld:{term['reason']}"
    if k == "document":
        if term["symbolized"]:
            raise TermError("UNKNOWN_SYMBOLIC_INPUT", f"{where}: documento com {len(term['symbolized'])} símbolo(s)")
        if typ not in (None, "string"):
            raise TermError("TYPE_MISMATCH", f"{where}: documento vira texto, campo é {json.dumps(typ)}")
        fn = "yamlencode" if term["format"] == "yaml" else "jsonencode"
        return f"{fn}({hcl.literal(term['tree'])})", "plan"
    if k == "expression":
        op, args = term["op"], term["args"]
        rendered, sources = [], set()
        for a in args:
            e, src = _term(ctx, step, value, a, None, where, pr, label)
            rendered.append(e)
            sources.add(src)
        if op in BINARY_OPS and len(args) == 2:
            expr = f"({rendered[0]} {op} {rendered[1]})"
        elif op in UNARY_OPS and len(args) == 1:
            expr = f"{op}{rendered[0]}"
        elif op in FUNCTIONS:
            expr = f"{op}({', '.join(rendered)})"
        else:
            raise TermError("UNSUPPORTED_TERM", f"{where}: operação {op!r} com {len(args)} argumento(s) fora da lista")
        src = "plan" if sources <= {"plan"} else "+".join(sorted(sources))
        return expr, src
    raise TermError("UNSUPPORTED_TERM", f"{where}: termo {k!r}")


def derived_value(ctx: PlanCtx, step: dict, dn: dict) -> dict:
    """derived_name com field (C26 1.1.0) vira um valor literal do passo, origem 'derived_name', marcado.

    Cada {tN} do template é trocado pelo termo tN do graph_ir: literal entra como texto; qualquer outro termo
    (símbolo, referência) é desconhecido -> UNKNOWN_SYMBOLIC_INPUT. Nada é inventado para preencher o nome.
    """
    out = dn["template"]
    for tid in dn["from_terms"]:
        t = ctx.terms.get(tid)
        if t is None:
            raise TermError("NO_GRAPH_IR", f"derived_name cita {tid} sem graph_ir com esse termo")
        if t["kind"] != "literal" or not isinstance(t["value"], (str, int)) or isinstance(t["value"], bool):
            raise TermError("UNKNOWN_SYMBOLIC_INPUT",
                            f"derived_name: termo {tid} ({t['kind']}) só existe depois da criação ou não é texto")
        out = out.replace("{" + tid + "}", str(t["value"]))
    if "{" in out or "}" in out:
        raise TermError("UNKNOWN_SYMBOLIC_INPUT", "derived_name com marcador sem termo em from_terms")
    return {"field": dn["field"], "term": {"kind": "literal", "datatype": "string", "value": out},
            "origin": "derived_name", "marked": True}


# ------------------------------------------------------------------------------------------- árvore do passo
@dataclass
class Node:
    """Corpo de um bloco em construção: atributos (nome -> folha ou dict de chaves) e blocos (nome -> {i: Node})."""
    attrs: dict = field(default_factory=dict)
    blocks: dict = field(default_factory=dict)
    explicit: dict = field(default_factory=dict)   # nome do bloco -> {True/False}: usou índice explícito?


@dataclass
class Leaf:
    expr: str
    written: Written


def _insert(node: Node, toks: tuple, leaf: Leaf, field_path: str, segs_explicit: list[bool]) -> None:
    t = toks[0]
    if t.kind == "block":
        node.explicit.setdefault(t.name, set()).add(segs_explicit[0])
        child = node.blocks.setdefault(t.name, {}).setdefault(t.index, Node())
        _insert(child, toks[1:], leaf, field_path, segs_explicit[1:])
        return
    # atributo, talvez com chaves
    keys = [x.name for x in toks[1:]]
    if not keys:
        if t.name in node.attrs:
            raise TermError("DUPLICATE_FIELD", f"{field_path}: campo dado mais de uma vez")
        node.attrs[t.name] = leaf
        return
    cur = node.attrs.setdefault(t.name, {})
    if isinstance(cur, Leaf):
        raise TermError("DUPLICATE_FIELD", f"{field_path}: '{t.name}' dado inteiro e por chave")
    for k in keys[:-1]:
        cur = cur.setdefault(k, {})
        if isinstance(cur, Leaf):
            raise TermError("DUPLICATE_FIELD", f"{field_path}: chave '{k}' dada inteira e por subchave")
    if keys[-1] in cur:
        raise TermError("DUPLICATE_FIELD", f"{field_path}: chave dada mais de uma vez")
    cur[keys[-1]] = leaf


def _explicit_flags(toks: tuple, field_path: str) -> list[bool]:
    """Para cada token de bloco, se o caminho trouxe índice explícito."""
    segs = field_path.split(".")
    flags, i = [], 0
    for t in toks:
        if t.kind == "block":
            i += 1
            explicit = i < len(segs) and segs[i].isdigit()
            if explicit:
                i += 1
            flags.append(explicit)
        else:
            break
    return flags


def _map_expr(d: dict) -> str:
    parts = []
    for k in sorted(d):
        v = d[k]
        parts.append(f"{hcl.string(k)} = {v.expr if isinstance(v, Leaf) else _map_expr(v)}")
    return "{ " + ", ".join(parts) + " }" if parts else "{}"


def _check_required(node: Node, block: S.Block, where: str, issues: list, step: dict) -> None:
    for name, a in block.attrs.items():
        if a.required and name not in node.attrs:
            issues.append(Issue("MISSING_REQUIRED_FIELD", step["order"], step["node_id"], f"{where}{name}",
                                f"obrigatório no schema do oci {PROVIDER_VERSION} e ausente do plano"))
        v = node.attrs.get(name)
        if isinstance(v, dict) and isinstance(a.type, list) and a.type[0] == "object":
            missing = sorted(set(n for n, _ in a.type[1]) - set(v))
            if missing:
                issues.append(Issue("MISSING_REQUIRED_FIELD", step["order"], step["node_id"], f"{where}{name}",
                                    f"objeto sem as chaves {missing}"))
    for name, bt in block.blocks.items():
        occ = node.blocks.get(name, {})
        n = len(occ)
        if n < bt.min_items:
            issues.append(Issue("MISSING_REQUIRED_BLOCK", step["order"], step["node_id"], f"{where}{name}",
                                f"bloco exige pelo menos {bt.min_items} ocorrência(s); o plano traz {n}"))
        if bt.max_items and n > bt.max_items:
            issues.append(Issue("MAX_ITEMS_EXCEEDED", step["order"], step["node_id"], f"{where}{name}",
                                f"bloco aceita até {bt.max_items}; o plano traz {n}"))
        if occ and sorted(occ) != list(range(n)):
            issues.append(Issue("INDEX_GAP", step["order"], step["node_id"], f"{where}{name}",
                                f"ocorrências {sorted(occ)} não são 0..{n - 1}"))
        if len(node.explicit.get(name, set())) > 1:
            issues.append(Issue("MIXED_INDEXING", step["order"], step["node_id"], f"{where}{name}",
                                "caminhos com e sem índice de ocorrência no mesmo bloco"))
        for i in sorted(occ):
            _check_required(occ[i], bt.block, f"{where}{name}.{i}." if bt.repeatable else f"{where}{name}.",
                            issues, step)


def _emit(node: Node, hb: hcl.Block) -> None:
    for name in sorted(node.attrs):
        v = node.attrs[name]
        hb.attr(name, v.expr if isinstance(v, Leaf) else _map_expr(v))
    for name in sorted(node.blocks):
        for i in sorted(node.blocks[name]):
            _emit(node.blocks[name][i], hb.block(hcl.Block(name)))


def _hcl_path(toks: tuple) -> str:
    out = []
    for t in toks:
        if t.kind == "block":
            out.append(f"{t.name}[{t.index}]")
        else:
            out.append(t.name)
    return ".".join(out)


# ------------------------------------------------------------------------------------------- plano
def render_plan(plan: dict, graph: dict | None, bindings: dict, tpl: Templates,
                table: S.SchemaTable | None = None) -> PlanRender:
    table = table or S.table()
    pr = PlanRender(plan["plan_id"], plan["graph_id"], plan["target_provider"])
    if plan["target_provider"] != PROVIDER:
        pr.status = "NOT_APPLICABLE"
        pr.notes.append(f"plano para {plan['target_provider']}; o harness do {PROVIDER} não renderiza outro provedor")
        return pr
    ctx = PlanCtx(plan, graph, bindings, tpl, table)
    pr.labels = dict(ctx.labels)
    dc = plan["dependency_closure"]
    if not dc["closed"]:
        pr.issues.append(Issue("OPEN_DEPENDENCY_CLOSURE", None, None, None,
                               f"fecho de dependências aberto; faltam {len(dc['missing'])} item(ns)"))
    for step in sorted(plan["steps"], key=lambda s: s["order"]):
        label = ctx.labels[step["order"]]
        kind = ctx.kind_of(step)
        rtype = step["resource_type"]
        for ch in step["typed_choices"]:
            pr.choices.append({"order": step["order"], "choice_id": ch["choice_id"], "selected": ch["selected"],
                               "reason": ch["reason"]})
            if ch["selected"] is None:
                pr.issues.append(Issue("UNRESOLVED_CHOICE", step["order"], step["node_id"], None,
                                       f"escolha {ch['choice_id']} sem seleção: {ch['reason']}"))
        for loss in step["losses"]:
            pr.losses.append({"order": step["order"], **loss})
        dn = step.get("derived_name")
        if dn and not dn.get("field"):
            pr.notes.append(f"passo {step['order']}: derived_name sem field (C26 1.1.0) não vai para o HCL")
        if not table.has(kind, rtype):
            pr.issues.append(Issue("RESOURCE_TYPE_NOT_IN_PIN", step["order"], step["node_id"], None,
                                   f"{kind} {rtype} não existe no oci {PROVIDER_VERSION}"))
            continue
        block = table.block(kind, rtype)
        root = Node()
        values = list(step["values"])
        if dn and dn.get("field"):
            try:
                values.append(derived_value(ctx, step, dn))
            except TermError as e:
                pr.issues.append(Issue(e.code, step["order"], step["node_id"], dn["field"], e.detail))
        for v in values:
            fpath = v["field"]
            try:
                toks, attr = S.resolve(block, fpath)
            except S.PathError as e:
                pr.issues.append(Issue(e.code, step["order"], step["node_id"], fpath, str(e)))
                continue
            typ = S.leaf_type(attr, toks)
            t = v["term"]
            if attr.required and len(toks) and toks[-1].kind == "attr" and t["kind"] == "literal" \
                    and t["value"] is None:
                # null num obrigatório é ausência: o Terraform recusaria, e o renderizador não troca por default
                pr.issues.append(Issue("MISSING_REQUIRED_FIELD", step["order"], step["node_id"], fpath,
                                       "obrigatório com valor nulo no plano"))
                continue
            try:
                expr, source = term_expr(ctx, step, v, typ, f"passo {step['order']} {fpath}", pr, label)
                derived = v["origin"] == "derived_name"
                w = Written(label, rtype, kind, fpath, _hcl_path(toks), v["origin"], v["marked"],
                            v["term"]["kind"], expr, "derived_name" if derived else source, step["node_id"],
                            v["term"]["value"] if derived else None)
                _insert(root, toks, Leaf(expr, w), fpath, _explicit_flags(toks, fpath))
            except TermError as e:
                pr.issues.append(Issue(e.code, step["order"], step["node_id"], fpath, e.detail))
                continue
            except hcl.HclError as e:
                pr.issues.append(Issue("UNSUPPORTED_TERM", step["order"], step["node_id"], fpath, str(e)))
                continue
            pr.written.append(w)
            if attr.deprecated:
                pr.notes.append(f"passo {step['order']}: {fpath} está marcado deprecated no schema")
        failed = {(i.order, i.field) for i in pr.issues}
        req: list = []
        _check_required(root, block, "", req, step)
        # campo que já falhou por outro motivo (símbolo sem binding, tipo) não é contado de novo como ausente
        pr.issues += [i for i in req if not (i.code == "MISSING_REQUIRED_FIELD" and (i.order, i.field) in failed)]
        hb = hcl.Block(kind, [rtype, label])
        _emit(root, hb)
        pr.blocks.append(hb)
    if any(i.cls == "invalid" for i in pr.issues):
        pr.status = "INVALID_PLAN"
    elif pr.issues:
        pr.status = "UNKNOWN_INPUT"
    if pr.status != "RENDERED":
        pr.blocks, pr.variables = [], {}
    else:
        pr.module = module_name(pr.plan_id)
    return pr


# ------------------------------------------------------------------------------------------- arquivos
def _required_providers(tpl: Templates) -> hcl.Block:
    rp = hcl.Block("required_providers")
    p = tpl.root["required_providers"][PROVIDER]
    rp.attr(PROVIDER, "{ " + f"source = {hcl.string(p['source'])}, version = {hcl.string(p['version'])}" + " }")
    return rp


def _variable(v: Var) -> hcl.Block:
    b = hcl.Block("variable", [v.name])
    b.attr("type", v.type if v.type in ("string", "number", "bool") else "any")
    if v.sensitive:
        b.attr("sensitive", "true")
    return b


def module_files(pr: PlanRender, tpl: Templates) -> dict[str, str]:
    tf = hcl.Block("terraform")
    tf.block(_required_providers(tpl))
    blocks = [tf] + [_variable(v) for v in sorted(pr.variables.values(), key=lambda v: v.name)] + pr.blocks
    head = [f"{MODULE_ID}: plano {pr.plan_id} (grafo {pr.graph_id}), oci {PROVIDER_VERSION}.",
            "Gerado por bo.harness.oci.render; cada atributo vem do plano (ver render_report.json)."]
    return {f"{pr.module}/main.tf": hcl.write_file(blocks, head)}


def root_file(renders: list[PlanRender], tpl: Templates) -> str:
    r = tpl.root
    tf = hcl.Block("terraform")
    tf.attr("required_version", hcl.string(r["terraform"]["required_version"]))
    tf.block(_required_providers(tpl))
    blocks = [tf]
    done = [p for p in renders if p.status == "RENDERED"]
    if done:
        prov = hcl.Block("provider", [r["provider"]["name"]])
        for attr, var in r["provider"]["attributes"].items():
            prov.attr(attr, hcl.traversal("var", var))
        blocks.append(prov)
        allv = {v["name"]: Var(v["name"], v["type"], v["sensitive"], "root") for v in r["root_variables"]}
        for p in done:
            for v in p.variables.values():
                allv.setdefault(v.name, v)
        blocks += [_variable(v) for v in sorted(allv.values(), key=lambda v: v.name)]
        for p in done:
            m = hcl.Block("module", [p.module])
            m.attr("source", hcl.string(f"./{p.module}"))
            for name in sorted(p.variables):
                m.attr(name, hcl.traversal("var", name))
            blocks.append(m)
    head = [f"{MODULE_ID}: raiz renderizada; {len(done)} de {len(renders)} plano(s) renderizado(s).",
            "Situação de cada plano em render_report.json."]
    return hcl.write_file(blocks, head)


def _allowed_out(out: Path) -> bool:
    out = out.resolve()
    roots = [tmp_root().resolve(), templates_dir().resolve()]
    if str(out).startswith(("/tmp/", "/private/tmp/")) or str(out) in ("/tmp", "/private/tmp"):
        return False
    return any(out == r or r in out.parents for r in roots)


def _prepare_out(out: Path) -> None:
    if out.exists():
        entries = list(out.iterdir())
        if entries and not (out / REPORT_NAME).exists():
            raise SystemExit(f"render: {out} não está vazio e não é saída anterior do render; nada é apagado")
        for e in entries:
            if e.is_dir():
                shutil.rmtree(e)
            else:
                e.unlink()
    out.mkdir(parents=True, exist_ok=True)


# ------------------------------------------------------------------------------------------- entrada
def load_jsonl(p: Path) -> list[dict]:
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]


def validate_input(plan_path: Path, graph_path: Path | None) -> list[str]:
    from bo.contracts import validate as V
    errs = []
    r = V.validate("lowering_plan", plan_path)
    errs += [f"{plan_path.name}: {e}" for e in r.errors]
    if graph_path is not None:
        g = V.validate("graph_ir", graph_path)
        errs += [f"{graph_path.name}: {e}" for e in g.errors]
    return errs


def load_bindings(p: Path | None) -> dict:
    if p is None:
        return {}
    d = json.loads(p.read_text(encoding="utf-8"))
    if d.get("schema") != "bo.harness.oci.bindings/1":
        raise SystemExit(f"render: {p} não é bo.harness.oci.bindings/1")
    out = {}
    for b in d["bindings"]:
        if not re.match(r"^SYM-[0-9a-f]{8,16}$", b["symbol_id"]):
            raise SystemExit(f"render: symbol_id inválido em {p.name}")
        if b["symbol_id"] in out:
            raise SystemExit(f"render: {b['symbol_id']} ligado duas vezes em {p.name}")
        out[b["symbol_id"]] = b["key"]
    return out


@dataclass
class RenderResult:
    renders: list
    report: dict
    out: Path


def render(plan_path: Path, out: Path, graph_path: Path | None = None, bindings_path: Path | None = None,
           plan_ids: list[str] | None = None, templates: Templates | None = None) -> RenderResult:
    plan_path = Path(plan_path)
    if graph_path is None and (plan_path.parent / "graph_ir.jsonl").exists():
        graph_path = plan_path.parent / "graph_ir.jsonl"
    if bindings_path is None and (plan_path.parent / "bindings.json").exists():
        bindings_path = plan_path.parent / "bindings.json"     # irmão explícito, como o graph_ir do C26
    errs = validate_input(plan_path, graph_path)
    if errs:
        raise ValueError("entrada fora do C26: " + "; ".join(errs[:5]))
    if not _allowed_out(out):
        raise ValueError(f"saída {out} fora de $BO_TMP e da pasta de moldes do módulo")
    tpl = templates or Templates.load()
    plans = load_jsonl(plan_path)
    if plan_ids:
        missing = sorted(set(plan_ids) - {p["plan_id"] for p in plans})
        if missing:
            raise ValueError(f"plan_id ausente do arquivo: {missing}")
        plans = [p for p in plans if p["plan_id"] in plan_ids]
    graphs = {g["graph_id"]: g for g in load_jsonl(graph_path)} if graph_path else {}
    bindings = load_bindings(bindings_path)
    renders = [render_plan(p, graphs.get(p["graph_id"]), bindings, tpl) for p in plans]
    _prepare_out(out)
    files = {"main.tf": root_file(renders, tpl)}
    for pr in renders:
        if pr.status == "RENDERED":
            files.update(module_files(pr, tpl))
    for rel, text in files.items():
        p = out / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    tdir = templates_dir()
    report = {
        "schema": REPORT_SCHEMA, "module": MODULE_ID, "generated_at": now_iso(),
        "provider": PROVIDER, "provider_version": PROVIDER_VERSION, "schema_sha256": SCHEMA_SHA256,
        "schema_table_sha256": sha256_file(SCHEMA_TABLE),
        "templates_sha256": {n: sha256_file(tdir / n) for n in ("root_template.json", "context_bindings.json")},
        "bindings": {"file": bindings_path.name if bindings_path else None,
                     "synthetic": bool(bindings_path and json.loads(bindings_path.read_text(encoding="utf-8"))
                                       .get("synthetic") is True),
                     "used_keys": sorted({w.source.split(":", 1)[1] for p in renders for w in p.written
                                          if w.source.startswith("binding:")}),
                     "values_written": False},
        "input": {"plan_sha256": sha256_file(plan_path),
                  "graph_ir_sha256": sha256_file(graph_path) if graph_path else None,
                  "bindings_sha256": sha256_file(bindings_path) if bindings_path else None},
        "counts": {s: sum(1 for p in renders if p.status == s) for s in STATUS},
        "plans": [p.report() for p in renders],
        "files": {rel: hashlib.sha256(t.encode()).hexdigest() for rel, t in sorted(files.items())},
    }
    (out / REPORT_NAME).write_text(json.dumps(report, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
                                   encoding="utf-8")
    return RenderResult(renders, report, out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="bo.harness.oci.render", description=__doc__.splitlines()[0])
    ap.add_argument("plan", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--graph-ir", type=Path)
    ap.add_argument("--bindings", type=Path)
    ap.add_argument("--plan-id", action="append")
    a = ap.parse_args(argv)
    if not a.plan.exists():
        print(f"render: plano não existe: {a.plan}", file=sys.stderr)
        return 2
    try:
        res = render(a.plan, a.out, a.graph_ir, a.bindings, a.plan_id)
    except ValueError as e:
        print(f"render: {e}", file=sys.stderr)
        return 2
    c = res.report["counts"]
    print(f"[{now_iso()}] render {a.plan.name}: " + ", ".join(f"{k} {v}" for k, v in c.items()) + f" -> {a.out}")
    for p in res.renders:
        codes = sorted({i.code for i in p.issues})
        print(f"  {p.plan_id} ({p.target_provider}): {p.status}" + (f" {codes}" if codes else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
