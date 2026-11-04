"""IR de grafo e plano de lowering (C26 1.2.0) a partir de uma tradução, e a configuração-alvo que o plano descreve.

Regra central: o plano é tudo o que o HCL terá. Valor transportado entra como carried; contexto de implantação
declarado (bo.pilot.sto.tbox.DEPLOY_CONTEXT) e nomes de namespace/grupo entram como synthesized + marked;
referências citam o nó do grafo (target_node, C00 3.0.1) e o passo de que dependem. A configuração-alvo em sintaxe
JSON (para o oráculo) é derivada só do plano, e o teste confere folha a folha que ela e o plano coincidem.
"""

from __future__ import annotations

from . import atoms as ATM
from . import common as C
from . import tbox as T

ROLE_ORDER = {"parent": 0, "namespace": 1, "container": 2, "c1": 2, "setting": 3}
CLASS_IRI = {"ResourceGroup": "bo:IndependentResource"}


def _sym(pid: str, node_id: str) -> str:
    return "SYM-" + C.short_id(pid, node_id)


def _order(tr) -> list:
    nodes = list(tr.nodes.values())
    deps = {n.node_id: {t for _, t, _ in n.refs} for n in nodes}
    done, out = set(), []
    pending = sorted(nodes, key=lambda n: (ROLE_ORDER.get(n.role, 9), int(n.node_id[1:])))
    while pending:
        progressed = False
        for n in list(pending):
            if deps[n.node_id] <= done:
                out.append(n)
                done.add(n.node_id)
                pending.remove(n)
                progressed = True
        if not progressed:                     # ciclo: não acontece no modelo; ordem estável e fecho aberto
            out += pending
            break
    return out


def build(tr, case: str, src_provider: str) -> tuple[dict, dict]:
    """(graph_ir, lowering_plan) da tradução."""
    pid = f"LP-PSTO-{C.CONTROL_CODE[tr.control].upper()}-{case}"
    gid = f"GIR-PSTO-{C.CONTROL_CODE[tr.control].upper()}-{case}"
    ordered = _order(tr)
    order_of = {n.node_id: i + 1 for i, n in enumerate(ordered)}
    terms, term_ids = [], {}

    def term_id(t: dict) -> str:
        k = C.canon(t)
        if k not in term_ids:
            term_ids[k] = f"t{len(terms) + 1}"
            terms.append({"term_id": term_ids[k], "term": t})
        return term_ids[k]

    resources, components, references = [], [], []
    for n in ordered:
        resources.append({"node_id": n.node_id, "class_iri": CLASS_IRI.get(n.cls, "sto:" + n.cls) if n.cls != "?" else "bo:Unit"})
        for f, tgt, _ in n.refs:
            tn = tr.nodes[tgt]
            kind = "facet_of" if n.role == "setting" else "reference"
            prop = "bo:facetOf" if kind == "facet_of" else ("sto:inScope" if tn.role == "namespace" else "bo:references")
            references.append({"from": n.node_id, "to": tgt, "property_iri": prop, "kind": kind})
    comp_seen = set()
    for n in ordered:
        for f in sorted(n.values):
            parts = f.split(".")
            for i, p in enumerate(parts):
                if p.isdigit():
                    key = (n.node_id, tuple(parts[:i + 1]))
                    if key not in comp_seen:
                        comp_seen.add(key)
                        components.append({"node_id": f"c{len(components) + 1}", "of": n.node_id,
                                           "class_iri": "sto:LifecycleRule", "occurrence_key": list(parts[:i + 1])})
                    break
    steps = []
    for n in ordered:
        vals, unknowns = [], []
        for f in sorted(n.values):
            term, origin, marked, _ = n.values[f]
            vals.append({"field": f, "term": term, "origin": origin, "marked": bool(marked)})
            if term["kind"] == "symbol":
                unknowns.append({"term_id": term_id(term), "reason": "contexto de implantação ligado na execução (variável sem default)"})
        for f, tgt, attr in sorted(n.refs):
            tn = tr.nodes[tgt]
            vals.append({"field": f, "origin": "carried", "marked": False,
                         "term": {"kind": "reference", "target_type": tn.rtype,
                                  "target_address": f"{tn.rtype}.{_sym(pid, tgt)}", "attribute": attr, "target_node": tgt}})
        losses = []
        seen = set()
        for ls in n.losses:
            k = (ls["code"], ls["field"])
            if k in seen:
                continue
            seen.add(k)
            losses.append({"code": ls["code"], "field": ls["field"], "detail": ls.get("detail") or "perda declarada"})
        deps = sorted({order_of[t] for _, t, _ in n.refs if t in order_of})
        steps.append({"order": order_of[n.node_id], "action": "create", "node_id": n.node_id, "resource_type": n.rtype,
                      "typed_choices": [], "values": vals, "losses": losses, "symbolic_unknowns": unknowns,
                      "depends_on": deps})
    missing = missing_required(tr, steps)
    closure = {"closed": not missing, "missing": missing}
    region_known = any(v["field"] == "location" and v["origin"] == "carried" for s in steps for v in s["values"])
    contexts = [{"key": "region", "state": "known" if region_known else "unknown", "value": None},
                {"key": "synthetic_account", "state": "symbolic", "value": None},
                {"key": "provider_version", "state": "known", "value": _pin(tr.dst)}]
    if region_known:
        contexts[0]["value"] = next(v["term"]["value"] for s in steps for v in s["values"]
                                    if v["field"] == "location" and v["origin"] == "carried" and v["term"]["kind"] == "literal")
    gir = {"graph_id": gid, "case_id": f"CASE-PSTO-{case}", "source_provider": src_provider, "terms": terms,
           "resources": resources or [{"node_id": "r1", "class_iri": "bo:Unit"}], "components": components,
           "references": references, "preconditions": _preconditions(tr, resources), "contexts": contexts}
    plan = {"plan_id": pid, "graph_id": gid, "target_provider": tr.dst, "steps": steps, "dependency_closure": closure}
    return gir, plan


