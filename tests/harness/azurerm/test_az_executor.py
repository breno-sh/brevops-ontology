"""Executor com respostas gravadas: ordem apply -> espera -> leitura -> destroy, redator antes de gravar,
intenção antes do apply, destroy sempre, resíduo relatado; o caminho de nuvem recusa nesta fase."""
import json

import pytest
from azh_helpers import FIX, REF, plan_with, recording, step, write_plan

from bo.contracts import validate as V
from bo.harness.azurerm import executor as E
from bo.harness.azurerm._common import tmp_dir

CASE1 = E.CaseRef("CASE-AZREF-STO-0001", "G-AZREF-0001", "CLM-EX-01", "object")
CASE2 = E.CaseRef("CASE-AZREF-DB-0002", "G-AZREF-0002", "CLM-EX-01", "object")


def _run(work, rec_name, pid, case, *, matches=True, extra=None, plan_file=None):
    rec = recording(rec_name)
    kit = E.OfflineKit(rec["identity_sha256"], matches_allowlist=matches, extra_redactors=extra)
    be = E.ReplayBackend(rec)
    sleeps = []
    cfg = E.RunConfig("RUN-AZTEST-01", "B-AZ-TEST", "HARNESS-AZURE", max_polls=3, poll_interval_s=5,
                      sleep=sleeps.append)
    res = E.run_case(plan_file or REF / "lowering_plan.jsonl", pid, case, cfg, work / "out", be, kit)
    return res, kit, be, sleeps


def _all_output_text(work):
    return "".join(p.read_text() for p in (work / "out").rglob("*") if p.is_file())


def test_success_order_and_contracts(work):
    res, kit, be, sleeps = _run(work, "ok_LP-AZREF-0001.json", "LP-AZREF-0001", CASE1)
    assert res["status"] == "READ"
    ev = kit.events
    for a, b in [("rendered", "identity_checked"), ("identity_checked", "intent_written"),
                 ("intent_written", "apply"), ("apply", "show"), ("show", "redacted"),
                 ("redacted", "readback_written"), ("readback_written", "destroy"), ("destroy", "ephemeral_removed")]:
        assert ev.index(a) < ev.index(b), (a, b, ev)
    assert be.calls == ["apply", "show", "show", "destroy", "state_list"]  # 1ª leitura incompleta: esperou
    assert sleeps == [5]
    assert kit.heartbeats == ["creating", "created", "confirmed", "removal_requested", "absent"]
    for k in ("intent_manifest", "run_manifest", "readback"):
        r = V.validate(k, work / "out" / f"{k}.jsonl")
        assert r.ok, r.errors
    assert res["residue"] == {"destroy_ok": True, "state_entries_left": 0}
    assert not (tmp_dir() / "ephemeral" / "RUN-AZTEST-01").exists()


def test_intents_have_ownership_tags_and_identity_hash_only(work):
    _run(work, "ok_LP-AZREF-0001.json", "LP-AZREF-0001", CASE1)
    intents = [json.loads(x) for x in (work / "out" / "intent_manifest.jsonl").read_text().splitlines()]
    assert [i["resource_type"] for i in intents] == ["azurerm_resource_group", "azurerm_storage_account",
                                                     "azurerm_virtual_network", "azurerm_subnet"]
    by = {i["resource_type"]: i for i in intents}
    assert by["azurerm_resource_group"]["tags"] == {"bo-run": "RUN-AZTEST-01", "bo-case": "CASE-AZREF-STO-0001"}
    assert by["azurerm_subnet"]["tag_supported"] is False and "tags" not in by["azurerm_subnet"]
    assert all(len(i["effective_identity_check"]["identity_sha256"]) == 64 for i in intents)


def test_secret_never_reaches_disk(work):
    seen = {}

    def spy(red):
        seen["red"] = json.dumps(red)
        return red

    res, kit, be, _ = _run(work, "ok_LP-AZREF-0002.json", "LP-AZREF-0002", CASE2, extra=[spy])
    assert res["status"] == "READ"
    secret = be._env["TF_VAR_secret_r2_administrator_password"]
    assert len(secret) >= 20
    assert secret not in _all_output_text(work)
    assert secret not in seen["red"]  # o redator extra (kit SAFETY) já recebe o state redigido
    assert "/subscriptions/" not in _all_output_text(work)
    rb = json.loads((work / "out" / "readback.jsonl").read_text())
    f = {x["path"]: x for x in rb["fields"]}
    assert f["r2.administrator_password"]["state"] == "withheld"
    res_json = json.loads((work / "out" / "case_result.json").read_text())
    b = {x["variable"]: x for x in res_json["bindings"]}
    assert "value" not in b["secret_r2_administrator_password"]


def test_apply_rejected_still_destroys_and_writes_infra_outcome(work):
    res, kit, be, _ = _run(work, "apply400_LP-AZREF-0001.json", "LP-AZREF-0001", CASE1)
    assert res["status"] == "APPLY_FAILED"
    assert res["apply"] == {"ok": False, "class": "REJECTED_BY_API", "pattern": "api_400"}
    assert "destroy" in be.calls and "show" not in be.calls
    assert not (work / "out" / "readback.jsonl").exists()
    r = V.validate("outcomes", work / "out" / "outcomes.jsonl")
    assert r.ok, r.errors
    assert "AccountNameInvalid" not in _all_output_text(work)  # só a classe e o nome do padrão


