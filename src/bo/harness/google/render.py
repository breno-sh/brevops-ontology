"""Renderizador de HCL do Google Cloud a partir do plano de lowering (C26), sem inserção silenciosa.

  python -I -m bo.harness.google.render PLANO.jsonl --out DIR [--graph GRAPH.jsonl] [--schema PROVIDERS_SCHEMA.json]
                                       [--side object|subject]

O renderizador só escreve no HCL o que o plano declara:
  - valores do passo (carried, synthesized, default_declared; os dois últimos vêm marcados no plano);
  - o nome derivado (derived_name) no atributo 'name' do tipo, com os termos citados;
  - depends_on a partir dos passos citados;
  - termo simbólico -> variável de entrada SEM default (o runner liga um valor sintético declarado);
  - termo withheld de segredo -> variável sensível SEM default (gerada na hora pelo runner, nunca gravada);
  - o andaime fixo do harness: bloco terraform com o provider e a versão de universe/pins.json;
  - a inserção declarada HI-GCP-01 (bo.harness.google.run_label): labels["bo-run"] = var.<plano>_bo_run, SEM
    default, só nos recursos dos tipos que a tabela de SKUs do SAFETY rastreia por rótulo (o plan_guard recusa
    o plano sem ela, PG-TAG); rótulo 'bo-run' já trazido pelo plano é CONFLICTING_VALUES.
Nada mais: campo obrigatório do schema fixado que o plano não traz faz o caso falhar como UNKNOWN_INPUT; campo
fora do schema, tipo errado, termo não suportado, escolha sem seleção, guarda falsa ou conteúdo withheld como
literal também reprovam o caso (código no render_report.json), e nenhum HCL do plano reprovado é escrito.

Convenções de nome (o no_silent_insert as confere): recurso '<tipo>.<plano>_<nó>', data source
'data.<tipo>.<plano>_<nó>', variável simbólica '<plano>_<sym_…>', variável de segredo '<plano>_<nó>_secret_<campo>',
variável do rótulo da execução '<plano>_bo_run', onde <plano> = plan_id em minúsculas com '-' -> '_'.
"""

from __future__ import annotations

import argparse
import copy
import json
import re
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path

from bo.transforms import guards as G
from bo.transforms.markers import SYMBOLIC

from . import common as C
from . import hcl as H
from . import run_label as RL
from .schema import Schema, attr_at, is_settable

# código de falha do renderizador -> block_code do C00 (para o traço C23 e o C12)
FAIL_TO_BLOCK = {
    "UNKNOWN_INPUT": "UNKNOWN_INPUT",
    "PLAN_NOT_CLOSED": "UNKNOWN_INPUT",
    "GRAPH_MISSING": "UNKNOWN_INPUT",
    "WRONG_PROVIDER": "OUT_OF_SUBSET",
    "UNSUPPORTED_TYPE": "OUT_OF_SUBSET",
    "FIELD_NOT_IN_SCHEMA": "OUT_OF_SUBSET",
    "COMPUTED_ONLY": "OUT_OF_SUBSET",
    "UNSUPPORTED_TERM": "OUT_OF_SUBSET",
    "WITHHELD_LITERAL": "OUT_OF_SUBSET",
    "DERIVED_NAME_NO_FIELD": "OUT_OF_SUBSET",
    "TYPE_MISMATCH": "TRANSFORM_OUT_OF_DOMAIN",
    "CONFLICTING_VALUES": "AMBIGUOUS_TARGET",
    "AMBIGUOUS_BLOCK_INDEX": "AMBIGUOUS_TARGET",
    "CHOICE_UNRESOLVED": "AMBIGUOUS_TARGET",
    "CONDITION_FALSE": "CONDITION_FALSE",
}
RENDERED = "RENDERED"
_PLACEHOLDER = re.compile(r"\{(t[0-9]+)\}")
_REF_ADDR = re.compile(r"^(data\.)?([a-z][a-z0-9_]*)\.(SYM-[0-9a-f]{8,16})$")


class Fail(Exception):
    def __init__(self, code: str, where: str, msg: str):
        super().__init__(msg)
        self.code, self.where, self.msg = code, where, msg

    def record(self) -> dict:
        return {"code": self.code, "block_code": FAIL_TO_BLOCK[self.code], "where": self.where, "detail": self.msg}


