"""Fatos mecânicos por tipo e por atributo (C25), um provedor por vez.

Níveis:
  published   a frase citada (doc fixado ou nó do schema fixado) diz o valor; o resolver confere na fonte.
  derived     regra declarada (rules.RULES) sobre fatos publicados deste mesmo arquivo (derived_from).
  (interpreted só no curated.py)
Desconhecido: status unknown + unknown_reason; a citação é a da publicação consultada (título da página, ou as
chaves do bloco do tipo no schema quando não há página), para que dê para refazer a busca.
"""

from __future__ import annotations

import collections
import re

from . import common, rules, sources

UNKNOWN = "UNKNOWN"
GCP_CONTAINERS = {"projects": "project", "organizations": "organization", "folders": "folder",
                  "billingAccounts": "billing_account"}
GCP_SKIP = {"locations", "regions", "zones", "global"}


class Ctx:
    def __init__(self, provider: str):
        self.p = provider
        self.v = common.version(provider)
        self.recs: list[dict] = []
        self.ids: set[str] = set()
        self.st = collections.Counter()

    def add(self, T: str, kind: str, key: str, api: dict, status: str, level: str, value=None,
            reason: str | None = None, doc: dict | None = None, cit: dict | None = None,
            derived: list | None = None, model: str | None = None, api_version: str | None = None) -> str:
        eid = common.se_id(self.p, T, kind, key)
        if eid in self.ids:
            return eid
        r = {"evidence_id": eid, "provider": self.p, "pin": {"provider_version": self.v},
             "api_resource": dict(api), "terraform_resource_type": T, "fact_kind": kind, "status": status,
             "level": level}
        if api_version:
            r["pin"]["api_version"] = api_version
        if status == "stated":
            r["value"] = value
        else:
            r["unknown_reason"] = reason or "not_documented"
        if doc:
            r["doc"] = doc
        if cit:
            r["citation"] = cit
        if derived:
            r["derived_from"] = sorted(set(derived))
        if model:
            r["model_id"] = model
        self.ids.add(eid)
        self.recs.append(r)
        self.st[f"{kind}:{level}:{status}"] += 1
        return eid


# ---------------------------------------------------------------- páginas

def title_line(p: str, rel: str) -> int | None:
    for i, ln in enumerate(common.page_lines(p, rel)):
        if ln.startswith("# "):
            return i + 1
    return None


def absent_cite(ctx: Ctx, T: str, page: str | None) -> tuple[dict | None, dict | None]:
    if page:
        tl = title_line(ctx.p, page)
        if tl:
            return common.doc_cite(ctx.p, page, tl), None
    ptr = common.schema_pointer(ctx.p, "resource_schemas", T, "block")
    return None, common.schema_cite(ctx.p, ptr, "keys")


def unknown(ctx: Ctx, T: str, kind: str, api: dict, page: str | None, reason: str = "not_documented"):
    doc, cit = absent_cite(ctx, T, page)
    ctx.add(T, kind, "unknown", api, "unknown", "published", reason=reason, doc=doc, cit=cit)


# ---------------------------------------------------------------- ponte API <-> Terraform

GCP_API = re.compile(r"\[API documentation\]\((https://cloud\.google\.com/[^)\s]+)\)")
OCI_API = re.compile(r"Api doc link for the resource: (https://docs\.oracle\.com/iaas/api/#/en/([^/\s]+)/([^/\s]+)/"
                     r"([A-Za-z0-9_]+))")
AWS_API = re.compile(r"https://docs\.aws\.amazon\.com/([A-Za-z0-9_-]+)/latest/APIReference/API_([A-Za-z0-9_]+)\.html")
GCP_VER = re.compile(r"^v\d+(?:p\d+)?(?:alpha|beta)?\d*$")


def gcp_bridge(url: str) -> tuple[str, str, str | None]:
    path = url.split("://", 1)[1].split("#", 1)[0].split("?", 1)[0]
    segs = [s for s in path.split("/")[1:] if s]
    svc = segs[0] if segs else UNKNOWN
    vi = next((i for i, s in enumerate(segs) if GCP_VER.match(s)), None)
    if vi is not None and vi + 1 < len(segs):
        return svc, "/".join(segs[vi + 1:]), segs[vi]
    return svc, UNKNOWN, (segs[vi] if vi is not None else None)


