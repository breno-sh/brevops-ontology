"""Testes do PILOT-NET-GLOSS: gate F4 (anchor_claims) com controles negativos e positivo, grão conservador,
recusa do build com evidência incompleta e higiene dos dados da fatia. Provedores sintéticos pa/pb."""

import copy
import json
import re
from pathlib import Path

import pytest

from bo.pilot_net_gloss import anchor_claims, build, hub
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
            "evidence_ref": {"contract": "C25", "id": f"SE-{atom.split(':')[0]}-1"},
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
    inp = {"se": se, "vs": vs, "docs": [], "roles": {}, "schema_atoms": [], "types": ["pa_rule", "pb_rule"]}
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
    ("claims.jsonl", lambda r: [dict(r[0], evidence_ref={"contract": "C25", "id": "SE-pb-1"}), r[1]], "A1"),
    ("claims.jsonl", lambda r: [{k: v for k, v in r[0].items() if k != "evidence_ref"}, r[1]], "A1"),
    ("claims.jsonl", lambda r: [dict({k: v for k, v in r[0].items() if k not in ("sentence",)},
                                     evidence_state="UNRESOLVED", context="curto"), r[1]], "A1"),
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


def test_e2_requires_decided_equal_signature():
    u = lambda uid, k, r, m: {"unit_id": uid, "kind": k, "rule_applied": r, "missing_evidence": m}
    same = [u("CU-aws-aws_security_group.ingress", "COMPONENT", "GRAIN-G2-COMPONENT", []),
            u("CU-aws-aws_vpc_security_group_ingress_rule", "COMPONENT", "GRAIN-G2-COMPONENT", [])]
    assert build.e2(same)[0]["equal"] is True
    unk = [dict(x, kind="UNKNOWN", rule_applied="GRAIN-G0-IDENTITY", missing_evidence=["identity"]) for x in same]
    assert build.e2(unk)[0]["equal"] is False      # dois UNKNOWN iguais não provam invariância
    assert build.e2(same[:1])[0]["equal"] is False


def test_build_refuses_incomplete_evidence():
    res = {"grain": {"ledger": [{"x": 1}]}, "inputs": {"docs": [], "schema_atoms": []}}
    bl = build.blockers(res)
    assert [b.split(":")[0] for b in bl] == ["CC-2", "CC-3"]
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
        assert a["concept_id"] in ids and a["ref"].split(":")[1] in SL.all_types()
        assert (a["kind"] == "atom") == ("implication" not in a)


def test_separation_f1_concepts_present():
    ids = {c["concept_id"] for c in SL.CONCEPTS}
    for need in ("concept:filter_rule_set", "concept:filter_rule", "concept:rule_target",
                 "concept:rule_set_attachment", "concept:rule_stateless", "concept:rule_priority",
                 "concept:rule_effect"):
        assert need in ids


def test_block_anchor_is_claim_with_implication(tmp_path):
    inp = _world(tmp_path)
    blk = dict(_anchor("ANC-pb-0002", "pb:pb_rule:priority", 20, S_B), anchor_kind="block",
               block_id="pb:pb_rule:deny", implication={"realization": "block_choice", "value": "deny",
                                                      "rule": "o bloco deny implica efeito negar"})
    del blk["atom_id"]
    _rewrite(tmp_path, "claims.jsonl", lambda r: r + [blk])
    errs, st = anchor_claims.run(tmp_path, dict(inp, types=["pa_rule", "pb_rule"]))
    assert any(e.startswith("A4") for e in errs)          # caminho novo pa→conceito←bloco não registrado
    bad = dict(blk, implication={"realization": "block_choice", "value": "deny", "rule": ""})
    _rewrite(tmp_path, "claims.jsonl", lambda r: r[:-1] + [bad])
    errs, _ = anchor_claims.run(tmp_path, dict(inp, types=["pa_rule", "pb_rule"]))
    assert any(e.startswith("A1") and "implicação" in e for e in errs)


def test_publish_swaps_only_from_complete_staging(tmp_path, monkeypatch):
    monkeypatch.setenv("BO_DATA", str(tmp_path))
    out = tmp_path / SL.MODULE
    st = out / ".staging"
    names = build.DATA_FILES + build.EXTRA_FILES + [f"bundle/{x}" for x in build.BUNDLE_FILES]
    for n in names[:-1]:
        (st / n).parent.mkdir(parents=True, exist_ok=True)
        (st / n).write_text("novo\n")
    (out / "claims.jsonl").parent.mkdir(parents=True, exist_ok=True)
    (out / "claims.jsonl").write_text("velho\n")
    assert build.publish() == 2 and (out / "claims.jsonl").read_text() == "velho\n"   # staging incompleto
    (st / names[-1]).write_text("novo\n")
    assert build.current_dir() == st
    assert build.publish() == 0
    assert (out / "claims.jsonl").read_text() == "novo\n" and not st.exists() and build.current_dir() == out


def test_candidates_never_carry_terraform_timeouts():
    row = lambda a, b: {"subject_atom": a, "object_atom": b, "subject_kind": "atom", "object_kind": "atom",
                        "concept_id": "concept:rule_priority", "hub_outcome": "UNPROVEN",
                        "subject_anchor_state": "STRUCTURALLY_VALID", "object_anchor_state": "STRUCTURALLY_VALID"}
    rows = [row("google:google_compute_firewall:timeouts.create", "azurerm:azurerm_network_security_rule:timeouts.create"),
            row("google:google_compute_firewall:priority", "azurerm:azurerm_network_security_rule:priority")]
    cands = build.build_candidates(rows)
    assert len(cands) == 1 and "timeouts" not in json.dumps(cands)
    assert build.terraform_meta("oci:oci_core_security_list:timeouts.update")
    assert not build.terraform_meta("oci:oci_core_security_list:vcn_id")