@dataclass
class Rendered:
    plan_id: str
    graph_id: str
    status: str = RENDERED
    failures: list = field(default_factory=list)
    hcl: str | None = None
    ledger: list = field(default_factory=list)
    variables: list = field(default_factory=list)
    synthesized: list = field(default_factory=list)
    losses: list = field(default_factory=list)
    choices: list = field(default_factory=list)
    deferred_guards: list = field(default_factory=list)
    addresses: dict = field(default_factory=dict)

    def report(self) -> dict:
        d = {k: getattr(self, k) for k in ("plan_id", "graph_id", "status", "failures", "ledger", "variables",
                                           "synthesized", "losses", "choices", "deferred_guards", "addresses")}
        d["file"] = file_name(self.plan_id) if self.status == RENDERED else None
        return d


def plan_slug(plan_id: str) -> str:
    return C.slug(plan_id)


def file_name(plan_id: str) -> str:
    return plan_slug(plan_id) + ".tf"


def load_rules() -> dict:
    return json.loads((C.templates() / "redaction_rules.json").read_text(encoding="utf-8"))


def withheld_rule(rules: dict, rtype: str, path: str, attr: dict | None) -> dict | None:
    """Regra de redação que cobre o campo (caminho C26 sem índices), ou None."""
    plain = ".".join(s for s in path.split(".") if not s.isdigit())
    for r in rules["rules"]:
        if attr is not None and set(r.get("schema_flags", [])) & set(attr["flags"]):
            return r
        for p in r.get("paths", {}).get(rtype, []):
            if plain == p or plain.startswith(p + "."):
                return r
    return None


# ------------------------------------------------------------------------------------------------ tipos
def type_ok(cty, v) -> bool:
    """Confere o literal contra o tipo cty do atributo, sem coerção (o Terraform converteria "7" em 7; aqui não)."""
    if v is None or cty == "dynamic":
        return True
    if isinstance(v, (H.Expr,)):
        return True
    if isinstance(v, H.Template):
        return cty == "string"
    if cty == "string":
        return isinstance(v, str)
    if cty == "number":
        return isinstance(v, (int, float)) and not isinstance(v, bool)
    if cty == "bool":
        return isinstance(v, bool)
    if isinstance(cty, list):
        kind = cty[0]
        if kind in ("list", "set"):
            return isinstance(v, list) and all(type_ok(cty[1], x) for x in v)
        if kind == "map":
            return isinstance(v, dict) and all(type_ok(cty[1], x) for x in v.values())
        if kind == "object":
            return isinstance(v, dict) and all(k in cty[1] and type_ok(cty[1][k], x) for k, x in v.items())
        if kind == "tuple":
            return isinstance(v, list) and len(v) == len(cty[1]) and all(type_ok(t, x) for t, x in zip(cty[1], v))
    return False


def var_type(cty) -> str:
    return cty if cty in ("string", "number", "bool") else "any"