def arm_parse(id_example: str):
    """(namespace, [tipos], [nomes], escopo antes de /providers/) ou None."""
    if "|" in id_example or "/providers/" not in id_example:
        return None
    scope, rest = id_example.rsplit("/providers/", 1)
    segs = [s for s in rest.split("/") if s]
    if len(segs) < 3:
        return None
    ns, tail = segs[0], segs[1:]
    return ns, tail[0::2], tail[1::2], scope


def bridge(ctx: Ctx, T: str, tsr: dict | None, page: str | None) -> tuple[dict, str | None, str | None]:
    """Grava o fato de ponte; devolve (api_resource, evidence_id, api_version)."""
    p = ctx.p
    sub = (tsr or {}).get("subcategory")
    fallback = {"service": sub["value"] if sub else UNKNOWN, "resource": UNKNOWN}
    if p == "google" and page:
        for i, ln in enumerate(common.page_lines(p, page)):
            m = GCP_API.search(ln)
            if m:
                svc, res, ver = gcp_bridge(m.group(1))
                api = {"service": svc, "resource": res}
                eid = ctx.add(T, "identity", "bridge", api, "stated", "published",
                              value={"aspect": "api_resource_bridge", "rule": "R-BRIDGE-GCP-APIDOC",
                                     "url": m.group(1), "service": svc, "resource": res, "api_version": ver},
                              doc=common.doc_cite(p, page, i + 1), api_version=ver)
                return api, eid, ver
    if p == "oci" and page:
        for i, ln in enumerate(common.page_lines(p, page)):
            m = OCI_API.search(ln)
            if m:
                api = {"service": m.group(2), "resource": m.group(4)}
                eid = ctx.add(T, "identity", "bridge", api, "stated", "published",
                              value={"aspect": "api_resource_bridge", "rule": "R-BRIDGE-OCI-APIDOC",
                                     "url": m.group(1), "service": m.group(2), "resource": m.group(4),
                                     "doc_link_version": m.group(3)},
                              doc=common.doc_cite(p, page, i + 1))
                return api, eid, None
    if p == "azurerm" and tsr and tsr["import"]["status"] == "stated":
        ex = (tsr["import"]["value"].get("values") or [None])[0]
        parsed = arm_parse(ex) if ex else None
        if parsed:
            ns, tps, _names, _scope = parsed
            api = {"service": ns, "resource": "/".join(tps)}
            imp_id = import_id(ctx, T)
            eid = ctx.add(T, "identity", "bridge", api, "stated", "derived",
                          value={"aspect": "api_resource_bridge", "rule": "R-BRIDGE-AZ-ARMID", "service": ns,
                                 "resource": "/".join(tps)},
                          derived=[imp_id])
            return api, eid, None
    if p == "aws" and sub:
        api = fallback
        eid = ctx.add(T, "identity", "bridge", api, "stated", "published",
                      value={"aspect": "api_resource_bridge", "rule": "R-BRIDGE-AWS-SUBCAT", "service": sub["value"],
                             "resource": UNKNOWN},
                      doc=dict(sub["source"]))
        return api, eid, None
    return fallback, None, None


def import_id(ctx: Ctx, T: str) -> str:
    return common.se_id(ctx.p, T, "import_key", "doc")


# ---------------------------------------------------------------- importação e identidade

GCP_IMPORT_HDR = re.compile(r"can be imported using any of these accepted formats|can be imported using")
GCP_FMT = re.compile(r"^\* `([^`]+)`\s*$")


def gcp_import(p: str, page: str) -> tuple[int, list[str]] | None:
    lines = common.page_lines(p, page)
    try:
        start = next(i for i, ln in enumerate(lines) if ln.strip() == "## Import")
    except StopIteration:
        return None
    for i in range(start + 1, min(start + 15, len(lines))):
        if GCP_IMPORT_HDR.search(lines[i]):
            fmts = []
            for j in range(i + 1, min(i + 20, len(lines))):
                m = GCP_FMT.match(lines[j].strip())
                if m:
                    fmts.append(m.group(1))
                elif fmts and lines[j].strip():
                    break
            return i + 1, fmts
    return None


