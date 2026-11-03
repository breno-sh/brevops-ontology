"""Composição pela tabela formal; projeções por ocorrência, alternativas e grupos (1:N, N:1, N:M, cruzando facetas)."""
import copy

import pytest

from bo.semantics import projections as PJ
from bo.semantics.composition import (closure, compose, hub_claim, rcc5_table, semantic_table, table_document,
                                      transport_composite)
from bo.semantics.composition_check import LIT, checks as comp_checks
from bo.semantics.content import examples as E
from bo.semantics.transforms import OutOfDomain


def test_rcc5_enumeration_matches_literature_and_is_stable():
    t = rcc5_table(4)
    assert t == rcc5_table(5)
    for k, v in LIT.items():
        assert t[k] == v
    for r in ("equal", "subset", "superset", "overlap", "disjoint"):
        assert t[("equal", r)] == [r] and t[(r, "equal")] == [r]


def test_semantic_table_properties():
    st = semantic_table()
    assert st[("exact", "exact")]["result"] == "exact"
    assert st[("close", "close")]["result"] is None
    assert st[("broad", "broad")]["result"] == "broad" and st[("narrow", "narrow")]["result"] == "narrow"
    assert st[("broad", "narrow")]["result"] is None and st[("related", "related")]["result"] is None
    assert len(table_document()["semantic_relation"]) == 25


def test_composition_check_all_pass_except_published_table_possibly_missing():
    res = {c["check"]: c["ok"] for c in comp_checks()}
    assert all(v for k, v in res.items()), {k: v for k, v in res.items() if not v}


def test_gate_core_three_claims():
    assert compose(E.CLOSE_VERSIONING, E.CLOSE_VERSIONING_2)["outcome"] != "COMPOSED"
    a = E.with_guard(E.EXACT_DAYS_HOURS, E.EDITION_STD)
    b = E.with_guard(E.EXACT_HOURS_SECS, [{"term": "subject.edition", "op": "edition_in", "value": ["premium"]}])
    assert compose(a, b)["outcome"] == "EMPTY"
    m = copy.deepcopy(E.EXACT_HOURS_SECS)
    m["subject_value_type"]["quantity_kind"], m["subject_value_type"]["unit"] = "quantitykind:Count", "unit:NUM"
    m["translation_fn"] = {"name": "scale", "params": {"factor": "3600"}}
    assert compose(E.EXACT_DAYS_HOURS, m)["outcome"] == "UNPROVEN"


def test_composite_chain_of_three_and_leg_verification():
    r12 = compose(E.EXACT_DAYS_HOURS, E.EXACT_HOURS_SECS)
    c = r12["claim"]
    third = E.claim("CLM-EX-07", "pc:log_retention_seconds", "exact", "pd:log_retention_ms", c["object_value_type"],
                    E.T("integer", quantity_kind="quantitykind:Time", unit="unit:SEC", range={"min": 1, "max": 2592000}),
                    {"name": "identity", "params": {}}, "equal", "lossless", tests=[{"input": 5, "expected": 5}])
    r = compose(c, third)
    assert r["outcome"] == "COMPOSED" and transport_composite(r, 2)["value"] == 172800
    forged = copy.deepcopy(c)
    forged["semantic_relation"] = "exact"
    forged["derivation"][1]["evidence_state"] = "UNRESOLVED"     # perna forjada: refeita, não passa
    assert compose(forged, third)["outcome"] == "UNPROVEN"


def test_closure_only_by_table():
    cl = closure([E.EXACT_DAYS_HOURS, E.EXACT_HOURS_SECS, E.CLOSE_VERSIONING, E.CLOSE_VERSIONING_2])
    comp = [x for x in cl if x["outcome"] == "COMPOSED"]
    assert {x["claim"]["semantic_relation"] for x in comp} == {"exact"}
    assert all(not any(i.startswith("CLM-CL") for i in x["chain"]) for x in comp)
    assert any(x["chain"] == ["CLM-EX-02", "CLM-EX-03"] for x in comp)


def test_hub_is_composition_of_anchors():
    r = hub_claim(E.ANCHOR_A, E.ANCHOR_B)
    assert r["outcome"] == "COMPOSED" and transport_composite(r, 7)["value"] == 604800
    u = copy.deepcopy(E.ANCHOR_B)
    u["evidence_state"] = "UNRESOLVED"
    assert hub_claim(E.ANCHOR_A, u)["outcome"] == "UNPROVEN"


