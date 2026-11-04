"""Carga e interpretação de grain/grain_rules.yaml (vocabulário fechado de predicados).

As regras são dados: o motor só sabe avaliar os predicados listados em PREDICATES, sobre a evidência
consolidada e a classe de identidade derivada. Chave de condição fora do vocabulário reprova na carga.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .common import rules_path

GRAINS = ("ENTITY", "COMPONENT", "FACET", "BINDING", "UNKNOWN")
IDENTITY_CLASSES = ("CONTRADICTORY", "ABSENT", "UNRESOLVED", "ORPHAN", "BORROWED", "REF_TUPLE",
                    "INDEPENDENT", "WITHIN", "REF_TUPLE_PLUS")
# predicado -> campo de evidência que ele lê (para listar o que falhou)
PREDICATES = {
    "identity_class_in": "identity",
    "identity_targets_min": "identity",
    "identity_targets_kind_in": "identity",
    "owner_kind_in": "owner",
    "owner_targets_count": "owner",
    "owner_targets_kind_in": "owner",
    "lifecycle_kind_in": "lifecycle_controller",
    "lifecycle_target_consistent": "lifecycle_controller",
    "lifecycle_target_resolved": "lifecycle_controller",
    "api_resource_status_in": "api_resource",
    "identity_targets_all_namespace": "identity",
    "identity_composition_targets_min": "identity",
    "identity_path_parent": "identity",
}
NEEDS = ("lifecycle_controller", "owner", "effective_scope", "api_resource")
RULE_KEYS = {"id", "priority", "grain", "text", "match", "needs", "guard", "emit", "missing",
             "also_missing_if_unknown", "multi_owner"}


class RulesError(ValueError):
    pass


@dataclass
class Rule:
    id: str
    priority: int
    grain: str
    text: str
    match: dict
    needs: list[str] = field(default_factory=list)
    guard: dict = field(default_factory=dict)
    emit: dict = field(default_factory=dict)
    missing: object = None
    also_missing_if_unknown: list[str] = field(default_factory=list)
    multi_owner: dict = field(default_factory=dict)


@dataclass
class RuleSet:
    rules: list[Rule]
    version: str
    status: str
    raw: dict

    def by_id(self, rid: str) -> Rule:
        for r in self.rules:
            if r.id == rid:
                return r
        raise KeyError(rid)


def _check_cond(rid: str, where: str, cond: dict):
    if not isinstance(cond, dict):
        raise RulesError(f"{rid}.{where}: não é mapa")
    for k, v in cond.items():
        if k not in PREDICATES:
            raise RulesError(f"{rid}.{where}: predicado fora do vocabulário: {k}")
        if k == "identity_class_in":
            bad = [x for x in v if x not in IDENTITY_CLASSES]
            if bad:
                raise RulesError(f"{rid}.{where}: classe de identidade desconhecida: {bad}")
        if k.endswith("_kind_in") and k.startswith(("identity_targets", "owner_targets")):
            bad = [x for x in v if x not in GRAINS]
            if bad:
                raise RulesError(f"{rid}.{where}: grão desconhecido: {bad}")


def parse(doc: dict) -> RuleSet:
    if doc.get("schema") != "bo.grain.rules/1":
        raise RulesError("schema diferente de bo.grain.rules/1")
    preds = set((doc.get("predicates") or {}).keys())
    if preds != set(PREDICATES):
        raise RulesError(f"seção predicates diverge do vocabulário do motor: {sorted(preds ^ set(PREDICATES))}")
    rules = []
    seen_p, seen_id = set(), set()
    for r in doc.get("rules", []):
        extra = set(r) - RULE_KEYS
        if extra:
            raise RulesError(f"{r.get('id')}: chave desconhecida {sorted(extra)}")
        if r["grain"] not in GRAINS:
            raise RulesError(f"{r['id']}: grão {r['grain']}")
        if r["id"] in seen_id or r["priority"] in seen_p:
            raise RulesError(f"{r['id']}: id ou prioridade repetidos")
        seen_id.add(r["id"])
        seen_p.add(r["priority"])
        _check_cond(r["id"], "match", r.get("match") or {})
        _check_cond(r["id"], "guard", r.get("guard") or {})
        for n in r.get("needs", []) or []:
            if n not in NEEDS:
                raise RulesError(f"{r['id']}: needs fora da lista: {n}")
        rules.append(Rule(id=r["id"], priority=int(r["priority"]), grain=r["grain"], text=r.get("text", ""),
                          match=r.get("match") or {}, needs=list(r.get("needs") or []),
                          guard=r.get("guard") or {}, emit=r.get("emit") or {}, missing=r.get("missing"),
                          also_missing_if_unknown=list(r.get("also_missing_if_unknown") or []),
                          multi_owner=r.get("multi_owner") or {}))
    rules.sort(key=lambda x: x.priority)
    ids = [r.id for r in rules]
    for req in ("GRAIN-G0-IDENTITY", "GRAIN-G0-NOMATCH"):
        if req not in ids:
            raise RulesError(f"falta a regra {req}")
    if ids[0] != "GRAIN-G0-IDENTITY" or ids[-1] != "GRAIN-G0-NOMATCH":
        raise RulesError("G0-IDENTITY tem de ser a primeira e G0-NOMATCH a última")
    return RuleSet(rules=rules, version=str(doc.get("rules_version")), status=str(doc.get("status")), raw=doc)


def load(path: Path | str | None = None) -> RuleSet:
    p = Path(path) if path else rules_path()
    with open(p, encoding="utf-8") as fh:
        return parse(yaml.safe_load(fh))


def reprioritized(rs: RuleSet, order: list[str]) -> RuleSet:
    """Cópia com a ordem de prioridade trocada (só para o teste de mutação do gate de prioridade)."""
    by = {r.id: r for r in rs.rules}
    rules = [Rule(**{**by[i].__dict__, "priority": n}) for n, i in enumerate(order)]
    return RuleSet(rules=rules, version=rs.version + "+mutated", status="MUTATED", raw=rs.raw)


def eval_pred(name: str, arg, ctx) -> bool:
    """ctx: engine.Context. Todo predicado é total (devolve bool) sobre evidência KNOWN."""
    if name == "identity_class_in":
        return ctx.identity_class in arg
    if name == "identity_targets_min":
        return len(ctx.targets) >= int(arg)
    if name == "identity_targets_kind_in":
        return all(ctx.kind_of(t) in arg for t in ctx.targets)
    if name == "owner_kind_in":
        return ctx.owner.known and ctx.owner.value["kind"] in arg
    if name == "owner_targets_count":
        return len(ctx.owner_targets) == int(arg)
    if name == "owner_targets_kind_in":
        return bool(ctx.owner_targets) and all(ctx.kind_of(t) in arg for t in ctx.owner_targets)
    if name == "lifecycle_kind_in":
        return ctx.lifecycle.known and ctx.lifecycle.value["kind"] in arg
    if name == "lifecycle_target_resolved":
        return (ctx.lifecycle_target is not None) == bool(arg)
    if name == "lifecycle_target_consistent":
        ok = (not ctx.targets) or (ctx.lifecycle_target in ctx.targets)
        return ok == bool(arg)
    if name == "identity_composition_targets_min":
        ns = ctx.namespace_fields
        comp = [t for f, t in ctx.ident.refs.items() if f not in ns]
        return (len(comp) if ctx.n.by_role else len(set(comp))) >= int(arg)
    if name == "identity_path_parent":
        return (ctx.path_parent is not None and bool(ctx.ident.own)) == bool(arg)
    if name == "identity_targets_all_namespace":
        ns = ctx.namespace_fields
        ok = bool(ctx.ident.own) and bool(ctx.ident.refs) and all(f in ns for f in ctx.ident.refs)
        return ok == bool(arg)
    if name == "api_resource_status_in":
        return ctx.api.known and ctx.api.value["status"] in arg
    raise RulesError(f"predicado desconhecido: {name}")