def import_and_identity(ctx: Ctx, T: str, tsr: dict | None, page: str | None, api: dict, api_ver):
    p = ctx.p
    imp_eid, template, val = None, None, None
    if p == "google" and page and (not tsr or tsr["import"]["status"] == "absent"):
        g = gcp_import(p, page)
        if g and g[1]:
            ln, fmts = g
            val = {"aspect": "import_formats", "rule": "R-IMPORT-DOC", "formats": fmts}
            imp_eid = ctx.add(T, "import_key", "doc", api, "stated", "published", value=val,
                              doc=common.doc_cite(p, page, ln), api_version=api_ver)
    elif tsr and tsr["import"]["status"] == "stated":
        imp = tsr["import"]
        val = dict(imp["value"])
        val.update({"aspect": "import_formats", "rule": "R-IMPORT-DOC"})
        kd = common.cite_or_none(p, imp["key_cite"]) if "key_cite" in imp else None
        if kd and kd["file"] == imp["cite"].get("file"):
            val["key_sentence"] = kd["sentence"]
            val["key_line"] = kd["line"]
            if kd.get("redacted"):
                val["key_redacted"] = True
        doc = common.cite_or_none(p, imp["cite"])
        if doc is None:
            ctx.st["citação_irresolúvel"] += 1
        else:
            imp_eid = ctx.add(T, "import_key", "doc", api, "stated", "published", value=val, doc=doc,
                              api_version=api_ver)
    if imp_eid is None:
        reason = (tsr or {}).get("import", {}).get("unknown_reason", "not_documented")
        doc, cit = absent_cite(ctx, T, page)
        ctx.add(T, "import_key", "unknown", api, "unknown", "published", reason=reason, doc=doc, cit=cit)

    # identidade pelo schema (Terraform >= 1.12)
    id_schema = common.schema(p).get("resource_identity_schemas", {}).get(T)
    sid = None
    if id_schema:
        req = sorted(k for k, a in id_schema["attributes"].items() if a.get("required_for_import"))
        opt = sorted(k for k, a in id_schema["attributes"].items() if a.get("optional_for_import"))
        ptr = common.schema_pointer(p, "resource_identity_schemas", T)
        sid = ctx.add(T, "identity", "schema", api, "stated", "published",
                      value={"aspect": "resource_identity_schema", "rule": "R-ID-SCHEMA", "required": req,
                             "optional": opt},
                      cit=common.schema_cite(p, ptr), api_version=api_ver)

    # modelo de identidade derivado da importação
    tid = None
    if imp_eid and val:
        if p == "azurerm":
            ex = (val.get("values") or [None])[0]
            parsed = arm_parse(ex) if ex else None
            ks = (val.get("key_sentence") or "").lower()
            if parsed and ("resource id" in ks or "resource manager id" in ks):
                ns, tps, names, scope = parsed
                scope_t = re.sub(r"/resourceGroups/[^/]+", "/resourceGroups/{resourceGroupName}", scope)
                parts = []
                for t_, _n in zip(tps, names):
                    parts += [t_, "{" + t_ + "}"]
                template = f"{scope_t}/providers/{ns}/" + "/".join(parts)
                tid = ctx.add(T, "identity", "template", api, "stated", "derived",
                              value={"aspect": "id_template", "rule": "R-ID-AZ-TEMPLATE", "template": template,
                                     "attribute": "id"},
                              derived=[imp_eid])
        elif p == "google":
            fmts = val.get("formats") or val.get("values") or []
            if fmts:
                template = max(fmts, key=lambda s: (s.count("{{"), len(s)))
                tid = ctx.add(T, "identity", "template", api, "stated", "derived",
                              value={"aspect": "id_template", "rule": "R-ID-GCP-LONGEST", "template": template},
                              derived=[imp_eid], api_version=api_ver)
        elif p == "oci":
            if val.get("id_is_plain_id"):
                tid = ctx.add(T, "identity", "template", api, "stated", "derived",
                              value={"aspect": "id_template", "rule": "R-ID-OCI-PLAIN", "attribute": "id"},
                              derived=[imp_eid])
            elif val.get("id_format"):
                template = val["id_format"]
                tid = ctx.add(T, "identity", "template", api, "stated", "derived",
                              value={"aspect": "id_template", "rule": "R-ID-OCI-FORMAT", "template": template},
                              derived=[imp_eid])
        elif p == "aws":
            attrs = val.get("id_attributes") or []
            seps = val.get("separators") or []
            if attrs:
                if len(attrs) == 1:
                    template = attrs[0]
                elif len(seps) == 1:
                    template = seps[0].join(attrs)
                elif len(seps) == len(attrs) - 1:
                    template = "".join(a + s for a, s in zip(attrs, seps + [""]))
                else:
                    template = None
                v = {"aspect": "id_template", "rule": "R-ID-AWS-ATTRS", "attributes": attrs}
                if template:
                    v["template"] = template
                tid = ctx.add(T, "identity", "template", api, "stated", "derived", value=v, derived=[imp_eid])
    return imp_eid, sid, tid, template, id_schema


