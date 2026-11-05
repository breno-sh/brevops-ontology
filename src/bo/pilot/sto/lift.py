"""Lifting: configuração Terraform (sintaxe JSON, fixture do oráculo) -> unidades neutras e valores tipados.

Decomposição pelo procedimento de grão com a evidência de serviço (C25), independente de ordem e de embalagem:
  contêiner     tipo que realiza sto:ObjectContainer; dono e ciclo de vida da camada de API;
  namespace     tipo que realiza sto:StorageNamespace (alvo da referência de identidade do contêiner);
  faceta        bloco ou atributo de um contêiner/namespace cujo conceito pertence a uma classe de configuração, ou
                recurso separado cujo dono (API) é o pai alcançado pela referência; ciclo de vida = o do pai;
  conta         tipo com alcance de conta (C25 type_scope): dono account:context, alcance todo contêiner da conta;
  UNKNOWN       dono em disputa (spec × doc), referência que não resolve, ou dono sem evidência de API.
Ids neutros: container:<endereço>, namespace:<endereço>, setting:<classe>@<dono> (dono = id da unidade,
account:context, namespace:context, UNRESOLVED:<endereço> ou DISPUTED:<endereço>).
O alcance efetivo segue as regras do c3 (cadeias de appliesTo); o ABox de bo.pilot.sto.abox materializa as
mesmas consequências por raciocínio e o teste confere que coincidem.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from . import common as C
from . import tbox as T

REF_RE = re.compile(r"^\$\{([a-z][a-z0-9_]*)\.([A-Za-z0-9_-]+)\.([a-z_]+)\}$")
VAR_RE = re.compile(r"^\$\{var\.([A-Za-z0-9_-]+)\}$")
MISSING_ORDER = ("owner", "effective_scope", "lifecycle_controller", "namespace")


@dataclass
class Value:
    addr: str
    rtype: str
    occ: tuple            # caminho com índices (('versioning_configuration', 0), 'status')
    atom_id: str
    raw: object
    term: dict
    concept: str
    unit_id: str | None = None
    component: str | None = None   # ocorrência de componente (regra de ciclo de vida)
    role: str = "config"            # config | wiring | context | out_of_slice

    @property
    def path(self) -> str:
        return C.path_of_atom(self.atom_id)


@dataclass
class Unit:
    unit_id: str
    cls: str | None
    kind: str
    owner: object
    effective_scope: object
    lifecycle_controller: object
    realized_by: list = field(default_factory=list)
    missing_evidence: list = field(default_factory=list)
    namespace: object = None
    disputed: list = field(default_factory=list)
    dispute: dict = field(default_factory=dict)
    rules: list = field(default_factory=list)

    def neutral(self) -> dict:
        d = {"kind": self.kind, "owner": self.owner, "lifecycle_controller": self.lifecycle_controller,
             "missing_evidence": list(self.missing_evidence)}
        if self.cls is None or self.cls not in ("ObjectContainer", "StorageNamespace"):
            d["effective_scope"] = self.effective_scope
        if self.namespace is not None:
            d["namespace"] = self.namespace
        if self.disputed:
            d["disputed"] = list(self.disputed)
            d["dispute"] = self.dispute
        return d


@dataclass
class Lifted:
    provider: str
    fixture_id: str
    resources: list
    units: dict
    values: list
    refs: dict                      # endereço -> endereço resolvido do dono (arestas)
    components: dict                # id do componente -> {setting, occ_key, addr}
    notes: list = field(default_factory=list)
    read: dict = field(default_factory=dict)   # completude da leitura da origem (fixture.read)

    def unit_of_container(self, addr: str) -> Unit | None:
        return self.units.get(f"container:{addr}")

    def containers(self) -> list[str]:
        return sorted(u[len("container:"):] for u in self.units if u.startswith("container:"))


# ----------------------------------------------------------------------------------------------------------
# termos (C00)
# ----------------------------------------------------------------------------------------------------------
def sym(*parts) -> str:
    return "SYM-" + C.short_id(*parts)


def term_of(v, ctx: str = "") -> dict:
    if isinstance(v, bool):
        return {"kind": "literal", "datatype": "bool", "value": v}
    if isinstance(v, (int, float)):
        return {"kind": "literal", "datatype": "number", "value": v}
    if v is None:
        return {"kind": "literal", "datatype": "null", "value": None}
    if isinstance(v, str):
        m = REF_RE.match(v)
        if m:
            return {"kind": "reference", "target_type": m.group(1), "target_address": f"{m.group(1)}.{sym(ctx, m.group(1), m.group(2))}",
                    "attribute": m.group(3)}
        m = VAR_RE.match(v)
        if m:
            return {"kind": "symbol", "symbol_id": sym(ctx, "var", m.group(1)), "name_class": "variable", "scope": "repo"}
        s = v.strip()
        if s.startswith("{") and s.endswith("}"):
            try:
                tree = json.loads(s)
            except ValueError:
                tree = None
            if isinstance(tree, dict):
                return _document(tree, ctx)
        return {"kind": "literal", "datatype": "string", "value": v}
    if isinstance(v, list):
        return {"kind": "literal", "datatype": "list", "value": v}
    if isinstance(v, dict):
        return {"kind": "literal", "datatype": "map", "value": v}
    return {"kind": "literal", "datatype": "string", "value": str(v)}


def _document(tree: dict, ctx: str) -> dict:
    """Documento de política: principais e identificadores de recurso viram símbolos (nunca ARN em claro)."""
    symbolized = []

    def walk(node, path):
        if isinstance(node, dict):
            out = {}
            for k, x in node.items():
                p = f"{path}/{k}"
                if k in ("Resource", "NotResource") or (isinstance(x, str) and ("${" in x or x.startswith("arn"))):
                    sid = sym(ctx, p, "res")
                    symbolized.append({"path": p, "symbol_id": sid, "role": "resource_name" if "Resource" in k else "identifier"})
                    out[k] = sid
                else:
                    out[k] = walk(x, p)
            return out
        if isinstance(node, list):
            return [walk(x, f"{path}/{i}") for i, x in enumerate(node)]
        return node

    return {"kind": "document", "format": "policy_json", "tree": walk(tree, ""), "symbolized": symbolized}


def ref_target(fx_res: dict, v) -> str | None:
    if not isinstance(v, str):
        return None
    m = REF_RE.match(v)
    if not m:
        return None
    addr = f"{m.group(1)}.{m.group(2)}"
    return addr if addr in fx_res else None


# ----------------------------------------------------------------------------------------------------------
# folhas
# ----------------------------------------------------------------------------------------------------------
def resources(fx: dict) -> list[tuple[str, str, dict]]:
    out = []
    for rtype, insts in ((fx.get("terraform") or {}).get("resource") or {}).items():
        for name, body in (insts or {}).items():
            out.append((rtype, name, body or {}))
    return sorted(out, key=lambda x: (x[0], x[1]))


def leaves(body: dict, prefix=()):
    """(occ, valor) de cada folha; bloco = lista de objetos (ou objeto) — mapa de atributo fica folha."""
    for k in sorted(body):
        if not prefix and k in C.META_ARGS:
            continue
        v = body[k]
        if isinstance(v, list) and v and all(isinstance(x, dict) for x in v):
            for i, b in enumerate(v):
                yield from leaves(b, prefix + ((k, i),))
        else:
            yield prefix + (k,), v


def atom_path(occ: tuple) -> str:
    return ".".join(p[0] if isinstance(p, tuple) else p for p in occ)


# ----------------------------------------------------------------------------------------------------------
# decomposição
# ----------------------------------------------------------------------------------------------------------
def _missing(*fields) -> list:
    return [f for f in MISSING_ORDER if f in fields]


def _block_class(provider: str, rtype: str, key: str, body_part, concept_of) -> str | None:
    """Classe de configuração realizada por um bloco ou atributo de topo (pelos conceitos das suas folhas)."""
    classes = set()
    if isinstance(body_part, list) and body_part and all(isinstance(x, dict) for x in body_part):
        for b in body_part:
            for occ, _ in leaves(b, ((key, 0),)):
                sc = T.setting_class_of(concept_of(f"{provider}:{rtype}:{atom_path(occ)}"))
                if sc:
                    classes.add(sc)
    else:
        sc = T.setting_class_of(concept_of(f"{provider}:{rtype}:{key}"))
        if sc:
            classes.add(sc)
    classes.discard("ObjectContainer")
    classes.discard("StorageNamespace")
    if len(classes) == 1:
        return classes.pop()
    return None if not classes else "AMBIGUOUS"


def _prefix_selects(rbody: dict, prefixes_path: str, members: list[str], res_by_addr: dict) -> list[str] | None:
    """Contêineres do namespace selecionados pelos prefixos do ciclo de vida; None = todos (alguma regra sem prefixo)."""
    rule_key, _, rest = prefixes_path.partition(".")
    rules = rbody.get(rule_key) or []
    rules = rules if isinstance(rules, list) else [rules]
    selected = set()
    for r in rules:
        prefixes = []
        cur = [r]
        for part in rest.split("."):
            nxt = []
            for c in cur:
                v = (c or {}).get(part)
                if isinstance(v, list) and v and all(isinstance(x, dict) for x in v):
                    nxt += v
                elif v is not None:
                    nxt.append(v)
            cur = nxt
        for c in cur:
            prefixes += c if isinstance(c, list) else [c]
        if not prefixes:
            return None
        for m in members:
            name = (res_by_addr.get(m) or {}).get("name") or ""
            for x in prefixes:
                if not isinstance(x, str):
                    continue
                if ("/" in x and name == x.split("/", 1)[0]) or ("/" not in x and name.startswith(x)):
                    selected.add(m)
    return sorted(selected)


def lift(fx: dict, claims, evidence) -> Lifted:
    prov = fx["provider"]
    fid = fx.get("fixture_id", "")
    res = resources(fx)
    res_by_addr = {f"{rt}.{n}": body for rt, n, body in res}
    concept_of = claims.concept
    ctype, ntype = T.CONTAINER_TYPE[prov], T.NAMESPACE_TYPE.get(prov)
    units: dict[str, Unit] = {}
    refs: dict[str, str] = {}
    wiring: dict[str, set] = {}     # endereço -> atributos que ligam ao dono (arestas, não valores)
    notes: list[str] = []
    containers = sorted(a for a in res_by_addr if a.split(".", 1)[0] == ctype)

    # namespaces
    if ntype:
        for a in sorted(x for x in res_by_addr if x.split(".", 1)[0] == ntype):
            ow, lc = evidence.owner(ntype), evidence.lifecycle(ntype)
            units[f"namespace:{a}"] = Unit(f"namespace:{a}", "StorageNamespace", "ENTITY", ow["kind"], None,
                                           lc["kind"], [a], [], rules=["DEC-OWN-API"])
    # contêineres (e o namespace pela referência de identidade)
    ns_of: dict[str, str | None] = {}
    for a in containers:
        ow, lc = evidence.owner(ctype), evidence.lifecycle(ctype)
        kind = "ENTITY" if ow["kind"] == "self" and lc["kind"] == "self" else "UNKNOWN"
        u = Unit(f"container:{a}", "ObjectContainer", kind, ow["kind"] if ow["kind"] != "UNKNOWN" else "UNKNOWN", None,
                 lc["kind"], [a], _missing(*([] if ow["kind"] == "self" else ["owner"]),
                                            *([] if lc["kind"] == "self" else ["lifecycle_controller"])),
                 rules=["DEC-OWN-API"])
        if ntype:
            irefs = evidence.get(ctype).identity_refs
            ns = None
            for attr, tgt in sorted(irefs.items()):
                if tgt == ntype:
                    ns = ref_target(res_by_addr, res_by_addr[a].get(attr))
                    if ns:
                        refs[a] = ns
                        wiring.setdefault(a, set()).add(attr)
            ns_of[a] = ns
            u.namespace = f"namespace:{ns}" if ns else "UNKNOWN"
            if not ns:
                u.missing_evidence = _missing(*u.missing_evidence, "namespace")
            u.rules.append("DEC-CONTAINER-IN-NAMESPACE")
        units[u.unit_id] = u

    def members_of(ns_addr: str) -> list[str]:
        return sorted(f"container:{c}" for c in containers if ns_of.get(c) == ns_addr)

    def add_setting(cls: str, owner_id: str, by: str, scope, lifecycle="parent", rules=()):
        uid = f"setting:{T.CLASSES[cls]['token']}@{owner_id}"
        u = units.get(uid)
        if u is None:
            u = Unit(uid, cls, "FACET", owner_id, scope, lifecycle, [], [], rules=list(rules))
            units[uid] = u
        elif isinstance(u.effective_scope, list) and isinstance(scope, list):
            u.effective_scope = sorted(set(u.effective_scope) | set(scope))
        u.realized_by = sorted(set(u.realized_by) | {by})
        u.rules = sorted(set(u.rules) | set(rules))
        return uid

    block_unit: dict[tuple[str, str], str] = {}     # (endereço, chave de topo) -> unidade de configuração
    res_unit: dict[str, str] = {}
    for a in containers:
        res_unit[a] = f"container:{a}"
    for a in res_by_addr:
        if f"namespace:{a}" in units:
            res_unit[a] = f"namespace:{a}"

    # facetas embutidas (blocos e atributos de contêiner ou namespace)
    for a, uid in sorted(res_unit.items()):
        rtype = a.split(".", 1)[0]
        body = res_by_addr[a]
        for key in sorted(body):
            if key in C.META_ARGS:
                continue
            cls = _block_class(prov, rtype, key, body[key], concept_of)
            if cls in (None, "AMBIGUOUS"):
                if cls == "AMBIGUOUS":
                    notes.append(f"{a}/{key}: bloco com conceitos de mais de uma classe")
                continue
            if uid.startswith("container:"):
                scope = [uid]
                rules = ["DEC-FACET-INLINE"]
            else:
                scope = members_of(a)
                rules = ["DEC-FACET-INLINE", "C3-SCOPE-NAMESPACE"]
            block_unit[(a, key)] = add_setting(cls, uid, f"{a}/{key}", scope, rules=rules)

    # configurações como recurso separado
    for rt, n, body in res:
        a = f"{rt}.{n}"
        if a in res_unit:
            continue
        cls = T.TYPE_CLASS.get(rt, (None,))[0]
        if cls is None or cls not in T.CLASSES:
            notes.append(f"{a}: tipo fora da tabela de realização")
            continue
        token = T.CLASSES[cls]["token"]
        te = evidence.get(rt)
        ow, lc = evidence.owner(rt, setting=True), evidence.lifecycle(rt)
        if rt in T.CONTEXT_NAMESPACE_TYPES:
            miss = _missing(*(["owner"] if ow["kind"] in ("UNKNOWN", "DISPUTED") else []),
                            *(["effective_scope"] if not te.scope_kinds and not te.type_scope else []),
                            *(["lifecycle_controller"] if lc["kind"] in ("UNKNOWN", "DISPUTED") else []))
            uid = f"setting:{token}@namespace:context"
            units[uid] = Unit(uid, cls, "UNKNOWN" if miss else "FACET", "UNKNOWN" if "owner" in miss else "namespace:context",
                              "UNKNOWN" if "effective_scope" in miss else "namespace:context",
                              "UNKNOWN" if "lifecycle_controller" in miss else lc["kind"], [a], miss,
                              rules=["DEC-NAMESPACE-CONTEXT"])
            res_unit[a] = uid
            continue
        if te.account_scoped:
            uid = add_setting(cls, "account:context", a, {"all_in": "account:context", "known": sorted(f"container:{c}" for c in containers)},
                              lifecycle=lc["kind"] if lc["kind"] != "UNKNOWN" else "UNKNOWN",
                              rules=["DEC-ACCOUNT-SCOPE", "C3-SCOPE-ACCOUNT"])
            res_unit[a] = uid
            continue
        via = list(ow.get("via") or []) or sorted(te.identity_refs)
        target = None
        for attr in via:
            target = ref_target(res_by_addr, body.get(attr))
            if target:
                break
        if target is None and ow.get("parent_types"):
            # sem atributo nomeado pela evidência: a referência a um recurso de um dos tipos do pai
            for attr in sorted(body):
                t2 = ref_target(res_by_addr, body.get(attr))
                if t2 and t2.split(".", 1)[0] in ow["parent_types"]:
                    target, via = t2, [attr]
                    break
        owner_unit = res_unit.get(target) if target else None
        if target:
            refs[a] = target
            wiring.setdefault(a, set()).update(x for x in via if body.get(x) is not None)
        published = evidence.disputes_of(rt)          # disputas spec × doc publicadas pelo SE (qualquer fato)
        if ow["kind"] == "DISPUTED" or lc["kind"] == "DISPUTED" or "effective_scope" in published:
            ds = sorted(f for f in ("owner", "lifecycle_controller", "effective_scope") if f in published)
            uid = f"setting:{token}@DISPUTED:{a}"
            units[uid] = Unit(uid, cls, "UNKNOWN", "UNKNOWN" if "owner" in ds else (owner_unit or "UNKNOWN"),
                              "UNKNOWN" if "effective_scope" in ds else ([owner_unit] if owner_unit else "UNKNOWN"),
                              "UNKNOWN" if "lifecycle_controller" in ds else "parent", [a], [],
                              disputed=ds, dispute={f: {"doc": evidence.get(rt).disputed[f]["doc"],
                                                        "spec": evidence.get(rt).disputed[f]["spec"]} for f in ds},
                              rules=["DEC-DISPUTED"])
            res_unit[a] = uid
            continue
        if ow["kind"] != "parent" or owner_unit is None:
            uid = f"setting:{token}@UNRESOLVED:{a}"
            units[uid] = Unit(uid, cls, "UNKNOWN", "UNKNOWN", "UNKNOWN", "UNKNOWN", [a], ["owner"],
                              rules=["REF-UNRESOLVED" if ow["kind"] == "parent" else "DEC-NO-API-OWNER"])
            res_unit[a] = uid
            continue
        if owner_unit.startswith("namespace:"):
            ns_addr = owner_unit[len("namespace:"):]
            scope = members_of(ns_addr)
            rules = ["DEC-FACET-REF", "C3-SCOPE-NAMESPACE"]
            sel_path = T.PREFIX_SELECTS_CONTAINER.get(rt)
            if sel_path:
                sel = _prefix_selects(body, sel_path, [m[len("container:"):] for m in scope], res_by_addr)
                if sel is not None:
                    scope = [f"container:{x}" for x in sel]
                    rules.append("C3-SCOPE-PREFIX")
        else:
            scope = [owner_unit]
            rules = ["DEC-FACET-REF"]
        res_unit[a] = add_setting(cls, owner_unit, a, scope, rules=rules)

    # valores
    values: list[Value] = []
    components: dict = {}
    for rt, n, body in res:
        a = f"{rt}.{n}"
        for occ, raw in leaves(body):
            atom = f"{prov}:{rt}:{atom_path(occ)}"
            top = occ[0][0] if isinstance(occ[0], tuple) else occ[0]
            unit = block_unit.get((a, top)) or res_unit.get(a)
            concept = concept_of(atom)
            v = Value(a, rt, occ, atom, raw, term_of(raw, fid), concept, unit)
            # papel do valor
            if len(occ) == 1 and occ[0] in wiring.get(a, ()) and v.term["kind"] == "reference":
                v.role = "wiring"
            elif T.prop_local(concept) in T.CONTEXT_CONCEPTS:
                v.role = "context"
            elif T.concept_class(concept) is None:
                # sem conceito: fora da fatia só em unidade de entidade (identidade/posicionamento do contêiner ou
                # do namespace); dentro de faceta ou componente é configuração não coberta e bloqueia (P1)
                uu = units.get(unit) if unit else None
                if uu is not None and uu.cls in ("ObjectContainer", "StorageNamespace"):
                    v.role = "out_of_slice"
            # componente (regra de ciclo de vida): chave de ocorrência = nome/id da regra, senão o índice
            if unit and T.concept_class(concept) == "LifecycleRule" and isinstance(occ[0], tuple):
                rk, ri = occ[0]
                rb = body.get(rk)
                rb = (rb if isinstance(rb, list) else [rb])[ri] if rb else {}
                key = None
                for kname in ("id", "name"):
                    if isinstance(rb, dict) and isinstance(rb.get(kname), str):
                        key = f"{kname}={rb[kname]}"
                        break
                comp = f"{unit}#rule[{key or ri}]"
                components.setdefault(comp, {"setting": unit, "occ_key": key or str(ri), "addr": a, "block": rk,
                                             "index": ri})
                v.component = comp
            values.append(v)
    return Lifted(prov, fid, res, units, values, refs, components, notes, dict(fx.get("read") or {}))


def decomposition(lf: Lifted) -> dict:
    return {uid: u.neutral() for uid, u in sorted(lf.units.items())}
