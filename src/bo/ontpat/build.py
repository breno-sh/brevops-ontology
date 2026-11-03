"""Gera os artefatos derivados do ONTPAT (regeneração idêntica conferida por --check).

  example-abox.ttl  = corpo escrito à mão (content/example_abox_body.ttl) + contexto TBox que a validação
                      SHACL precisa sob o regime declarado (grafo de dados tal como dado, sem entailment):
                      subclasses e subpropriedades nomeadas, declarações, tipos dos valores controlados e os descritores de bo:.
  upper_trial/*/cases.ttl  (bo.ontpat.upper_trial.write_cases)

Uso: python -I -m bo.ontpat.build [--check]
"""

from __future__ import annotations

import sys
from pathlib import Path

import rdflib
from rdflib.namespace import OWL, RDF, RDFS

from . import common as c

CONTEXT_MARK = "# ==== contexto TBox para a validação SHACL (gerado por bo.ontpat.build; não editar) ===="
PROP_TYPES = (OWL.ObjectProperty, OWL.DatatypeProperty, OWL.AnnotationProperty)


def tbox_context(closure: rdflib.Graph) -> rdflib.Graph:
    ctx = rdflib.Graph()
    for s, o in closure.subject_objects(RDFS.subClassOf):
        if isinstance(s, rdflib.URIRef) and isinstance(o, rdflib.URIRef):
            ctx.add((s, RDFS.subClassOf, o))
    for s, o in closure.subject_objects(RDFS.subPropertyOf):
        if isinstance(s, rdflib.URIRef) and isinstance(o, rdflib.URIRef):
            ctx.add((s, RDFS.subPropertyOf, o))
    for t in (OWL.Class, *PROP_TYPES):
        for s in closure.subjects(RDF.type, t):
            if isinstance(s, rdflib.URIRef):
                ctx.add((s, RDF.type, t))
    for s in closure.subjects(RDF.type, OWL.NamedIndividual):  # valores controlados de bo: (tipos)
        for o in closure.objects(s, RDF.type):
            ctx.add((s, RDF.type, o))
    for k in (c.BO.PropertyDescriptor, c.BO.ClassDescriptor):
        for s in closure.subjects(RDF.type, k):
            for p, o in closure.predicate_objects(s):
                ctx.add((s, p, o))
    return ctx


def nt_lines(g: rdflib.Graph) -> list[str]:
    return sorted(line for line in g.serialize(format="nt").splitlines() if line.strip())


def example_text() -> str:
    pdir = c.patterns_dir()
    closure, _ = c.load_closure(pdir / c.PATTERNS)
    body = (c.content_dir() / "example_abox_body.ttl").read_text(encoding="utf-8")
    body_g = rdflib.Graph()
    body_g.parse(data=body, format="turtle", publicID=(pdir / c.EXAMPLE).resolve().as_uri())
    ctx = tbox_context(closure)
    for t in body_g:  # o que o corpo já diz não se repete no contexto
        ctx.remove(t)
    head = ("# BrevOps Ontology, módulo ONTPAT: ABox de exemplo dos padrões. Gerado por bo.ontpat.build a partir de\n"
            "# src/bo/ontpat/content/example_abox_body.ttl; não editar à mão (o gate confere a regeneração idêntica).\n")
    return head + body.split("\n", 2)[2] + "\n" + CONTEXT_MARK + "\n" + "\n".join(nt_lines(ctx)) + "\n"


def targets() -> dict[Path, str]:
    from . import upper_trial
    out = {c.patterns_dir() / c.EXAMPLE: example_text()}
    out.update(upper_trial.cases_texts())
    return out


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    check = "--check" in argv
    bad = []
    for p, text in targets().items():
        if check:
            cur = p.read_text(encoding="utf-8") if p.exists() else None
            if cur != text:
                bad.append(str(p))
        else:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text, encoding="utf-8")
            c.emit(f"escrito {p}")
    if bad:
        c.emit("regeneração difere: " + ", ".join(bad))
        return 1
    if check:
        c.emit("regeneração idêntica: ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