# ---------------------------------------------------------------- dono

def owner(ctx: Ctx, T: str, api: dict, template: str | None, tid: str | None, sid: str | None, id_schema,
          bridges: dict, page: str | None):
    p = ctx.p
    got = False
    if p == "azurerm" and template and tid:
        parsed = arm_parse(template)
        if parsed:
            ns, tps, _n, scope = parsed
            if len(tps) > 1:
                parent = f"{ns}/" + "/".join(tps[:-1])
                cands = sorted(t for t, a in bridges.items() if a and f"{a['service']}/{a['resource']}" == parent)
                val = {"aspect": "parent", "rule": "R-OWN-AZ-PARENT", "scope_kind": "resource",
                       "parent_api_type": parent, "parent_terraform_types": cands}
            elif "/providers/" in scope:
                val = {"aspect": "parent", "rule": "R-OWN-AZ-PARENT", "scope_kind": "extension_scope",
                       "parent_api_type": UNKNOWN, "parent_terraform_types": []}
            elif "/resourceGroups/" in scope:
                val = {"aspect": "parent", "rule": "R-OWN-AZ-PARENT", "scope_kind": "resource_group",
                       "parent_api_type": "Microsoft.Resources/resourceGroups",
                       "parent_terraform_types": ["azurerm_resource_group"]}
            else:
                val = {"aspect": "parent", "rule": "R-OWN-AZ-PARENT", "scope_kind": "subscription",
                       "parent_api_type": "subscriptions", "parent_terraform_types": []}
            ctx.add(T, "owner", "template", api, "stated", "derived", value=val, derived=[tid])
            got = True
    if p == "google" and template and tid:
        segs = template.split("/")
        cols = [segs[i - 1] for i, x in enumerate(segs)
                if i > 0 and x.startswith("{{") and not segs[i - 1].startswith("{{") and segs[i - 1] not in GCP_SKIP]
        if len(cols) >= 2:
            par = cols[-2]
            if par in GCP_CONTAINERS:
                val = {"aspect": "parent", "rule": "R-OWN-GCP-PARENT", "scope_kind": GCP_CONTAINERS[par],
                       "parent_collection": par, "parent_terraform_types": []}
            else:
                cands = sorted(t for t, a in bridges.items()
                               if a and a["service"] == api["service"] and a["resource"] != UNKNOWN
                               and re.split(r"[./]", a["resource"])[-1] == par)
                val = {"aspect": "parent", "rule": "R-OWN-GCP-PARENT", "scope_kind": "resource",
                       "parent_collection": par, "parent_terraform_types": cands}
            ctx.add(T, "owner", "template", api, "stated", "derived", value=val, derived=[tid])
            got = True
    if p == "aws" and id_schema and sid:
        keys = set(id_schema["attributes"])
        if keys & {"account_id", "region"}:
            ctx.add(T, "owner", "identity", api, "stated", "derived",
                    value={"aspect": "identity_scope", "rule": "R-OWN-AWS-IDENTITY",
                           "account": "account_id" in keys, "region": "region" in keys},
                    derived=[sid])
            got = True
    # atributos de referência cuja frase diz a quem pertence
    for path, depth, req, opt, comp, conf in sources.atoms(p).get(T, []):
        if depth or "." in path or not req:
            continue
        lf = rules.leaf(path)
        if not (lf.endswith("_id") or lf == "compartment_id"):
            continue
        facts, can = sources.facts_for(p, f"{p}:{T}:{path}", ctx.st)
        for f in facts:
            if f["fact_kind"] != "description":
                continue
            s = f["source"]["sentence"]
            doc = fdoc(f, p)
            if doc is None:
                ctx.st["citação_irresolúvel"] += 1
                continue
            s = doc["sentence"]
            if lf == "compartment_id" or rules.OWNER_DESC.search(s):
                v = {"aspect": "parent_attribute", "rule": "R-OWN-DOC-PARENT", "attribute": path,
                     "c03_fact_id": f["fact_id"]}
                if lf == "compartment_id":
                    v["scope_kind"] = "compartment"
                if can:
                    v["doc_atom"] = can
                ctx.add(T, "owner", f"attr:{path}", api, "stated", "published", value=v, doc=doc)
                got = True
                break
    if not got:
        unknown(ctx, T, "owner", api, page)