# ------------------------------------------------------------------------------------------------ corpo
class Builder:
    """Monta o corpo de UM recurso a partir dos valores do plano, com o schema do tipo."""

    def __init__(self, r: "PlanRenderer", rtype: str, kind: str, block: dict, address: str):
        self.r, self.rtype, self.kind, self.schema, self.address = r, rtype, kind, block, address
        self.body = H.Body.new()
        self.set_paths: dict[str, int] = {}
        self.deps: list[str] = []
        self._secret = False

    # instâncias de bloco: lista de (nome, Body) no Body; repetidos mantêm a ordem
    @staticmethod
    def instances(body: H.Body, name: str) -> list:
        return [b for n, b in body.blocks if n == name]

    def sub(self, body: H.Body, name: str, idx: int) -> H.Body:
        inst = self.instances(body, name)
        while len(inst) <= idx:
            nb = H.Body.new()
            body.blocks.append((name, nb))
            inst.append(nb)
        return inst[idx]

    def place(self, path: str, value, origin: str, order: int, where: str, ref: dict, secret: bool = False):
        """Coloca um valor; se falhar, o corpo e o livro voltam ao estado anterior (nada parcial fica)."""
        snap, n = copy.deepcopy(self.body), len(self.r.out.ledger)
        self._secret = secret
        try:
            self._place(self.body, self.schema, path.split("."), [], value, origin, order, where, ref)
        except Fail:
            self.body.attrs, self.body.blocks = snap.attrs, snap.blocks
            del self.r.out.ledger[n:]
            raise

    def _place(self, body, node, segs, done, value, origin, order, where, ref):
        s = segs[0]
        here = done + [s]
        if s in node["attributes"]:
            attr = node["attributes"][s]
            if not is_settable(attr):
                raise Fail("COMPUTED_ONLY", where, f"{'.'.join(here)} é só computado no google {self.r.schema.version}")
            rule = withheld_rule(self.r.rules, self.rtype, ".".join(here), attr)
            rest = segs[1:]
            if rest:
                cty = attr["type"]
                if "nested_type" in attr or not (isinstance(cty, list) and cty[0] in ("map", "object")):
                    raise Fail("FIELD_NOT_IN_SCHEMA", where, f"{'.'.join(here)} não é mapa/objeto; "
                               f"'{'.'.join(segs)}' não existe")
                cur = body.attrs.setdefault(s, {})
                if not isinstance(cur, dict):
                    raise Fail("CONFLICTING_VALUES", where, f"{'.'.join(here)} recebe valor inteiro e por chave")
                sub_t = cty[1] if cty[0] == "map" else cty[1].get(rest[0])
                if len(rest) > 1 or sub_t is None:
                    raise Fail("FIELD_NOT_IN_SCHEMA", where, f"chave '{'.'.join(rest)}' fora do tipo de {s}")
                self._check_leaf(sub_t, value, rule, here + rest, where, origin)
                if rest[0] in cur:
                    raise Fail("CONFLICTING_VALUES", where, f"{'.'.join(here + rest)} recebe dois valores")
                cur[rest[0]] = value
                self._mark(here + rest, origin, order, ref)
                return
            self._check_leaf(attr["type"], value, rule, here, where, origin)
            if s in body.attrs:
                raise Fail("CONFLICTING_VALUES", where, f"{'.'.join(here)} recebe dois valores")
            body.attrs[s] = value
            self._mark(here, origin, order, ref)
            return
        if s in node["blocks"]:
            bt = node["blocks"][s]
            single = bt["nesting_mode"] in ("single", "group") or bt["max_items"] == 1
            rest = segs[1:]
            if rest and rest[0].isdigit():
                idx = int(rest[0])
                if single and idx != 0:
                    raise Fail("FIELD_NOT_IN_SCHEMA", where, f"bloco {'.'.join(here)} tem no máximo 1 instância")
                if bt["max_items"] and idx >= bt["max_items"]:
                    raise Fail("FIELD_NOT_IN_SCHEMA", where, f"bloco {'.'.join(here)}: índice {idx} além de max_items")
                child = self.sub(body, s, idx)
                if not rest[1:]:
                    self._whole_block(child, bt, value, here + [rest[0]], origin, order, where, ref)
                else:
                    self._place(child, bt["block"], rest[1:], here + [rest[0]], value, origin, order, where, ref)
                return
            if not rest:
                if single:
                    self._whole_block(self.sub(body, s, 0), bt, value, here, origin, order, where, ref)
                    return
                if not isinstance(value, list) or not all(isinstance(x, dict) for x in value):
                    raise Fail("TYPE_MISMATCH", where, f"bloco repetido {'.'.join(here)} pede lista de objetos")
                if self.instances(body, s):
                    raise Fail("CONFLICTING_VALUES", where, f"bloco {'.'.join(here)} recebe lista e outro valor")
                if bt["max_items"] and len(value) > bt["max_items"]:
                    raise Fail("TYPE_MISMATCH", where, f"bloco {'.'.join(here)}: {len(value)} > max_items")
                for i, item in enumerate(value):
                    self._whole_block(self.sub(body, s, i), bt, item, here + [str(i)], origin, order, where, ref)
                return
            if not single:
                raise Fail("AMBIGUOUS_BLOCK_INDEX", where, f"bloco repetido {'.'.join(here)} sem índice de instância")
            self._place(self.sub(body, s, 0), bt["block"], rest, here, value, origin, order, where, ref)
            return
        raise Fail("FIELD_NOT_IN_SCHEMA", where, f"'{'.'.join(here)}' não existe em {self.rtype} "
                   f"(google {self.r.schema.version})")

    def _whole_block(self, body, bt, value, here, origin, order, where, ref):
        if not isinstance(value, dict):
            raise Fail("TYPE_MISMATCH", where, f"bloco {'.'.join(here)} pede objeto")
        for k in sorted(value):
            self._place(body, bt["block"], [k], here, value[k], origin, order, where, ref)

    def _check_leaf(self, cty, value, rule, here, where, origin):
        p = ".".join(here)
        if rule is not None and not self._secret:
            raise Fail("WITHHELD_LITERAL", where, f"{p} é coberto por {rule['rule_id']} ({rule['reason']}); "
                       "o plano não pode carregar esse conteúdo")
        if not type_ok(cty, value):
            raise Fail("TYPE_MISMATCH", where, f"{p}: valor do plano não tem o tipo {json.dumps(cty)}")

    def _mark(self, here, origin, order, ref):
        p = ".".join(here)
        self.set_paths[p] = order
        self.r.out.ledger.append({"address": self.address, "path": p, "origin": origin, "order": order, **ref})

    def missing_required(self) -> list[str]:
        out: list[str] = []
        self._missing(self.body, self.schema, [], out)
        return out

    def _missing(self, body, node, pre, out):
        for name, a in node["attributes"].items():
            if "required" in a["flags"]:
                if body.attrs.get(name) is None:
                    out.append(".".join(pre + [name]))
        for name, bt in node["blocks"].items():
            inst = self.instances(body, name)
            if len(inst) < bt["min_items"]:
                out.append(".".join(pre + [name]) + f" (bloco, mínimo {bt['min_items']})")
            multi = not (bt["nesting_mode"] in ("single", "group") or bt["max_items"] == 1)
            for i, b in enumerate(inst):
                self._missing(b, bt["block"], pre + [name] + ([str(i)] if multi else []), out)


