"""Obrigações de prova por tipo e transporte por direção (tabela da §1.5 com a direção SKOS correta)."""
import copy

import pytest

from bo.semantics.claims import Claim, invert
from bo.semantics.content import examples as E
from bo.semantics.obligations import assess, check_set, derive_fidelity
from bo.semantics.transport import check_trace, transport
from bo.semantics.vocab import ABSENT, NOT_READ, SYMBOLIC


def test_all_examples_ok():
    bad = {k: assess(v).failures for k, v in E.all_examples().items() if assess(v).verdict != "OK"}
    assert not bad


def test_exact_both_directions_with_normalization():
    assert transport(E.EXACT_DAYS_SECS, 7) == {"claim_id": "CLM-EX-01", "direction": "forward", "result": "carried",
                                               "value": 604800, "fidelity": "lossless", "losses": []}
    assert transport(E.EXACT_DAYS_SECS, 604800, direction="inverse")["value"] == 7


def test_close_declares_loss_and_inverse_only_with_partial_inverse():
    o = transport(E.CLOSE_VERSIONING, "Suspended")
    assert o["result"] == "carried" and o["fidelity"] == "declared_loss" and o["losses"][0]["kind"] == "semantic"
    assert transport(E.CLOSE_VERSIONING, "Enabled")["fidelity"] == "lossless"
    b = transport(E.CLOSE_VERSIONING, False, direction="inverse")
    assert b["value"] == "Suspended" and b["fidelity"] == "declared_loss"
    nb = transport(E.TIER_CLOSE, "slow", direction="inverse")       # tabela não injetiva: sem inversa
    assert nb["result"] == "blocked" and nb["rule"] == "T-INVERSE"


def test_broad_forward_integral_backward_subset():
    for v in ("flexible_retrieval", "deep_archive"):
        assert transport(E.BROAD_ARCHIVE, v)["result"] == "carried"
    got = {v: transport(E.BROAD_ARCHIVE, v, direction="inverse") for v in ("standard", "nearline", "coldline", "archive")}
    assert {v for v, o in got.items() if o["result"] == "carried"} == {"coldline", "archive"}
    assert {o["code"] for o in got.values() if o["result"] == "blocked"} == {"OUT_OF_SUBSET"}


def test_narrow_forward_subset_backward_integral():
    assert transport(E.NARROW_TLS, "1.0")["code"] == "OUT_OF_SUBSET"
    assert transport(E.NARROW_TLS, "1.3")["value"] == "P13"
    assert all(transport(E.NARROW_TLS, v, direction="inverse")["result"] == "carried" for v in ("P12", "P13"))


def test_related_never_transports():
    o = transport(E.RELATED_KMS, "k")
    assert o["result"] == "blocked" and o["code"] == "RELATED_ONLY"
    assert transport(E.RELATED_KMS, "k", direction="inverse")["code"] == "RELATED_ONLY"


def test_guards_in_transport():
    c = E.with_guard(E.EXACT_DAYS_SECS, E.EDITION_STD)
    assert transport(c, 7, {"object.edition": "standard"})["result"] == "carried"
    assert transport(c, 7, {"object.edition": "premium"})["code"] == "CONDITION_FALSE"
    assert transport(c, 7, {})["code"] == "CONDITION_INDETERMINATE"
    req = copy.deepcopy(c)
    req["object_value_type"]["required"] = True        # guarda falsa: a alegação nem vale, antes de olhar o valor
    assert transport(req, ABSENT, {"object.edition": "premium"})["code"] == "CONDITION_FALSE"
    assert transport(req, ABSENT, {"object.edition": "standard"})["code"] == "UNKNOWN_INPUT"


def test_fixed_default_needs_coinciding_value():
    ctx = {"object.provider_version": "5.1"}
    ok = transport(E.FIXED_ENCRYPTION, True, ctx)
    assert ok["result"] == "carried" and ok["emitted"] is False and ok["origin"] == "Fixed"
    assert transport(E.FIXED_ENCRYPTION, False, ctx)["code"] == "OUT_OF_SUBSET"
    nodate = copy.deepcopy(E.FIXED_ENCRYPTION)
    del nodate["fixed_default"]["evidence"]["date"]
    assert assess(nodate).verdict == "UNPROVEN" and "FIXED-DATED" in assess(nodate).rules


