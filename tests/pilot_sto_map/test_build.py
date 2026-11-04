"""Testes do PILOT-STO-MAP: o build sobre o pacote real e sobre pacotes alterados (rerodada sem quebrar)."""

from __future__ import annotations

import copy
import json

import pytest

from bo.contracts import sssom as CS
from bo.pilot_sto_map import build as B
from bo.pilot_sto_map import decisions as DEC
from bo.pilot_sto_map.common import MAPPING_SET_ID, PAIR_SIDES, PREFIXES, load_bundle, provider_of
from bo.semantics import transforms as ST
from bo.transforms import registry as TR


@pytest.fixture(scope="module")
def bundle():
    return load_bundle()


@pytest.fixture(scope="module")
def built(bundle):
    rows, log = B.build_records(bundle)
    return rows, log


def claims(rows):
    return [r for r in rows if r["object_id"] != B.NO_TERM]


def test_exhaustive_every_atom_of_both_sides_per_pair(bundle, built):
    rows, _ = built
    assert B.exhaustive_gaps(bundle, rows) == []
    # e o teste não é vazio: tirar uma linha de ausência abre um buraco
    victim = next(i for i, r in enumerate(rows) if r["object_id"] == B.NO_TERM)
    assert len(B.exhaustive_gaps(bundle, rows[:victim] + rows[victim + 1:])) == 1


def test_canonical_orientation_and_no_inverse_rows(built):
    rows, _ = built
    seen = set()
    for r in claims(rows):
        sp, op = PAIR_SIDES[B.pair_of(r["claim_id"])]
        assert provider_of(r["subject_id"]) == sp and provider_of(r["object_id"]) == op, r["claim_id"]
        seen.add((r["subject_id"], r["object_id"]))
    assert not {(o, s) for s, o in seen} & seen


def test_bundle_only_atoms(bundle, built):
    rows, _ = built
    for r in rows:
        assert r["subject_id"] in bundle.atoms
        assert r["object_id"] in bundle.atoms or r["object_id"] == B.NO_TERM


def test_registry_only_functions(built):
    rows, _ = built
    for r in claims(rows):
        for step in ST.chain_of(r.get("translation_fn")) if r.get("translation_fn") else []:
            name = step["name"]
            if name in ST.REGISTRY:
                continue
            t = TR.get(name)
            assert not str(name).startswith("compare_") and not getattr(t, "c11_name", None), name


def test_predicate_matches_relation_and_direction_fields(built):
    rows, _ = built
    for r in rows:
        assert r["predicate_id"] == B.PREDICATE[r["semantic_relation"]]
        assert r["value_domain_relation"]["orientation"] == "subject_to_object"
        assert r["mapping_justification"] == "semapv:UnspecifiedMatching"
        assert r["mapping_tool"] == "claude-opus-5-5" and r["creator_id"] == "PILOT-STO-MAP"
        if r["semantic_relation"] in ("broad", "narrow"):
            assert r.get("membership_predicate")


def test_absence_rows_are_typed_and_do_not_transport(built):
    rows, _ = built
    for r in rows:
        none = r["object_id"] == B.NO_TERM
        assert none == ("absence" in r)
        if none:
            assert r["semantic_relation"] == "related" and r["transport_fidelity"] == "none"
            assert "translation_fn" not in r and r["object_concept"] == "bo:UNGLOSSED"
            assert r["absence"]["kind"] in ("ABSENCE_DEMONSTRATED", "OUT_OF_PIN", "UNSUPPORTED_BY_TRANSLATOR",
                                            "UNRESOLVED")
            assert r["absence"]["searched"] and all(len(s) >= 3 for s in r["absence"]["searched"])


def test_related_only_atoms_get_absence_with_the_decision_kind(built):
    rows, _ = built
    moved = {(B.pair_of(r["claim_id"]), a) for r in claims(rows) if r["semantic_relation"] in B.TRANSPORTING
             for a in (r["subject_id"], r["object_id"])}
    absent = {(B.pair_of(r["claim_id"]), r["subject_id"]): r for r in rows if r["object_id"] == B.NO_TERM}
    for d in DEC.DECISIONS:
        if d.relation != "related":
            continue
        for a in (d.subject, d.object):
            if (d.pair, a) in moved:
                continue
            row = absent[(d.pair, a)]
            assert any(d.claim_id in s for s in row["absence"]["searched"])


def test_doc_supported_only_with_two_published_citations(bundle, built):
    rows, _ = built
    for r in claims(rows):
        cites = r["proof"]["evidence"]
        if r["evidence_state"] == "DOC_SUPPORTED":
            atoms = {c["atom_id"] for c in cites}
            assert atoms == {r["subject_id"], r["object_id"]}
            assert all(c["evidence_level"] in ("published", "derived") and c["tag"] and c["line"] for c in cites)
            assert all(bundle.anchors[a]["evidence_state"] != "UNRESOLVED" for a in atoms)
        else:
            assert r["evidence_state"] == "STRUCTURALLY_VALID"