# ------------------------------------------------------------------------------------------------ plano
class PlanRenderer:
    def __init__(self, plan: dict, graph: dict | None, schema: Schema, side: str = "object", rules=None):
        self.plan, self.graph, self.schema, self.side = plan, graph, schema, side
        self.rules = rules or load_rules()
        self.slug = plan_slug(plan["plan_id"])
        self.out = Rendered(plan["plan_id"], plan["graph_id"])
        self.terms = {t["term_id"]: t["term"] for t in (graph or {}).get("terms", [])}
        self.variables: dict[str, dict] = {}
        self.steps = {s["order"]: s for s in plan["steps"]}

    # --- contexto das guardas: contextos do grafo como termos do lado do caso
    def ctx(self) -> dict:
        c = {}
        for k in (self.graph or {}).get("contexts", []):
            if k["state"] == "known":
                c[f"{self.side}.{k['key']}"] = k["value"]
            elif k["state"] == "symbolic":
                c[f"{self.side}.{k['key']}"] = SYMBOLIC
        return c

    def guard(self, g: dict, where: str, what: str):
        verdict, terms = G.evaluate(g, self.ctx())
        if verdict == G.FALSE:
            raise Fail("CONDITION_FALSE", where, f"{what}: guarda falsa no contexto do grafo ({', '.join(terms)})")
        if verdict == G.INDETERMINATE:
            self.out.deferred_guards.append({"where": where, "what": what, "guard": g, "terms": terms,
                                             "note": "reavaliar com o contexto de execução antes do apply"})

    def local(self, node_id: str) -> str:
        return f"{self.slug}_{node_id}"

    def address(self, step: dict) -> str:
        kind = "data" if step["action"] == "reference" else "resource"
        a = f"{step['resource_type']}.{self.local(step['node_id'])}"
        return "data." + a if kind == "data" else a

    # --- termos -> valores HCL
    def sym_var(self, term: dict, cty, why: str) -> H.Expr:
        name = f"{self.slug}_{C.slug(term['symbol_id'])}"
        t = var_type(cty)
        v = self.variables.setdefault(name, {"name": name, "kind": "symbolic_input", "type": t,
                                             "symbol_id": term["symbol_id"], "name_class": term["name_class"],
                                             "sensitive": False, "used_by": []})
        if v["type"] != t:
            v["type"] = "any"
        v["used_by"].append(why)
        return H.Expr("var." + name)

    def secret_var(self, node_id: str, fld: str, cty) -> H.Expr:
        name = f"{self.slug}_{node_id}_secret_{C.slug(fld)}"
        self.variables[name] = {"name": name, "kind": "runtime_secret", "type": var_type(cty), "sensitive": True,
                                "field": fld, "node_id": node_id, "used_by": [fld]}
        return H.Expr("var." + name)

    def ref_expr(self, term: dict, where: str) -> H.Expr:
        m = _REF_ADDR.match(term["target_address"])
        if not m:
            raise Fail("UNSUPPORTED_TERM", where, "referência indexada não é suportada pelo harness")
        is_data, ttype, sym = bool(m.group(1)), m.group(2), m.group(3)
        if "attribute" not in term:
            raise Fail("UNKNOWN_INPUT", where, f"referência a {ttype} sem atributo; o harness não escolhe um")
        hits = []
        for s in self.plan["steps"]:
            if s["resource_type"] != ttype or (s["action"] == "reference") != is_data:
                continue
            tids = (s.get("derived_name") or {}).get("from_terms", [])
            if any(self.terms.get(t, {}).get("symbol_id") == sym for t in tids):
                hits.append(s)
        if len(hits) != 1:
            raise Fail("UNKNOWN_INPUT", where, f"referência a {ttype} ({sym}) com {len(hits)} alvo(s) no plano")
        return H.Expr(f"{self.address(hits[0])}.{term['attribute']}")

    def term_value(self, term: dict, step: dict, fld: str, cty, where: str):
        k = term["kind"]
        if k == "literal":
            dt, v = term["datatype"], term["value"]
            want = {"string": str, "bool": bool, "list": list, "map": dict}.get(dt)
            if dt == "number" and (isinstance(v, bool) or not isinstance(v, (int, float))):
                raise Fail("TYPE_MISMATCH", where, f"{fld}: literal number com valor não numérico")
            if want is not None and not isinstance(v, want):
                raise Fail("TYPE_MISMATCH", where, f"{fld}: literal {dt} com valor de outro tipo")
            if dt == "null" and v is not None:
                raise Fail("TYPE_MISMATCH", where, f"{fld}: literal null com valor")
            return v
        if k == "symbol":
            return self.sym_var(term, cty, f"{step['node_id']}.{fld}")
        if k == "reference":
            return self.ref_expr(term, where)
        if k == "withheld":
            if term["reason"] == "secret":
                return self.secret_var(step["node_id"], fld, cty)
            raise Fail("UNKNOWN_INPUT", where, f"{fld}: conteúdo withheld ({term['reason']}) não existe no plano; "
                       "o harness não inventa")
        if k == "document":
            if term["symbolized"]:
                raise Fail("UNSUPPORTED_TERM", where, f"{fld}: documento com {len(term['symbolized'])} trecho(s) "
                           "simbolizado(s) não é renderizado")
            return json.dumps(term["tree"], ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        raise Fail("UNSUPPORTED_TERM", where, f"{fld}: termo '{k}' não é renderizado pelo harness")

    def derived_name(self, step: dict, block: dict, where: str):
        dn = step["derived_name"]
        attr = block["attributes"].get("name")
        if attr is None or not is_settable(attr):
            raise Fail("DERIVED_NAME_NO_FIELD", where, f"{step['resource_type']} não tem atributo 'name' configurável")
        parts: list = []
        pos = 0
        for m in _PLACEHOLDER.finditer(dn["template"]):
            if m.start() > pos:
                parts.append(dn["template"][pos:m.start()])
            tid = m.group(1)
            if tid not in dn["from_terms"] or tid not in self.terms:
                raise Fail("UNKNOWN_INPUT", where, f"nome derivado cita {tid} fora de from_terms/termos do grafo")
            t = self.terms[tid]
            if t["kind"] == "literal" and t["datatype"] in ("string", "number") and not isinstance(t["value"], bool):
                parts.append(str(t["value"]))
            elif t["kind"] == "symbol":
                parts.append(self.sym_var(t, "string", f"{step['node_id']}.name"))
            else:
                raise Fail("UNSUPPORTED_TERM", where, f"nome derivado com termo {t['kind']}")
            pos = m.end()
        if pos < len(dn["template"]):
            parts.append(dn["template"][pos:])
        if "{" in "".join(p for p in parts if isinstance(p, str)):
            raise Fail("UNKNOWN_INPUT", where, "nome derivado com chave sem termo")
        merged: list = []
        for p in parts:
            if isinstance(p, str) and merged and isinstance(merged[-1], str):
                merged[-1] += p
            else:
                merged.append(p)
        if all(isinstance(p, str) for p in merged):
            return "".join(merged)
        return H.Template(tuple(merged))

    # --- passo a passo
    def run(self) -> Rendered:
        p, o = self.plan, self.out
        try:
            if p["target_provider"] != C.PROVIDER:
                raise Fail("WRONG_PROVIDER", p["plan_id"], f"plano para {p['target_provider']}, harness do google")
            if not p["dependency_closure"]["closed"]:
                raise Fail("PLAN_NOT_CLOSED", p["plan_id"],
                           f"dependências faltando: {', '.join(p['dependency_closure']['missing'])}")
            if self.graph is None:
                raise Fail("GRAPH_MISSING", p["plan_id"], f"graph_ir {p['graph_id']} não encontrado")
        except Fail as f:
            o.failures.append(f.record())
            return self.finish({}, [])
        builders: dict[int, Builder] = {}
        owner: dict[int, int] = {}       # passo -> passo dono do bloco (configure fundido no recurso pai)
        comps = {c["node_id"]: c for c in self.graph.get("components", [])}
        node_order = {s["node_id"]: s["order"] for s in p["steps"]}
        for pre in self.graph.get("preconditions", []):
            try:
                self.guard(pre["guard"], pre["precondition_id"], f"pré-condição em {', '.join(pre['applies_to'])}")
            except Fail as f:
                o.failures.append(f.record())
        for st in sorted(p["steps"], key=lambda s: s["order"]):
            where = f"passo {st['order']} ({st['node_id']})"
            try:
                self.step(st, where, builders, owner, comps, node_order)
            except Fail as f:
                o.failures.append(f.record())
        return self.finish(builders, owner)

    def step(self, st, where, builders, owner, comps, node_order):
        o = self.out
        kind = "data" if st["action"] == "reference" else "resource"
        for ch in st["typed_choices"]:
            o.choices.append({"order": st["order"], **ch})
            if ch["selected"] is None:
                raise Fail("CHOICE_UNRESOLVED", where, f"{ch['choice_id']} sem opção selecionada: {ch['reason']}")
            if "guard" in ch:
                self.guard(ch["guard"], where, ch["choice_id"])
        for loss in st["losses"]:
            o.losses.append({"order": st["order"], "address": None, **loss})
        parent = None
        if st["action"] == "configure" and st["node_id"] in comps:
            po = node_order.get(comps[st["node_id"]]["of"])
            if po is not None and self.steps[po]["resource_type"] == st["resource_type"]:
                parent = owner.get(po, po)
        if parent is not None:
            if parent not in builders:
                raise Fail("UNKNOWN_INPUT", where, "configure de componente cujo recurso pai não renderizou")
            b = builders[parent]
            owner[st["order"]] = parent
        else:
            block = self.schema.block(kind, st["resource_type"])
            if block is None:
                raise Fail("UNSUPPORTED_TYPE", where, f"{kind} {st['resource_type']} fora do schema do harness "
                           f"(google {self.schema.version}; use --schema com o providers-schema.json completo)")
            b = Builder(self, st["resource_type"], kind, block, self.address(st))
            if b.address in o.addresses.values():
                raise Fail("CONFLICTING_VALUES", where, f"{b.address} já foi criado por outro passo")
            o.addresses[str(st["order"])] = b.address
        if parent is None:
            builders[st["order"]] = b
        loss_fields = {x["field"] for x in st["losses"]}
        for v in st["values"]:
            # cada valor falha sozinho: o caso reprova, mas o relatório lista todos os defeitos do passo
            fld = v["field"]
            try:
                if fld in loss_fields:
                    raise Fail("CONFLICTING_VALUES", where, f"{fld} é perda declarada e valor carregado ao mesmo tempo")
                attr, rest = attr_at(b.schema, fld.split("."))
                cty = attr["type"] if attr else "dynamic"
                if attr and rest and isinstance(cty, list) and cty[0] in ("map", "object"):
                    cty = cty[1] if cty[0] == "map" else cty[1].get(rest[0], "dynamic")
                val = self.term_value(v["term"], st, fld, cty, where)
                secret = v["term"]["kind"] == "withheld"      # só chega aqui o withheld de segredo (variável sensível)
                b.place(fld, val, v["origin"], st["order"], where, {"field": fld}, secret=secret)
                if v["origin"] in ("synthesized", "default_declared"):
                    o.synthesized.append({"order": st["order"], "address": b.address, "field": fld,
                                          "origin": v["origin"], "marked": v["marked"], "term": v["term"]})
            except Fail as f:
                o.failures.append(f.record())
        if "derived_name" in st:
            try:
                name = self.derived_name(st, b.schema, where)
                b.place("name", name, "derived_name", st["order"], where,
                        {"field": "name", "template": st["derived_name"]["template"]})
            except Fail as f:
                o.failures.append(f.record())
        deps = []
        for d in st["depends_on"]:
            if d not in self.steps:
                raise Fail("UNKNOWN_INPUT", where, f"depends_on cita passo {d} inexistente")
            if d not in builders and owner.get(d) not in builders:
                raise Fail("UNKNOWN_INPUT", where, f"depende do passo {d}, que não renderizou")
            addr = builders[owner.get(d, d)].address
            if addr != b.address and addr not in deps:
                deps.append(addr)
        b.deps += [x for x in deps if x not in b.deps]
        for x in deps:
            o.ledger.append({"address": b.address, "path": "depends_on", "origin": "plan_depends_on",
                             "order": st["order"], "target": x})

    def run_label(self, order: int, b: "Builder"):
        """HI-GCP-01: labels["bo-run"] = var.<plano>_bo_run nos recursos dos tipos rastreados por rótulo."""
        if b.kind != "resource" or b.rtype not in RL.types():
            return
        where = f"passo {order} ({b.address})"
        attr = b.schema["attributes"].get(RL.ATTRIBUTE)
        if attr is None or not is_settable(attr) or attr["type"] != ["map", "string"]:
            raise Fail("FIELD_NOT_IN_SCHEMA", where, f"{b.rtype} está em {RL.path().name} mas não tem "
                       f"'{RL.ATTRIBUTE}' map(string) configurável no google {self.schema.version}")
        cur = b.body.attrs.get(RL.ATTRIBUTE)
        if isinstance(cur, dict):
            b.body.attrs[RL.ATTRIBUTE] = dict(cur)     # cópia: o termo do plano não é alterado
        name = RL.var_name(self.slug)
        v = self.variables.setdefault(name, {"name": name, "kind": "run_label", "type": "string",
                                             "sensitive": False, "insertion_id": RL.INSERTION_ID, "used_by": []})
        b.place(f"{RL.ATTRIBUTE}.{RL.LABEL_KEY}", H.Expr("var." + name), "harness_declared", order, where,
                {"field": f"{RL.ATTRIBUTE}.{RL.LABEL_KEY}", "insertion_id": RL.INSERTION_ID})
        v["used_by"].append(b.address)

    def finish(self, builders, owner) -> Rendered:
        o = self.out
        if not o.failures:
            for order, b in sorted(builders.items()):
                try:
                    self.run_label(order, b)
                except Fail as f:
                    o.failures.append(f.record())
        for order, b in sorted(builders.items()):
            miss = b.missing_required()
            if miss:
                o.failures.append(Fail("UNKNOWN_INPUT", f"passo {order} ({b.address})",
                                       "campo(s) obrigatório(s) do schema que o plano não traz: "
                                       + ", ".join(miss)).record())
        for loss in o.losses:
            loss["address"] = o.addresses.get(str(owner.get(loss["order"], loss["order"])))
        o.variables = sorted(self.variables.values(), key=lambda v: v["name"])
        if o.failures:
            codes = [f["code"] for f in o.failures]
            o.status = "UNKNOWN_INPUT" if any(FAIL_TO_BLOCK[c] == "UNKNOWN_INPUT" for c in codes) else codes[0]
            return o
        blocks = []
        for v in o.variables:
            vb = H.Body.new()
            vb.attrs["type"] = H.Expr(v["type"])
            vb.attrs["description"] = ("valor sintético ligado pelo runner (símbolo " + v["symbol_id"] + ")"
                                       if v["kind"] == "symbolic_input"
                                       else "rótulo bo-run da execução, ligado pelo executor (" + v["insertion_id"]
                                       + ")" if v["kind"] == "run_label"
                                       else "segredo gerado na hora pelo runner; nunca gravado")
            if v["sensitive"]:
                vb.attrs["sensitive"] = True
            blocks.append(("variable", [v["name"]], vb))
        for order, b in sorted(builders.items()):
            body = H.Body(dict(b.body.attrs), list(b.body.blocks))
            if b.deps:
                body.attrs["depends_on"] = [H.Expr(a) for a in b.deps]
            rtype, local = b.address.removeprefix("data.").split(".", 1)
            blocks.append(("data" if b.kind == "data" else "resource", [rtype, local], body))
        header = [f"Gerado por bo.harness.google.render a partir de {o.plan_id} (grafo {o.graph_id}).",
                  "HCL = plano + valores sintetizados declarados + rótulo bo-run declarado (HI-GCP-01). Não editar."
                  if any(v["kind"] == "run_label" for v in o.variables) else
                  "HCL = plano + valores sintetizados declarados; nada inserido pelo harness. Não editar."]
        o.hcl = H.document(blocks, header)
        return o


def render_plan(plan: dict, graph: dict | None, schema: Schema, side: str = "object", rules=None) -> Rendered:
    return PlanRenderer(plan, graph, schema, side, rules).run()


def versions_tf(schema: Schema) -> str:
    pins = C.pins()
    rp = H.Body.new()
    rp.attrs["google"] = {"source": "hashicorp/google", "version": "= " + schema.version}
    tb = H.Body.new()
    tb.attrs["required_version"] = "= " + pins["terraform"]["version"]
    tb.blocks.append(("required_providers", rp))
    return H.document([("terraform", [], tb)], [
        "Andaime fixo do harness (universe/pins.json): Terraform e provider google fixados.",
        "Sem bloco provider: projeto, região e credencial vêm do runner, depois da checagem de identidade."])


# ------------------------------------------------------------------------------------------------ E/S
def load_inputs(plan_path: Path, graph_path: Path | None) -> tuple[list, dict, list[str]]:
    errs = C.validate("C26", plan_path)
    gp = graph_path or plan_path.with_name("graph_ir.jsonl")
    graphs: dict = {}
    if gp.exists():
        errs += C.validate("C26", gp)
        graphs = {g["graph_id"]: g for g in C.read_jsonl(gp)}
    plans = C.read_jsonl(plan_path) if not errs else []
    return plans, graphs, errs


def render_file(plan_path: Path, out: Path, graph_path: Path | None = None, full_schema: Path | None = None,
                side: str = "object") -> tuple[int, dict]:
    plans, graphs, errs = load_inputs(plan_path, graph_path)
    if errs:
        return 1, {"errors": errs}
    schema = Schema.load(full_schema)
    prepare_out(out)
    rules = load_rules()
    results = [render_plan(p, graphs.get(p["graph_id"]), schema, side, rules) for p in plans]
    (out / "versions.tf").write_text(versions_tf(schema), encoding="utf-8")
    for r in results:
        if r.status == RENDERED:
            (out / file_name(r.plan_id)).write_text(r.hcl, encoding="utf-8")
    rep = {"schema": "bo.harness_google.render_report/1", "module": C.MODULE, "generated_at": C.now(),
           "input": {"plan": str(plan_path), "plan_sha256": C.sha256_file(plan_path)},
           "provider": {"source": schema.source, "version": schema.version, "schema_sha256": schema.sha256},
           "side": side, "files": ["versions.tf"] + [file_name(r.plan_id) for r in results if r.status == RENDERED],
           "counts": {"plans": len(results), "rendered": sum(r.status == RENDERED for r in results),
                      "failed": sum(r.status != RENDERED for r in results)},
           "plans": [r.report() for r in results]}
    (out / "render_report.json").write_text(C.dump(rep), encoding="utf-8")
    return 0, rep


def prepare_out(out: Path) -> None:
    """Diretório de saída exclusivo: vazio, ou uma saída anterior deste renderizador (que é limpa)."""
    out = out.resolve()
    tmp = C.tmp()
    if not str(out).startswith(str(tmp) + "/"):
        raise SystemExit(f"--out tem de ficar dentro de $BO_TMP ({tmp}): {out}")
    if out.exists():
        rep = out / "render_report.json"
        names = {p.name for p in out.iterdir()}
        if names and not rep.exists():
            raise SystemExit(f"{out} não está vazio e não é saída do renderizador; nada apagado")
        if rep.exists():
            old = json.loads(rep.read_text(encoding="utf-8"))
            for f in old.get("files", []) + ["render_report.json"]:
                (out / f).unlink(missing_ok=True)
            leftover = [p.name for p in out.iterdir()]
            if leftover:
                raise SystemExit(f"{out} tem arquivos que o renderizador não escreveu: {', '.join(sorted(leftover))}")
    out.mkdir(parents=True, exist_ok=True)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="bo.harness.google.render", description=__doc__.split("\n")[0])
    ap.add_argument("plan", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--graph", type=Path, default=None)
    ap.add_argument("--schema", type=Path, default=None)
    ap.add_argument("--side", choices=("object", "subject"), default="object")
    a = ap.parse_args(argv)
    if not a.plan.exists():
        print(f"[{C.now()}] render: plano não existe: {a.plan}", file=sys.stderr)
        return 2
    rc, rep = render_file(a.plan, a.out, a.graph, a.schema, a.side)
    if rc:
        print(f"[{C.now()}] render: entrada reprovada no validador do C26; nada escrito", file=sys.stderr)
        for e in rep["errors"][:20]:
            print("  " + e, file=sys.stderr)
        return rc
    c = rep["counts"]
    print(f"[{C.now()}] render: {c['plans']} plano(s), {c['rendered']} renderizado(s), {c['failed']} reprovado(s) "
          f"-> {a.out}")
    for p in rep["plans"]:
        line = f"  {p['plan_id']}: {p['status']}"
        if p["failures"]:
            line += " — " + "; ".join(f"{f['code']} {f['where']}: {f['detail']}" for f in p["failures"])
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
