"""Redator antes da 1ª serialização: state/plan sem redator é recusado; sensível, Withheld e ids nunca saem."""

from __future__ import annotations

import importlib.util
import json
import os

import pytest

from bo.safety import redaction as R
from bo.safety.common import bo_repo

ACCT = "4" * 6 + "7" * 6
ARN = "ar" + "n:aws:iam::" + ACCT + ":role/bo-x"
AKEY = "AK" + "IA" + "Q" * 16
SUB = "/subscr" + "iptions/12345678-1234-4123-8123-123456789abc/resourceGroups/rg"
OCID = "ocid" + "1.bucket.oc1.sa-saopaulo-1.aaaaexemplo"
SECRET = "Sup3r-" + "s3cret-val"
UD = "user" + "_data"
PEM = "-----BEGIN RSA PRIV" + "ATE KEY-----\nMIIabc\n-----END RSA PRIV" + "ATE KEY-----"
MAIL = "fulano" + "@" + "empresa.com.br"


def plan_doc():
    return {
        "format_version": "1.2", "terraform_version": "1.9.8",
        "variables": {"db_password": {"value": SECRET}, "bo_region": {"value": "us-east-1"}},
        "resource_changes": [{
            "address": "aws_db_instance.caso", "type": "aws_db_instance", "mode": "managed",
            "change": {"actions": ["create"],
                       "after": {"instance_class": "db.t4g.micro", "password": SECRET, "username": "bo",
                                 "tags": {"bo-run": "b-aws-01"}, "arn": ARN},
                       "after_sensitive": {"password": True}, "after_unknown": {}}}, {
            "address": "aws_lambda_function.f", "type": "aws_lambda_function", "mode": "managed",
            "change": {"actions": ["create"],
                       "after": {"function_name": "bo-f", "environment": [{"variables": {"API": "abc123xyz"}}],
                                 "role": ARN}, "after_sensitive": {}, "after_unknown": {}}}],
        "output_changes": {"conn": {"after": "postgres://" + SECRET, "after_sensitive": True}},
    }


def state_file_doc():
    return {"version": 4, "terraform_version": "1.9.8", "serial": 3, "lineage": "abc",
            "outputs": {"pw": {"value": SECRET, "sensitive": True}},
            "resources": [{"mode": "managed", "type": "aws_instance", "name": "x", "instances": [
                {"attributes": {"id": "i-0abc", UD: "#!/bin/bash\necho " + SECRET, "account": ACCT,
                                "nested": {"token_value": SECRET}},
                 "sensitive_attributes": [[{"type": "get_attr", "value": "nested"}]],
                 "private": "eyJzY2hlbWEiOiAxfQ=="}]}]}


def test_plan_sensitive_values_variables_and_ids_withheld():
    red = R.redact_tf(plan_doc())
    txt = red.text()
    assert SECRET not in txt and ACCT not in txt and "abc123xyz" not in txt
    assert red.meta["kind"] == "plan"
    for rule in ("R-SENS", "R-VAR", "R-CONTENT", "R-IDENT"):
        assert red.meta["counts"].get(rule, 0) >= 1, rule
    after = red.obj["resource_changes"][0]["change"]["after"]
    assert after["password"] == R.WITHHELD and after["instance_class"] == "db.t4g.micro"
    assert after["tags"] == {"bo-run": "b-aws-01"}  # o que não é sensível continua legível


def test_state_file_v4_sensitive_paths_private_and_user_data():
    red = R.redact_tf(state_file_doc())
    assert red.meta["kind"] == "state_file"
    txt = red.text()
    assert SECRET not in txt and ACCT not in txt and "eyJzY2hlbWEi" not in txt
    inst = red.obj["resources"][0]["instances"][0]
    assert inst["attributes"][UD] == R.WITHHELD
    assert inst["attributes"]["nested"]["token_value"] == R.WITHHELD


def test_state_show_json_masks():
    st = {"format_version": "1.0", "values": {"root_module": {"resources": [
        {"address": "a.b", "values": {"secret_string": SECRET, "name": "bo-x", "key": "v"},
         "sensitive_values": {"key": True}}]}}}
    red = R.redact_tf(st)
    vals = red.obj["values"]["root_module"]["resources"][0]["values"]
    assert red.meta["kind"] == "state" and vals["key"] == R.WITHHELD and vals["secret_string"] == R.WITHHELD
    assert vals["name"] == "bo-x"


