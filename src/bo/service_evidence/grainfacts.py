"""Fatos de grão DERIVADOS pedidos pelo GRAIN para decidir contêiner e faceta (sem nenhum INTERPRETADO).

  R-OWN-TOP   owner {kind: self}: tipo de topo com ID de importação publicado é dono da própria configuração
  R-LIFE-TF   lifecycle_controller {kind: self, layer: terraform}: timeouts com create e delete no schema; é
              ciclo de vida NO TERRAFORM, não na API (o fato publicado de apoio é R-LIFE-TIMEOUTS)
  R-TWIN      bloco/coleção embutido com gêmeo separado citado na página: herda a ponte e a identidade do gêmeo
  R-REF-*     alvo de atributo REFERENCE quando a descrição nomeia a coisa ("ID of the VPC" -> aws_vpc)
Os valores de R-OWN-TOP e R-LIFE-TF não têm aspect: são a alegação direta {kind, via} que o GRAIN lê (T99);
value.rule e value.layer ficam no registro para a citação da regra (o GRAIN normaliza só kind e via).
"""

from __future__ import annotations

import re

from . import common, rules, sources

LAYER_NOTE = "ciclo de vida do recurso no Terraform (create/delete do provider); não diz quem cria ou apaga o " \
             "objeto na API"
REF_RX = re.compile(r"\b(?:ID|IDs|Id|OCID|OCIDs|ARN|ARNs|name|names|resource ID|resource id|self[_ ]link|"
                    r"identifier|URI)\s+of\s+(?:the|a|an|an existing|the existing)\s+"
                    r"([A-Za-z0-9][A-Za-z0-9 \-]{0,60}?)"
                    r"(?=\s+(?:to|that|which|in|for|where|with|used|this|associated|from|on|whose|you|under|"
                    r"resource|object)\b|[.,;:()`]|$)")
TICK = re.compile(r"`([a-z][a-z0-9_]*)`")


def own_top(ctx, T: str, api: dict, imp_eid: str | None) -> None:
    r = ctx.by_id.get(imp_eid) if imp_eid else None
    if not r or r["status"] != "stated" or (r.get("value") or {}).get("supported") is False:
        return
    ctx.add(T, "owner", "own_top", api, "stated", "derived",
            value={"kind": "self", "via": [], "rule": "R-OWN-TOP", "layer": "terraform"}, derived=[imp_eid])
    ctx.st["R-OWN-TOP"] += 1


def life_tf(ctx, T: str, api: dict) -> None:
    p = ctx.p
    bt = (common.schema(p)["resource_schemas"][T]["block"].get("block_types") or {}).get("timeouts")
    if not bt:
        return
    ops = sorted((bt.get("block") or {}).get("attributes") or {})
    ptr = common.schema_pointer(p, "resource_schemas", T, "block", "block_types", "timeouts", "block", "attributes")
    tid = ctx.add(T, "lifecycle_controller", "timeouts", api, "stated", "published",
                  value={"aspect": "terraform_timeouts", "rule": "R-LIFE-TIMEOUTS", "operations": ops},
                  cit=common.schema_cite(p, ptr, "keys"))
    if {"create", "delete"} <= set(ops):
        ctx.add(T, "lifecycle_controller", "life_tf", api, "stated", "derived",
                value={"kind": "self", "via": [], "rule": "R-LIFE-TF", "layer": "terraform", "note": LAYER_NOTE},
                derived=[tid])
        ctx.st["R-LIFE-TF"] += 1


def _tokens(s: str) -> set[str]:
    return {t for t in s.split("_") if t}


def _norm_thing(x: str) -> str:
    return re.sub(r"[\s\-]+", "_", x.strip().lower())


def references(ctx, T: str, api: dict) -> None:
    p = ctx.p
    refs = sources.references(p).get(T)
    if not refs:
        return
    types = set(sources.types(p))
    depths = {path: depth for path, depth, *_ in sources.atoms(p).get(T, [])}
    for path in sorted(refs):
        facts, _can = sources.facts_for(p, f"{p}:{T}:{path}", ctx.st)
        desc = next((f for f in facts if f["fact_kind"] == "description"), None)
        if not desc:
            continue
        from .extract import fdoc, with_bp
        doc = fdoc(desc, p)
        if not doc:
            continue
        m = REF_RX.search(doc["sentence"])
        if not m:
            continue
        thing = m.group(1).strip()
        depth = depths.get(path, 0)
        v = with_bp({"aspect": "reference_phrase", "rule": "R-REF-PHRASE", "attribute": path, "phrase": thing,
                     "c03_fact_id": desc["fact_id"]}, path, depth)
        pid = ctx.add(T, "identity", f"refphrase:{path}", api, "stated", "published", value=v, doc=doc)
        ctx.st["R-REF-PHRASE"] += 1
        n = _norm_thing(thing)
        exact = f"{p}_{n}"
        if exact in types:
            cands = [exact]
        else:
            cands = sorted(t for t in types if t.endswith("_" + n))
        if not cands or len(cands) > 3:
            ctx.st["R-REF-TARGET_sem_alvo"] += 1
            continue
        v2 = with_bp({"aspect": "reference_target", "rule": "R-REF-TARGET", "attribute": path,
                      "target_types": cands, "resolved": cands[0] if len(cands) == 1 else None,
                      "references": {path: cands[0]} if len(cands) == 1 else {}}, path, depth)
        ctx.add(T, "identity", f"reftarget:{path}", api, "stated", "derived", value=v2, derived=[pid])
        ctx.st["R-REF-TARGET"] += 1


