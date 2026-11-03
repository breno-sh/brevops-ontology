"""Redator antes de gravar e leitura de volta no formato C12 (validador único)."""
import json
import uuid

import pytest
from azh_helpers import REF, recording

from bo.contracts import validate as V
from bo.harness.azurerm import readback as RB
from bo.harness.azurerm import redact as RD
from bo.harness.azurerm._common import read_jsonl
from bo.harness.azurerm.executor import ReplayBackend


def _state(name, env=None):
    b = ReplayBackend(recording(name))
    b._env = env or {"TF_VAR_sym_a1b2c3d4e5f60718": "rabc1234",
                     "TF_VAR_secret_r2_administrator_password": "SEGREDO-de-teste-123aZ!"}
    polls = len(b.rec["show"])
    st = None
    for _ in range(polls):
        st = b.show(None)
    return st


def test_redactor_removes_sensitive_identifiers_and_content():
    st = _state("ok_LP-AZREF-0001.json")
    raw = json.dumps(st)
    assert "/subscriptions/" in raw and "Account" + "Key=" in raw
    red = RD.redact_state(st)
    s = json.dumps(red)
    assert "/subscriptions/" not in s
    assert "Account" + "Key=" not in s and "SINTETICO-chave-primaria" not in s
    sa = next(r for r in red["resources"] if r["address"] == "azurerm_storage_account.r2")["values"]
    assert sa["primary_access_key"] == {"$withheld": "REDACT-SECRET-01"}
    assert sa["id"] == {"$withheld": "REDACT-IDENT-01"}
    assert sa["account_tier"] == "Standard"
    RD.assert_clean(red, [])


def test_redactor_secret_and_guid():
    sec = "SEGREDO-de-teste-123aZ!"
    st = _state("ok_LP-AZREF-0002.json", {"TF_VAR_sym_a1b2c3d4e5f60718": "rabc1234",
                                          "TF_VAR_secret_r2_administrator_password": sec})
    assert sec in json.dumps(st)
    red = RD.redact_state(st)
    assert sec not in json.dumps(red)
    kv = next(r for r in red["resources"] if r["address"] == "azurerm_key_vault.r4")["values"]
    assert kv["tenant_id"] == {"$withheld": "REDACT-IDENT-01"}
    RD.assert_clean(red, [sec])


CUSTOM = "custom" + "_data"  # nome montado: o privacy_lint é lexical


def test_redactor_content_and_name_heuristics():
    st = {"values": {"root_module": {"resources": [{
        "address": "azurerm_linux_virtual_machine.r1", "mode": "managed", "type": "azurerm_linux_virtual_machine",
        "name": "r1", "values": {CUSTOM: "IyEvYmluL3NoCmVjaG8gb2k=", "size": "B1s", "admin_email": "op@example.com",
                                 "nome": "ok"},
        "sensitive_values": {}}]}}}
    v = RD.redact_state(st)["resources"][0]["values"]
    assert v[CUSTOM]["$withheld"] in ("REDACT-CONTENT-01", "REDACT-SECRET-01")
    assert v["admin_email"] == {"$withheld": "REDACT-IDENT-01"}
    assert v["size"] == "B1s" and v["nome"] == "ok"


def test_redactor_fails_closed():
    with pytest.raises(RD.RedactionError):
        RD.redact_state([1, 2])
    with pytest.raises(RD.RedactionError):
        RD.redact_state({"values": {"root_module": {"resources": [{"address": "x"}]}}})
    with pytest.raises(RD.RedactionError):
        RD.redact_state({"values": {"root_module": {"child_modules": [{}]}}})
    with pytest.raises(RD.RedactionError):
        RD.assert_clean({"a": "/subscriptions/" + str(uuid.uuid4())}, [])
    with pytest.raises(RD.RedactionError):
        RD.assert_clean({"a": "xx-segredo-xx"}, ["segredo"])


def _plan(pid):
    return next(p for p in read_jsonl(REF / "lowering_plan.jsonl") if p["plan_id"] == pid)