# ---------------------------------------------------------------- frases do tipo (alcance, ciclo de vida)

def intro_lines(p: str, page: str) -> list[tuple[int, str]]:
    """Front matter e prosa antes do primeiro '## ' (descrição do tipo)."""
    out = []
    for i, ln in enumerate(common.page_lines(p, page)):
        if ln.startswith("## "):
            break
        if ln.strip() and not ln.startswith("```"):
            out.append((i + 1, ln))
    return out


def scope_and_life(ctx: Ctx, T: str, api: dict, page: str | None):
    p = ctx.p
    got_scope = got_life = False
    if page:
        for ln_no, ln in intro_lines(p, page):
            sc = rules.scope_of(ln)
            if sc:
                ctx.add(T, "effective_scope", f"type:{sc}", api, "stated", "published",
                        value={"aspect": "type_scope", "rule": "R-SCOPE-DOC", "scope": sc},
                        doc=common.doc_cite(p, page, ln_no))
                got_scope = True
        for i, ln in enumerate(common.page_lines(p, page)):
            m = rules.LIFE_RX.search(ln)
            if m:
                txt = m.group(0).lower()
                eff = "state_only" if "state" in txt else ("suspend" if "suspend" in txt else "not_deleted")
                ctx.add(T, "lifecycle_controller", f"life:{i + 1}", api, "stated", "published",
                        value={"aspect": "destroy_effect", "rule": "R-LIFE-DOC", "effect": eff},
                        doc=common.doc_cite(p, page, i + 1))
                got_life = True
    for path, depth, req, opt, comp, conf in sources.atoms(p).get(T, []):
        aid = f"{p}:{T}:{path}"
        facts, can = sources.facts_for(p, aid, ctx.st)
        if not facts:
            continue
        for f in facts:
            if f["fact_kind"] != "description":
                continue
            doc = fdoc(f, p)
            if doc is None:
                ctx.st["citação_irresolúvel"] += 1
                continue
            sc = rules.scope_of(doc["sentence"])
            if sc:
                v = {"aspect": "attribute_scope", "rule": "R-SCOPE-DOC", "attribute": path, "scope": sc,
                     "c03_fact_id": f["fact_id"]}
                if can:
                    v["doc_atom"] = can
                ctx.add(T, "effective_scope", f"attr:{path}:{sc}", api, "stated", "published", value=v,
                        doc=doc)
                got_scope = True
        if rules.leaf(path) == "deletion_policy":
            vals = allowed(facts)
            desc = next((f for f in facts if f["fact_kind"] == "description"), None)
            ddoc = fdoc(desc, p) if desc else None
            if ddoc:
                v = {"aspect": "deletion_policy", "rule": "R-LIFE-DELETION-POLICY", "attribute": path,
                     "values": vals, "c03_fact_id": desc["fact_id"]}
                ctx.add(T, "lifecycle_controller", f"attr:{path}", api, "stated", "published", value=v,
                        doc=ddoc)
                got_life = True
    if not got_scope:
        unknown(ctx, T, "effective_scope", api, page)
    if not got_life:
        unknown(ctx, T, "lifecycle_controller", api, page)


def fdoc(f: dict, provider: str) -> dict | None:
    """doc_source que resolve para o fato C03, ou None. Para descrição, tenta antes citar o texto INTEIRO (o value
    do C03) a partir de uma linha perto da citada (o DOCS-* às vezes cita só a 1ª frase); depois a frase do C03
    (common.cite_or_none). As regras classificam só a frase que fica citada."""
    src = f["source"]
    if f.get("fact_kind") == "description" and isinstance(f.get("value"), str):
        full = common.norm(f["value"])
        if len(full) > len(common.norm(src["sentence"])):
            n = len(common.page_lines(provider, src["file"]))
            for ln in range(max(1, src["line"] - 2), min(n, src["line"] + 5) + 1):
                d = common.doc_cite(provider, src["file"], ln, sentence=full)
                if common.resolve_doc(provider, d) is None:
                    return d
    return common.cite_or_none(provider, src)