def _pin(provider: str) -> str:
    return {"aws": "6.71.0", "google": "8.9.0", "azurerm": "5.12.0", "oci": "9.11.0"}[provider]


def _preconditions(tr, resources) -> list:
    out = []
    applies = [r["node_id"] for r in resources[:1]]
    for c in tr.carries:
        if c.result == "carried" and c.guard and c.guard["guard"].get("all"):
            out.append({"precondition_id": f"PRE-{c.view.claim.claim_id}".replace(":", "-"), "guard": c.guard["guard"],
                        "applies_to": applies})
    uniq = {}
    for p in out:
        uniq[p["precondition_id"]] = p
    return [uniq[k] for k in sorted(uniq)]


def missing_required(tr, steps) -> list:
    """Campos obrigatórios (C01) de cada passo que o plano não traz, e blocos com obrigatórios internos."""
    atoms = ATM.load()
    out = []
    for s in steps:
        ta = atoms.get(s["resource_type"])
        if ta is None:
            out.append(f"{s['resource_type']}: tipo sem átomos C01")
            continue
        have = {v["field"] for v in s["values"]}
        for f in ta.required_top():
            if f not in have:
                out.append(f"{s['resource_type']}.{f}")
        plain = {".".join(p for p in f.split(".") if not p.isdigit()) for f in have}
        blocks_present = set()
        for f in plain:
            parts = f.split(".")
            for i in range(1, len(parts)):
                blocks_present.add(".".join(parts[:i]))
        for b in ta.required_blocks(""):
            if b not in blocks_present:
                out.append(f"{s['resource_type']}.{b} (bloco)")
        for b in sorted(blocks_present):
            if not ta.is_block(b):
                continue
            for req in ta.required_in(b):
                if req not in plain:
                    out.append(f"{s['resource_type']}.{req}")
            for rb in ta.required_blocks(b):
                if rb not in blocks_present:
                    out.append(f"{s['resource_type']}.{rb} (bloco)")
    return sorted(set(out))


