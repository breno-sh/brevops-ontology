"""Identidade efetiva conferida contra a allowlist privada: fora dela, aborta; allowlist frouxa, aborta."""

from __future__ import annotations

import json
import os
import subprocess
from datetime import timedelta

import pytest

from bo.safety import identity as I
from bo.safety.common import iso, now_dt

ACCT = "1" * 6 + "2" * 6
SUB1 = "00000000-0000-4000-8000-" + "0" * 11 + "1"
SUB9 = "00000000-0000-4000-8000-" + "0" * 10 + "99"
OTHER = "9" * 6 + "8" * 6


def runner(outputs: dict):
    def run(argv, env):
        key = " ".join(argv[:3])
        if key not in outputs:
            return 1, ""
        return 0, json.dumps(outputs[key])
    return run


def aws_out(acct=ACCT, principal="user/bo-runner"):
    return {"aws sts get-caller-identity": {"Account": acct, "Arn": "ar" + f"n:aws:iam::{acct}:{principal}"}}


def test_aws_sandbox_matches(allowlist):
    chk = I.check("aws", env={}, run=runner(aws_out()))
    assert chk["matches_allowlist"] and len(chk["identity_sha256"]) == 64
    assert ACCT not in json.dumps(chk)  # só o hash sai


def test_identity_outside_allowlist_aborts(allowlist):
    with pytest.raises(I.IdentityRefused, match="fora da allowlist"):
        I.check("aws", env={}, run=runner(aws_out(OTHER)))


def test_root_user_refused(allowlist):
    with pytest.raises(I.IdentityRefused, match="root"):
        I.check("aws", env={}, run=runner(aws_out(principal="root")))


def test_cli_failure_aborts(allowlist):
    with pytest.raises(I.IdentityRefused, match="falhou"):
        I.check("aws", env={}, run=lambda a, e: (255, ""))


@pytest.mark.parametrize("provider,outputs,env", [
    ("google", {"gcloud config list": {"core": {"project": "bo-sandbox", "account": "dev@example.com"}}}, {}),
    ("azurerm", {"az account show": {"id": SUB1, "tenantId": "t-sintetico"}},
     {"ARM_SUBSCRIPTION_ID": SUB1}),
])
def test_other_providers_match(allowlist, provider, outputs, env):
    assert I.check(provider, env=env, run=runner(outputs))["matches_allowlist"]


def test_oci_reads_profile_and_confirms_user(allowlist, work):
    cfg = work / "oci_config"
    cfg.write_text("[DEFAULT]\ntenancy=ten-sintetico\nuser=usr-sintetico\nregion=sa-saopaulo-1\n")
    out = {"oci iam user": {"data": {"id": "usr-sintetico", "lifecycle-state": "ACTIVE"}}}
    assert I.check("oci", env={"OCI_CLI_CONFIG_FILE": str(cfg)}, run=runner(out))["matches_allowlist"]
    bad = {"oci iam user": {"data": {"id": "usr-sintetico", "lifecycle-state": "INACTIVE"}}}
    with pytest.raises(I.IdentityRefused):
        I.check("oci", env={"OCI_CLI_CONFIG_FILE": str(cfg)}, run=runner(bad))


@pytest.mark.parametrize("provider,env", [
    ("google", {"GOOGLE_APPLICATION_CREDENTIALS": "/x/key.json"}),
    ("google", {"GOOGLE_PROJECT": "outro-projeto"}),
    ("azurerm", {"ARM_CLIENT_SECRET": "x" * 10}),
    ("azurerm", {"ARM_SUBSCRIPTION_ID": SUB9}),
    ("oci", {"OCI_CLI_AUTH": "instance_principal"}),
    ("aws", {"AWS_ACCESS_KEY_ID": "x", "AWS_PROFILE": "y"}),
])
def test_env_that_changes_terraform_identity_is_refused(allowlist, provider, env):
    outs = {"gcloud config list": {"core": {"project": "bo-sandbox", "account": "dev@example.com"}},
            "az account show": {"id": SUB1, "tenantId": "t-sintetico"},
            **aws_out()}
    with pytest.raises(I.IdentityRefused):
        I.check(provider, env=env, run=runner(outs))


def test_allowlist_missing_open_permissions_symlink_or_inside_repo(allowlist, work, monkeypatch):
    p = allowlist["path"]
    os.chmod(p, 0o644)
    with pytest.raises(I.IdentityRefused, match="600"):
        I.load_allowlist(p)
    os.chmod(p, 0o600)
    link = work / "cfg" / "link"
    link.symlink_to(p)
    with pytest.raises(I.IdentityRefused, match="link"):
        I.load_allowlist(link)
    with pytest.raises(I.IdentityRefused, match="ausente"):
        I.load_allowlist(work / "nao-existe")
    repo = work / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    inside = repo / "allowlist"
    inside.write_text(p.read_text())
    os.chmod(inside, 0o600)
    with pytest.raises(I.IdentityRefused, match="repositório"):
        I.load_allowlist(inside)


def test_allowlist_accepts_raw_identity_line_and_rejects_garbage(work):
    p = work / "al"
    p.write_text(f"aws aws|account={ACCT} pessoal\n")
    os.chmod(p, 0o600)
    assert I.identity_hash(f"aws|account={ACCT}") in I.load_allowlist(p)["aws"]
    p.write_text("nuvemx 123\n")
    with pytest.raises(I.IdentityRefused, match="formato"):
        I.load_allowlist(p)


def test_freshness_immediately_before_apply():
    chk = {"identity_sha256": "a" * 64, "checked_at": iso(now_dt()), "matches_allowlist": True}
    I.require_fresh(chk)
    old = dict(chk, checked_at=iso(now_dt() - timedelta(seconds=I.FRESH_SECONDS + 5)))
    with pytest.raises(I.IdentityRefused, match="velha"):
        I.require_fresh(old)
    with pytest.raises(I.IdentityRefused):
        I.require_fresh(dict(chk, matches_allowlist=False))
    with pytest.raises(I.IdentityRefused):
        I.require_fresh(None)


def test_cli_verify_allowlist_prints_counts_only(allowlist):
    import sys
    from bo.safety.common import bo_repo
    r = subprocess.run([sys.executable, "-I", str(bo_repo() / "deploy/safety/identity_guard.py"), "verify-allowlist"],
                       capture_output=True, text=True, env=dict(os.environ))
    assert r.returncode == 0 and "aws=1" in r.stdout and "sha256" not in r.stdout
