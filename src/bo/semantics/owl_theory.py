"""Teoria OWL/SKOS: o que se INFERE das alegações (separado do que se TRANSPORTA).

Usa os axiomas do próprio W3C (core.rdf da SKOS, sha256 fixado) e o fecho OWL 2 RL do owlrl:
  - skos:broadMatch owl:inverseOf skos:narrowMatch; broadMatch ⊑ broader ('more general in meaning')
  - skos:exactMatch é TransitiveProperty e SymmetricProperty, ⊑ closeMatch
  - skos:closeMatch e skos:relatedMatch são só simétricas (não transitivas)
O fecho vê triplas, não guardas, domínios nem perdas. Por isso uma consequência OWL (ex.: a exactMatch c pela
transitividade) NUNCA habilita transporte: o transporte composto sai só da tabela formal (composition), que
intersecta guardas e confere domínios. separation_report() mostra os dois lados no mesmo caso.
"""

from __future__ import annotations

import rdflib
from rdflib import URIRef
from rdflib.namespace import OWL, RDF

from . import common
from .sssom_io import PREFIXES, expand, hydrate, to_rdf
from .vocab import SKOS

S = rdflib.Namespace(SKOS)


class SkosSchemaError(RuntimeError):
    pass


def skos_graph() -> rdflib.Graph:
    p = common.skos_schema_path()
    if not p.is_file():
        raise SkosSchemaError(f"schema SKOS ausente: {p} (ver SOURCE.txt; baixar de https://www.w3.org/2004/02/skos/core.rdf)")
    sha = common.sha256_file(p)
    if sha != common.SKOS_SHA256:
        raise SkosSchemaError(f"schema SKOS mudou: sha256 {sha} != {common.SKOS_SHA256}")
    g = rdflib.Graph()
    g.parse(str(p), format="xml")
    return g


def skos_axioms(g: rdflib.Graph | None = None) -> dict:
    g = g or skos_graph()
    out = {}
    for name in ("exactMatch", "closeMatch", "broadMatch", "narrowMatch", "relatedMatch", "broader", "narrower"):
        u = S[name]
        out[name] = {
            "types": sorted(str(o).split("#")[-1] for o in g.objects(u, RDF.type)),
            "subPropertyOf": sorted(str(o).split("#")[-1] for o in g.objects(u, rdflib.RDFS.subPropertyOf)),
            "inverseOf": sorted(str(o).split("#")[-1] for o in g.objects(u, OWL.inverseOf)),
            "definition": str(g.value(u, S.definition) or ""),
        }
    return out


def closure(records: list[dict], ms_id: str = "https://example.org/mapping-set/owl-theory",
            prefixes: dict | None = None) -> rdflib.Graph:
    import owlrl
    g = hydrate(to_rdf(records, ms_id, prefixes=prefixes, extensions=False))
    g += skos_graph()
    owlrl.DeductiveClosure(owlrl.OWLRL_Semantics, axiomatic_triples=False, datatype_axioms=False).expand(g)
    return g


def has(g: rdflib.Graph, s: str, p: str, o: str, prefixes: dict | None = None) -> bool:
    px = prefixes or PREFIXES
    return (expand(s, px), expand(p, px), expand(o, px)) in g


def mapping_triples(g: rdflib.Graph) -> set[tuple[str, str, str]]:
    """Triplas entre recursos de provedor com predicado SKOS de mapeamento ou hierárquico (para relatório)."""
    inv = sorted(((v, k) for k, v in PREFIXES.items()), key=lambda kv: -len(kv[0]))

    def c(u):
        s = str(u)
        for ns, p in inv:
            if s.startswith(ns):
                return f"{p}:{s[len(ns):]}"
        return s
    preds = {S[n] for n in ("exactMatch", "closeMatch", "broadMatch", "narrowMatch", "relatedMatch", "broader",
                            "narrower", "broaderTransitive", "narrowerTransitive", "related", "mappingRelation")}
    out = set()
    for s, p, o in g:
        if p in preds and isinstance(s, URIRef) and isinstance(o, URIRef) and not str(s).startswith(SKOS):
            out.add((c(s), c(p), c(o)))
    return out


def separation_report(m1: dict, m2: dict) -> dict:
    """Mesmo par de alegações: o que o fecho OWL infere entre as pontas e o que a tabela de composição faz."""
    from .composition import compose
    g = closure([m1, m2])
    a, c = m1["subject_id"], m2["object_id"]
    inferred = sorted(p for (s, p, o) in mapping_triples(g) if s == a and o == c)
    comp = compose(m1, m2)
    return {"ends": [a, c], "owl_inferred_between_ends": inferred,
            "composition_outcome": comp["outcome"], "composition_rule": comp.get("rule"),
            "composition_relation": (comp.get("claim") or {}).get("semantic_relation")}