def test_tables_use_only_enum_values_from_the_bundle(built):
    rows, _ = built
    for r in claims(rows):
        fn = r.get("translation_fn") or {}
        params = fn.get("params") or {} if isinstance(fn, dict) else {}
        senum = set((r.get("subject_value_type") or {}).get("enum") or [])
        oenum = set((r.get("object_value_type") or {}).get("enum") or [])
        if fn.get("name") == "enum_map":
            assert set(params["table"]) <= senum and set(params["table"].values()) <= oenum
        if fn.get("name") == "enum_to_bool":
            assert set(params["true"]) | set(params["false"]) <= senum
            assert r["object_value_type"]["datatype"] == "boolean"


def test_value_type_conversion(bundle):
    assert B.value_type(bundle, DEC.A_BUCKET) == {"datatype": "string", "quantity_kind": "NOT_APPLICABLE",
                                                  "unit": "NOT_APPLICABLE"}
    st = B.value_type(bundle, DEC.A_VER_STATUS)
    assert st["datatype"] == "enum" and st["enum"] == bundle.value_space[DEC.A_VER_STATUS]["enum"]
    assert B.value_type(bundle, DEC.G_PREFIX) is None            # lista: o C09 não exprime, nada inventado
    z = B.value_type(bundle, DEC.Z_DELETE)
    assert z["range"] == {"min": 0, "max": 99999} and z["unit"] == "unit:DAY"


def test_tsv_roundtrip_and_determinism(bundle, built, tmp_path):
    rows, _ = built
    text = CS.write_tsv(rows, MAPPING_SET_ID, PREFIXES)
    _m, back, _c = CS.read_tsv(text)
    assert back == rows
    r1 = B.build(bundle, tmp_path / "a")
    r2 = B.build(bundle, tmp_path / "b")
    assert (tmp_path / "a" / "mapping.sssom.tsv").read_bytes() == (tmp_path / "b" / "mapping.sssom.tsv").read_bytes()
    assert (tmp_path / "a" / "build_record.json").read_bytes() == (tmp_path / "b" / "build_record.json").read_bytes()
    assert r1["mapping_sha256"] == r2["mapping_sha256"]


def test_block_fields_carry_keyed_occurrence(built):
    rows, _ = built
    for r in rows:
        for p in r.get("projection") or []:
            assert p["occurrence"]["scope"] == "block" and p["occurrence"]["key_fields"]
            assert p["field"] in (r["subject_id"], r["object_id"])
            assert not set(p["occurrence"]["key_fields"]) & {"index", "position", "ordinal"}


def test_rerun_with_changed_bundle_drops_and_downgrades_without_inventing(bundle):
    b2 = copy.deepcopy(bundle)
    gone = DEC.Z_RULE_NAME
    del b2.atoms[gone]
    b2.by_provider["azurerm"] = [a for a in b2.by_provider["azurerm"] if a != gone]
    b2.anchors[DEC.A_BUCKET] = dict(b2.anchors[DEC.A_BUCKET], evidence_state="UNRESOLVED")
    rows, log = B.build_records(b2)
    assert B.exhaustive_gaps(b2, rows) == []
    assert {d["claim_id"] for d in log["dropped"]} == {d.claim_id for d in DEC.DECISIONS
                                                       if gone in (d.subject, d.object)}
    name = next(r for r in rows if r["claim_id"] == "CLM-AWSGCP-STO-0001")
    assert name["evidence_state"] == "STRUCTURALLY_VALID"


def test_arbiter_never_ok_without_minimal_proof(built):
    from bo.arbiter import engine
    from bo.arbiter.run import minimal_proof_gaps
    rows, _ = built
    items = [{"rec": r, "source": "test", "domain": "STO", "line": i} for i, r in enumerate(rows, 1)]
    res = engine.arbitrate(items, decided_at=DEC.DECIDED_AT, arbiter_sha256="0" * 64)
    byv = {c.vid: c.rec for c in res["checked"]}
    oks = [v for v in res["verdicts"] if v["verdict"] == "OK" and v["claim_version_id"] in byv]
    assert oks
    assert [v["claim_id"] for v in oks if minimal_proof_gaps(byv[v["claim_version_id"]], False)] == []
    assert not any(v["verdict"] == "OK" for v in res["verdicts"] if v["claim_id"].startswith("CLM-") and
                   "-STO-NONE-" in v["claim_id"])


def test_decision_ids_unique_and_paired():
    ids = [d.claim_id for d in DEC.DECISIONS]
    assert len(ids) == len(set(ids))
    for d in DEC.DECISIONS:
        assert B.pair_of(d.claim_id) == d.pair
        assert json.dumps(d.fn) if d.fn is not None else d.relation == "related"
