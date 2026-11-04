"""Motor do grão: classe de identidade, regras por prioridade e normalização de cima para baixo.

O motor é o mesmo nas duas camadas que o usam:
  * camada de schema (tipos Terraform → unidades canônicas C19), em bo.grain.schema;
  * camada de instância (configuração → ocorrências com identidade por hash), em bo.grain.instance.
Cada camada monta os nós (Node) com o pai estrutural efetivo e o alvo resolvido de cada campo de referência;
o motor decide cada nó só depois do pai e dos alvos (ordem topológica; ciclo dá UNKNOWN).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import rules as R
from .evidence import (C19_MISSING, CONTRADICTORY, KNOWN, PARENT, UNKNOWN, CandidateEvidence, Fact)

EXT = "EXT:"            # prefixo de nó de contêiner externo (T51): referenciado pela evidência, fora da decomposição
SEL = "SEL:"            # prefixo de nó SELECTOR (T60): predicado de seleção (chave e valor), sem ciclo de vida
G0_NEEDS = "GRAIN-G0-NEEDS"
G0_CYCLE = "GRAIN-G0-CYCLE"
G0_IDENTITY = "GRAIN-G0-IDENTITY"
G0_NOMATCH = "GRAIN-G0-NOMATCH"


@dataclass
class Node:
    nid: str
    provider: str
    cid: str                       # candidato na camada de schema (tipo, tipo.bloco..., tipo.bloco:grupo)
    resource_type: str
    block_path: tuple = ()
    group: str | None = None
    parent: str | None = None      # pai estrutural EFETIVO (transparentes já pulados)
    ev: CandidateEvidence = field(default_factory=CandidateEvidence)
    ref_targets: dict = field(default_factory=dict)   # campo canônico -> nid alvo ou None (não resolvido)
    atoms: list = field(default_factory=list)          # [(caminho completo no tipo, caminho na unidade)]
    values: dict = field(default_factory=dict)         # camada de instância: campo canônico -> valor bruto
    by_role: bool = False   # camada de schema: alvos contados por papel (campo), pois dois papéis podem ter o mesmo tipo


@dataclass
class Identity:
    cls: str
    own: list = field(default_factory=list)            # campos próprios da chave natural
    refs: dict = field(default_factory=dict)           # campo de referência da chave -> nid alvo
    key_fields: list = field(default_factory=list)     # para o C19
    anonymous: bool = False
    unresolved: list = field(default_factory=list)


@dataclass
class Decision:
    nid: str
    grain: str
    rule: str
    missing: list
    identity: Identity
    parent: str | None = None
    endpoints: dict = field(default_factory=dict)      # papel -> nid (vínculo)
    lifecycle: dict = field(default_factory=dict)      # {"kind", "target"}
    owner: dict = field(default_factory=dict)          # {"kind", "targets"}
    scope: dict = field(default_factory=dict)          # {"kind", "target"}
    api: dict | None = None
    label: str = ""
    notes: list = field(default_factory=list)
    trace: list = field(default_factory=list)
    cascade: list = field(default_factory=list)       # contêineres de namespace: relação cascade_delete_by
    own_api_lifecycle: bool = False                    # G2-CHILD: componente com operações próprias na API


def _order_missing(xs) -> list:
    s = set(xs)
    return [m for m in C19_MISSING if m in s]


def derive_identity(n: Node, kind_of) -> Identity:
    ev = n.ev
    idf, imp, nk = ev.fact("identity"), ev.fact("import_key"), ev.fact("element_name_key")
    ref_fields = {f for f, m in ev.field_map.items() if m.get("ref")}
    if CONTRADICTORY in (idf.state, imp.state, nk.state):
        return Identity("CONTRADICTORY")
    if idf.state == imp.state == nk.state == UNKNOWN:
        return Identity("ABSENT")
    api = ev.fact("api_resource")
    if api.known and api.value["status"] == "payload" and not idf.known:
        # carga útil da API do pai: só a alegação de identidade diz se é transparente (T0) ou elemento
        return Identity("ABSENT")
    absent = idf.known and idf.value["status"] == "absent"
    scope = surrogate = None
    anonymous = False
    own_api: list | None = None
    api_refs: list = []
    claim_keys: list = []
    if idf.known and not absent:
        v = idf.value
        scope, surrogate, anonymous = v["scope"], v["surrogate"], v["anonymous"]
        claim_keys = list(v["key_fields"])
        api_refs = [f for f in v["key_fields"] if f in ref_fields]
        own_api = [] if surrogate else [f for f in v["key_fields"] if f not in ref_fields]
    imp_refs: list = []
    own_imp: list | None = None
    if imp.known and imp.value["status"] == "present":
        imp_refs = [f for f in imp.value["fields"] if f in ref_fields]
        own_imp = [f for f in imp.value["fields"] if f not in ref_fields]
    own_nk = list(nk.value["fields"]) if nk.known and nk.value["status"] == "present" else None
    sets = {frozenset(x) for x in (own_api, own_imp, own_nk) if x}
    if len(sets) > 1:
        return Identity("CONTRADICTORY")
    if absent and (own_imp or own_nk):
        return Identity("CONTRADICTORY")
    if own_nk and anonymous:
        return Identity("CONTRADICTORY")
    own = sorted(next(iter(sets))) if sets else []
    named = bool(own_nk) or (bool(own) and not anonymous)
    refs_f = sorted(set(api_refs) | set(imp_refs))
    nested = n.parent is not None
    relative = absent or scope == "within_parent" or (own_nk is not None and scope is None)
    if relative and nested:
        refs_f = [PARENT] + refs_f
    elif relative and not nested and not refs_f and not absent:
        return Identity("CONTRADICTORY")
    if nested and scope is None and not absent and own_nk is None and not refs_f and not idf.known:
        return Identity("ABSENT")
    if surrogate and imp.state == UNKNOWN and not own_nk:
        return Identity("ABSENT")
    if surrogate and not own and not refs_f:
        own = ["$id"]
    refs, unresolved = {}, []
    for f in refs_f:
        t = n.parent if f == PARENT else n.ref_targets.get(f)
        if t is None or kind_of(t) == "UNKNOWN":
            unresolved.append(f)
        else:
            refs[f] = t
    key_fields = [f for f in own if f != "$id"] + [f for f in refs_f if f != PARENT]
    if surrogate and not key_fields:
        key_fields = claim_keys
    ident = Identity("", own=own, refs=refs, key_fields=sorted(set(key_fields)),
                     anonymous=bool(own) and not named and own != ["$id"], unresolved=unresolved)
    if unresolved:
        ident.cls = "UNRESOLVED"
        return ident
    t = list(refs.values()) if n.by_role else set(refs.values())
    if not own:
        ident.cls = "ORPHAN" if not t else ("BORROWED" if len(t) == 1 else "REF_TUPLE")
    else:
        ident.cls = "INDEPENDENT" if not t else ("WITHIN" if len(t) == 1 else "REF_TUPLE_PLUS")
    return ident


class Context:
    """Vista de um nó no momento da decisão (o que os predicados leem)."""

    def __init__(self, n: Node, ident: Identity, decided: dict, bindings: dict):
        self.n, self.ident, self.decided = n, ident, decided
        ev = n.ev
        self.identity_class = ident.cls
        # campos de referência que a evidência marca como contêiner de namespace (G4-NS)
        self.namespace_fields = {f for f, m in ev.field_map.items() if m.get("ref") and m.get("namespace")}
        # pai de composição marcado como segmento de caminho acima da unidade (G2-CHILD)
        pp = {f for f, m in ev.field_map.items() if m.get("ref") and m.get("path_parent")}
        if ev.parent_is_path_parent:
            pp.add(PARENT)
        comp = {f: t for f, t in ident.refs.items() if f not in self.namespace_fields}
        self.path_parent = None
        if comp and set(comp) <= pp and len(set(comp.values())) == 1:
            self.path_parent = next(iter(comp.values()))
        self.targets = sorted(ident.refs.values()) if n.by_role else sorted(set(ident.refs.values()))
        self.lifecycle: Fact = ev.fact("lifecycle_controller")
        self.owner: Fact = ev.fact("owner")
        self.scope: Fact = ev.fact("effective_scope")
        self.api: Fact = ev.fact("api_resource")
        self.unresolved_fields: set = set()
        self.lifecycle_target = self._one(self.lifecycle, "lifecycle_controller")
        self.owner_targets = self._many(self.owner, "owner")
        self.owner_via_binding = None
        if len(self.owner_targets) >= 2:
            b = bindings.get(tuple(sorted(self.owner_targets)))
            if b is not None:
                self.owner_via_binding = b
                self.owner_targets = [b]
        self.scope_target = self._one(self.scope, "effective_scope") if self.scope.known and \
            self.scope.value["kind"] in ("parent", "container") else None

    def _default_via(self):
        if self.n.parent is not None:
            return [PARENT]
        if len(self.targets) == 1:
            return [next(f for f, t in self.ident.refs.items())]
        return []

    def _resolve(self, f):
        t = self.n.parent if f == PARENT else self.n.ref_targets.get(f)
        if t is None or self.kind_of(t) == "UNKNOWN":
            return None
        return t

    def _one(self, fact: Fact, name: str):
        if not fact.known or fact.value["kind"] in ("self", "provider", "external", "global"):
            return None
        via = fact.value.get("via") or self._default_via()
        if name == "effective_scope" and fact.value["kind"] == "container" and not fact.value.get("via"):
            via = (self.owner.value.get("via") if self.owner.known else None) or via
        if len(via) != 1:
            self.unresolved_fields.add(name)
            return None
        t = self._resolve(via[0])
        if t is None:
            self.unresolved_fields.add(name)
        return t

    def _many(self, fact: Fact, name: str) -> list:
        if not fact.known or fact.value["kind"] != "parent":
            return []
        via = fact.value.get("via") or self._default_via()
        out = []
        for f in via:
            t = self._resolve(f)
            if t is None:
                self.unresolved_fields.add(name)
                return []
            out.append(t)
        if not out:
            self.unresolved_fields.add(name)
        return sorted(out) if self.n.by_role else sorted(set(out))

    def unit_of(self, nid):
        """A13 (0.1.10): a FACET não tem identidade própria (é grupo de atributos do dono); como ponta de vínculo ela
        é lida como a unidade dona da faceta (o pai que a G3 emitiu), subindo por facetas aninhadas."""
        seen = set()
        while nid in self.decided and self.decided[nid].grain == "FACET" and self.decided[nid].parent \
                and nid not in seen:
            seen.add(nid)
            nid = self.decided[nid].parent
        return nid

    def kind_of(self, nid):
        if nid.startswith(EXT):
            return "EXTERNAL"
        if nid.startswith(SEL):
            return "SELECTOR"
        d = self.decided.get(nid)
        return d.grain if d else "UNKNOWN"

    def unknown(self, fld: str) -> bool:
        f = {"lifecycle_controller": self.lifecycle, "owner": self.owner, "effective_scope": self.scope,
             "api_resource": self.api}[fld]
        return f.state != KNOWN or fld in self.unresolved_fields


def _label(n: Node, api: Fact) -> str:
    if api.known and api.value.get("label"):
        return str(api.value["label"])
    if n.ev.twin:
        return n.ev.twin.replace("_", " ")
    return (n.cid.split(".")[-1] if n.group is None else n.group).replace("_", " ")


def decide_node(n: Node, rs: R.RuleSet, decided: dict, bindings: dict) -> Decision:
    ident = derive_identity(n, lambda t: "EXTERNAL" if t.startswith(EXT) else "SELECTOR" if t.startswith(SEL) else
                            (decided[t].grain if t in decided else "UNKNOWN"))
    ctx = Context(n, ident, decided, bindings)
    trace = [f"identity_class={ident.cls}"]
    failed: list = []
    base = dict(nid=n.nid, identity=ident, label=_label(n, ctx.api),
                api=ctx.api.value if ctx.api.known else None)

    def fill(d: Decision) -> Decision:
        lk = ctx.lifecycle.value["kind"] if ctx.lifecycle.known else "UNKNOWN"
        ok = ctx.owner.value["kind"] if ctx.owner.known else "UNKNOWN"
        sk = ctx.scope.value["kind"] if ctx.scope.known else "UNKNOWN"
        d.lifecycle = {"kind": "UNKNOWN" if "lifecycle_controller" in d.missing else lk,
                       "target": None if "lifecycle_controller" in d.missing else ctx.lifecycle_target}
        d.owner = {"kind": "UNKNOWN" if "owner" in d.missing else ok,
                   "targets": [] if "owner" in d.missing else list(ctx.owner_targets)}
        d.scope = {"kind": "UNKNOWN" if "effective_scope" in d.missing else sk,
                   "target": None if "effective_scope" in d.missing else ctx.scope_target}
        if ctx.owner_via_binding:
            d.notes.append("faceta com vários donos: fica no vínculo entre eles")
        d.cascade = sorted({t for f, t in ident.refs.items() if f in ctx.namespace_fields})
        if d.rule == "GRAIN-G2-CHILD" and ctx.path_parent and ctx.path_parent not in d.cascade:
            d.cascade = sorted(d.cascade + [ctx.path_parent])
        d.trace = trace
        return d

    for rule in rs.rules:
        if not all(R.eval_pred(k, v, ctx) for k, v in rule.match.items()):
            continue
        trace.append(f"match {rule.id}")
        if rule.id == G0_IDENTITY:
            miss = ["identity"] + [f for f in rule.also_missing_if_unknown if ctx.unknown(f)]
            if ident.unresolved:
                miss += [m for m in ("lifecycle_controller", "owner", "effective_scope") if _via_hits(n, m, ident)]
            return fill(Decision(grain="UNKNOWN", rule=rule.id, missing=_order_missing(miss), **base))
        if rule.id == G0_NOMATCH:
            miss = _order_missing(failed) or ["identity"]
            return fill(Decision(grain="UNKNOWN", rule=rule.id, missing=miss, **base))
        miss = [f for f in rule.needs if ctx.unknown(f)]
        if miss:
            trace.append(f"needs {rule.id}: falta {miss}")
            d = Decision(grain="UNKNOWN", rule=G0_NEEDS, missing=_order_missing(miss), **base)
            d.notes.append(f"match de {rule.id} sem a evidência de que a regra precisa")
            return fill(d)
        bad = [k for k, v in rule.guard.items() if not R.eval_pred(k, v, ctx)]
        if bad:
            trace.append(f"guard {rule.id} falso: {bad}")
            failed += [R.PREDICATES[k] for k in bad]
            continue
        d = Decision(grain=rule.grain, rule=rule.id, missing=[], **base)
        par = rule.emit.get("parent")
        if par == "lifecycle_target":
            d.parent = ctx.lifecycle_target
        elif par == "owner_target":
            d.parent = ctx.owner_targets[0]
        elif par == "path_parent":
            d.parent = ctx.path_parent
            d.own_api_lifecycle = True
        if rule.emit.get("endpoints") == "identity_targets":
            d.endpoints = {(n.ev.parent_role if f == PARENT else f): ctx.unit_of(t) for f, t in ident.refs.items()}
            lifted = sorted(t for t in ident.refs.values() if ctx.unit_of(t) != t)
            if lifted:
                d.notes.append(f"ponta FACET lida como a unidade dona da faceta (A13): {lifted}")
        return fill(d)
    raise R.RulesError("nenhuma regra final (G0-NOMATCH ausente)")


def _via_hits(n: Node, fld: str, ident: Identity) -> bool:
    f = n.ev.fact(fld)
    if not f.known or f.value["kind"] not in ("parent", "container"):
        return False
    via = f.value.get("via") or ([PARENT] if n.parent is not None else ident.unresolved)
    return any(v in ident.unresolved for v in via)


def _deps(n: Node) -> set:
    ev = n.ev
    used = set()
    for fld in ("identity", "import_key"):
        for c in ev.claims.get(fld, []):
            used |= set(c.get("key_fields", []) or []) | set(c.get("fields", []) or [])
    for fld in ("lifecycle_controller", "owner", "effective_scope"):
        for c in ev.claims.get(fld, []):
            v = c.get("via")
            used |= ({v} if isinstance(v, str) else set(v or []))
    out = {n.parent} if n.parent else set()
    for f in used:
        t = n.ref_targets.get(f)
        if t:
            out.add(t)
    out.discard(n.nid)
    return out


def _identity_ref_count(n: Node) -> int:
    refs = {f for f, m in n.ev.field_map.items() if m.get("ref")}
    used = set()
    for fld in ("identity", "import_key"):
        for c in n.ev.claims.get(fld, []):
            used |= (set(c.get("key_fields", []) or []) | set(c.get("fields", []) or [])) & refs
    return len(used) + (1 if n.parent else 0)


def _multi_owner(n: Node) -> bool:
    return any(isinstance(c.get("via"), list) and len(c.get("via")) >= 2 for c in n.ev.claims.get("owner", []))


def decide_graph(nodes: list[Node], rs: R.RuleSet) -> dict[str, Decision]:
    """Decide todos os nós de cima para baixo. Determinístico: não depende da ordem da lista."""
    by = {n.nid: n for n in nodes}
    deps = {n.nid: {d for d in _deps(n) if d in by} for n in nodes}
    # faceta com vários donos espera os vínculos possíveis (nós com duas ou mais referências na identidade)
    maybe_binding = {n.nid for n in nodes if not _multi_owner(n) and _identity_ref_count(n) >= 2}
    for n in nodes:
        if _multi_owner(n):
            deps[n.nid] |= {b for b in maybe_binding if n.nid not in _reach(b, deps)}
    decided: dict[str, Decision] = {}
    bindings: dict = {}
    pending = set(by)
    while pending:
        ready = sorted(x for x in pending if deps[x] <= set(decided))
        if not ready:
            for x in sorted(pending):
                n = by[x]
                ident = Identity("CYCLE")
                d = Decision(nid=x, grain="UNKNOWN", rule=G0_CYCLE, missing=["identity"], identity=ident,
                             label=_label(n, n.ev.fact("api_resource")))
                d.lifecycle = {"kind": "UNKNOWN", "target": None}
                d.owner = {"kind": "UNKNOWN", "targets": []}
                d.scope = {"kind": "UNKNOWN", "target": None}
                d.trace = ["ciclo de dependência"]
                decided[x] = d
            break
        for x in ready:
            d = decide_node(by[x], rs, decided, bindings)
            decided[x] = d
            if d.grain == "BINDING":
                bindings[tuple(sorted(d.endpoints.values()))] = x
            pending.discard(x)
    return decided


def _reach(start, deps) -> set:
    seen, stack = set(), [start]
    while stack:
        x = stack.pop()
        for y in deps.get(x, ()):
            if y not in seen:
                seen.add(y)
                stack.append(y)
    return seen
