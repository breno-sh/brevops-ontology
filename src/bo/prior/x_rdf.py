"""Extrator RDF (RDF/XML ou Turtle, via rdflib, só parse): DevOps-Infra e CoCoOn.

Classe = owl:Class ou rdfs:Class com IRI no espaço de nomes do próprio modelo; pais = rdfs:subClassOf nomeado;
propriedade = owl:ObjectProperty/DatatypeProperty do espaço do modelo, com rdfs:domain/rdfs:range (owl:unionOf
desdobrado). Definição: skos:definition, rdfs:comment ou dcterms:description (inglês primeiro).
"""

from __future__ import annotations

from pathlib import Path

import rdflib
from rdflib import OWL, RDF, RDFS, SKOS, BNode, URIRef
from rdflib.collection import Collection
from rdflib.namespace import DCTERMS

from .common import Cls, Extract, Prop, clean, line_of, local


def _lit(g, s, preds) -> str:
    for p in preds:
        vals = list(g.objects(s, p))
        en = [v for v in vals if getattr(v, "language", None) in ("en", None)]
        for v in en or vals:
            return str(v)
    return ""


def _members(g, node) -> list:
    if isinstance(node, URIRef):
        return [node]
    if isinstance(node, BNode):
        u = g.value(node, OWL.unionOf)
        if u is not None:
            return [m for m in Collection(g, u) if isinstance(m, URIRef)]
    return []


def extract(model: str, files: list[tuple[str, Path]], ns: dict, fmt_by_suffix: dict | None = None) -> Extract:
    ex = Extract(model=model, files=list(files))
    fmt_by_suffix = fmt_by_suffix or {".rdf": "xml", ".xml": "xml", ".ttl": "turtle", ".owl": "xml"}
    bases = sorted(ns.items(), key=lambda kv: -len(kv[1]))

    def curie(i) -> str:
        i = str(i)
        for pre, base in bases:
            if i.startswith(base):
                return f"{pre}:{local(i[len(base):])}"
        return i

    def mine(i) -> bool:
        return isinstance(i, URIRef) and any(str(i).startswith(b) for _, b in bases)

    seen_c, seen_p = set(), set()
    for label_path, path in files:
        text = path.read_text(encoding="utf-8", errors="replace")
        g = rdflib.Graph()
        g.parse(data=text, format=fmt_by_suffix[path.suffix])
        pfx = {str(v): k for k, v in g.namespaces()}

        def line(i) -> int:
            s = str(i)
            n = line_of(text, f'"{s}"') or line_of(text, f"<{s}>")
            if n:
                return n
            for base, k in pfx.items():
                if s.startswith(base) and base:
                    n = line_of(text, f"{k}:{s[len(base):]}")
                    if n:
                        return n
            return 0

        cls = set(g.subjects(RDF.type, OWL.Class)) | set(g.subjects(RDF.type, RDFS.Class))
        for c in sorted((c for c in cls if mine(c)), key=str):
            if c in seen_c:
                continue
            seen_c.add(c)
            parents = sorted({curie(p) for p in g.objects(c, RDFS.subClassOf) if isinstance(p, URIRef)})
            ex.classes.append(Cls(id=curie(c), native=str(c), label=_lit(g, c, [RDFS.label, SKOS.prefLabel])
                                  or str(c).rsplit("#", 1)[-1].rsplit("/", 1)[-1],
                                  definition=clean(_lit(g, c, [SKOS.definition, RDFS.comment, DCTERMS.description])),
                                  parents=parents, source=label_path, line=line(c)))
        for kind, t in (("object", OWL.ObjectProperty), ("datatype", OWL.DatatypeProperty)):
            for p in sorted((p for p in g.subjects(RDF.type, t) if mine(p)), key=str):
                if p in seen_p:
                    continue
                seen_p.add(p)
                dom = sorted({curie(m) for d in g.objects(p, RDFS.domain) for m in _members(g, d)})
                rng = sorted({curie(m) for r in g.objects(p, RDFS.range) for m in _members(g, r)})
                ex.props.append(Prop(id=curie(p), native=str(p),
                                     label=_lit(g, p, [RDFS.label, SKOS.prefLabel])
                                     or str(p).rsplit("#", 1)[-1].rsplit("/", 1)[-1], kind=kind, domain=dom,
                                     domain_kind="declared" if dom else "", range="|".join(rng),
                                     definition=clean(_lit(g, p, [SKOS.definition, RDFS.comment,
                                                                   DCTERMS.description])),
                                     source=label_path, line=line(p)))
    ex.prefixes = dict(ns)
    ex.counts = {"classes_in_model_namespace": len(ex.classes), "properties_in_model_namespace": len(ex.props)}
    return ex