def test_loss_contract_kinds():
    s = transport(E.EXACT_SATURATING, 400)
    assert s["value"] == 365 and s["losses"] == [{"kind": "saturation", "from": 400, "to": 365}]
    r = transport(E.EXACT_GIB_GB, 1)
    assert r["value"] == 2 and r["losses"][0]["kind"] == "rounding"
    assert transport(E.SENTINEL_RETENTION, 0)["rule"] == "T-SENTINEL"
    assert transport(E.SENTINEL_RETENTION, 2)["value"] == 172800
    assert transport(E.DURATION_MONTHS, "P1M")["code"] == "TRANSFORM_OUT_OF_DOMAIN"
    assert transport(E.DURATION_MONTHS, "P30D")["value"] == 2592000
    req = copy.deepcopy(E.EXACT_DAYS_SECS)
    req["object_value_type"]["required"] = True
    assert transport(req, ABSENT)["code"] == "UNKNOWN_INPUT"
    assert transport(E.EXACT_DAYS_SECS, ABSENT)["result"] == "omitted"
    assert transport(E.EXACT_DAYS_SECS, SYMBOLIC)["code"] == "UNKNOWN_SYMBOLIC_INPUT"
    assert transport(E.EXACT_DAYS_SECS, NOT_READ)["code"] == "UNKNOWN_INPUT"


def test_vacuous_non_member_is_refuted():
    c = copy.deepcopy(E.BROAD_ARCHIVE)
    c["membership_predicate"]["tests"]["non_members"] = ["glacier_z"]     # fora do tipo do lado mais amplo
    assert "BN-PRED-TESTS" in assess(c).rules


def test_unproven_and_refuted_never_transport():
    u = copy.deepcopy(E.EXACT_DAYS_SECS)
    u["evidence_state"] = "UNRESOLVED"
    assert transport(u, 7)["code"] == "UNPROVEN"
    r = copy.deepcopy(E.EXACT_DAYS_SECS)
    r["proof"]["tests"] = [{"input": 7, "expected": 1}]
    assert transport(r, 7)["code"] == "REFUTED_BY_RULE"


def test_three_fields_are_independent():
    # mesmo significado (exact), domínio superconjunto, perda declarada
    a = assess(E.EXACT_SATURATING)
    assert a.verdict == "OK" and a.computed["vdr"] == "superset" and a.computed["fidelity"] == "declared_loss"
    # conversão exata de unidade é exact, não close
    assert assess(E.EXACT_DAYS_SECS).verdict == "OK"
    as_close = copy.deepcopy(E.EXACT_DAYS_SECS)
    as_close["semantic_relation"], as_close["predicate_id"] = "close", "skos:closeMatch"
    assert "CLOSE-LOSS" in assess(as_close).rules


def test_inverse_fidelity_is_recomputed_not_copied():
    inv = invert(Claim(E.BROAD_ARCHIVE))
    assert inv["predicate_id"] == "skos:narrowMatch" and inv["transport_fidelity"] is None
    a = assess(inv)
    assert a.verdict == "OK" and a.computed["vdr"] == "superset" and a.computed["fidelity"] == "partial"
    assert derive_fidelity("related", "equal", [], False, False) == "none"
    assert derive_fidelity("exact", "disjoint", [], False, False) == "none"


def test_shared_concept_alone_is_not_proof():
    c = copy.deepcopy(E.EXACT_DAYS_SECS)
    c["basis"] = "shared_concept"
    c["anchors"] = [{"evidence_state": "DOC_SUPPORTED"}, {"evidence_state": "STRUCTURALLY_VALID"}]
    assert assess(c).verdict == "UNPROVEN" and "ANCHOR-NOT-PROOF" in assess(c).rules


def test_skos_disjointness_set_rule():
    rel = E.claim("R", E.EXACT_DAYS_SECS["subject_id"], "related", E.EXACT_DAYS_SECS["object_id"], None, None, None,
                  "unknown", "none")
    assert check_set([E.EXACT_DAYS_SECS, rel])[0]["verdict"] == "CONTESTED"
    assert check_set([E.with_guard(E.EXACT_DAYS_SECS, E.EDITION_STD), E.with_guard(rel, E.EDITION_PREM)]) == []


def test_check_trace_rejects_wrong_assertion():
    row = {"claim": E.EXACT_SATURATING, "value": 400, "asserted": {"result": "carried", "value": 400, "fidelity": "lossless"}}
    r = check_trace(row)
    assert not r["accepted"] and r["rule"] == "T-SATURATION"