def allowed(facts: list) -> list:
    for f in facts:
        if f["fact_kind"] == "allowed_values":
            v = f.get("value")
            if isinstance(v, dict):
                v = v.get("values") or []
            if isinstance(v, str):
                v = [v]
            return [str(x) for x in (v or [])]
    return []


def default_of(facts: list) -> dict | None:
    for f in facts:
        if f["fact_kind"] == "default":
            d = {"value": f.get("value"), "c03_fact_id": f["fact_id"]}
            if f.get("as_of"):
                d["as_of"] = f["as_of"]
            return d
    return None


# ---------------------------------------------------------------- regras de rede, tag, TTL

def attributes(ctx: Ctx, T: str, api: dict, page: str | None):
    p = ctx.p
    top = {path for path, depth, *_ in sources.atoms(p).get(T, []) if not depth and "." not in path}
    # tag
    tag_attrs = [a for a in rules.TAG_ATTRS[p] if a in top]
    for a in tag_attrs:
        facts, _ = sources.facts_for(p, f"{p}:{T}:{a}", ctx.st)
        desc = next((f for f in facts if f["fact_kind"] == "description"), None)
        v = {"aspect": "terraform_attribute", "rule": "R-TAG-ATTR", "attribute": a, "supported": True}
        ddoc = fdoc(desc, p) if desc else None
        if ddoc:
            v["c03_fact_id"] = desc["fact_id"]
            ctx.add(T, "tag_support", f"attr:{a}", api, "stated", "published", value=v, doc=ddoc)
        else:
            ptr = common.schema_pointer(p, "resource_schemas", T, "block", "attributes", a)
            ctx.add(T, "tag_support", f"attr:{a}", api, "stated", "published", value=v,
                    cit=common.schema_cite(p, ptr))
    if not tag_attrs:
        ptr = common.schema_pointer(p, "resource_schemas", T, "block", "attributes")
        ctx.add(T, "tag_support", "absent", api, "stated", "published",
                value={"aspect": "terraform_attribute", "rule": "R-TAG-ABSENT", "supported": False,
                       "attributes_checked": list(rules.TAG_ATTRS[p])},
                cit=common.schema_cite(p, ptr, "keys"))
    got_ttl = False
    for path, depth, req, opt, comp, conf in sources.atoms(p).get(T, []):
        lf = rules.leaf(path)
        aid = f"{p}:{T}:{path}"
        is_ttl = bool(rules.TTL_LEAF.search(lf)) and not rules.TTL_EXCLUDE.search(path) and conf
        is_state = bool(rules.STATE_LEAF.match(lf))
        is_eff = bool(rules.EFFECT_LEAF.match(lf) or rules.EFFECT_BLOCK.match(lf))
        is_prec = bool(rules.PREC_LEAF.match(lf))
        facts, can = sources.facts_for(p, aid, ctx.st)
        desc = next((f for f in facts if f["fact_kind"] == "description"), None)
        ddoc = fdoc(desc, p) if desc and (is_ttl or is_state or is_eff or is_prec or
                                          rules.STATE_DESC.search(str(desc.get("value", "")))) else None
        if ddoc and not is_state and rules.STATE_DESC.search(ddoc["sentence"]):
            is_state = True
        extra = {"doc_atom": can} if can else {}
        if is_ttl:
            if ddoc:
                v = {"aspect": "expiry_attribute", "rule": "R-TTL-ATTR", "attribute": path,
                     "target": rules.ttl_target(ddoc["sentence"]),
                     "c03_fact_ids": sorted(f["fact_id"] for f in facts), **extra}
                ctx.add(T, "ttl_support", f"attr:{path}", api, "stated", "published", value=v, doc=ddoc)
            elif depth == 0 and "." not in path:
                v = {"aspect": "expiry_attribute", "rule": "R-TTL-ATTR", "attribute": path, "target": UNKNOWN}
                ptr = common.schema_pointer(p, "resource_schemas", T, "block", "attributes", path)
                ctx.add(T, "ttl_support", f"attr:{path}", api, "stated", "published", value=v,
                        cit=common.schema_cite(p, ptr))
            else:
                ctx.st["ttl_aninhado_sem_frase"] += 1
                continue
            got_ttl = True
        if is_state and ddoc:
            s = ddoc["sentence"]
            v = {"aspect": "rule_state_attribute", "rule": "R-CONN-DOC", "attribute": path,
                 "mentions": sorted({m.group(0).lower() for m in rules.STATE_DESC.finditer(s)}),
                 "c03_fact_id": desc["fact_id"], **extra}
            d = default_of(facts)
            if d:
                v["default"] = d
            ctx.add(T, "connection_state", f"attr:{path}", api, "stated", "published", value=v, doc=ddoc)
        if is_eff:
            vals = [x for x in allowed(facts) if rules.EFFECT_VALUES.match(x)]
            av = next((f for f in facts if f["fact_kind"] == "allowed_values"), None)
            avdoc = fdoc(av, p) if av else None
            if rules.EFFECT_LEAF.match(lf) and vals and avdoc:
                v = {"aspect": "effect_attribute", "rule": "R-EFFECT-DOC", "attribute": path,
                     "values": allowed(facts), "c03_fact_id": av["fact_id"], **extra}
                d = default_of(facts)
                if d:
                    v["default"] = d
                ctx.add(T, "effect", f"attr:{path}", api, "stated", "published", value=v, doc=avdoc)
            elif rules.EFFECT_BLOCK.match(lf) and ddoc:
                m = rules.EFFECT_BLOCK_DESC.search(ddoc["sentence"])
                if m:
                    v = {"aspect": "effect_block", "rule": "R-EFFECT-DOC", "attribute": path,
                         "effect": m.group(1).lower(), "c03_fact_id": desc["fact_id"], **extra}
                    ctx.add(T, "effect", f"attr:{path}", api, "stated", "published", value=v, doc=ddoc)
        if is_prec and ddoc:
            s = ddoc["sentence"]
            v = {"aspect": "order_attribute", "rule": "R-PREC-DOC", "attribute": path,
                 "order": rules.prec_order(s), "c03_fact_ids": sorted(f["fact_id"] for f in facts), **extra}
            ctx.add(T, "precedence", f"attr:{path}", api, "stated", "published", value=v, doc=ddoc)
    if not got_ttl:
        unknown(ctx, T, "ttl_support", api, page)