@pytest.mark.parametrize("value", [ARN, AKEY, SUB, OCID, MAIL, ACCT, PEM,
                                   "DefaultEndpointsProtocol=https;AccountName=x;AccountKey=" + "Zm9v" * 6])
def test_identifiers_in_free_text_become_marker(value):
    red = R.redact_tf({"note": f"erro em {value} ao criar"}, "record")
    assert value not in red.text() and R.IDENT in red.text()


def test_symbols_replace_known_real_values_and_hashes_survive():
    h = "a" * 64
    red = R.redact_tf({"ref": "bucket-real-123", "sha": h}, "record", symbols={"bucket-real-123": "ref:bucket"})
    assert red.obj == {"ref": "ref:bucket", "sha": h}


def test_raw_state_without_redactor_is_refused(work):
    with pytest.raises(R.RedactionRefused):
        R.write_raw(work / "state.json", state_file_doc())
    with pytest.raises(R.RedactionRefused):
        R.write_redacted(work / "state.json", state_file_doc())  # dict cru não atravessa a porta
    assert not (work / "state.json").exists()


def test_write_redacted_writes_only_redacted_and_rechecks_privacy(work):
    R.write_redacted(work / "plan.json", R.redact_tf(plan_doc()))
    txt = (work / "plan.json").read_text()
    assert SECRET not in txt and R.SCHEMA in txt  # selo, sem valores
    assert R.find_raw_tf_artifacts([work]) == []  # redigido não conta como state cru
    forged = R.Redacted({"leak": ARN}, {})
    with pytest.raises(R.RedactionRefused):
        R.write_redacted(work / "forjado.json", forged)  # Redacted forjado ainda passa pelo privacy_lint
    assert not (work / "forjado.json").exists()


def test_write_inside_ephemeral_channel_refused(work):
    eph = work / "eph"
    eph.mkdir()
    with pytest.raises(R.RedactionRefused):
        R.write_redacted(eph / "x.json", R.redact_tf({"a": 1}, "record"), ephemeral_roots=[eph])


def test_plan_binary_refused():
    with pytest.raises(R.RedactionRefused):
        R.redact_tf(b"PK\x03\x04tfplan")


def test_find_raw_tf_artifacts(work):
    (work / "cfg").mkdir()
    (work / "cfg" / "main.tf").write_text('resource "x" "y" {}')
    assert R.find_raw_tf_artifacts([work / "cfg"]) == []
    (work / "cfg" / "terraform.tfstate").write_text("{}")
    (work / "cfg" / "dump.json").write_text(json.dumps(state_file_doc()))
    (work / "cfg" / "crash.log").write_text("panic")
    assert R.find_raw_tf_artifacts([work / "cfg"]) == ["crash.log", "dump.json", "terraform.tfstate"]


def test_harness_interface_redact_obj_context_from_deploy_file():
    """Os harnesses carregam deploy/safety/redactor.py por caminho e chamam redact(obj, context)."""
    p = bo_repo() / "deploy" / "safety" / "redactor.py"
    spec = importlib.util.spec_from_file_location("bo_safety_redactor_t", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    rec = {"atom": "aws:aws_db_instance:password", "state": "withheld", "message": "ok", "note": "em " + ARN}
    out = mod.redact(rec, "readback")
    assert out["atom"] == rec["atom"] and out["state"] == "withheld" and out["message"] == "ok"
    assert ARN not in json.dumps(out)
    assert mod.redact({UD: "#!/bin/sh"}, "readback") == {UD: "WITHHELD"}


def test_cli_filter(work):
    import subprocess
    import sys
    p = bo_repo() / "deploy" / "safety" / "redactor.py"
    r = subprocess.run([sys.executable, "-I", str(p), "--kind", "plan"], input=json.dumps(plan_doc()),
                       capture_output=True, text=True, env={**os.environ})
    assert r.returncode == 0 and SECRET not in r.stdout and "R-SENS" in r.stderr
