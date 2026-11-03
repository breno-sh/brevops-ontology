"""Plano de lowering (C26) -> HCL do provider aws, sem inserção silenciosa.

  python -I -m bo.harness.aws.render PLANO.jsonl --out DIR [--graph GRAFO.jsonl] [--schema ARQ] [--plan-id LP-x]
                                                 [--strict]

Para cada plano com target_provider = aws:
  RENDERED       todo valor do plano virou HCL e todo campo obrigatório do schema fixado está presente;
  UNKNOWN_INPUT  falta valor que o harness não pode inventar (campo obrigatório ausente, escolha sem seleção,
                 dependência fora do plano, símbolo/expressão/documento sem valor, referência sem alvo no plano).
                 O HCL sai fiel e incompleto, marcado no cabeçalho; o executor nunca o aplica;
  INVALID_PLAN   o plano cita tipo ou campo que o schema fixado não tem (nenhum HCL é escrito).
Planos de outro provedor são listados como OTHER_PROVIDER e não são renderizados. Sem nenhum plano aws, sai 2.

Saída: DIR/<plan_id>.tf (um por plano), os modelos de deploy/fixtures/aws/_templates/ e DIR/render_manifest.json
(estado, campos faltantes, origem de cada atributo renderizado e as inserções declaradas usadas).
Sai 0 quando todo plano aws recebeu um estado tipado; com --strict, sai 1 se algum não for RENDERED.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path

from . import MODULE_ID, PROVIDER, hcl, pins
from . import schema as sch

RENDER_VERSION = "1.0.0"
TEMPLATE_FILES = ("versions.tf", "providers.tf", "variables.tf")
STATUSES = ("RENDERED", "UNKNOWN_INPUT", "INVALID_PLAN")
REF_ADDR = re.compile(r"^(data\.)?([a-z][a-z0-9_]*)\.(SYM-[0-9a-f]{8,16})(\[[^\]]+\])?$")


def templates_dir() -> Path:
    return pins.repo_root() / "deploy" / "fixtures" / "aws" / "_templates"


def slug(plan_id: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", plan_id.lower()).strip("_")


def label(plan_id: str, node_id: str) -> str:
    return f"{slug(plan_id)}_{node_id}"


def sym_var(plan_id: str, symbol_id: str) -> str:
    return f"{slug(plan_id)}_sym_{symbol_id[4:]}"


def secret_var(plan_id: str, n: int) -> str:
    return f"{slug(plan_id)}_secret_{n}"


@dataclass
class PlanRender:
    plan_id: str
    graph_id: str
    status: str = "RENDERED"
    missing: list = field(default_factory=list)       # [{field, address, reason}]  -> UNKNOWN_INPUT
    problems: list = field(default_factory=list)      # [{field, address, reason}]  -> INVALID_PLAN
    provenance: list = field(default_factory=list)    # [{address, field, origin, marked, term_kind}]
    variables: list = field(default_factory=list)     # [{name, kind, symbol_id|field, sensitive}]
    unrendered: list = field(default_factory=list)    # valores do plano que não viraram HCL, com o motivo
    resources: list = field(default_factory=list)     # [{address, order, node_id, resource_type, action}]
    record: dict = field(default_factory=dict)        # info do plano: escolhas, perdas, nomes derivados
    text: str = ""

    def manifest(self) -> dict:
        d = {k: getattr(self, k) for k in ("plan_id", "graph_id", "status", "missing", "problems", "provenance",
                                           "variables", "unrendered", "resources", "record")}
        d["file"] = f"{self.plan_id}.tf" if self.text else None
        return d


class _Ctx:
    def __init__(self, plan: dict, graph: dict | None, schema: sch.ProviderSchema, pr: PlanRender):
        self.plan, self.graph, self.schema, self.pr = plan, graph, schema, pr
        self.steps = sorted(plan["steps"], key=lambda s: s["order"])
        self.by_order = {s["order"]: s for s in self.steps}
        self.secrets = 0
        self.vars_seen: dict[str, dict] = {}
        terms = {t["term_id"]: t["term"] for t in (graph or {}).get("terms", [])}
        self.symbol_owner: dict[str, list] = {}
        for s in self.steps:
            for tid in (s.get("derived_name") or {}).get("from_terms") or []:
                t = terms.get(tid)
                if t and t.get("kind") == "symbol":
                    self.symbol_owner.setdefault(t["symbol_id"], []).append(s)

    def address(self, step: dict) -> str:
        return f"{step['resource_type']}.{label(self.plan['plan_id'], step['node_id'])}"


# ------------------------------------------------------------------------------------------- termos -> HCL
class Unrenderable(Exception):
    def __init__(self, reason: str, unknown_input: bool = True):
        super().__init__(reason)
        self.reason = reason
        self.unknown_input = unknown_input


def _check_literal(t: dict):
    dt, v = t["datatype"], t["value"]
    ok = {"string": isinstance(v, str), "number": isinstance(v, (int, float)) and not isinstance(v, bool),
          "bool": isinstance(v, bool), "null": v is None, "list": isinstance(v, list),
          "map": isinstance(v, dict)}[dt]
    if not ok:
        raise Unrenderable(f"literal {dt} com valor de outro tipo ({type(v).__name__})", unknown_input=False)


def _reference(ctx: _Ctx, step: dict, fieldname: str, t: dict) -> hcl.Expr:
    m = REF_ADDR.match(t["target_address"])
    if not m:
        raise Unrenderable(f"endereço de referência fora da forma esperada: {t['target_address']}")
    if m.group(1):
        raise Unrenderable("referência a data source: o harness não lê recurso fora da execução")
    if m.group(4):
        raise Unrenderable("referência indexada (count/for_each) sem passo correspondente no plano")
    ttype, symbol = m.group(2), m.group(3)
    if ttype != t["target_type"]:
        raise Unrenderable(f"target_type {t['target_type']} difere do endereço {ttype}", unknown_input=False)
    cands = [s for s in ctx.symbol_owner.get(symbol, []) if s["resource_type"] == ttype]
    how = "símbolo do nome derivado"
    if not cands and ctx.graph is not None:
        to_nodes = {r["to"] for r in ctx.graph.get("references", []) if r["from"] == step["node_id"]}
        cands = [s for s in ctx.steps if s["node_id"] in to_nodes and s["resource_type"] == ttype]
        how = "referência do grafo"
    if len(cands) != 1:
        raise Unrenderable(f"referência a {ttype} sem alvo único no plano ({len(cands)} candidato(s))")
    tgt = cands[0]
    if tgt["order"] >= step["order"]:
        raise Unrenderable(f"referência ao passo {tgt['order']}, que não é anterior ao {step['order']}",
                           unknown_input=False)
    attr = t.get("attribute") or "id"
    tblock = ctx.schema.resource(ttype)
    if attr.split(".")[0] not in tblock.attributes:
        raise Unrenderable(f"atributo {attr} não existe em {ttype}", unknown_input=False)
    ctx.pr.record.setdefault("references", []).append(
        {"from_step": step["order"], "field": fieldname, "to_step": tgt["order"], "attribute": attr,
         "resolved_by": how})
    return hcl.Ref(f"{ttype}.{label(ctx.plan['plan_id'], tgt['node_id'])}.{attr}")


def term_expr(ctx: _Ctx, step: dict, fieldname: str, t: dict) -> hcl.Expr:
    k = t["kind"]
    if k == "literal":
        _check_literal(t)
        return hcl.from_value(t["value"])
    if k == "symbol":
        name = sym_var(ctx.plan["plan_id"], t["symbol_id"])
        if name not in ctx.vars_seen:
            ctx.vars_seen[name] = {"name": name, "kind": "symbol", "symbol_id": t["symbol_id"],
                                   "name_class": t["name_class"], "sensitive": False}
        return hcl.Ref(f"var.{name}")
    if k == "reference":
        return _reference(ctx, step, fieldname, t)
    if k == "expression":
        raise Unrenderable(f"expressão '{t['op']}' sem redução pelo lowering")
    if k == "document":
        if t["symbolized"]:
            raise Unrenderable(f"documento com {len(t['symbolized'])} símbolo(s) sem valor")
        fn = "yamlencode" if t["format"] == "yaml" else "jsonencode"
        return hcl.Call(fn, hcl.from_value(t["tree"]))
    if k == "withheld":
        if t["reason"] != "secret":
            raise Unrenderable(f"conteúdo withheld ({t['reason']}) nunca chega ao harness")
        ctx.secrets += 1
        name = secret_var(ctx.plan["plan_id"], ctx.secrets)
        ctx.vars_seen[name] = {"name": name, "kind": "secret", "field": fieldname, "sensitive": True}
        return hcl.Ref(f"var.{name}")
    raise Unrenderable(f"termo de tipo desconhecido {k}", unknown_input=False)


# ------------------------------------------------------------------------------- árvore de campos do recurso
class _Node:
    """Corpo de um recurso ou bloco aninhado: atributos (expressões ou objetos parciais) e blocos filhos."""

    def __init__(self, block: sch.Block):
        self.block = block
        self.attrs: dict[str, object] = {}       # nome -> Expr | dict (objeto montado por caminho)
        self.children: dict[str, _Node] = {}


def _place(node: _Node, path: list[str], expr: hcl.Expr, fieldname: str):
    head, rest = path[0], path[1:]
    if head in node.block.attributes:
        a = node.block.attributes[head]
        if not a.configurable:
            raise Unrenderable(f"atributo {fieldname} é só computado no schema", unknown_input=False)
        if not rest:
            if head in node.attrs:
                raise Unrenderable(f"campo {fieldname} aparece duas vezes", unknown_input=False)
            node.attrs[head] = expr
            return
        if not (isinstance(a.type, list) and a.type and a.type[0] in ("object", "map")):
            raise Unrenderable(f"caminho {fieldname} entra no atributo escalar {head}", unknown_input=False)
        cur = node.attrs.setdefault(head, {})
        if not isinstance(cur, dict):
            raise Unrenderable(f"campo {fieldname} conflita com valor inteiro de {head}", unknown_input=False)
        for seg in rest[:-1]:
            cur = cur.setdefault(seg, {})
            if not isinstance(cur, dict):
                raise Unrenderable(f"campo {fieldname} conflita com valor já posto", unknown_input=False)
        if rest[-1] in cur:
            raise Unrenderable(f"campo {fieldname} aparece duas vezes", unknown_input=False)
        cur[rest[-1]] = expr
        return
    if head in node.block.blocks:
        if not rest:
            raise Unrenderable(f"campo {fieldname} é um bloco, não um valor", unknown_input=False)
        nb = node.block.blocks[head]
        child = node.children.get(head) or _Node(nb.block)
        node.children[head] = child
        _place(child, rest, expr, fieldname)
        return
    raise Unrenderable(f"campo {fieldname} não existe no schema fixado", unknown_input=False)


def _object_required_keys(t) -> set:
    if isinstance(t, list) and len(t) >= 2 and t[0] == "object" and isinstance(t[1], dict):
        optional = set(t[2]) if len(t) > 2 and isinstance(t[2], list) else set()
        return set(t[1]) - optional
    return set()


def _attr_type(block: sch.Block, path: list[str]):
    cur = block
    for seg in path:
        if seg in cur.attributes:
            return cur.attributes[seg].type
        if seg in cur.blocks:
            cur = cur.blocks[seg].block
            continue
        return None
    return None


def _missing(node: _Node, prefix: str) -> list[str]:
    out = []
    for n, a in sorted(node.block.attributes.items()):
        if a.required and n not in node.attrs:
            out.append(prefix + n)
        v = node.attrs.get(n)
        if isinstance(v, dict):
            for k in sorted(_object_required_keys(a.type) - set(v)):
                out.append(f"{prefix}{n}.{k}")
    for n, nb in sorted(node.block.blocks.items()):
        if n in node.children:
            out.extend(_missing(node.children[n], f"{prefix}{n}."))
        elif nb.min_items >= 1:
            out.append(prefix + n)
    return out


def _to_body(node: _Node) -> list:
    body: list = []
    for n in sorted(node.attrs):
        v = node.attrs[n]
        body.append(hcl.Attribute(n, _dict_expr(v) if isinstance(v, dict) else v))
    for n in sorted(node.children):
        body.append(hcl.BlockN(n, [], _to_body(node.children[n])))
    return body


def _dict_expr(d: dict) -> hcl.Expr:
    return hcl.ObjE([(k, _dict_expr(v) if isinstance(v, dict) else v) for k, v in sorted(d.items())])


# ----------------------------------------------------------------------------------------------- um plano
def render_plan(plan: dict, graph: dict | None, schema: sch.ProviderSchema) -> PlanRender:
    pr = PlanRender(plan["plan_id"], plan["graph_id"])
    ctx = _Ctx(plan, graph, schema, pr)
    pr.record = {"target_provider": plan["target_provider"], "graph_found": graph is not None,
                 "dependency_closure": plan["dependency_closure"], "choices": [], "losses": [],
                 "derived_names": [], "symbolic_unknowns": []}
    if not plan["dependency_closure"]["closed"]:
        for m in plan["dependency_closure"]["missing"]:
            pr.missing.append({"field": None, "address": None, "reason": f"dependência fora do plano: {m}"})
    blocks = []
    for step in ctx.steps:
        addr = ctx.address(step)
        pr.resources.append({"address": addr, "order": step["order"], "node_id": step["node_id"],
                             "resource_type": step["resource_type"], "action": step["action"]})
        for ch in step["typed_choices"]:
            pr.record["choices"].append({"step": step["order"], **{k: ch[k] for k in ("choice_id", "selected",
                                                                                        "options", "reason")}})
            if ch["selected"] is None:
                pr.missing.append({"field": None, "address": addr,
                                   "reason": f"escolha {ch['choice_id']} sem seleção ({ch['reason']})"})
        pr.record["losses"] += [{"step": step["order"], **ls} for ls in step["losses"]]
        pr.record["symbolic_unknowns"] += [{"step": step["order"], **u} for u in step["symbolic_unknowns"]]
        if step.get("derived_name"):
            pr.record["derived_names"].append({"step": step["order"], **step["derived_name"]})
        if step["action"] == "reference":
            pr.missing.append({"field": None, "address": addr,
                               "reason": "passo 'reference' aponta para recurso preexistente; o harness só cria"})
            continue
        if not schema.has(step["resource_type"]):
            pr.problems.append({"field": None, "address": addr,
                                "reason": f"tipo {step['resource_type']} não existe no aws {schema.provider_version}"})
            continue
        root = _Node(schema.resource(step["resource_type"]))
        for v in step["values"]:
            f = v["field"]
            try:
                expr = term_expr(ctx, step, f, v["term"])
                _place(root, f.split("."), expr, f)
            except Unrenderable as e:
                target = pr.missing if e.unknown_input else pr.problems
                target.append({"field": f, "address": addr, "reason": e.reason})
                pr.unrendered.append({"address": addr, "field": f, "origin": v["origin"],
                                      "reason": e.reason})
                continue
            pr.provenance.append({"address": addr, "field": f, "origin": v["origin"], "marked": v["marked"],
                                  "term_kind": v["term"]["kind"]})
            if v["term"]["kind"] == "literal" and isinstance(v["term"]["value"], dict):
                for k in sorted(_object_required_keys(_attr_type(root.block, f.split("."))) -
                                set(v["term"]["value"])):
                    pr.missing.append({"field": f"{f}.{k}", "address": addr,
                                       "reason": "chave obrigatória do objeto ausente no plano"})
        for m in _missing(root, ""):
            pr.missing.append({"field": m, "address": addr,
                               "reason": "campo obrigatório no schema fixado e ausente no plano"})
        body = _to_body(root)
        deps = []
        for d in step["depends_on"]:
            tgt = ctx.by_order.get(d)
            if tgt is None:
                pr.problems.append({"field": "depends_on", "address": addr, "reason": f"passo {d} inexistente"})
                continue
            if tgt["action"] == "reference" or not schema.has(tgt["resource_type"]):
                continue
            deps.append(hcl.Ref(ctx.address(tgt)))
        if deps:
            body.append(hcl.Attribute("depends_on", hcl.ListE(deps)))
            pr.provenance.append({"address": addr, "field": "depends_on", "origin": "plan.depends_on",
                                  "marked": False, "term_kind": "meta"})
        blocks.append(hcl.BlockN("resource", [step["resource_type"], label(plan["plan_id"], step["node_id"])],
                                 body))
    pr.variables = sorted(ctx.vars_seen.values(), key=lambda x: x["name"])
    pr.status = "INVALID_PLAN" if pr.problems else ("UNKNOWN_INPUT" if pr.missing else "RENDERED")
    if pr.status == "INVALID_PLAN":
        return pr
    var_blocks = []
    for v in pr.variables:
        body = [hcl.Attribute("type", _type_expr(v)),
                hcl.Attribute("nullable", hcl.Lit(False))]
        if v["sensitive"]:
            body.append(hcl.Attribute("sensitive", hcl.Lit(True)))
        var_blocks.append(hcl.BlockN("variable", [v["name"]], body))
    header = [f"HARNESS-AWS render {RENDER_VERSION}: {plan['plan_id']} (grafo {plan['graph_id']})",
              f"BO-STATUS: {pr.status}"]
    if pr.status != "RENDERED":
        header.append("NÃO APLICÁVEL: o executor recusa este arquivo; faltam:")
        header += [f"  - {m['address'] or '(plano)'} {m['field'] or ''}: {m['reason']}".rstrip()
                   for m in pr.missing]
    pr.text = hcl.render_file(var_blocks + blocks, header)
    return pr


class _TypeExpr(hcl.Expr):
    def __init__(self, s: str):
        self.s = s

    def lines(self, indent):
        return [self.s]


def _type_expr(v: dict) -> hcl.Expr:
    return _TypeExpr("string" if v["kind"] == "secret" else "any")


# ------------------------------------------------------------------------------------------------- entrada
def read_jsonl(p: Path) -> list[dict]:
    out = []
    for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
        if line.strip():
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError as e:
                raise ValueError(f"{p}:{i}: JSON inválido ({e.msg})") from e
    return out


def validate_contract(plan_path: Path) -> list[str]:
    from bo.contracts import validate as v
    r = v.validate("lowering_plan", plan_path)
    return list(r.errors)


def check_templates(tdir: Path, pin: pins.Pin) -> list[str]:
    errs = []
    for f in TEMPLATE_FILES:
        if not (tdir / f).exists():
            errs.append(f"modelo ausente: {tdir / f}")
    if not errs:
        v = (tdir / "versions.tf").read_text(encoding="utf-8")
        if f'required_version = "= {pin.terraform_version}"' not in v:
            errs.append(f"versions.tf não fixa o Terraform {pin.terraform_version} do pins.json")
        if f'version = "= {pin.provider_version}"' not in v:
            errs.append(f"versions.tf não fixa o aws {pin.provider_version} do pins.json")
    return errs


def render_file(plan_path: Path, out: Path, graph_path: Path | None = None, schema_arg: str | None = None,
                plan_ids: list[str] | None = None, check_contract: bool = True) -> dict:
    """Renderiza um lowering_plan.jsonl em out/. Devolve o manifesto (também gravado em render_manifest.json)."""
    plan_path = Path(plan_path)
    if check_contract:
        errs = validate_contract(plan_path)
        if errs:
            raise ValueError("plano reprova no contrato C26: " + "; ".join(errs[:5]))
    plans = read_jsonl(plan_path)
    gpath = Path(graph_path) if graph_path else plan_path.with_name("graph_ir.jsonl")
    graphs = {g["graph_id"]: g for g in read_jsonl(gpath)} if gpath.exists() else {}
    schema = sch.load(schema_arg)
    pin = pins.load_pin()
    tdir = templates_dir()
    terrs = check_templates(tdir, pin)
    if terrs:
        raise ValueError("; ".join(terrs))
    out = Path(out)
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    for f in TEMPLATE_FILES:
        shutil.copyfile(tdir / f, out / f)
    entries, others = [], []
    for p in plans:
        if plan_ids and p["plan_id"] not in plan_ids:
            continue
        if p["target_provider"] != PROVIDER:
            others.append({"plan_id": p["plan_id"], "status": "OTHER_PROVIDER",
                           "target_provider": p["target_provider"]})
            continue
        pr = render_plan(p, graphs.get(p["graph_id"]), schema)
        if pr.text:
            (out / f"{pr.plan_id}.tf").write_text(pr.text, encoding="utf-8")
        entries.append(pr.manifest())
    man = {
        "schema": "bo.harness_render_manifest/1", "module": MODULE_ID, "render_version": RENDER_VERSION,
        "input": {"plan": str(plan_path), "graph": str(gpath) if gpath.exists() else None,
                  "plan_sha256": pins.sha256_file(plan_path)},
        "provider": {"source": "registry.terraform.io/hashicorp/aws", "version": schema.provider_version,
                     "schema_sha256": schema.sha256},
        "terraform_version": pin.terraform_version,
        "templates": {f: pins.sha256_file(tdir / f) for f in TEMPLATE_FILES},
        "declared_insertions": str(tdir / "DECLARED_INSERTIONS.json"),
        "counts": {s: sum(1 for e in entries if e["status"] == s) for s in STATUSES} |
                  {"OTHER_PROVIDER": len(others)},
        "plans": entries, "other_provider": others,
    }
    (out / "render_manifest.json").write_text(json.dumps(man, ensure_ascii=False, indent=1) + "\n",
                                              encoding="utf-8")
    return man


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="bo.harness.aws.render", description=__doc__.split("\n")[0])
    ap.add_argument("plan")
    ap.add_argument("--out", required=True)
    ap.add_argument("--graph")
    ap.add_argument("--schema")
    ap.add_argument("--plan-id", action="append")
    ap.add_argument("--strict", action="store_true")
    a = ap.parse_args(argv)
    plan = Path(a.plan)
    if not plan.exists():
        print(f"render: plano inexistente: {plan}", file=sys.stderr)
        return 2
    try:
        man = render_file(plan, Path(a.out), a.graph, a.schema, a.plan_id)
    except (ValueError, KeyError, pins.PinError) as e:
        print(f"render: {e}", file=sys.stderr)
        return 2
    c = man["counts"]
    print(f"render: {c['RENDERED']} RENDERED, {c['UNKNOWN_INPUT']} UNKNOWN_INPUT, {c['INVALID_PLAN']} INVALID_PLAN, "
          f"{c['OTHER_PROVIDER']} de outro provedor -> {a.out}")
    for e in man["plans"]:
        for m in e["missing"] + e["problems"]:
            print(f"  {e['plan_id']} {e['status']}: {m['address'] or ''} {m['field'] or ''}: {m['reason']}")
    if not man["plans"]:
        print("render: nenhum plano com target_provider=aws na entrada (nada renderizado)", file=sys.stderr)
        return 2
    if a.strict and any(e["status"] != "RENDERED" for e in man["plans"]):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
