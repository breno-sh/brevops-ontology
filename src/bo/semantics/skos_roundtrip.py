"""Gate G2: python -I -m bo.semantics.skos_roundtrip

SSSOM 'a broadMatch b' -> RDF -> rdflib (+ axiomas SKOS do W3C, fecho OWL 2 RL): b é o mais amplo; 'b narrowMatch a'
sai do inverso; o transporte A->B é integral e B->A só no subconjunto. Também: as colunas padrão saem iguais às do
sssom-py (referência independente), o C09 completo volta igual do TSV e do RDF, a leitura invertida da v2 é
rejeitada, closeMatch não é transitiva no fecho e o fecho OWL não habilita transporte (separação teoria x regra).
Relatório com hora em $BO_DATA/SEMANTICS/skos_roundtrip_report.json. Sai 0 só se todas as checagens passam.
"""

from __future__ import annotations

import copy
import sys

from rdflib.compare import isomorphic

from . import common
from . import owl_theory as O
from . import sssom_io as S
from .claims import FIELDS, Claim, invert
from .composition import compose
from .content import examples as E
from .obligations import assess
from .transport import transport
from .valuetypes import EnumDomain

MS = "https://example.org/mapping-set/skos-roundtrip"


def _fields(r):
    return {k: r[k] for k in FIELDS if k in r and r[k] is not None}