TWIN_LEFTOVER = {"rule", "configuration", "vpc"}


def twin_name_ok(p: str, T: str, B: str, U: str) -> bool:
    """Regra de nome do R-TWIN: termos de B no nome de U; U tem ao menos um termo próprio de T (sem o prefixo do
    provedor); o que sobra de U fora de B e de T é só rule/configuration/vpc (ligação, anexo e associação ficam de
    fora: são vínculo, não o mesmo objeto)."""
    tu, tb, tt = _tokens(U), _tokens(B), _tokens(T) - {p}
    return tb <= tu and bool(tu & tt) and (tu - tb - tt - {p}) <= TWIN_LEFTOVER


def _collections(p: str, T: str) -> set[str]:
    b = common.schema(p)["resource_schemas"][T]["block"]
    from .blocks import object_collection
    out = {k for k in (b.get("block_types") or {}) if k != "timeouts"}
    out |= {k for k, a in (b.get("attributes") or {}).items() if object_collection(a.get("type"))}
    return out


def twins(ctx, pages: dict, info: dict) -> None:
    p = ctx.p
    types = set(sources.types(p))
    found = {}
    for T, page in pages.items():
        if not page:
            continue
        blocks_ = _collections(p, T)
        if not blocks_:
            continue
        for i, ln in enumerate(common.page_lines(p, page)):
            ticks = set(TICK.findall(ln))
            for B in blocks_ & ticks:
                for U in ticks & types:
                    if U == T or not twin_name_ok(p, T, B, U):
                        continue
                    found.setdefault((T, B, U), (page, i + 1))
    # o mesmo vínculo dito na página do gêmeo (cita `T` e `B`)
    for U, page in pages.items():
        if not page:
            continue
        for i, ln in enumerate(common.page_lines(p, page)):
            ticks = set(TICK.findall(ln))
            for T in ticks & types:
                if T == U:
                    continue
                for B in _collections(p, T) & ticks:
                    if twin_name_ok(p, T, B, U):
                        found.setdefault((T, B, U), (page, i + 1))
    by_type = {}
    for r in ctx.recs:
        if r["status"] == "stated" and not r.get("block_path"):
            by_type.setdefault(r["terraform_resource_type"], []).append(r)
    for (T, B, U), (page, ln) in sorted(found.items()):
        api_t = info[T][0]
        lid = ctx.add(T, "identity", f"twin:{B}:{U}", api_t, "stated", "published",
                      value={"aspect": "twin_type", "rule": "R-TWIN", "block_path": B, "twin": U},
                      doc=common.doc_cite(p, page, ln))
        ctx.st["R-TWIN_vinculos"] += 1
        for r in by_type.get(U, []):
            a = (r.get("value") or {}).get("aspect")
            if (r["fact_kind"] == "api_bridge" and r["value"].get("resource") not in (None, "UNKNOWN")) or \
                    a == "resource_identity_schema":
                v = dict(r["value"])
                v.update({"block_path": B, "inherited_from": U, "source_rule": v.get("rule"), "rule": "R-TWIN"})
                ctx.add(T, r["fact_kind"], f"twin:{B}:{U}:{a}", r["api_resource"], "stated", "derived", value=v,
                        derived=[lid, r["evidence_id"]])
                ctx.st["R-TWIN_herdados"] += 1
    _ = rules


PREVAIL = {"type_scope", "attachment_scope"}  # R-SCOPE-DOC publicado do tipo ou do bloco


