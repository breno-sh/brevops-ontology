"""Testes do PILOT-NET-GLOSS: gate F4 (anchor_claims) com controles negativos e positivo, grão conservador,
recusa do build com evidência incompleta e higiene dos dados da fatia. Provedores sintéticos pa/pb."""

import copy
import json
import re
from pathlib import Path

import pytest

from bo.pilot_net_gloss import anchor_claims, build, grain_apply, hub
from bo.pilot_net_gloss import slice as SL

DOC = {"repo": "example-org/provider-docs", "tag": "v1.0.0", "file": "docs/rule.md"}
S_A = "frase sintética: ordem da regra, o menor número prevalece"
S_B = "frase sintética: prioridade da regra, menor vence"


def _anchor(cid, atom, line, sent, state="STRUCTURALLY_VALID"):
    return {"claim_id": cid, "claim_version_id": f"{cid}@1", "event_id": f"EV-{cid}-1",
            "concept_id": "concept:item_order", "atom_id": atom, "sentence": sent, "context": "argumento sintético",
            "source": dict(DOC, line=line, sentence=sent),
            "counterexample_search": {"query": "order", "found": False, "result": "nada com outro sentido"},
            "extraction_method": "parser", "evidence_level": "published", "evidence_state": state,
            "recorded_at": "2026-11-04T02:30:00-03:00"}


def _world(tmp_path: Path):
    claims = [_anchor("ANC-pa-0001", "pa:pa_rule:order", 10, S_A), _anchor("ANC-pb-0001", "pb:pb_rule:priority", 20, S_B)]
    glossary = [{"concept_id": "concept:item_order", "label": "ordem do item", "definition": "número ordinal que decide a regra que prevalece",
                 "domain": "NET", "quantity_kind": "NOT_APPLICABLE", "unit": "NOT_APPLICABLE", "status": "active",
                 "evidence_state": "STRUCTURALLY_VALID"}]
    decisions = [{"schema": "bo.glossary_decision/1", "decision_id": "GD-T-0001", "kind": "value_type",
                  "concept_id": "concept:item_order", "value": {"datatype": "integer"}, "reason": "tipo",
                  "evidence": [], "author": "PILOT-NET-GLOSS", "recorded_at": "2026-11-04T02:30:00-03:00"}]
    vs = {"pa:pa_rule:order": {"datatype": {"kind": "scalar", "scalar": "integer"}, "quantity_kind": "NOT_APPLICABLE",
                               "unit_qudt": "NOT_APPLICABLE", "range": {"min": 0, "max": 100}},
          "pb:pb_rule:priority": {"datatype": {"kind": "scalar", "scalar": "integer"}, "quantity_kind": "NOT_APPLICABLE",
                                  "unit_qudt": "NOT_APPLICABLE", "range": {"min": 0, "max": 100}}}
    se = [{"evidence_id": "SE-pa-1", "terraform_resource_type": "pa_rule", "doc": dict(DOC, line=10, sentence=S_A)},
          {"evidence_id": "SE-pb-1", "terraform_resource_type": "pb_rule", "doc": dict(DOC, line=20, sentence=S_B)}]
    inp = {"se": se, "vs": vs, "docs": [], "roles": {}, "schema_atoms": []}
    rows = hub.evaluate(claims, glossary, decisions, vs)
    for n, recs in (("claims.jsonl", claims), ("glossary.jsonl", glossary), ("decisions.jsonl", decisions),
                    ("anchor_paths.jsonl", rows)):
        build.write_jsonl(tmp_path / n, recs)
    return inp


def _rewrite(tmp_path, name, fn):
    recs = [json.loads(l) for l in (tmp_path / name).read_text().splitlines()]
    build.write_jsonl(tmp_path / name, fn(recs))


def test_gate_passes_on_wellformed_world(tmp_path):
    inp = _world(tmp_path)
    errs, st = anchor_claims.run(tmp_path, inp)
    assert errs == [] and st["multi_provider_paths"] == 1
    assert st["outcomes"] == ["UNPROVEN"] and st["control_composed_exact"] == 1


def test_positive_control_composes_exact(tmp_path):
    inp = _world(tmp_path)
    c = [json.loads(l) for l in (tmp_path / "claims.jsonl").read_text().splitlines()]
    g = [json.loads(l) for l in (tmp_path / "glossary.jsonl").read_text().splitlines()]
    d = [json.loads(l) for l in (tmp_path / "decisions.jsonl").read_text().splitlines()]
    real = hub.evaluate(c, g, d, inp["vs"])
    ctrl = hub.evaluate(c, g, d, inp["vs"], promote="DOC_SUPPORTED")
    assert real[0]["hub_outcome"] == "UNPROVEN" and "ANCHOR-NOT-PROOF" in real[0]["shared_concept_failed_rules"]
    assert ctrl[0]["hub_outcome"] == "COMPOSED" and ctrl[0]["hub_relation"] == "exact"


