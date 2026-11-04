"""Tabela de SKUs a partir do SERVICE-EVIDENCE, regeração idêntica, injeção de falha amostrada e o gate dos
módulos de nuvem (intent_reconciled)."""

from __future__ import annotations

import json
import os
import shutil

import pytest

from bo.safety import build, residue, skus
from bo.safety.common import bo_tmp
from bo.safety.failure_injection import run_one
from bo.safety.intent_reconciled import check as ir_check


def test_build_check_regenerates_identically():
    assert build.main(["--check"]) == 0


def test_tag_support_comes_from_service_evidence(work):
    t = skus.load_table()
    assert t["providers"]["google"]["types"]["google_sql_database_instance"]["tag"]["supported"] is False
    assert t["providers"]["google"]["types"]["google_storage_bucket"]["tag"]["attributes"] == ["labels"]
    for p in t["providers"].values():
        for e in p["types"].values():
            if e["tag"]["supported"]:
                assert e["tag"]["evidence_ids"] and all(x.startswith("SE-") for x in e["tag"]["evidence_ids"])
    # sem fato de tag no SERVICE-EVIDENCE: tipo vira nome sintético + manifesto (nunca filtro por tag)
    empty = work / "se.jsonl"
    empty.write_text(json.dumps({"provider": "aws", "terraform_resource_type": "outro", "fact_kind": "tag_support",
                                 "status": "stated", "value": {"supported": True}, "evidence_id": "SE-x",
                                 "level": "published"}) + "\n")
    t2 = skus.build_table(empty)
    b = t2["providers"]["aws"]["types"]["aws_s3_bucket"]
    assert b["tag"]["status"] == "no_evidence" and b["trace"] == "name" and "nome sintético" in b["trace_reason"]
    assert skus.intent_fields(t2, "aws", "aws_s3_bucket")["tag_supported"] is False


def test_ttl_attribute_is_never_native_destruction():
    t = skus.load_table()
    q = t["providers"]["aws"]["types"]["aws_sqs_queue"]["ttl"]
    assert q["supported"] and "message_retention_seconds" in q["attributes"]
    assert q["native_resource_destruction"] is False


def test_policy_validation_catches_bad_entries(monkeypatch):
    pol = skus.load_policy()
    pol["providers"]["aws"]["types"]["aws_redshift_cluster"] = {"cost": {"hourly": 1}, "trace": "tag",
                                                                "delete_order": 1}
    pol["providers"]["aws"]["types"]["aws_route_table_association"]["cost"] = {"hourly": 0.5}
    errs = skus.validate_policy(pol)
    assert any("Classe C" in e for e in errs) and any("custo zero" in e for e in errs)


def test_expected_residue_matches_table_removal_modes():
    t = skus.load_table()
    res = residue.load()
    sched = {(p, k) for p, pv in t["providers"].items() for k, e in pv["types"].items()
             if e["removal"]["mode"] in ("scheduled", "soft_delete", "retained")}
    assert sched == {(r["provider"], r["resource_type"]) for r in res["owned"]}


@pytest.mark.parametrize("provider,step,mode", [("aws", 9, "torn"), ("google", 20, "split"), ("oci", 31, "before"),
                                                ("azurerm", 40, "torn")])
def test_failure_injection_sample(provider, step, mode):
    base = bo_tmp() / "pytest_fi"
    out = run_one(base, provider, skus.load_table(), residue.load(), step, mode)
    shutil.rmtree(base / provider, ignore_errors=True)
    assert out["returncode"] == -9 and out["fails"] == [], out


def test_intent_reconciled_gate_passes_clean_run_and_catches_leftovers(work, monkeypatch):
    from bo.safety.sim_runner import paths, run_batch, setup
    d = work / "sim"
    setup(d, "aws", skus.load_table())
    run_batch(d, "aws")
    p = paths(d)
    monkeypatch.setenv("BO_PRIVATE_DIR", str(d))
    os.rename(p["private"], d / "SIM-AWS")
    assert ir_check("SIM-AWS", p["public"], sweep=False) == []
    rn = p["public"] / "run_manifest.jsonl"
    lines = rn.read_text().splitlines()
    last_absent = max(i for i, x in enumerate(lines) if '"absent"' in x)
    rn.write_text("\n".join(lines[:last_absent] + lines[last_absent + 1:]) + "\n")
    errs = ir_check("SIM-AWS", p["public"], sweep=False)
    assert any(e.startswith("I3") for e in errs) and any(e.startswith("I4") for e in errs)
    assert any(e.startswith("I5") for e in ir_check("SIM-AWS", p["public"], sweep=True))
