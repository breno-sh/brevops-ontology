"""Extrator TOSCA 2.0 (perfis da comunidade OASIS) e EDMM (docs/types.yml), por yaml.safe_load.

Classe = tipo (node_types, relationship_types, capability_types, data_types, artifact_types, group_types,
policy_types, interface_types; no EDMM, component_types e relation_types). Pais = derived_from (TOSCA) ou extends
(EDMM), resolvidos pelo namespace do import. Propriedade = chaves de properties e attributes do tipo. Provedor:
perfis com.amazon.aws, com.google.cloud e com.microsoft.azure; no EDMM, tipos com prefixo aws_/azure_/gcp_.
Vínculo publicado: tipo do provedor -> primeiro ancestral neutro na cadeia derived_from/extends.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from .common import Cls, Extract, Link, Prop, clean, line_of, local

SECTIONS = ("node_types", "relationship_types", "capability_types", "data_types", "artifact_types", "group_types",
            "policy_types", "interface_types")
PROFILE_PROVIDER = {"com.amazon.aws": "aws", "com.google.cloud": "google", "com.microsoft.azure": "azurerm",
                    "io.terraform": "other:terraform"}
PRIMITIVE = {"string", "integer", "float", "boolean", "timestamp", "map", "list", "range", "version", "scalar-unit",
             "scalar-unit.size", "scalar-unit.time", "scalar-unit.frequency", "scalar-unit.bitrate", "bytes",
             "nil", "any"}


def _slug(profile: str) -> str:
    name = profile.split(":")[0]
    return "t_" + local(name.replace(".", "_").replace("-", "_"))


def _provider(profile: str) -> str:
    name = profile.split(":")[0]
    for k, v in PROFILE_PROVIDER.items():
        if name.startswith(k):
            return v
    return ""


def extract(model: str, tosca_files: list[tuple[str, Path]], edmm_file: tuple[str, Path]) -> Extract:
    ex = Extract(model=model, files=list(tosca_files) + [edmm_file])
    docs = []
    for lb, p in tosca_files:
        text = p.read_text(encoding="utf-8")
        d = yaml.safe_load(text) or {}
        prof = d.get("profile") or ("community.edmm:0" if p.name == "edmm.yaml" else p.parent.name)
        docs.append((lb, p, text, d, prof))
    known = {prof.split(":")[0] for *_, prof in docs}
    types = {}   # (perfil-base, nome) -> (Cls, seção, dict)
    for lb, p, text, d, prof in docs:
        pslug, prov = _slug(prof), _provider(prof)
        ex.prefixes[pslug] = f"https://w3id.org/brevops/prior/tosca/{prof.split(':')[0]}/"
        for sec in SECTIONS:
            for name, body in (d.get(sec) or {}).items():
                body = body if isinstance(body, dict) else {}
                c = Cls(id=f"{pslug}:{local(name)}", native=f"{prof}#{name}", label=name,
                        definition=clean(body.get("description")), provider=prov, source=lb,
                        line=line_of(text, f"\n  {name}:") + 1 if line_of(text, f"\n  {name}:") else 0)
                types[(prof.split(":")[0], name)] = (c, sec, body, d, text, lb)
    def resolve(prof_doc: dict, prof: str, ref: str):
        base = prof.split(":")[0]
        ns, _, nm = ref.rpartition(":")
        if ns:
            for imp in prof_doc.get("imports") or []:
                if isinstance(imp, dict) and imp.get("namespace") == ns:
                    tgt = imp["profile"].split(":")[0]
                    return (tgt, nm), tgt in known
            return (f"?{ns}", nm), False
        if (base, nm) in types:
            return (base, nm), True
        for imp in prof_doc.get("imports") or []:
            if isinstance(imp, dict) and not imp.get("namespace"):
                tgt = imp["profile"].split(":")[0]
                if (tgt, nm) in types:
                    return (tgt, nm), True
        return None, False
    unresolved = 0
    for (pbase, name), (c, sec, body, d, text, lb) in sorted(types.items()):
        ref = body.get("derived_from")
        if isinstance(ref, str) and ref not in PRIMITIVE:
            key, ok = resolve(d, d.get("profile") or pbase, ref)
            if key and ok and key in types:
                c.parents.append(types[key][0].id)
            elif key:
                unresolved += 1
                pre = _slug(key[0].lstrip("?"))
                ex.prefixes.setdefault(pre, f"https://w3id.org/brevops/prior/tosca/{key[0].lstrip('?')}/")
                c.parents.append(f"{pre}:{local(key[1])}")
            else:
                unresolved += 1
        ex.classes.append(c)
        for kind in ("properties", "attributes"):
            for pn, pb in (body.get(kind) or {}).items():
                pb = pb if isinstance(pb, dict) else {}
                ex.props.append(Prop(id=f"{c.id}.{local(pn)}", native=f"{c.native}.{pn}", label=pn,
                                     kind="datatype", domain=[c.id], domain_kind="class_member",
                                     range=f"tt:{local(str(pb.get('type', '')))}" if pb.get("type") else "",
                                     definition=clean(pb.get("description")), provider=c.provider, source=lb,
                                     line=c.line))
    ex.prefixes["tt"] = "https://docs.oasis-open.org/tosca/TOSCA/v2.0/TOSCA-v2.0.html#type-"
    byid = {c.id: c for c in ex.classes}

    def first_neutral(c: Cls, chain=None):
        chain = (chain or []) + [c.id]
        for pid in c.parents:
            pc = byid.get(pid)
            if pc is None:
                return pid, chain + [pid]
            if not pc.provider:
                return pid, chain + [pid]
            if pid not in chain:
                r = first_neutral(pc, chain)
                if r:
                    return r
        return None
    for c in ex.classes:
        if c.provider and not c.provider.startswith("other:"):
            r = first_neutral(c)
            if r:
                tgt, chain = r
                ex.links.append(Link(subject=c.id, object=tgt, native_relation="tosca:derived_from",
                                     link_kind="provider_class_to_model_class", level="class", provider=c.provider,
                                     source=c.source, line=c.line, sentence="derived_from: " + " -> ".join(chain),
                                     subject_label=c.label, object_label=tgt.split(":", 1)[1]))
    # EDMM
    lb, p = edmm_file
    text = p.read_text(encoding="utf-8")
    d = yaml.safe_load(text) or {}
    ex.prefixes["edmm"] = "https://github.com/UST-EDMM/edmm#type/"
    edmm = {}
    for sec in ("component_types", "relation_types"):
        for name, body in (d.get(sec) or {}).items():
            body = body if isinstance(body, dict) else {}
            prov = next((v for k, v in (("aws_", "aws"), ("azure_", "azurerm"), ("gcp_", "google"),
                                        ("google_", "google")) if name.startswith(k)), "")
            ln = line_of(text, f"\n  {name}:")
            c = Cls(id=f"edmm:{local(name)}", native=name, label=name, definition=clean(body.get("description")),
                    parents=[f"edmm:{local(body['extends'])}"] if body.get("extends") else [], provider=prov,
                    source=lb, line=ln + 1 if ln else 0)
            edmm[name] = c
            ex.classes.append(c)
            for pn, pb in (body.get("properties") or {}).items():
                pb = pb if isinstance(pb, dict) else {}
                ex.props.append(Prop(id=f"edmm:{local(name)}.{local(pn)}", native=f"{name}.{pn}", label=pn,
                                     kind="datatype", domain=[c.id], domain_kind="class_member",
                                     range=f"tt:{local(str(pb.get('type', '')))}" if pb.get("type") else "",
                                     definition=clean(pb.get("description")), provider=prov, source=lb, line=c.line))
    for name, c in sorted(edmm.items()):
        if not c.provider:
            continue
        cur, chain = c, [name]
        while cur.parents:
            nxt = edmm.get(cur.parents[0].split(":", 1)[1])
            if nxt is None:
                break
            chain.append(nxt.native)
            if not nxt.provider:
                ex.links.append(Link(subject=c.id, object=nxt.id, native_relation="edmm:extends",
                                     link_kind="provider_class_to_model_class", level="class", provider=c.provider,
                                     source=lb, line=c.line, sentence="extends: " + " -> ".join(chain),
                                     subject_label=name, object_label=nxt.native))
                break
            cur = nxt
    ex.counts = {"tosca_types": sum(1 for c in ex.classes if not c.id.startswith("edmm:")),
                 "edmm_types": len(edmm), "unresolved_derived_from": unresolved,
                 "provider_types": sum(1 for c in ex.classes if c.provider and not c.provider.startswith("other:"))}
    return ex
