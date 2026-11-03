"""Nenhum IRI usado como classe ou propriedade E como indivíduo (sem punning), nem metamodelagem.

  python -I -m bo.ontpat.no_punning [ARQ.ttl ...]

Sem argumentos, confere os artefatos do ONTPAT: o fecho de bo-patterns.ttl, o ABox de exemplo, as formas e
cada upper_trial/*/cases.ttl junto com o fecho (não junto com a candidata: o que se confere é o que NÓS
escrevemos). Antes, roda os controles: um grafo com punning plantado tem de ser pego e o padrão de descritor
tem de passar. Se um controle falha, sai 2 (o verificador não é confiável). Relatório em $BO_DATA/ONTPAT/.

Papéis de um IRI:
  classe       tipado owl:Class/rdfs:Class, ou em posição de classe (subClassOf, equivalentClass, disjointWith,
               someValuesFrom, allValuesFrom, onClass, domain/range de propriedade de objeto, membros de
               unionOf/intersectionOf/AllDisjointClasses/disjointUnionOf, sujeito de hasKey, objeto de rdf:type)
  propriedade  tipado como propriedade, usado como predicado fora do vocabulário embutido, onProperty,
               subPropertyOf, inverseOf, propertyChainAxiom, membro de hasKey
  indivíduo    owl:NamedIndividual, sujeito de rdf:type com classe não embutida, sujeito ou objeto de
               asserção de propriedade de objeto, membro de oneOf/AllDifferent, sameAs/differentFrom
Valores de anotação NÃO tipam o IRI (é o que o padrão de descritor usa).
Metamodelagem: domain/range ou rdf:type com objeto owl:Class, rdfs:Class ou propriedade-tipo.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import rdflib
from rdflib.collection import Collection
from rdflib.namespace import OWL, RDF, RDFS, XSD

from . import common as c

BUILTIN = (str(RDF), str(RDFS), str(OWL), str(XSD), "http://www.w3.org/ns/shacl#")
META = {OWL.Class, RDFS.Class, OWL.ObjectProperty, OWL.DatatypeProperty, OWL.AnnotationProperty, RDF.Property,
        OWL.Restriction, OWL.Ontology}
PROP_TYPES = {OWL.ObjectProperty, OWL.DatatypeProperty, OWL.AnnotationProperty, RDF.Property, OWL.FunctionalProperty,
              OWL.InverseFunctionalProperty, OWL.TransitiveProperty, OWL.SymmetricProperty, OWL.AsymmetricProperty,
              OWL.ReflexiveProperty, OWL.IrreflexiveProperty}
CLASS_OBJ_PREDS = {RDFS.subClassOf, OWL.equivalentClass, OWL.disjointWith, OWL.someValuesFrom, OWL.allValuesFrom,
                   OWL.onClass, OWL.complementOf}
LIST_CLASS_PREDS = {OWL.unionOf, OWL.intersectionOf, OWL.disjointUnionOf}


def builtin(x) -> bool:
    return isinstance(x, rdflib.URIRef) and str(x).startswith(BUILTIN)


def _lst(g, node):
    try:
        return list(Collection(g, node))
    except Exception:
        return []


def roles(g: rdflib.Graph) -> dict:
    cls, prop, ind = set(), set(), set()
    ann = set(g.subjects(RDF.type, OWL.AnnotationProperty))
    objp = set(g.subjects(RDF.type, OWL.ObjectProperty))
    onts = set(g.subjects(RDF.type, OWL.Ontology))
    for s, p, o in g:
        if p == RDF.type:
            if o in (OWL.Class, RDFS.Class):
                cls.add(s)
            elif o in PROP_TYPES:
                prop.add(s)
            elif o == OWL.NamedIndividual:
                ind.add(s)
            elif o not in META and not builtin(o) and o not in (OWL.AllDisjointClasses, OWL.AllDifferent,
                                                              OWL.AllDisjointProperties, OWL.NegativePropertyAssertion):
                ind.add(s)
                cls.add(o)
            continue
        if p in CLASS_OBJ_PREDS:
            cls.add(o)
            if p in (RDFS.subClassOf, OWL.equivalentClass, OWL.disjointWith):
                cls.add(s)
        elif p in LIST_CLASS_PREDS:
            cls.update(_lst(g, o))
            if p == OWL.disjointUnionOf:
                cls.add(s)
        elif p == OWL.hasKey:
            cls.add(s)
            prop.update(_lst(g, o))
        elif p in (OWL.onProperty, OWL.inverseOf):
            prop.add(o)
        elif p in (RDFS.subPropertyOf, OWL.equivalentProperty, OWL.propertyDisjointWith):
            prop.update((s, o))
        elif p == OWL.propertyChainAxiom:
            prop.add(s)
            prop.update(_lst(g, o))
        elif p in (RDFS.domain, RDFS.range):
            prop.add(s)
            if s in objp or p == RDFS.domain:
                cls.add(o)
        elif p == OWL.oneOf or p == OWL.distinctMembers:
            ind.update(_lst(g, o))
        elif p == OWL.members:
            pass
        elif p in (OWL.sameAs, OWL.differentFrom):
            ind.update((s, o))
        elif p in (OWL.imports, OWL.versionIRI, OWL.priorVersion, OWL.backwardCompatibleWith, OWL.incompatibleWith):
            pass
        elif not builtin(p):
            prop.add(p)
            if p in ann or s in onts:
                continue  # anotação: o valor não tipa o IRI
            ind.add(s)
            if isinstance(o, rdflib.URIRef) and p in objp:
                ind.add(o)
    keep = lambda xs: {x for x in xs if isinstance(x, rdflib.URIRef) and not builtin(x) and x not in onts}
    return {"class": keep(cls), "property": keep(prop), "individual": keep(ind)}


def metamodelling(g: rdflib.Graph) -> list[str]:
    out = []
    for p in (RDFS.domain, RDFS.range):
        for s, o in g.subject_objects(p):
            if o in META - {OWL.Ontology}:
                out.append(f"{s} {p.split('#')[-1]} {o.split('#')[-1]}")
    return out


def punned(g: rdflib.Graph) -> list:
    r = roles(g)
    return sorted((r["class"] | r["property"]) & r["individual"]) + sorted(r["class"] & r["property"])


def report(g: rdflib.Graph) -> dict:
    r = roles(g)
    return {"class_and_individual": sorted(str(x) for x in r["class"] & r["individual"]),
            "property_and_individual": sorted(str(x) for x in r["property"] & r["individual"]),
            "class_and_property": sorted(str(x) for x in r["class"] & r["property"]),
            "metamodelling": metamodelling(g),
            "counts": {k: len(v) for k, v in r.items()}}


def clean(rep: dict) -> bool:
    return not (rep["class_and_individual"] or rep["property_and_individual"] or rep["class_and_property"] or rep["metamodelling"])


CONTROL_BAD = """@prefix owl: <http://www.w3.org/2002/07/owl#> . @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix bo: <https://w3id.org/brevops/ontology#> . @prefix x: <https://example.org/ctl#> .
bo:of a owl:ObjectProperty .
x:C a owl:Class . x:p a owl:ObjectProperty .
x:r1 bo:of x:p .
x:r2 a x:C ; x:p x:C .
x:hasRealization a owl:ObjectProperty ; rdfs:domain owl:Class .
"""
CONTROL_GOOD = """@prefix owl: <http://www.w3.org/2002/07/owl#> . @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix bo: <https://w3id.org/brevops/ontology#> . @prefix x: <https://example.org/ctl#> .
bo:of a owl:ObjectProperty . bo:describesProperty a owl:AnnotationProperty .
x:C a owl:Class . x:p a owl:ObjectProperty .
x:desc_p a owl:NamedIndividual , bo:PropertyDescriptor ; bo:describesProperty x:p .
x:r1 bo:of x:desc_p .
x:r2 a x:C ; x:p x:r3 .
"""


def controls() -> list[str]:
    bad = []
    rb = report(rdflib.Graph().parse(data=CONTROL_BAD, format="turtle"))
    want = {"https://example.org/ctl#p", "https://example.org/ctl#C"}
    if set(rb["property_and_individual"]) | set(rb["class_and_individual"]) != want or not rb["metamodelling"]:
        bad.append(f"controle positivo falhou: {rb}")
    rg = report(rdflib.Graph().parse(data=CONTROL_GOOD, format="turtle"))
    if not clean(rg):
        bad.append(f"controle negativo (padrão de descritor) acusado: {rg}")
    return bad


def default_targets() -> list[tuple[str, rdflib.Graph]]:
    pdir = c.patterns_dir()
    closure, _ = c.load_closure(pdir / c.PATTERNS)
    out = [("bo-patterns.ttl (fecho)", closure)]
    ex = rdflib.Graph()
    ex += closure
    c.parse(pdir / c.EXAMPLE, ex)
    out.append(("example-abox.ttl + fecho", ex))
    out.append(("patterns.shacl.ttl", c.parse(c.repo() / "shapes" / "patterns.shacl.ttl")))
    for cand in c.CANDIDATES:
        g = rdflib.Graph()
        g += closure
        c.parse(pdir / "upper_trial" / cand / "cases.ttl", g)
        out.append((f"upper_trial/{cand}/cases.ttl + fecho", g))
    return out


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    ctl = controls()
    if ctl:
        for b in ctl:
            c.emit("CONTROLE: " + b)
        return 2
    targets = [(a, c.parse(Path(a))) for a in argv] if argv else default_targets()
    out, ok = {"controls": "ok", "checked_at": c.now(), "targets": {}}, True
    for name, g in targets:
        rep = report(g)
        out["targets"][name] = rep
        status = "ok" if clean(rep) else "PUNNING"
        ok = ok and clean(rep)
        c.emit(f"{status}  {name}: {rep['counts']['class']} classes, {rep['counts']['property']} propriedades, "
               f"{rep['counts']['individual']} indivíduos; conflitos={len(rep['class_and_individual']) + len(rep['property_and_individual']) + len(rep['class_and_property'])}, "
               f"metamodelagem={len(rep['metamodelling'])}")
        for k in ("class_and_individual", "property_and_individual", "class_and_property", "metamodelling"):
            for x in rep[k][:10]:
                c.emit(f"     {k}: {x}")
    d = c.data_dir() / "ONTPAT"
    d.mkdir(parents=True, exist_ok=True)
    (d / "no_punning_report.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