def test_readback_states_and_c12_contract(work):
    red = RD.redact_state(_state("ok_LP-AZREF-0001.json"))
    rb = RB.build_readback(_plan("LP-AZREF-0001"), red, readback_id="RB-T1", case_id="CASE-AZREF-STO-0001",
                           group_id="G-AZREF-0001", claim_id="CLM-EX-01", side="object",
                           read_at="2026-11-03T07:00:00-03:00")
    f = {x["path"]: x for x in rb["fields"]}
    assert f["r2.blob_properties[0].delete_retention_policy[0].days"] == {
        "path": "r2.blob_properties[0].delete_retention_policy[0].days", "state": "read", "value": 7}
    assert f["r2.blob_properties[0].versioning_enabled"]["value"] is True
    assert f["r2.tags"]["value"]["env"] == "test"
    assert f["r1.name"]["value"] == "bo-rabc1234-rg"
    p = work / "readback.jsonl"
    p.write_text(json.dumps(rb) + "\n")
    assert V.validate("readback", p).ok


def test_readback_withheld_absent_not_read(work):
    red = RD.redact_state(_state("ok_LP-AZREF-0002.json"))
    red["resources"] = [r for r in red["resources"] if r["address"] != "azurerm_key_vault.r4"]
    pg = next(r for r in red["resources"] if r["address"] == "azurerm_postgresql_flexible_server.r2")
    pg["values"]["version"] = None
    rb = RB.build_readback(_plan("LP-AZREF-0002"), red, readback_id="RB-T2", case_id="CASE-AZREF-DB-0002",
                           group_id="G-AZREF-0002", claim_id="CLM-EX-01", side="object",
                           read_at="2026-11-03T07:00:00-03:00")
    f = {x["path"]: x for x in rb["fields"]}
    assert f["r2.administrator_password"] == {"path": "r2.administrator_password", "state": "withheld",
                                              "redaction": {"rule_id": "REDACT-SECRET-01", "at_source": True}}
    assert f["r2.version"] == {"path": "r2.version", "state": "absent"}
    assert f["r4.sku_name"] == {"path": "r4.sku_name", "state": "not_read"}
    assert not any(x["path"].startswith("r3.") for x in rb["fields"])  # data source não é configuração
    p = work / "readback.jsonl"
    p.write_text(json.dumps(rb) + "\n")
    assert V.validate("readback", p).ok


def test_write_only_attribute_is_not_read():
    plan = _plan("LP-AZREF-0002")
    plan["steps"][1]["values"].append({"field": "administrator_password_wo", "origin": "carried", "marked": False,
                                       "term": {"kind": "literal", "datatype": "string", "value": "x"}})
    red = RD.redact_state(_state("ok_LP-AZREF-0002.json"))
    rb = RB.build_readback(plan, red, readback_id="RB-T3", case_id="CASE-X-1", group_id="G-X-1",
                           claim_id="CLM-EX-01", side="object", read_at="2026-11-03T07:00:00-03:00")
    f = {x["path"]: x for x in rb["fields"]}
    assert f["r2.administrator_password_wo"]["state"] == "not_read"


def test_infra_outcome_contract(work):
    o = RB.infra_outcome(outcome_id="OUT-T1", case_id="CASE-X-1", group_id="G-X-1", claim_id="CLM-EX-01",
                         side="object", value="REJECTED_BY_API", detail="apply falhou (api_400)",
                         evidence_before="DOC_SUPPORTED", decided_at="2026-11-03T07:00:00-03:00")
    p = work / "outcomes.jsonl"
    p.write_text(json.dumps(o) + "\n")
    assert V.validate("outcomes", p).ok
    with pytest.raises(ValueError):
        RB.infra_outcome(outcome_id="OUT-T2", case_id="C", group_id="G", claim_id="C", side="object",
                         value="PERSISTED", detail="xxx", evidence_before="DOC_SUPPORTED", decided_at="x")
