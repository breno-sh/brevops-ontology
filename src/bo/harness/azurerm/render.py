"""Renderizador de HCL azurerm a partir de um plano de lowering (C26), sem inserção silenciosa.

  python -I -m bo.harness.azurerm.render PLANO.jsonl --out DIR [--graph-ir G.jsonl] [--plan-id LP-x]
                                         [--templates DIR] [--ownership-tag bo-k=v ...]

Regra central: o HCL é o plano mais o que está declarado. Entra no HCL só
  (1) cada valor do plano (values[].field = term), com a forma do bloco tirada do schema fixado;
  (2) o nome derivado do plano (derived_name -> atributo `name`, que precisa existir no tipo);
  (3) depends_on igual ao do plano;
  (4) declarações de variável para entradas declaradas: símbolo de nome derivado (o executor liga a um nome
      sintético da execução) e segredo withheld (gerado na hora pelo executor, nunca gravado);
  (5) o versions.tf dos templates (terraform/provider fixados, declarados em TEMPLATES.json);
  (6) tags de propriedade, só quando o executor pede (--ownership-tag), declaradas uma a uma.
Nada mais: o renderizador não completa campo. Campo obrigatório do schema que o plano não traz bloqueia o caso
com UNKNOWN_INPUT; símbolo sem valor em posição de valor, UNKNOWN_SYMBOLIC_INPUT; escolha tipada sem seleção ou
referência ambígua, AMBIGUOUS_TARGET (códigos de bloqueio do C00). Plano que contradiz o schema é INVALID_PLAN.
Caso bloqueado ou inválido não gera HCL.

Saída: com um único plano azurerm, DIR é o módulo raiz (versions.tf, main.tf, render_manifest.json); com vários,
DIR/<plan_id>/. DIR/render_report.json lista todos os planos lidos e o estado de cada um.
Saídas: 0 = ao menos um plano renderizado; 2 = erro de entrada; 4 = nenhum plano azurerm; 5 = nenhum renderizado.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path

from . import hclwrite as H
from . import schema as S
from ._common import (MODULE, PROVIDER, HarnessError, dumps, now, portable, read_jsonl, sha256_bytes,
                      templates_dir)

BLOCK_CODES = {"UNKNOWN_INPUT", "UNKNOWN_SYMBOLIC_INPUT", "AMBIGUOUS_TARGET", "OUT_OF_SUBSET"}
INVALID_CODES = {"TYPE_NOT_IN_SCHEMA", "FIELD_NOT_IN_SCHEMA", "FIELD_NOT_CONFIGURABLE", "DUPLICATE_FIELD",
                 "NAME_FIELD_ABSENT", "NAME_CONFLICT", "TERM_DATATYPE", "TOO_MANY_BLOCKS", "BAD_EXPRESSION",
                 "BAD_TEMPLATE", "BLOCK_VALUE_SHAPE", "GRAPH_MISSING"}
REPORT_SCHEMA = "bo.harness_azurerm.render_report/1"
MANIFEST_SCHEMA = "bo.harness_azurerm.render_manifest/1"
TAG_KEY = re.compile(r"^bo-[a-z\-]+$")
TAG_VAL = re.compile(r"^[A-Za-z0-9_.:\-]{1,63}$")
PY_TYPES = {"string": (str,), "number": (int, float), "bool": (bool,), "null": (type(None),), "list": (list,),
            "map": (dict,)}


@dataclass
class Issue:
    code: str
    order: int | None
    field: str | None
    detail: str

    def as_dict(self) -> dict:
        return {"code": self.code, "order": self.order, "field": self.field, "detail": self.detail}


@dataclass
class Rendered:
    plan_id: str
    graph_id: str
    case_id: str | None
    target_provider: str
    status: str = "RENDERED"
    issues: list = field(default_factory=list)
    main_tf: str | None = None
    manifest: dict | None = None


# ------------------------------------------------------------------------------------------------ termos
class Ctx:
    def __init__(self, plan: dict, graph: dict | None, sch: S.Schema):
        self.plan = plan
        self.graph = graph
        self.terms = {t["term_id"]: t["term"] for t in (graph or {}).get("terms", [])}
        self.sch = sch
        self.issues: list[Issue] = []
        self.inputs: dict[str, dict] = {}
        self.entries: list[dict] = []
        self.by_order = {s["order"]: s for s in plan["steps"]}
        self.labels = _labels(plan["steps"])

    def issue(self, code, order, fld, detail):
        self.issues.append(Issue(code, order, fld, detail))

    def address(self, step: dict) -> str:
        kind = "data" if step["action"] == "reference" else "resource"
        a = f"{step['resource_type']}.{self.labels[step['order']]}"
        return "data." + a if kind == "data" else a


def _labels(steps: list[dict]) -> dict[int, str]:
    seen, out = {}, {}
    for s in sorted(steps, key=lambda s: s["order"]):
        key = (s["action"] == "reference", s["resource_type"], s["node_id"])
        out[s["order"]] = s["node_id"] if key not in seen else f"{s['node_id']}_{s['order']}"
        seen[key] = True
    return out


def sym_var(symbol_id: str) -> str:
    return "sym_" + symbol_id.split("-", 1)[1].lower()


def term_expr(ctx: Ctx, step: dict, fld: str, term: dict, kinds: list):
    """Termo do plano -> expressão HCL. `kinds` recebe a classe de origem de cada pedaço (para o manifesto)."""
    k = term["kind"]
    o = step["order"]
    if k == "literal":
        dt, v = term["datatype"], term["value"]
        if not isinstance(v, PY_TYPES[dt]) or (dt == "number" and isinstance(v, bool)):
            ctx.issue("TERM_DATATYPE", o, fld, f"literal declarado {dt} com valor {type(v).__name__}")
            return None
        kinds.append("literal")
        return H.Lit(v)
    if k == "symbol":
        ctx.issue("UNKNOWN_SYMBOLIC_INPUT", o, fld,
                  f"símbolo {term['symbol_id']} ({term['name_class']}) sem valor no plano")
        return None
    if k == "reference":
        return ref_expr(ctx, step, fld, term, kinds)
    if k == "withheld":
        if term["reason"] != "secret":
            ctx.issue("UNKNOWN_INPUT", o, fld, f"conteúdo withheld ({term['reason']}) não é reproduzível")
            return None
        var = f"secret_{ctx.labels[o]}_{fld.replace('.', '_')}"
        ctx.inputs.setdefault(var, {"variable": var, "kind": "secret_at_run", "sensitive": True,
                                    "steps": [], "field": fld})["steps"].append(o)
        kinds.append("secret_at_run")
        return H.Ref("var." + var)
    if k == "expression":
        op, args = term["op"], term["args"]
        xs = [term_expr(ctx, step, fld, a, kinds) for a in args]
        if any(x is None for x in xs):
            return None
        kinds.append("expression")
        if re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", op):
            return H.Call(op, tuple(xs))
        if len(xs) == 2:
            return H.BinOp(op, xs[0], xs[1])
        if len(xs) == 1 and op in ("-", "!"):
            return H.UnOp(op, xs[0])
        ctx.issue("BAD_EXPRESSION", o, fld, f"operador {op!r} com {len(xs)} argumento(s)")
        return None
    if k == "document":
        if term["symbolized"]:
            ids = ", ".join(sorted({s["symbol_id"] for s in term["symbolized"]}))
            ctx.issue("UNKNOWN_SYMBOLIC_INPUT", o, fld, f"documento com trechos simbólicos sem valor: {ids}")
            return None
        fn = "yamlencode" if term["format"] == "yaml" else "jsonencode"
        kinds.append("document")
        return H.Call(fn, (H.Lit(term["tree"]),))
    ctx.issue("BAD_EXPRESSION", o, fld, f"termo de tipo {k!r} sem forma HCL")
    return None


def ref_expr(ctx: Ctx, step: dict, fld: str, term: dict, kinds: list):
    o = step["order"]
    want_data = term["target_address"].startswith("data.")
    cands = [ctx.by_order[d] for d in step["depends_on"] if d in ctx.by_order
             and ctx.by_order[d]["resource_type"] == term["target_type"]
             and (ctx.by_order[d]["action"] == "reference") == want_data]
    if not cands:
        ctx.issue("UNKNOWN_INPUT", o, fld,
                  f"referência a {term['target_type']} sem passo correspondente em depends_on {step['depends_on']}")
        return None
    if len(cands) > 1:
        ctx.issue("AMBIGUOUS_TARGET", o, fld,
                  f"referência a {term['target_type']} casa {len(cands)} passos de depends_on")
        return None
    tr = ctx.address(cands[0]) + ("." + term["attribute"] if term.get("attribute") else "")
    kinds.append("reference")
    return H.Ref(tr)


def name_expr(ctx: Ctx, step: dict):
    dn = step["derived_name"]
    o = step["order"]
    toks = re.split(r"(\{t[0-9]+\})", dn["template"])
    used = [t[1:-1] for t in toks if re.fullmatch(r"\{t[0-9]+\}", t)]
    if any("{" in t or "}" in t for t in toks if not re.fullmatch(r"\{t[0-9]+\}", t)):
        ctx.issue("BAD_TEMPLATE", o, "name", f"chave solta no modelo {dn['template']!r}")
        return None
    if set(used) != set(dn["from_terms"]):
        ctx.issue("BAD_TEMPLATE", o, "name", f"termos do modelo {sorted(set(used))} ≠ from_terms {dn['from_terms']}")
        return None
    parts = []
    for t in toks:
        if not t:
            continue
        m = re.fullmatch(r"\{(t[0-9]+)\}", t)
        if not m:
            parts.append(t)
            continue
        tid = m.group(1)
        term = ctx.terms.get(tid)
        if term is None:
            ctx.issue("GRAPH_MISSING", o, "name", f"termo {tid} não está no graph_ir")
            return None
        if term["kind"] == "literal" and term["datatype"] in ("string", "number") and not isinstance(term["value"], bool):
            parts.append(str(term["value"]))
        elif term["kind"] == "symbol":
            var = sym_var(term["symbol_id"])
            ctx.inputs.setdefault(var, {"variable": var, "kind": "name_symbol", "term_id": tid,
                                        "symbol_id": term["symbol_id"], "name_class": term["name_class"],
                                        "sensitive": False, "steps": []})["steps"].append(o)
            parts.append(H.Ref("var." + var))
        else:
            ctx.issue("TERM_DATATYPE", o, "name", f"termo {tid} ({term['kind']}) não cabe num nome")
            return None
    # junta literais vizinhos
    merged = []
    for p in parts:
        if merged and isinstance(p, str) and isinstance(merged[-1], str):
            merged[-1] += p
        else:
            merged.append(p)
    if all(isinstance(p, str) for p in merged):
        return H.Lit("".join(merged))
    return H.Tmpl(tuple(merged))


# ------------------------------------------------------------------------------------------------ árvore do corpo
def new_tree() -> dict:
    return {"attrs": {}, "blocks": {}}


def put_literal_block(ctx, o, fld, node, value, out_list):
    """Valor literal (mapa ou lista de mapas) em posição de bloco -> instâncias de bloco."""
    items = value if isinstance(value, list) else [value]
    for idx, inst in enumerate(items):
        if not isinstance(inst, dict):
            ctx.issue("BLOCK_VALUE_SHAPE", o, fld, f"instância {idx} do bloco não é mapa")
            return False
        t = new_tree()
        for k, v in inst.items():
            sub = f"{fld}[{idx}].{k}"
            a, b = S.attrs(node), S.blocks(node)
            if k in b:
                t["blocks"].setdefault(k, [])
                if not put_literal_block(ctx, o, sub, b[k].node, v, t["blocks"][k]):
                    return False
            elif k in a:
                if not a[k].configurable:
                    ctx.issue("FIELD_NOT_CONFIGURABLE", o, sub, "atributo só computado")
                    return False
                t["attrs"][k] = H.Lit(v)
            else:
                ctx.issue("FIELD_NOT_IN_SCHEMA", o, sub, "não existe no schema fixado")
                return False
        out_list.append(t)
    return True


def place(ctx: Ctx, step: dict, root: dict, tree: dict, fld: str, expr, is_literal_value, raw_value):
    o = step["order"]
    segs = fld.split(".")
    node, cur = root, tree
    for i, seg in enumerate(segs):
        last = i == len(segs) - 1
        a, b = S.attrs(node), S.blocks(node)
        if seg in b:
            insts = cur["blocks"].setdefault(seg, [])
            if last:
                if not is_literal_value or not isinstance(raw_value, (dict, list)):
                    ctx.issue("BLOCK_VALUE_SHAPE", o, fld, "bloco precisa de literal mapa ou lista de mapas")
                    return
                if insts:
                    ctx.issue("DUPLICATE_FIELD", o, fld, "bloco já preenchido por outro valor")
                    return
                put_literal_block(ctx, o, fld, b[seg].node, raw_value, insts)
                return
            if len(insts) > 1:
                ctx.issue("DUPLICATE_FIELD", o, fld, "caminho pontuado em bloco com várias instâncias")
                return
            if not insts:
                insts.append(new_tree())
            cur, node = insts[0], b[seg].node
            continue
        if seg in a:
            if not a[seg].configurable:
                ctx.issue("FIELD_NOT_CONFIGURABLE", o, fld, "atributo só computado")
                return
            if last:
                if seg in cur["attrs"]:
                    ctx.issue("DUPLICATE_FIELD", o, fld, "atributo com dois valores no plano")
                    return
                cur["attrs"][seg] = expr
                return
            ty = a[seg].type
            if not (isinstance(ty, list) and ty and ty[0] in ("object", "map")):
                ctx.issue("FIELD_NOT_IN_SCHEMA", o, fld, f"{seg} é atributo {ty!r}, sem subcampo")
                return
            obj = cur["attrs"].setdefault(seg, {"__obj__": {}})
            if not isinstance(obj, dict) or "__obj__" not in obj:
                ctx.issue("DUPLICATE_FIELD", o, fld, f"{seg} já tem valor inteiro no plano")
                return
            d = obj["__obj__"]
            for s2 in segs[i + 1:-1]:
                d = d.setdefault(s2, {})
                if not isinstance(d, dict):
                    ctx.issue("DUPLICATE_FIELD", o, fld, "subcampo em conflito")
                    return
            if segs[-1] in d:
                ctx.issue("DUPLICATE_FIELD", o, fld, "subcampo com dois valores")
                return
            d[segs[-1]] = expr
            return
        ctx.issue("FIELD_NOT_IN_SCHEMA", o, fld, f"segmento {seg!r} não existe no schema fixado")
        return


def check_required(ctx: Ctx, o: int, node: dict, tree: dict, prefix: str, reported=frozenset()):
    """`reported`: campos cujo valor já bloqueou por causa do termo (não repetir como ausente)."""
    a, b = S.attrs(node), S.blocks(node)
    for name, ai in sorted(a.items()):
        if ai.required and name not in tree["attrs"] and prefix + name not in reported:
            ctx.issue("UNKNOWN_INPUT", o, prefix + name, "atributo obrigatório no schema fixado e ausente do plano")
    for name, bi in sorted(b.items()):
        insts = tree["blocks"].get(name, [])
        if len(insts) < bi.min_items:
            ctx.issue("UNKNOWN_INPUT", o, prefix + name,
                      f"bloco obrigatório (min_items={bi.min_items}) ausente do plano ({len(insts)})")
        if bi.max_items and len(insts) > bi.max_items:
            ctx.issue("TOO_MANY_BLOCKS", o, prefix + name, f"{len(insts)} instâncias > max_items={bi.max_items}")
        for i, t in enumerate(insts):
            check_required(ctx, o, bi.node, t, f"{prefix}{name}[{i}].")


def tree_body(tree: dict) -> list:
    body = []
    for k in sorted(tree["attrs"]):
        v = tree["attrs"][k]
        body.append(H.Attr(k, _obj_expr(v["__obj__"]) if isinstance(v, dict) else v))
    for k in sorted(tree["blocks"]):
        for t in tree["blocks"][k]:
            body.append(H.Block(k, (), tree_body(t)))
    return body


def _obj_expr(d: dict):
    return H.ObjE(tuple((k, _obj_expr(v) if isinstance(v, dict) else v) for k, v in sorted(d.items())))


# ------------------------------------------------------------------------------------------------ plano
def render_plan(plan: dict, graph: dict | None, sch: S.Schema, tmpl: dict,
                ownership_tags: dict | None = None) -> Rendered:
    r = Rendered(plan["plan_id"], plan["graph_id"], (graph or {}).get("case_id"), plan["target_provider"])
    if plan["target_provider"] != PROVIDER:
        r.status = "WRONG_PROVIDER"
        r.issues.append(Issue("WRONG_PROVIDER", None, None, f"plano para {plan['target_provider']}, não azurerm"))
        return r
    ctx = Ctx(plan, graph, sch)
    if graph is None and any(s.get("derived_name") for s in plan["steps"]):
        ctx.issue("GRAPH_MISSING", None, None, "plano cita termos e o graph_ir irmão não foi achado")
    if not plan["dependency_closure"]["closed"]:
        ctx.issue("UNKNOWN_INPUT", None, None,
                  "fechamento de dependências aberto: falta " + ", ".join(plan["dependency_closure"]["missing"]))
    if ownership_tags:
        for k, v in ownership_tags.items():
            if not TAG_KEY.match(k) or not TAG_VAL.match(v):
                raise HarnessError(f"tag de propriedade fora do padrão do C16: {k}={v}")
    blocks_out = []
    for step in sorted(plan["steps"], key=lambda s: s["order"]):
        o = step["order"]
        kind = "data" if step["action"] == "reference" else "resource"
        for ch in step["typed_choices"]:
            if ch["selected"] is None:
                ctx.issue("AMBIGUOUS_TARGET", o, None, f"escolha {ch['choice_id']} sem seleção: {ch['reason']}")
        root = sch.node(kind, step["resource_type"])
        if root is None:
            ctx.issue("TYPE_NOT_IN_SCHEMA", o, None,
                      f"{kind} {step['resource_type']} não existe no azurerm {sch.version}")
            continue
        addr = ctx.address(step)
        tree = new_tree()
        if step.get("derived_name"):
            na = S.attrs(root).get("name")
            if na is None or not na.configurable:
                ctx.issue("NAME_FIELD_ABSENT", o, "name", f"{step['resource_type']} não tem atributo name configurável")
            elif any(v["field"] == "name" for v in step["values"]):
                ctx.issue("NAME_CONFLICT", o, "name", "plano traz derived_name e também values[name]")
            else:
                ne = name_expr(ctx, step)
                if ne is not None:
                    tree["attrs"]["name"] = ne
                    ctx.entries.append({"address": addr, "field": "name", "origin": "plan.derived_name",
                                        "order": o, "template": step["derived_name"]["template"]})
        reported = set()
        for v in step["values"]:
            kinds: list = []
            e = term_expr(ctx, step, v["field"], v["term"], kinds)
            if e is None:
                reported.add(v["field"])
                continue
            lit = v["term"]["kind"] == "literal"
            n_before = len(ctx.issues)
            place(ctx, step, root, tree, v["field"], e, lit, v["term"].get("value"))
            if len(ctx.issues) == n_before:
                ctx.entries.append({"address": addr, "field": v["field"], "origin": f"plan.values.{v['origin']}",
                                    "marked": v["marked"], "order": o, "term_kinds": sorted(set(kinds))})
        if ownership_tags and kind == "resource":
            ta = S.attrs(root).get("tags")
            if ta is not None and ta.configurable:
                cur = tree["attrs"].get("tags")
                if cur is None:
                    tree["attrs"]["tags"] = H.Lit(dict(sorted(ownership_tags.items())))
                    applied = sorted(ownership_tags)
                elif isinstance(cur, H.Lit) and isinstance(cur.value, dict):
                    merged = dict(cur.value)
                    applied = [k for k in sorted(ownership_tags) if k not in merged]
                    for k in applied:
                        merged[k] = ownership_tags[k]
                    tree["attrs"]["tags"] = H.Lit(merged)
                else:
                    applied = []
                for k in applied:
                    ctx.entries.append({"address": addr, "field": f"tags.{k}", "origin": "harness.ownership_tag",
                                        "order": o, "value": ownership_tags[k]})
        check_required(ctx, o, root, tree, "", frozenset(reported))
        body = tree_body(tree)
        if step["depends_on"]:
            deps = [ctx.address(ctx.by_order[d]) for d in step["depends_on"] if d in ctx.by_order]
            body.append(H.Attr("depends_on", H.ListE(tuple(H.Ref(d) for d in deps))))
            ctx.entries.append({"address": addr, "field": "depends_on", "origin": "plan.depends_on", "order": o,
                                "value": deps})
        blocks_out.append(H.Block(kind, (step["resource_type"], ctx.labels[o]), body))
    r.issues = ctx.issues
    codes = {i.code for i in ctx.issues}
    if codes & INVALID_CODES:
        r.status = "INVALID_PLAN"
    elif codes & BLOCK_CODES:
        r.status = "BLOCKED"
    if r.status != "RENDERED":
        return r
    var_blocks = []
    for name in sorted(ctx.inputs):
        inp = ctx.inputs[name]
        body = [H.Attr("type", H.Ref("string"))]
        if inp["sensitive"]:
            body.append(H.Attr("sensitive", H.Lit(True)))
        var_blocks.append(H.Block("variable", (name,), body))
    r.main_tf = H.file_text(var_blocks + blocks_out)
    r.manifest = {
        "schema": MANIFEST_SCHEMA, "module": MODULE, "plan_id": plan["plan_id"], "graph_id": plan["graph_id"],
        "case_id": r.case_id, "provider": PROVIDER, "provider_version": tmpl["provider_version"],
        "terraform_version": tmpl["terraform_version"],
        "plan_sha256": sha256_bytes(json.dumps(plan, sort_keys=True, ensure_ascii=False).encode()),
        "templates_sha256": dict(tmpl["files"]),
        "entries": ctx.entries,
        "inputs": [ctx.inputs[k] for k in sorted(ctx.inputs)],
        "declared_boilerplate": tmpl["declared_boilerplate"],
        "ownership_tags": dict(sorted((ownership_tags or {}).items())),
        "addresses": {str(s["order"]): ctx.address(s) for s in plan["steps"]},
        "losses": [dict(loss, order=s["order"]) for s in plan["steps"] for loss in s["losses"]],
        "typed_choices": [dict(ch, order=s["order"]) for s in plan["steps"] for ch in s["typed_choices"]],
        "symbolic_unknowns": [dict(u, order=s["order"]) for s in plan["steps"] for u in s["symbolic_unknowns"]],
        "main_tf_sha256": sha256_bytes(r.main_tf.encode()),
    }
    return r


# ------------------------------------------------------------------------------------------------ E/S
def validate_plan_file(path: Path) -> list[str]:
    from bo.contracts import validate as V
    res = V.validate("lowering_plan", path)
    return list(res.errors)


def load_graphs(plan_path: Path, graph_path: Path | None) -> dict[str, dict]:
    gp = graph_path or plan_path.with_name("graph_ir.jsonl")
    if not gp.is_file():
        return {}
    return {g["graph_id"]: g for g in read_jsonl(gp)}


def render_file(plan_path: Path, out: Path, graph_path: Path | None = None, plan_id: str | None = None,
                tdir: Path | None = None, ownership_tags: dict | None = None, validate: bool = True) -> dict:
    if not plan_path.is_file():
        raise HarnessError(f"plano não encontrado: {plan_path}")
    if validate:
        errs = validate_plan_file(plan_path)
        if errs:
            raise HarnessError("plano reprovado no validador C26: " + "; ".join(errs[:5]))
    sch = S.load(tdir)
    tmpl = S.templates_manifest(tdir)
    graphs = load_graphs(plan_path, graph_path)
    plans = read_jsonl(plan_path)
    if plan_id:
        plans = [p for p in plans if p["plan_id"] == plan_id]
        if not plans:
            raise HarnessError(f"plan_id {plan_id} não está em {plan_path}")
    results = [render_plan(p, graphs.get(p["graph_id"]), sch, tmpl, ownership_tags) for p in plans]
    az = [r for r in results if r.status != "WRONG_PROVIDER"]
    _prepare_out(out)
    single = len(az) == 1
    rows = []
    for r in results:
        row = {"plan_id": r.plan_id, "graph_id": r.graph_id, "case_id": r.case_id,
               "target_provider": r.target_provider, "status": r.status,
               "issues": [i.as_dict() for i in r.issues]}
        if r.status == "RENDERED":
            d = out if single else out / r.plan_id
            d.mkdir(parents=True, exist_ok=True)
            (d / "versions.tf").write_bytes(((tdir or templates_dir()) / "versions.tf").read_bytes())
            (d / "main.tf").write_text(r.main_tf, encoding="utf-8")
            (d / "render_manifest.json").write_text(dumps(dict(r.manifest, generated_at=now())), encoding="utf-8")
            row["dir"] = portable(d)
        rows.append(row)
    report = {"schema": REPORT_SCHEMA, "module": MODULE, "generated_at": now(), "plan_file": portable(plan_path),
              "plan_file_sha256": sha256_bytes(plan_path.read_bytes()), "layout": "single" if single else "per_plan",
              "counts": _counts(results), "plans": rows}
    (out / "render_report.json").write_text(dumps(report), encoding="utf-8")
    return report


def _counts(results) -> dict:
    c: dict = {}
    for r in results:
        c[r.status] = c.get(r.status, 0) + 1
    return dict(sorted(c.items()))


def _prepare_out(out: Path):
    """DIR novo, vazio, ou de um render anterior (tem render_report.json): o conteúdo antigo sai inteiro."""
    if out.exists():
        entries = list(out.iterdir())
        if entries and not (out / "render_report.json").is_file():
            raise HarnessError(f"--out {out} não está vazio e não é saída de render (sem render_report.json)")
        for e in entries:
            shutil.rmtree(e) if e.is_dir() else e.unlink()
    out.mkdir(parents=True, exist_ok=True)


def parse_tags(items) -> dict:
    out = {}
    for kv in items or []:
        k, sep, v = kv.partition("=")
        if not sep:
            raise HarnessError(f"--ownership-tag precisa de k=v: {kv!r}")
        out[k] = v
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="bo.harness.azurerm.render", description=__doc__.split("\n")[0])
    ap.add_argument("plan")
    ap.add_argument("--out", required=True)
    ap.add_argument("--graph-ir")
    ap.add_argument("--plan-id")
    ap.add_argument("--templates")
    ap.add_argument("--ownership-tag", action="append")
    a = ap.parse_args([x for x in (argv if argv is not None else sys.argv[1:]) if x != MODULE])
    try:
        rep = render_file(Path(a.plan), Path(a.out), Path(a.graph_ir) if a.graph_ir else None, a.plan_id,
                          Path(a.templates) if a.templates else None, parse_tags(a.ownership_tag))
    except HarnessError as e:
        print(f"render: {e}", file=sys.stderr)
        return 2
    c = rep["counts"]
    print(f"[{rep['generated_at']}] render: {sum(c.values())} plano(s) lidos; " +
          ", ".join(f"{k}={v}" for k, v in c.items()) + f"; relatório em {a.out}/render_report.json")
    for p in rep["plans"]:
        for i in p["issues"]:
            print(f"  {p['plan_id']} {p['status']}: {i['code']} passo={i['order']} campo={i['field']}: {i['detail']}")
    if not any(p["status"] != "WRONG_PROVIDER" for p in rep["plans"]):
        print("render: nenhum plano com target_provider=azurerm (nada a renderizar)", file=sys.stderr)
        return 4
    if not c.get("RENDERED"):
        print("render: nenhum plano azurerm renderizado (todos bloqueados ou inválidos)", file=sys.stderr)
        return 5
    return 0


if __name__ == "__main__":
    sys.exit(main())