# ----------------------------------------------------------------------------------------------- projeções
def test_one_field_many_concepts_no_injectivity():
    r = PJ.check_projections(E.ALARM_PROJECTIONS)
    assert r["verdict"] == "OK" and r["n"] == 5
    got = PJ.project_value(E.ALARM_PROJECTIONS, "pa:alarm.query", "Latency[1h].max() <= 250")
    assert got == {"concept:alarm_metric": "Latency", "concept:alarm_operator": "le", "concept:alarm_threshold": 250,
                   "concept:alarm_window": "PT1H", "concept:alarm_statistic": "max"}
    with pytest.raises(OutOfDomain):
        PJ.project_value(E.ALARM_PROJECTIONS, "pa:alarm.query", "Cpu[1m]{dim=\"a\"}.mean() > 1")   # fora do subconjunto


def test_overlap_declared_is_accepted():
    a = E.ALARM_PROJECTIONS[0]
    b = dict(a, projection_id="PRJ-AL-metric-2", concept="concept:alarm_signal", overlaps=[a["projection_id"]])
    assert PJ.check_projections([a, b])["verdict"] == "OK"
    b.pop("overlaps")
    assert PJ.check_projections([a, b])["verdict"] == "REFUTED_BY_RULE"


def test_several_occurrences_keyed_by_identity():
    p = {"projection_id": "P1", "field": "pa:rule[].port", "occurrence": {"scope": "block", "key_fields": ["rule_name"]},
         "extractor": {"name": "identity"}, "concept": "concept:port", "type": E.T("integer"),
         "tests": [{"input": 22, "expected": 22}]}
    assert PJ.check_projections([p], {"pa:rule[].port": {"repeated": True}})["verdict"] == "OK"
    # duas ocorrências do mesmo bloco, cada uma com a sua chave, aplicam o grupo separadamente
    outs = [PJ.apply_group(E.PORT_GROUP, {"?r": {"pa:rule.protocol": pr, "pa:rule.from_port": a, "pa:rule.to_port": b}})
            for pr, a, b in (("tcp", 22, 22), ("udp", 1000, 2000))]
    assert outs == [{"?proto_b": "tcp", "?ports": "22"}, {"?proto_b": "udp", "?ports": "1000-2000"}]


def test_groups_1N_N1_NM_cross_facet():
    for g in (E.ALARM_GROUP, E.PORT_GROUP, E.CIDR_GROUP):
        assert PJ.check_group(g)["verdict"] == "OK", PJ.check_group(g)
    assert E.ALARM_GROUP["cardinality"] == "1:N" and E.PORT_GROUP["cardinality"] == "N:M"
    assert E.CIDR_GROUP["cardinality"] == "N:1"
    out = PJ.apply_group(E.CIDR_GROUP, {"?n": {"pa:network.base_address": "10.2.0.0"},
                                        "?s": {"pa:subnet_sizing.prefix_length": 16}})
    assert out == {"?cidr": "10.2.0.0/16"}
    nojoin = copy.deepcopy(E.CIDR_GROUP)
    nojoin["joins"] = []
    assert "G-OCC" in {f["rule"] for f in PJ.check_group(nojoin)["failures"]}
    with pytest.raises(OutOfDomain):     # componente faltando na volta: UNKNOWN_INPUT, nunca valor inventado
        PJ.apply_group(E.PORT_GROUP, {"?r": {"pa:rule.protocol": "tcp", "pa:rule.from_port": 80}})


def test_group_output_cannot_overwrite_source_variable():
    g = copy.deepcopy(E.PORT_GROUP)
    g["steps"][0]["outputs"] = {"value": "?from"}          # escreve numa variável do lado de origem
    assert "G-VARS" in {f["rule"] for f in PJ.check_group(g)["failures"]}


def test_alternative_realizations():
    assert PJ.check_alternatives(E.REALIZATIONS_EXCLUSIVE)["exclusivity"] == "ProvenExclusive"
    amb = [dict(E.REALIZATIONS_EXCLUSIVE[0], exclusivity=None),
           dict(E.REALIZATIONS_EXCLUSIVE[1], guard={"all": E.EDITION_ANY}, exclusivity=None)]
    r = PJ.check_alternatives(amb)
    assert r["verdict"] == "AMBIGUOUS" and r["exclusivity"] == "Ambiguous"