# ----------------------------------------------------------------------------------------------------------
# configuração-alvo (sintaxe JSON do Terraform) e entrada do oráculo
# ----------------------------------------------------------------------------------------------------------
def _var_name(symbol_id: str) -> str:
    return "v_" + symbol_id[4:].lower()


def tf_json(plan: dict, tr) -> dict:
    """Só o que o plano diz: endereço <tipo>.<nó>; referência = ${tipo.nó.atributo}; símbolo = ${var.x}."""
    atoms = ATM.load()
    res: dict = {}
    variables: dict = {}
    for s in plan["steps"]:
        ta = atoms.get(s["resource_type"])
        body: dict = {}
        for v in s["values"]:
            t = v["term"]
            if t["kind"] == "literal":
                val = t["value"]
            elif t["kind"] == "reference":
                val = "${%s.%s.%s}" % (t["target_type"], t["target_node"], t.get("attribute") or "id")
            elif t["kind"] == "symbol":
                vn = _var_name(t["symbol_id"])
                variables[vn] = {"type": "string"}
                val = "${var.%s}" % vn
            elif t["kind"] == "document":
                val = C.canon(t["tree"])
            else:
                val = None
            _put(body, v["field"].split("."), val, ta)
        res.setdefault(s["resource_type"], {})[s["node_id"]] = body
    out = {"resource": res}
    if variables:
        out["variable"] = variables
    return out


def _put(body: dict, parts: list[str], val, ta, prefix=()):
    head, rest = parts[0], parts[1:]
    if not rest:
        body[head] = val
        return
    path = ".".join(prefix + (head,))
    if ta is not None and ta.is_block(path):
        idx = 0
        if rest and rest[0].isdigit():
            idx, rest = int(rest[0]), rest[1:]
        lst = body.setdefault(head, [])
        while len(lst) <= idx:
            lst.append({})
        if not rest:
            return
        _put(lst[idx], rest, val, ta, prefix + (head,))
    else:
        m = body.setdefault(head, {})
        _put(m, rest, val, ta, prefix + (head,))


def target_fixture(src_fx: dict, plan: dict, tr, env: dict, entry_id: str) -> tuple[dict, dict]:
    """(fixture-alvo para o oráculo, mapa de contêineres origem -> endereço no alvo). O ambiente (vizinhos do
    contexto de implantação) entra no mundo julgado, não no plano: ele já existe e não é criado pelo tradutor."""
    tf = tf_json(plan, tr)
    ctype = T.CONTAINER_TYPE[tr.dst]
    cmap = {}
    for sc, nid in tr.container_map.items():
        if tr.nodes[nid].rtype == ctype:
            cmap[sc] = f"{ctype}.{nid}"
    for b in tr.env_bystanders:
        rt, name = b["container"].split(".", 1)
        body = {"name": name}
        rf = T.REF_FIELD.get(rt)
        if rf:
            ns = tr.nodes[b["namespace_node"]]
            body[rf[0]] = "${%s.%s.%s}" % (ns.rtype, ns.node_id, rf[1])
        tf["resource"].setdefault(rt, {})[name] = body
    fx = {"schema": "bo.pilot.sto.fixture/1", "fixture_id": f"{entry_id}-E2E-{C.CONTROL_CODE[tr.control]}",
          "provider": tr.dst, "provider_version": _pin(tr.dst), "context": dict(env or {}),
          "read": {"completeness": "complete", "not_read": [], "withheld": []}, "summary": "", "terraform": tf}
    tl = src_fx.get("timeline")
    if tl:
        t2 = dict(tl)
        t2["container"] = cmap.get(tl.get("container"), tl.get("container"))
        fx["timeline"] = t2
    return fx, cmap