@pytest.mark.parametrize("name,fn,code", [
    ("anchor_paths.jsonl", lambda r: [], "A4"),
    ("anchor_paths.jsonl", lambda r: [dict(r[0], hub_outcome="COMPOSED")], "A4"),
    ("claims.jsonl", lambda r: [dict(r[0], evidence_state="DOC_SUPPORTED"), r[1]], "A2"),
    ("claims.jsonl", lambda r: [dict(r[0], sentence="frase que não está em nenhum fato"), r[1]], "A1"),
    ("claims.jsonl", lambda r: [dict(r[0], source=dict(r[0]["source"], line=99)), r[1]], "A1"),
    ("claims.jsonl", lambda r: [dict(r[0], extraction_method="model", evidence_level="published"), r[1]], "A2"),
    ("claims.jsonl", lambda r: [dict(r[0], counterexample_search={"query": "x", "found": False, "result": ""}), r[1]], "A1"),
    ("glossary.jsonl", lambda r: [dict(r[0], evidence_state="UNRESOLVED")], "A3"),
])
def test_negative_controls_fail(tmp_path, name, fn, code):
    inp = _world(tmp_path)
    _rewrite(tmp_path, name, fn)
    errs, _ = anchor_claims.run(tmp_path, inp)
    assert any(e.startswith(code) for e in errs), errs


def test_paths_only_between_providers():
    a = _anchor("ANC-pa-0001", "pa:pa_rule:order", 1, S_A)
    a2 = _anchor("ANC-pa-0002", "pa:pa_other:order", 2, S_A)
    b = _anchor("ANC-pb-0001", "pb:pb_rule:priority", 3, S_B)
    ps = hub.paths([a, a2, b])
    assert len(ps) == 2 and all(hub.provider_of(x["atom_id"]) != hub.provider_of(y["atom_id"]) for x, y in ps)


def test_grain_sanitizer_only_removes_evidence():
    recs = [{"evidence_id": "SE-x-1", "fact_kind": "identity", "level": "published", "status": "stated",
             "terraform_resource_type": "pa_box", "api_resource": {"service": "s", "resource": "r"},
             "value": {"aspect": "resource_identity_schema", "required": ["id"], "rule": "R"}},
            {"evidence_id": "SE-x-2", "fact_kind": "import_key", "level": "published", "status": "stated",
             "terraform_resource_type": "pa_box", "api_resource": {"service": "s", "resource": "r"},
             "value": {"status": "present", "fields": ["name"]}}]
    table, ledger = grain_apply.sanitized_table(recs)
    ent = table["pa_box"]
    assert ent["identity"] == [{"status": "unknown", "source": {"level": "published", "ref": "SE-x-1"}}]
    assert ent["import_key"][0]["status"] == "present"
    assert [x["evidence_id"] for x in ledger] == ["SE-x-1"]
    assert sum(len(v) for k, v in ent.items() if isinstance(v, list)) == 2


def test_build_refuses_incomplete_evidence():
    res = {"grain": {"ledger": [{"x": 1}]}, "inputs": {"docs": [], "schema_atoms": []}}
    bl = build.blockers(res)
    assert [b.split(":")[0] for b in bl] == ["CC-1", "CC-2", "CC-3"]
    assert build.blockers({"grain": {"ledger": []}, "inputs": {"docs": [1], "schema_atoms": [1]}}) == []


TOKENS = ["aws", "amazon", "gcp", "google", "azure", "azurerm", "microsoft", "oci", "oracle", "ec2", "s3", "vpc",
          "vnet", "vcn", "arn", "ocid", "gke", "eks", "aks", "lambda", "dynamodb", "cosmosdb", "bigquery",
          "cloudwatch", "stackdriver", "nsg", "elb", "alb"]


def test_slice_concepts_hygiene():
    ids = [c["concept_id"] for c in SL.CONCEPTS]
    assert len(ids) == len(set(ids))
    rx = re.compile(r"\b(" + "|".join(TOKENS) + r")\b", re.I)
    for c in SL.CONCEPTS:
        for k in ("concept_id", "label", "definition"):
            assert not rx.search(c[k].replace("concept:", "").replace("_", " ")), (c["concept_id"], k)
    for n, kind, concept, related, *_ in SL.DECISION_SPECS:
        assert concept in ids and (related is None or (related in ids and related != concept))
    for a in SL.ANCHORS:
        assert a["concept_id"] in ids and a["atom_id"].split(":")[1] in SL.all_types()


def test_separation_f1_concepts_present():
    ids = {c["concept_id"] for c in SL.CONCEPTS}
    for need in ("concept:filter_rule_set", "concept:filter_rule", "concept:rule_target",
                 "concept:rule_set_attachment", "concept:rule_stateless", "concept:rule_priority",
                 "concept:rule_effect"):
        assert need in ids