# ---------------------------------------------------------------- provedor inteiro

def run(provider: str) -> tuple["Ctx", dict, dict]:
    ctx = Ctx(provider)
    ts, variants = sources.typesub(provider)
    all_types = sources.types(provider)
    pages, bridges, info = {}, {}, {}
    for T in all_types:
        tsr = ts.get(T)
        page = tsr["doc_file"] if tsr and tsr.get("doc_file") and common.page_lines(provider, tsr["doc_file"]) \
            else None
        pages[T] = page
        api, beid, ver = bridge(ctx, T, tsr, page)
        bridges[T] = api if beid else None
        info[T] = (api, ver)
    for T in all_types:
        api, ver = info[T]
        tsr = ts.get(T)
        page = pages[T]
        imp_eid, sid, tid, template, id_schema = import_and_identity(ctx, T, tsr, page, api, ver)
        if bridges[T] is None and not sid and not tid:
            unknown(ctx, T, "identity", api, page)
        if provider == "aws" and page:
            seen = set()
            for i, ln in enumerate(common.page_lines(provider, page)):
                for m in AWS_API.finditer(ln):
                    if m.group(0) in seen:
                        continue
                    seen.add(m.group(0))
                    ctx.add(T, "identity", f"apiref:{m.group(0)}", {"service": m.group(1), "resource": UNKNOWN},
                            "stated", "published",
                            value={"aspect": "api_reference", "rule": "R-APIREF-AWS", "doc_service": m.group(1),
                                   "name": m.group(2), "url": m.group(0)},
                            doc=common.doc_cite(provider, page, i + 1))
        owner(ctx, T, api, template, tid, sid, id_schema, bridges, page)
        scope_and_life(ctx, T, api, page)
        attributes(ctx, T, api, page)
    out_of_pin = sorted(t for t in ts if t not in set(all_types))
    stats = {"types": len(all_types), "types_with_page": sum(1 for t in all_types if pages[t]),
             "types_with_bridge": sum(1 for t in all_types if bridges[t] is not None),
             "type_subcategory_resources_out_of_pin_schema": len(out_of_pin),
             "type_subcategory_variants": variants, "counters": dict(ctx.st)}
    return ctx, stats, {"out_of_pin_examples": out_of_pin[:20], "bridges": bridges}
