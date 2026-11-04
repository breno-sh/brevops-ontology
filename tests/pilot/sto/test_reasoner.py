"""O raciocinador RL do pipeline dá as mesmas consequências que o owlrl no mesmo grafo (vocabulário da fatia)."""
import owlrl
from rdflib import Graph, Literal, URIRef
from rdflib.namespace import RDF

from bo.pilot.sto import abox as A
from bo.pilot.sto import common as C
from bo.pilot.sto import lift as L


def _rdf(triples):
    g = Graph()
    for s, p, o in triples:
        g.add((URIRef(s), URIRef(p), Literal(o[2:]) if o.startswith("L:") else URIRef(o)))
    return g


def test_rl_matches_owlrl(ctx_syn, expected, ev):
    ttl = ctx_syn.owl_dir / "sto-c3_full.ttl"
    tb = Graph()
    tb.parse(ttl, format="turtle")
    ix = ctx_syn.tbox["c3_full"]
    picks = [f for f in sorted(expected["fixtures"]) if "DEC-SCOPE" in f or "DEC-PACK-P" in f][:6]
    for fid in picks:
        fx = C.read_json(C.repo() / expected["fixtures"][fid]["file"])
        tr, iri = A.abox_of(L.lift(fx, ctx_syn.claims, ev))
        mine = A.reason(tr, ix)
        g = _rdf(tr) + tb
        owlrl.DeductiveClosure(owlrl.OWLRL_Semantics, axiomatic_triples=False, datatype_axioms=False).expand(g)
        for ind in iri.values():
            theirs_t = {str(o) for o in g.objects(URIRef(ind), RDF.type) if str(o).startswith(A.S(""))}
            mine_t = {o for o in mine.types(ind) if o.startswith(A.S(""))}
            assert mine_t == theirs_t, (fid, ind)
            theirs_a = {str(o) for o in g.objects(URIRef(ind), URIRef(A.S("appliesTo")))}
            assert set(mine.objects(ind, A.S("appliesTo"))) == theirs_a, (fid, ind)


def test_c2_has_no_chain(ctx_syn):
    assert ctx_syn.tbox["c2_taxonomy"].chains == [] and ctx_syn.tbox["c2_taxonomy"].disjoint == set()
    assert len(ctx_syn.tbox["c3_full"].chains) == 2 and ctx_syn.tbox["c3_full"].disjoint