def test_quota_failure_with_residue_is_reported(work):
    res, kit, be, _ = _run(work, "quota_residue_LP-AZREF-0002.json", "LP-AZREF-0002", CASE2)
    assert res["status"] == "APPLY_FAILED+RESIDUE"
    assert res["apply"]["class"] == "INFRA_ERROR"
    assert res["residue"] == {"destroy_ok": False, "state_entries_left": 1}
    stages = [json.loads(x)["stage"] for x in (work / "out" / "run_manifest.jsonl").read_text().splitlines()]
    assert "removal_pending" in stages and "absent" not in stages
    assert V.validate("run_manifest", work / "out" / "run_manifest.jsonl").ok


def test_identity_mismatch_never_applies(work):
    res, kit, be, _ = _run(work, "ok_LP-AZREF-0001.json", "LP-AZREF-0001", CASE1, matches=False)
    assert res["status"] == "REFUSED_IDENTITY"
    assert be.calls == []
    assert not (work / "out" / "intent_manifest.jsonl").exists()


def test_blocked_plan_never_applies(work):
    res, kit, be, _ = _run(work, "ok_LP-AZREF-0001.json", "LP-AZREF-0003", CASE1)
    assert res["status"] == "BLOCKED"
    assert res["issues"][0]["code"] == "UNKNOWN_INPUT"
    assert be.calls == [] and "identity_checked" not in kit.events


def test_classify():
    assert E.classify("QuotaExceeded: x")[0] == "INFRA_ERROR"
    assert E.classify("StatusCode=429 TooManyRequests")[0] == "INFRA_ERROR"
    assert E.classify("Error: expected sku_name to be one of")[0] == "REJECTED_BY_API"
    assert E.classify("algo estranho") == ("UNKNOWN", "nao_classificado")


def test_cloud_backend_refuses_in_this_phase(work, monkeypatch):
    monkeypatch.delenv("BO_CLOUD_GO", raising=False)
    with pytest.raises(E.CloudRefused, match="GO"):
        E.TerraformBackend("HARNESS-AZURE")
    monkeypatch.setenv("BO_CLOUD_GO", "1")
    with pytest.raises(E.CloudRefused):
        E.TerraformBackend("HARNESS-AZURE")


def test_cli_replay(work):
    cases = work / "cases.jsonl"
    cases.write_text(json.dumps({"case_id": "CASE-AZREF-DB-0002", "group_id": "G-AZREF-0002",
                                 "claim_id": "CLM-EX-01"}) + "\n")
    rc = E.main([
        "--replay", str(FIX / "recorded" / "ok_LP-AZREF-0002.json"),
        "--plan", str(REF / "lowering_plan.jsonl"), "--plan-id", "LP-AZREF-0002", "--cases", str(cases),
        "--out", str(work / "out"), "--run-id", "RUN-AZCLI-01"])
    assert rc == 0
    assert json.loads((work / "out" / "case_result.json").read_text())["status"] == "READ"


def test_literal_name_needs_no_binding(work):
    # nome literal no plano: nenhuma entrada a ligar; o plano mínimo roda até a leitura
    plan, graph = plan_with([step(1, "r1", "azurerm_resource_group",
                                  [{"field": "location", "origin": "carried", "marked": False,
                                    "term": {"kind": "literal", "datatype": "string", "value": "x"}},
                                   {"field": "name", "origin": "carried", "marked": False,
                                    "term": {"kind": "literal", "datatype": "string", "value": "bo-fixo-rg"}}])])
    p = write_plan(work, plan, graph)
    res, kit, be, _ = _run(work, "ok_LP-AZREF-0001.json", "LP-T-0001",
                           E.CaseRef("CASE-T-0001", "G-T-0001", "CLM-EX-01", "object"), plan_file=p)
    assert res["status"] == "READ" and res["bindings"] == []


def test_readback_tags_exclude_declared_ownership_tags(work):
    _run(work, "ok_LP-AZREF-0001.json", "LP-AZREF-0001", CASE1)
    rb = json.loads((work / "out" / "readback.jsonl").read_text())
    f = {x["path"]: x for x in rb["fields"]}
    assert f["r2.tags"] == {"path": "r2.tags", "state": "read", "value": {"env": "test"}}


def test_redaction_failure_writes_nothing_and_still_destroys(work):
    def leaky(red):  # redator extra quebrado: devolve um id de assinatura ao objeto
        red["resources"][0]["values"]["vaza"] = "/subscriptions/" + "0" * 8 + "-0000-0000-0000-" + "0" * 12
        return red

    with pytest.raises(E.RD.RedactionError):
        _run(work, "ok_LP-AZREF-0001.json", "LP-AZREF-0001", CASE1, extra=[leaky])
    assert not (work / "out" / "readback.jsonl").exists()
    res = json.loads((work / "out" / "case_result.json").read_text())
    assert res["status"] == "REDACTION_FAILED"
    assert res["residue"] == {"destroy_ok": True, "state_entries_left": 0}