def scopes(ctx, api_primary: set | None = None) -> None:
    """R-SCOPE-SELF e R-SCOPE-PARENT, depois do extract e da curadoria (R-SCOPE-DOC prevalece). Tipo primário
    de ponte de API (api_layer) e seus blocos: camada api (derived_from inclui a ponte); os outros: terraform."""
    api_primary = api_primary or set()
    bridge_id = {r["terraform_resource_type"]: r["evidence_id"] for r in ctx.recs
                 if r["fact_kind"] == "api_bridge" and r["status"] == "stated" and not r.get("block_path")
                 and r["terraform_resource_type"] in api_primary
                 and (r.get("value") or {}).get("aspect") == "api_resource_bridge"
                 and (r.get("value") or {}).get("resource") not in (None, "", "UNKNOWN")}
    doc_scoped, anchor, blocks_ = set(), {}, {}
    for r in ctx.recs:
        if r["status"] != "stated":
            continue
        T, bp, v = r["terraform_resource_type"], r.get("block_path"), r.get("value") or {}
        if r["fact_kind"] == "effective_scope" and v.get("aspect") in PREVAIL:
            doc_scoped.add((T, bp))
        if v.get("aspect") == "block_schema":
            blocks_[(T, bp)] = r
        if not bp and r["level"] == "published":
            rank = {"import_key": 0, "identity": 1, "tag_support": 2}.get(r["fact_kind"])
            if rank is not None and (T not in anchor or rank < anchor[T][0]):
                anchor[T] = (rank, r)
    for T in sources.types(ctx.p):
        if (T, None) in doc_scoped:
            ctx.st["R-SCOPE-DOC_tipo"] += 1
        elif T in anchor:
            r = anchor[T][1]
            api = T in bridge_id
            ctx.add(T, "effective_scope", "scope_self", r["api_resource"], "stated", "derived",
                    value={"kind": "self", "rule": "R-SCOPE-SELF", "layer": "api" if api else "terraform"},
                    derived=[r["evidence_id"]] + ([bridge_id[T]] if api else []))
            if api:
                ctx.st["R-SCOPE-SELF_api"] += 1
            ctx.st["R-SCOPE-SELF"] += 1
    for (T, bp), r in sorted(blocks_.items()):
        if (T, bp) in doc_scoped:
            ctx.st["R-SCOPE-DOC_bloco"] += 1
            continue
        api = T in bridge_id
        ctx.add(T, "effective_scope", f"scope_parent:{bp}", r["api_resource"], "stated", "derived",
                value={"kind": "parent", "rule": "R-SCOPE-PARENT", "block_path": bp,
                       "layer": "api" if api else "terraform"},
                derived=[r["evidence_id"]] + ([bridge_id[T]] if api else []))
        if api:
            ctx.st["R-SCOPE-PARENT_api"] += 1
        ctx.st["R-SCOPE-PARENT"] += 1


def api_layer(ctx) -> set[str]:
    """CC-1d: dono, ciclo de vida e alcance na camada de API, só com ponte publicada/derivada para um recurso
    de API (resource != UNKNOWN). Tipos com a mesma ponte formam um grupo; quem referencia (R-REF-TARGET
    resolvido, atributo de topo) outro membro do grupo configura o objeto dele (dono e ciclo = pai, via o
    atributo); o único membro que não referencia nenhum outro é o primário (dono e ciclo = self). Mais de um
    primário: nada (ambíguo). Devolve os tipos primários (camada API para R-SCOPE-*)."""
    bridge, refs, life = {}, {}, {}
    for r in ctx.recs:
        if r["status"] != "stated" or r.get("block_path"):
            continue
        v = r.get("value") or {}
        T = r["terraform_resource_type"]
        if r["fact_kind"] == "api_bridge" and not v.get("inherited_from") and v.get("rule") != "R-BRIDGE-SPEC" \
                and v.get("resource") not in (None, "", "UNKNOWN"):
            bridge.setdefault(T, r)
        if v.get("aspect") == "reference_target" and v.get("resolved"):
            refs.setdefault(T, {})[v["attribute"]] = (v["resolved"], r["evidence_id"])
        if v.get("rule") == "R-LIFE-TF":
            life[T] = r
    groups = {}
    for T, r in bridge.items():
        groups.setdefault((r["value"].get("service"), r["value"]["resource"]), []).append(T)
    primaries = set()
    for key, members in sorted(groups.items()):
        mset = set(members)
        pointing = {U: [(a, tgt, rid) for a, (tgt, rid) in sorted(refs.get(U, {}).items()) if tgt in mset and tgt != U]
                    for U in members}
        prim = [U for U in members if not pointing[U]]
        if len(prim) != 1:
            ctx.st["R-OWN-API_ambiguo"] += len(members)
            continue
        P = prim[0]
        primaries.add(P)
        br = bridge[P]
        ctx.add(P, "owner", "own_api", br["api_resource"], "stated", "derived",
                value={"kind": "self", "rule": "R-OWN-API", "layer": "api"}, derived=[br["evidence_id"]])
        ctx.st["R-OWN-API"] += 1
        if P in life:
            ctx.add(P, "lifecycle_controller", "life_api", br["api_resource"], "stated", "derived",
                    value={"kind": "self", "rule": "R-LIFE-API", "layer": "api"},
                    derived=[br["evidence_id"], life[P]["evidence_id"]])
            ctx.st["R-LIFE-API"] += 1
        for U in members:
            for a, tgt, rid in pointing[U][:1]:
                if tgt != P:
                    continue
                bu = bridge[U]
                for kind, rule in (("owner", "R-OWN-API-SHARED"), ("lifecycle_controller", "R-LIFE-API-SHARED")):
                    ctx.add(U, kind, f"{rule}", bu["api_resource"], "stated", "derived",
                            value={"kind": "parent", "via": [a], "rule": rule, "layer": "api", "shared_with": P},
                            derived=[bu["evidence_id"], br["evidence_id"], rid])
                    ctx.st[rule] += 1
    return primaries
