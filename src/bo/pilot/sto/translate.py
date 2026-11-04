"""Tradução de uma configuração da fatia sto para outro provedor pelos três controles, com a MESMA entrada, a
MESMA política de perda (bo.pilot.sto.policy) e as MESMAS transformações (registro fechado do C10).

Passo 1 (igual nos três): transporte por valor pela tabela de alegações OK (guarda, transformação, perda).
Passo 2 (o que muda entre controles): onde o valor transportado mora no destino.
  c1_table     sem modelo: um recurso de destino por (tipo de destino, recurso de origem); nenhuma referência
               nova; nada de alcance.
  c2_taxonomy  taxonomia + realizações: a faceta segue o dono asserido (facetOf) até o contêiner; o destino
               põe o valor no contêiner, no namespace dele ou num recurso de configuração que referencia o dono.
  c3_full      c2 + axiomas: alcance efetivo por cadeia (faceta de namespace/conta alcança os contêineres), conflito
               de disjunção/funcional bloqueia a tradução, e alcance do destino maior que o traduzido vira perda
               declarada SCOPE_WIDENED (justificada pelo axioma de cadeia).
Saída: rastro C23 por valor, graph_ir e lowering_plan C26, a configuração-alvo (sintaxe JSON do Terraform, só o
que o plano diz) e o mapa de contêineres para o julgamento.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from bo.transforms import guards as G
from bo.transforms import registry as R
from bo.transforms.errors import DeclarationError, NoUnit, OutOfDomain, SymbolicInput, TransformError, UnknownInput

from . import abox as A
from . import atoms as ATM
from . import common as C
from . import policy as P
from . import tbox as T

ERR_CODE = [(SymbolicInput, "UNKNOWN_SYMBOLIC_INPUT"), (UnknownInput, "UNKNOWN_INPUT"), (NoUnit, "NO_UNIT"),
            (OutOfDomain, "TRANSFORM_OUT_OF_DOMAIN"), (DeclarationError, "TRANSFORM_OUT_OF_DOMAIN"),
            (TransformError, "TRANSFORM_OUT_OF_DOMAIN")]


# ----------------------------------------------------------------------------------------------------------
# passo 1: transporte por valor (idêntico nos três controles)
# ----------------------------------------------------------------------------------------------------------
@dataclass
class Carry:
    value: object
    result: str                      # carried | blocked | omitted
    code: str | None = None
    rule: str | None = None
    detail: str | None = None
    view: object = None
    out_atom: str | None = None
    out_value: object = None
    out_term: dict | None = None
    transform: dict | None = None
    guard: dict | None = None
    losses: list = field(default_factory=list)


def _literal_value(term: dict):
    if term["kind"] == "literal":
        return term["value"]
    return None


def _guard_ctx(lf, v, inverse: bool) -> dict:
    role = "object" if inverse else "subject"
    ctx = {}
    for x in lf.values:
        if x.addr == v.addr and x.term["kind"] == "literal":
            ctx[f"{role}.{x.path}"] = x.raw
    return ctx


def transport(lf, v, dst: str, claims) -> Carry:
    views = claims.views(v.atom_id, lf.provider, dst)
    if v.role == "out_of_slice":
        return Carry(v, "blocked", "NO_REALIZATION", "T-OUT-OF-SLICE", "átomo de entidade sem conceito da fatia (bo:UNGLOSSED)")
    if not T.concept_class(v.concept):
        return Carry(v, "blocked", "NO_REALIZATION", "T-UNGLOSSED-IN-FACET",
                     "átomo sem conceito da fatia dentro de faceta: configuração não coberta")
    if v.term["kind"] == "literal" and v.term["value"] is None:
        return Carry(v, "omitted")
    if not views:
        return Carry(v, "blocked", "NO_REALIZATION", "T-NO-CORRESPONDENCE", f"nenhuma alegação liga o átomo a {dst}")
    ok = [w for w in views if w.claim.verdict == "OK"]
    if not ok:
        vv = sorted(views, key=lambda w: w.claim.claim_id)[0]
        code = P.VERDICT_BLOCK.get(vv.claim.verdict, "UNPROVEN")
        return Carry(v, "blocked", code, "T-VERDICT", f"veredito {vv.claim.verdict} da alegação", view=vv)
    moving = [w for w in ok if w.relation != "related" and w.claim.transport_fidelity != "none"]
    if not moving:
        vv = sorted(ok, key=lambda w: w.claim.claim_id)[0]
        return Carry(v, "blocked", "RELATED_ONLY", "T-RELATED", "alegação OK sem transporte (related ou fidelidade none)", view=vv)
    live, guard_info = [], None
    for w in sorted(moving, key=lambda w: (w.claim.claim_id, w.inverse)):
        g = w.guard or {"all": []}
        if not g.get("all"):
            live.append((w, {"guard": {"all": []}, "result": "TRUE"}))
            continue
        try:
            res, _ = G.evaluate(g, _guard_ctx(lf, v, w.inverse))
        except Exception:                                     # guarda mal tipada: indeterminada
            res = "INDETERMINATE"
        info = {"guard": g, "result": res}
        if res == "TRUE":
            live.append((w, info))
        elif guard_info is None or res == "INDETERMINATE":
            guard_info = (w, info)
    if not live:
        w, info = guard_info
        code = "CONDITION_FALSE" if info["result"] == "FALSE" else "CONDITION_INDETERMINATE"
        return Carry(v, "blocked", code, "T-GUARD", "guarda da alegação não vale", view=w, guard=info)
    if len({w.dst_atom for w, _ in live}) > 1:
        w, info = live[0]
        return Carry(v, "blocked", "AMBIGUOUS_TARGET", "T-AMBIGUOUS",
                     "mais de um átomo de destino com guarda verdadeira: " + ", ".join(sorted({x.dst_atom for x, _ in live})),
                     view=w, guard=info)
    w, info = live[0]
    if w.relation in ("broad", "narrow") or w.domain_relation in ("superset", "overlap", "disjoint"):
        if not w.membership_predicate:
            return Carry(v, "blocked", "OUT_OF_SUBSET", "T-MEMBERSHIP",
                         f"domínio de destino {w.domain_relation} sem predicado de pertença", view=w, guard=info)
    fn = w.translation_fn or {"name": "identity", "params": {}}
    chain = R.chain_of(fn)
    extra_loss = []
    if w.inverse:
        inv = []
        for item in reversed(chain):
            iv = R.inverse_of(item["name"], item.get("params") or {})
            if iv is None:
                return Carry(v, "blocked", "TRANSFORM_OUT_OF_DOMAIN", "T-NO-INVERSE",
                             f"{item['name']} não tem inversa no registro", view=w, guard=info)
            inv.append({"name": iv[0], "params": iv[1]})
            if getattr(R.get(item["name"]), "partial", False):
                extra_loss.append({"kind": "semantic", "why": f"inversa parcial de {item['name']}"})
        chain = inv
    t = v.term
    if t["kind"] in ("symbol", "reference", "expression"):
        if all(c["name"] == "identity" for c in chain):
            out_term, out_value = t, None
        else:
            return Carry(v, "blocked", "UNKNOWN_SYMBOLIC_INPUT", "T-SYMBOLIC", "valor simbólico só passa por identity",
                         view=w, guard=info)
    elif t["kind"] in ("withheld",):
        return Carry(v, "blocked", "UNKNOWN_INPUT", "T-WITHHELD", "valor retido não é lido", view=w, guard=info)
    elif t["kind"] == "document":
        if all(c["name"] == "identity" for c in chain):
            out_term, out_value = t, v.raw
        else:
            return Carry(v, "blocked", "TRANSFORM_OUT_OF_DOMAIN", "T-DOCUMENT", "documento só passa por identity",
                         view=w, guard=info)
    else:
        try:
            out_value = R.apply_chain(chain, v.raw)
        except TransformError as e:
            code = next(c for k, c in ERR_CODE if isinstance(e, k))
            return Carry(v, "blocked", code, "T-TRANSFORM", str(e)[:200], view=w, guard=info,
                         transform=chain[0] if len(chain) == 1 else {"name": "chain", "params": {"chain": chain}})
        out_term = _term_of_value(out_value)
    losses = [x for x in (w.loss_contract or []) if isinstance(x, dict)] + extra_loss
    tf = chain[0] if len(chain) == 1 else {"name": "chain", "params": {"chain": chain}}
    return Carry(v, "carried", view=w, out_atom=w.dst_atom, out_value=out_value, out_term=out_term,
                 transform={"name": tf["name"], "params": tf.get("params") or {}}, guard=info, losses=losses)


def _term_of_value(x) -> dict:
    if isinstance(x, bool):
        return {"kind": "literal", "datatype": "bool", "value": x}
    if isinstance(x, (int, float)):
        return {"kind": "literal", "datatype": "number", "value": x}
    if isinstance(x, list):
        return {"kind": "literal", "datatype": "list", "value": x}
    if isinstance(x, dict):
        return {"kind": "literal", "datatype": "map", "value": x}
    if x is None:
        return {"kind": "literal", "datatype": "null", "value": None}
    return {"kind": "literal", "datatype": "string", "value": str(x)}


# ----------------------------------------------------------------------------------------------------------
# passo 2: grafo de destino
# ----------------------------------------------------------------------------------------------------------
@dataclass
class Node:
    node_id: str
    rtype: str
    cls: str
    role: str                         # container | namespace | setting | parent | c1
    src_key: str
    values: dict = field(default_factory=dict)       # campo -> (termo, origem, marcado, valor bruto)
    refs: list = field(default_factory=list)         # (campo, nó alvo, atributo)
    losses: list = field(default_factory=list)       # {code, field, detail}
    env: bool = False
    component_of: str | None = None


@dataclass
class Translation:
    control: str
    src: object
    dst: str
    carries: list
    nodes: dict
    container_map: dict
    blocked: list                       # (código, regra, detalhe) que impedem a unidade completa
    effects: list                       # códigos de perda do oráculo declarados (política)
    justifying: dict                    # id do valor -> axiomas
    clashes: list
    contexts: list
    inferred: dict = field(default_factory=dict)    # unit_id -> classes inferidas (c2/c3)
    individuals: dict = field(default_factory=dict)
    env_bystanders: list = field(default_factory=list)

    @property
    def complete(self) -> bool:
        return not self.blocked


class Graph:
    def __init__(self, dst: str):
        self.dst = dst
        self.nodes: dict[str, Node] = {}
        self.by_key: dict = {}

    def get(self, key, rtype, cls, role, src_key) -> Node:
        if key in self.by_key:
            return self.nodes[self.by_key[key]]
        nid = f"r{len(self.nodes) + 1}"
        n = Node(nid, rtype, cls, role, src_key)
        self.nodes[nid] = n
        self.by_key[key] = nid
        return n


def _field(dst_path: str, comp_index: int | None, atoms_t) -> str:
    """Caminho do campo no plano: índice só no bloco repetido que contém o componente (regra)."""
    parts = dst_path.split(".")
    if comp_index is None or not atoms_t:
        return dst_path
    for i in range(1, len(parts)):
        blk = ".".join(parts[:i])
        if atoms_t.is_block(blk):
            return ".".join(parts[:i] + [str(comp_index)] + parts[i:])
    return dst_path


def translate(lf, dst: str, claims, control: str, tbox_ix: dict, env: dict | None = None,
              carries: list | None = None) -> Translation:
    env = env or {}
    atoms = ATM.load()
    carries = carries if carries is not None else [transport(lf, v, dst, claims) for v in lf.values
                                                   if v.role != "wiring"]
    level = control
    ix = tbox_ix.get(level)
    tr_src, iri = A.abox_of(lf)
    closure = A.reason(tr_src, ix)
    blocked, justifying, clashes, contexts = [], {}, [], []
    if level == "c3_full" and closure.clashes:
        clashes = closure.clashes
        blocked.append(("SHACL_VIOLATION", "T-C3-INCONSISTENT",
                        "ABox de origem inconsistente com o TBox do c3: " + "; ".join(
                            f"{c['kind']} {c.get('classes') or c.get('property')}" for c in clashes)))
    back = {v: k for k, v in iri.items()}
    scope = {}
    if level != "c1_table":
        for uid in lf.units:
            if uid in iri:
                scope[uid] = sorted(back.get(o, o) for o in closure.objects(iri[uid], A.S("appliesTo")))
    g = Graph(dst)
    ctype, ntype = T.CONTAINER_TYPE[dst], T.NAMESPACE_TYPE.get(dst)
    cmap: dict[str, str] = {}
    # contêineres de destino
    src_containers = lf.containers()
    for sc in src_containers:
        key = ("c1", ctype, sc) if level == "c1_table" else ("container", sc)
        n = g.get(key, ctype, "ObjectContainer", "container" if level != "c1_table" else "c1", sc)
        cmap[sc] = n.node_id
    ns_nodes: dict[str, Node] = {}

    def ns_of(cnode: Node) -> Node:
        if cnode.node_id in ns_nodes:
            return ns_nodes[cnode.node_id]
        src_c = lf.units.get(f"container:{cnode.src_key}")
        src_ns = src_c.namespace if src_c is not None and isinstance(src_c.namespace, str) else None
        share = src_ns if (src_ns and src_ns.startswith("namespace:")) else f"per:{cnode.src_key}"
        if env.get("bystanders"):
            share = "env:shared"
        n = g.get(("namespace", share), ntype, "StorageNamespace", "namespace", share)
        ns_nodes[cnode.node_id] = n
        return n

    def place(c: Carry):
        """Nós de destino que recebem o valor transportado; [] com motivo quando não há unidade."""
        v = c.value
        dtype, dpath = C.type_of_atom(c.out_atom), C.path_of_atom(c.out_atom)
        if level == "c1_table":
            key = ("c1", dtype, v.addr)
            n = g.get(key, dtype, T.TYPE_CLASS.get(dtype, ("?",))[0], "c1", v.addr)
            return [(n, None)], []
        u = lf.units.get(v.unit_id) if v.unit_id else None
        if u is None:
            return [], ["NO_UNIT", "T-NO-UNIT", "valor sem unidade de configuração"]
        if u.cls == "ObjectContainer":
            conts = [u.unit_id]
        elif u.cls == "StorageNamespace":
            conts = sorted(x for x, uu in lf.units.items() if uu.cls == "ObjectContainer" and uu.namespace == u.unit_id)
            if T.concept_class(v.concept) != "ObjectContainer":
                return [], ["NO_UNIT", "T-NAMESPACE-VALUE", "valor do namespace sem classe de configuração"]
        elif isinstance(u.owner, str) and u.owner.startswith("container:"):
            conts = [u.owner]
            justifying.setdefault(id(v), []).append("sto:facetOfContainer ⊑ sto:appliesTo")
        elif u.kind == "FACET":
            conts = [x for x in scope.get(u.unit_id, []) if x.startswith("container:")]
            if not conts:
                return [], ["NO_UNIT", "T-NO-SCOPE",
                            f"faceta de {u.owner} sem contêiner alcançado (o controle não infere o alcance)"]
            justifying.setdefault(id(v), []).append("sto:scopeAnchor ∘ sto:hasContainer ⊑ sto:appliesTo")
        else:
            return [], ["NO_UNIT", "T-UNIT-UNKNOWN", f"unidade {u.unit_id} {u.kind}: dono sem evidência"]
        out = []
        for cu in conts:
            sc = cu[len("container:"):]
            cn = g.nodes[cmap[sc]]
            comp_index = None
            if v.component:
                comps = sorted(k for k, d in lf.components.items() if d["setting"] == lf.components[v.component]["setting"])
                comp_index = comps.index(v.component)
            if dtype == ctype:
                out.append((cn, comp_index))
            elif dtype == ntype:
                out.append((ns_of(cn), comp_index))
            else:
                rf = T.REF_FIELD.get(dtype)
                if rf is None:
                    return [], ["NO_REALIZATION", "T-NO-LOWERING", f"tipo de destino {dtype} sem descritor de lowering"]
                owner = ns_of(cn) if (ntype and rf[0] == "storage_account_id") else cn
                sn = g.get(("setting", dtype, owner.node_id), dtype, T.TYPE_CLASS.get(dtype, ("?",))[0], "setting",
                           owner.src_key)
                if not any(r[0] == rf[0] for r in sn.refs):
                    sn.refs.append((rf[0], owner.node_id, rf[1]))
                out.append((sn, comp_index))
        return out, []

    for c in carries:
        v = c.value
        if c.result == "omitted":
            continue
        if c.result == "blocked":
            if v.role == "config":
                blocked.append((c.code, c.rule, f"{v.atom_id}: {c.detail}"))
            elif v.role == "context":
                contexts.append({"atom": v.atom_id, "code": c.code})
            continue
        targets, why = place(c)
        if why:
            c2 = Carry(v, "blocked", why[0], why[1], why[2], view=c.view, guard=c.guard, transform=c.transform)
            c.result, c.code, c.rule, c.detail = c2.result, c2.code, c2.rule, c2.detail
            c.out_atom = None
            if v.role == "config":
                blocked.append((c.code, c.rule, f"{v.atom_id}: {c.detail}"))
            continue
        for n, comp_index in targets:
            fld = _field(C.path_of_atom(c.out_atom), comp_index, atoms.get(n.rtype))
            prev = n.values.get(fld)
            if prev is not None and C.canon(prev[0]) != C.canon(c.out_term):
                blocked.append(("AMBIGUOUS_TARGET", "T-CONFLICT", f"{n.rtype}.{fld}: dois valores transportados"))
                continue
            n.values[fld] = (c.out_term, "carried", False, c.out_value)
            for ls in c.losses:
                # o campo da perda é o átomo de ORIGEM (o que se perdeu da origem); o campo de destino vai no
                # detalhe: perda em campo de destino que também é valor é recusada por harness (CONFLICTING_VALUES)
                n.losses.append({"code": P.field_loss_code(ls), "field": v.atom_id,
                                 "detail": (f"{fld}: " + (ls.get("why") or ls.get("kind") or "perda declarada"))[:200]})
    # dependências compartilhadas e campos obrigatórios (contexto declarado, nunca default inventado)
    for n in list(g.nodes.values()):
        sp = T.SHARED_PARENT.get(n.rtype)
        if sp:
            pn = g.get(("parent", sp[0], n.node_id), sp[0], "ResourceGroup", "parent", n.src_key)
            if not any(r[0] == sp[1] for r in n.refs):
                n.refs.append((sp[1], pn.node_id, sp[2]))
        if n.rtype == ctype and ntype and level != "c1_table":
            nsn = ns_of(n)
            rf = T.REF_FIELD.get(ctype)
            if rf and not any(r[0] == rf[0] for r in n.refs):
                n.refs.append((rf[0], nsn.node_id, rf[1]))
    for n in g.nodes.values():
        for fld, (kind, what) in T.DEPLOY_CONTEXT.get(n.rtype, {}).items():
            if fld in n.values or any(r[0] == fld for r in n.refs):
                continue
            if kind == "literal":
                n.values[fld] = ({"kind": "literal", "datatype": "string", "value": what}, "synthesized", True, what)
            else:
                n.values[fld] = ({"kind": "symbol", "symbol_id": "SYM-" + C.short_id("ctx", what), "name_class": "variable",
                                  "scope": "repo"}, "synthesized", True, None)
        nf = T.NAME_FIELD.get(n.rtype)
        if nf and nf not in n.values:
            if n.role in ("namespace", "parent"):
                nm = ("bosto" + C.short_id(lf.fixture_id, n.node_id)[:10]) if n.rtype == "azurerm_storage_account" else (
                    "bo-sto-" + C.short_id(lf.fixture_id, n.node_id)[:10])
                n.values[nf] = ({"kind": "literal", "datatype": "string", "value": nm}, "synthesized", True, nm)
    # alcance no destino (c3): faceta de namespace que alcança mais contêineres do que os traduzidos
    effects = set()
    for n in g.nodes.values():
        for ls in n.losses:
            effects |= P.effects_of(ls["code"], dst, n.rtype, ls["field"], claims.concept)
    bystanders = []
    if ntype:
        for b in env.get("bystanders", []):
            nsn = None
            for cn in (g.nodes[x] for x in cmap.values()):
                nsn = ns_of(cn)
            if nsn is not None:
                bystanders.append({"container": b["container"], "namespace_node": nsn.node_id, "before": b.get("before", {})})
    if level != "c1_table" and ntype:
        tgt_scope = _target_scope(g, cmap, bystanders, ix)
        translated = {f"container:{n}" for n in cmap.values()}
        for n in g.nodes.values():
            anchor = n.node_id if n.role == "namespace" else next(
                (t for f, t, _ in n.refs if g.nodes[t].role == "namespace"), None) if n.role == "setting" else None
            if anchor is None:
                continue
            extra = sorted(set(tgt_scope.get(anchor, [])) - translated)
            setting_fields = [f for f in n.values
                              if (P.field_class(dst, n.rtype, f, claims.concept) or "ObjectContainer") != "ObjectContainer"]
            if extra and setting_fields:
                for f in sorted(setting_fields):
                    n.losses.append({"code": "SCOPE_WIDENED", "field": f,
                                     "detail": "configuração do namespace alcança contêineres além dos traduzidos: "
                                               + ", ".join(x.split(":", 1)[1] for x in extra)})
                effects.add("SCOPE_WIDENED")
                for c in carries:
                    if c.result == "carried":
                        justifying.setdefault(id(c.value), []).append("sto:scopeAnchor ∘ sto:hasContainer ⊑ sto:appliesTo")
    return Translation(control, lf, dst, carries, g.nodes, {sc: cmap[sc] for sc in src_containers}, blocked,
                       sorted(effects), justifying, clashes, contexts,
                       inferred={uid: sorted(A._short(t) for t in closure.types(iri[uid])) for uid in lf.units if uid in iri},
                       individuals=iri, env_bystanders=bystanders)


def _target_scope(g: Graph, cmap: dict, bystanders: list, ix) -> dict:
    """Fecho do ABox de destino: nó de configuração -> contêineres alcançados (só o c3 tem a cadeia)."""
    tr = set()
    for n in g.nodes.values():
        if n.role == "container":
            tr.add((A.IND + n.node_id, A.TYPE, A.S("ObjectContainer")))
            for f, tgt, _ in n.refs:
                if g.nodes[tgt].role == "namespace":
                    tr.add((A.IND + n.node_id, A.S("inScope"), A.IND + tgt))
        if n.role == "namespace":
            tr.add((A.IND + n.node_id, A.TYPE, A.S("StorageNamespace")))
            tr.add((A.IND + n.node_id + "#settings", A.S("facetOfNamespace"), A.IND + n.node_id))
            tr.add((A.IND + n.node_id + "#settings", A.S("scopeAnchor"), A.IND + n.node_id))
    for b in bystanders:
        bi = A.IND + "env:" + b["container"]
        tr.add((bi, A.TYPE, A.S("ObjectContainer")))
        tr.add((bi, A.S("inScope"), A.IND + b["namespace_node"]))
    cl = A.reason(tr, ix)
    out = {}
    for n in g.nodes.values():
        if n.role == "namespace":
            reached = cl.objects(A.IND + n.node_id + "#settings", A.S("appliesTo"))
            out[n.node_id] = sorted("container:" + x[len(A.IND):] for x in reached)
    return out