def checks() -> list[dict]:
    out = []

    def check(name, ok, **detail):
        out.append({"check": name, "ok": bool(ok), **detail})

    a_b = E.BROAD_ARCHIVE                      # pa:archive_class skos:broadMatch pb:storage_class
    a, b = a_b["subject_id"], a_b["object_id"]

    # 0. o schema SKOS é o do W3C, e a definição oficial de broader fixa a direção
    ax = O.skos_axioms()
    check("skos_schema_sha256", True, sha256=common.SKOS_SHA256)
    check("skos_broader_is_more_general", "more general" in ax["broader"]["definition"],
          definition=ax["broader"]["definition"])
    check("skos_axioms", ax["broadMatch"]["inverseOf"] == ["narrowMatch"] and "broader" in ax["broadMatch"]["subPropertyOf"]
          and "TransitiveProperty" in ax["exactMatch"]["types"] and "TransitiveProperty" not in ax["closeMatch"]["types"],
          axioms={k: {kk: v[kk] for kk in ("types", "subPropertyOf", "inverseOf")} for k, v in ax.items()})

    # 1. TSV do C09 -> sssom-py (referência) e -> nosso leitor
    recs = [a_b, E.NARROW_TLS, E.EXACT_DAYS_SECS, E.CLOSE_VERSIONING]
    tsv = S.write_tsv(recs, MS)
    view = S.sssom_py_view(tsv, common.tmp_dir())
    std = [{k: r[k] for k in ("subject_id", "predicate_id", "object_id", "mapping_justification")} for r in recs]
    key = lambda r: (r["subject_id"], r["object_id"])
    check("sssom_py_standard_columns_equal", sorted(view["rows"], key=key) == sorted(std, key=key),
          sssom_py_rows=len(view["rows"]), ours=len(std))
    dropped = sorted({k for r in recs for k in S.to_row(r)} - set(view["columns"]))
    check("sssom_py_extension_slots_report", True, finding="sssom-py 0.4.22 descarta os slots de extensão declarados",
          dropped_by_sssom_py=dropped)
    _, back = S.read_tsv(tsv)
    check("c09_tsv_roundtrip_equal", [_fields(r) for r in back] == [_fields(r) for r in recs])

    # 2. RDF: núcleo isomorfo ao do sssom-py; C09 completo volta do RDF
    ours = S.to_rdf(recs, MS)
    check("rdf_core_isomorphic_to_sssom_py", isomorphic(S.core_subgraph(ours), S.core_subgraph(view["graph"])))
    back_rdf = S.from_rdf(ours)
    want = sorted((_fields(r) for r in recs), key=lambda r: r["claim_id"])
    check("c09_rdf_roundtrip_equal", [_fields(r) for r in back_rdf] == want)

    # 3. inferência com os axiomas do W3C: b é o mais amplo; b narrowMatch a sai do inverso
    g = O.closure([a_b])
    check("inferred_b_narrowMatch_a", O.has(g, b, "skos:narrowMatch", a))
    check("inferred_a_broader_b (b mais geral)", O.has(g, a, "skos:broader", b))
    check("not_inferred_b_broadMatch_a", not O.has(g, b, "skos:broadMatch", a))
    check("not_inferred_a_narrowMatch_b", not O.has(g, a, "skos:narrowMatch", b))
    inv = invert(Claim(a_b))
    check("executable_inverse_equals_owl_inverse",
          (inv["subject_id"], inv["predicate_id"], inv["object_id"]) == (b, "skos:narrowMatch", a)
          and O.has(g, inv["subject_id"], inv["predicate_id"], inv["object_id"]))
    g2 = O.closure([E.NARROW_TLS])
    check("narrowMatch_inverse_is_broadMatch",
          O.has(g2, E.NARROW_TLS["object_id"], "skos:broadMatch", E.NARROW_TLS["subject_id"]))

    # 4. semântica de conjuntos e transporte: A->B integral, B->A só no subconjunto
    ta, tb = Claim(a_b).subject_value_type, Claim(a_b).object_value_type
    dom_a = sorted(ta.domain().values) if isinstance(ta.domain(), EnumDomain) else []
    dom_b = sorted(tb.domain().values) if isinstance(tb.domain(), EnumDomain) else []
    fwd = [transport(a_b, v) for v in dom_a]
    check("transport_A_to_B_integral", all(o["result"] == "carried" for o in fwd), n=len(fwd),
          carried=sum(o["result"] == "carried" for o in fwd))
    bwd = {v: transport(a_b, v, direction="inverse") for v in dom_b}
    image = {transport(a_b, v).get("value") for v in dom_a}
    ok_b = all((o["result"] == "carried") == (v in image) for v, o in bwd.items()) and \
        all(o["code"] == "OUT_OF_SUBSET" for v, o in bwd.items() if v not in image)
    check("transport_B_to_A_only_subset", ok_b, n=len(bwd), carried=sorted(v for v, o in bwd.items() if o["result"] == "carried"),
          out_of_subset=sorted(v for v, o in bwd.items() if o["result"] != "carried"))
    check("roundtrip_values_A_B_A", all(transport(a_b, transport(a_b, v).get("value"), direction="inverse").get("value") == v
                                         for v in dom_a))
    check("claim_assessed_ok", assess(a_b).verdict == "OK")

    # 5. a tabela da v2 (invertida) é rejeitada
    v2 = copy.deepcopy(a_b)
    v2["membership_predicate"]["subset"] = "object"
    check("v2_inverted_reading_refuted", "SKOS-ORIENT" in assess(v2).rules)
    v2b = copy.deepcopy(a_b)
    v2b["value_domain_relation"]["relation"] = "superset"
    check("v2_inverted_domain_refuted", "VDR-COMPUTED" in assess(v2b).rules)

    # 6. closeMatch não é transitiva no fecho; exactMatch é — e o fecho não habilita transporte
    gc = O.closure([E.CLOSE_VERSIONING, E.CLOSE_VERSIONING_2])
    check("owl_closeMatch_not_transitive",
          not O.has(gc, E.CLOSE_VERSIONING["subject_id"], "skos:closeMatch", E.CLOSE_VERSIONING_2["object_id"]))
    m1 = E.with_guard(E.EXACT_DAYS_HOURS, E.EDITION_STD)
    m2 = E.with_guard(E.EXACT_HOURS_SECS, [{"term": "subject.edition", "op": "edition_in", "value": ["premium"]}])
    sep = O.separation_report(m1, m2)
    check("owl_exactMatch_transitive_but_no_transport",
          "skos:exactMatch" in sep["owl_inferred_between_ends"] and sep["composition_outcome"] == "EMPTY", **sep)
    ok_comp = compose(E.EXACT_DAYS_HOURS, E.EXACT_HOURS_SECS)
    check("exact_chain_with_compatible_guards_composes", ok_comp["outcome"] == "COMPOSED"
          and ok_comp["claim"]["semantic_relation"] == "exact")
    return out


def main(argv=None) -> int:
    try:
        res = checks()
    except O.SkosSchemaError as e:
        common.emit(f"FAIL: {e}")
        return 1
    for c in res:
        common.emit(f"  {'OK  ' if c['ok'] else 'FAIL'} {c['check']}")
    ok = all(c["ok"] for c in res)
    p = common.write_report("skos_roundtrip_report", {"module": "SEMANTICS", "gate": "skos_roundtrip",
                                                       "n": len(res), "n_ok": sum(c["ok"] for c in res), "checks": res})
    common.emit(f"[{common.now()}] skos_roundtrip: {sum(c['ok'] for c in res)}/{len(res)} -> {'PASS' if ok else 'FAIL'}  ({p})")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
