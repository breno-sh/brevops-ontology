"""Extrator OWL/XML (sintaxe funcional em XML, export do WebProtégé): Cloud Property Graph e CertGraph.

Lê Declaration, SubClassOf (nomeada e com restrição DataSomeValuesFrom/ObjectSomeValuesFrom), AnnotationAssertion
(rdfs:label, rdfs:comment, dc:description), *PropertyDomain/Range e ClassAssertion. Vínculo de provedor = só o que a
ontologia publica: ClassAssertion de um indivíduo no espaço de nomes de um provedor (individuals/aws/,
individuals/azure/...) a uma classe. Linha = primeira ocorrência do IRI no arquivo.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from .common import Cls, Extract, Link, Prop, clean, line_of, local

OWL = "{http://www.w3.org/2002/07/owl#}"
XML_BASE = "{http://www.w3.org/XML/1998/namespace}base"


class Owx:
    def __init__(self, path: Path):
        self.path = path
        self.text = path.read_text(encoding="utf-8")
        self.root = ET.fromstring(self.text)
        self.base = self.root.get(XML_BASE) or self.root.get("ontologyIRI") or ""
        self.prefixes = {p.get("name"): p.get("IRI") for p in self.root.findall(f"{OWL}Prefix")}

    def iri(self, el) -> str:
        if el is None:
            return ""
        v = el.get("IRI")
        if v is None and el.get("abbreviatedIRI"):
            pre, _, loc = el.get("abbreviatedIRI").partition(":")
            return self.prefixes.get(pre, pre + ":") + loc
        if v is None:
            v = (el.text or "").strip()
            if el.tag == f"{OWL}AbbreviatedIRI":
                pre, _, loc = v.partition(":")
                return self.prefixes.get(pre, pre + ":") + loc
        if v and not v.startswith(("http://", "https://", "urn:")):
            return self.base.rstrip("/") + ("" if v.startswith("/") else "/") + v
        return v

    def line(self, el) -> int:
        raw = el.get("IRI") or el.get("abbreviatedIRI") or (el.text or "").strip()
        return line_of(self.text, f'"{raw}"') or line_of(self.text, raw)


def extract(model: str, path: Path, label_path: str, ns: dict, ind_ns: dict) -> Extract:
    """ns: {prefixo: base} para classes/propriedades; ind_ns: {base de indivíduo: provedor}."""
    o = Owx(path)
    ex = Extract(model=model, files=[(label_path, path)])

    def curie(i: str) -> str:
        for pre, base in sorted(ns.items(), key=lambda kv: -len(kv[1])):
            if i.startswith(base):
                return f"{pre}:{local(i[len(base):])}"
        return i

    classes, dprops, oprops, inds, lines = {}, {}, {}, {}, {}
    for d in o.root.findall(f"{OWL}Declaration"):
        for child in d:
            i = o.iri(child)
            tag = child.tag.replace(OWL, "")
            lines.setdefault(i, o.line(child))
            {"Class": classes, "DataProperty": dprops, "ObjectProperty": oprops,
             "NamedIndividual": inds}.get(tag, {}).setdefault(i, {})
    labels, comments = {}, {}
    for a in o.root.findall(f"{OWL}AnnotationAssertion"):
        prop = o.iri(a.find(f"{OWL}AnnotationProperty"))
        subj = a.find(f"{OWL}IRI")
        if subj is None:
            subj = a.find(f"{OWL}AbbreviatedIRI")
        lit = a.find(f"{OWL}Literal")
        if subj is None or lit is None:
            continue
        s = o.iri(subj)
        if prop.endswith("#label"):
            labels.setdefault(s, (lit.text or "").strip())
        elif prop.endswith("#comment") or prop.endswith("/description"):
            comments.setdefault(s, (lit.text or "").strip())
    parents = {c: [] for c in classes}
    pdomain = {}
    prange = {}
    for sc in o.root.findall(f"{OWL}SubClassOf"):
        kids = list(sc)
        if len(kids) != 2 or kids[0].tag != f"{OWL}Class":
            continue
        sub = o.iri(kids[0])
        sup = kids[1]
        if sup.tag == f"{OWL}Class":
            parents.setdefault(sub, []).append(o.iri(sup))
        elif sup.tag in (f"{OWL}DataSomeValuesFrom", f"{OWL}ObjectSomeValuesFrom"):
            p, r = list(sup)[0], list(sup)[1] if len(sup) > 1 else None
            pi = o.iri(p)
            pdomain.setdefault(pi, set()).add(sub)
            if r is not None:
                prange.setdefault(pi, set()).add(o.iri(r) if r.get("IRI") or r.get("abbreviatedIRI") else "")
    declared_dom, declared_rng = {}, {}
    for kind in ("Data", "Object"):
        for el in o.root.findall(f"{OWL}{kind}PropertyDomain"):
            k = list(el)
            declared_dom.setdefault(o.iri(k[0]), set()).add(o.iri(k[1]))
        for el in o.root.findall(f"{OWL}{kind}PropertyRange"):
            k = list(el)
            declared_rng.setdefault(o.iri(k[0]), set()).add(o.iri(k[1]))

    for c in sorted(classes):
        ex.classes.append(Cls(id=curie(c), native=c, label=labels.get(c) or c.rsplit("/", 1)[-1],
                              definition=clean(comments.get(c)),
                              parents=[curie(p) for p in sorted(set(parents.get(c, [])))],
                              source=label_path, line=lines.get(c, 0)))
    for kind, table in (("datatype", dprops), ("object", oprops)):
        for p in sorted(table):
            dom = declared_dom.get(p)
            dk = "declared" if dom else ("restriction" if pdomain.get(p) else "")
            dom = dom or pdomain.get(p) or set()
            rng = sorted(x for x in (declared_rng.get(p) or prange.get(p) or set()) if x)
            ex.props.append(Prop(id=curie(p), native=p, label=labels.get(p) or p.rsplit("/", 1)[-1], kind=kind,
                                 domain=[curie(d) for d in sorted(dom)], domain_kind=dk,
                                 range="|".join(curie(r) for r in rng), definition=clean(comments.get(p)),
                                 source=label_path, line=lines.get(p, 0)))
    for ca in o.root.findall(f"{OWL}ClassAssertion"):
        k = list(ca)
        if len(k) != 2 or k[0].tag != f"{OWL}Class":
            continue
        cl, ind = o.iri(k[0]), o.iri(k[1])
        prov = next((pv for base, pv in ind_ns.items() if ind.startswith(base)), None)
        if prov is None:
            continue
        ex.links.append(Link(subject=curie(ind), object=curie(cl), native_relation="owl:ClassAssertion",
                             link_kind="provider_class_to_model_class", level="class", provider=prov,
                             source=label_path, line=o.line(k[1]),
                             sentence=f"ClassAssertion({cl.rsplit('/', 1)[-1]} {ind.rsplit('/', 1)[-1]})",
                             subject_label=labels.get(ind) or ind.rsplit("/", 1)[-1],
                             object_label=labels.get(cl) or cl.rsplit("/", 1)[-1]))
    ex.prefixes = dict(ns)
    ex.counts = {"declared_classes": len(classes), "declared_data_properties": len(dprops),
                 "declared_object_properties": len(oprops), "declared_individuals": len(inds),
                 "provider_individuals": sum(1 for i in inds if any(i.startswith(b) for b in ind_ns))}
    byp = {}
    for i in inds:
        pv = next((v for b, v in ind_ns.items() if i.startswith(b)), None)
        if pv:
            byp.setdefault(pv, []).append(curie(i))
    ex.counts["provider_individuals_by_provider"] = {k: len(v) for k, v in sorted(byp.items())}
    ex.provider_terms = {k: sorted(v) for k, v in byp.items()}
    ex.provider_unit = "indivíduos OWL de provedor"
    return ex
