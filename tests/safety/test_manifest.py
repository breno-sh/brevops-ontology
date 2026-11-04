"""Manifesto de intenção C16: intenção não gravada = criação recusada; ordem, identidade, cópia pública redigida,
linha rasgada tolerada; arquivos validam no validador único do CONTRACTS."""

from __future__ import annotations

import json
from datetime import timedelta

import pytest

from bo.contracts import validate as V
from bo.safety import skus
from bo.safety.common import iso, now_dt, read_jsonl
from bo.safety.manifest import Manifest, ManifestRefused
from safety_helpers import fresh_check


@pytest.fixture
def man(work):
    return Manifest("SMOKE-AWS", work / "public", work / "private")


def intent(man, rtype="aws_s3_bucket", **kw):
    t = skus.load_table()
    return man.record_intent(provider="aws", batch_id="B-AWS-01", resource_type=rtype, identity_check=fresh_check(),
                             ttl_hours=2, table_fields=skus.intent_fields(t, "aws", rtype),
                             address=f"{rtype}.caso", region="us-east-1", **kw)


def test_creation_without_recorded_intent_is_refused(man):
    for st in ("creating", "created", "confirmed", "removal_requested", "absent"):
        with pytest.raises(ManifestRefused, match="sem intenção"):
            man.stage("INT-B-AWS-01-0001", st, identity_check=fresh_check(), ref="r")


def test_full_lifecycle_validates_c16_public_and_private(man):
    it = intent(man, case_id="CASE-AWSGCP-STO-0001")
    iid = it["intent_id"]
    chk = fresh_check()
    man.stage(iid, "creating", identity_check=chk)
    man.stage(iid, "created", identity_check=chk, ref="bucket-real-xyz")
    man.stage(iid, "confirmed", identity_check=chk)
    man.stage(iid, "removal_requested", identity_check=chk)
    man.stage(iid, "absent", residual_usd=0.0)
    for side in ("public", "private"):
        for f in ("intent_manifest.jsonl", "run_manifest.jsonl"):
            r = V.validate("C16", man.public / f if side == "public" else man.private / f)
            assert r.ok, (side, f, r.errors)
    pub = (man.public / "run_manifest.jsonl").read_text()
    assert "bucket-real-xyz" not in pub and '"visibility":"public"' in pub
    assert "bucket-real-xyz" in (man.private / "run_manifest.jsonl").read_text()
    assert man.public_consistent()
    assert (man.private.stat().st_mode & 0o777) == 0o700


def test_intent_fields_tag_ttl_and_synthetic_name(man):
    b = intent(man)
    assert b["tag_supported"] and b["tags"]["bo-run"] == "b-aws-01" and b["ttl_hours"] == 2
    a = intent(man, rtype="aws_kms_alias")
    assert not a["tag_supported"] and "tags" not in a and a["logical_name"] == "bo-aws-01-0002"
    k = intent(man, rtype="aws_kms_key")
    assert k["max_residual_cost"]["amount"] == 1.0
    assert (now_dt() + timedelta(days=6)).isoformat() < k["purge_deadline"]  # prazo inclui a janela do KMS


def test_intent_without_ttl_or_fresh_identity_refused(man):
    t = skus.load_table()
    f = skus.intent_fields(t, "aws", "aws_s3_bucket")
    with pytest.raises(ManifestRefused, match="TTL"):
        man.record_intent(provider="aws", batch_id="B-AWS-01", resource_type="aws_s3_bucket",
                          identity_check=fresh_check(), ttl_hours=0, table_fields=f)
    old = dict(fresh_check(), checked_at=iso(now_dt() - timedelta(hours=1)))
    with pytest.raises(Exception, match="velha"):
        man.record_intent(provider="aws", batch_id="B-AWS-01", resource_type="aws_s3_bucket", identity_check=old,
                          ttl_hours=2, table_fields=f)


def test_creating_requires_fresh_same_identity_and_created_requires_ref(man):
    iid = intent(man)["intent_id"]
    other = fresh_check(canon="aws|account=outra")
    with pytest.raises(ManifestRefused, match="identidade mudou"):
        man.stage(iid, "creating", identity_check=other)
    with pytest.raises(Exception):
        man.stage(iid, "creating", identity_check=None)
    man.stage(iid, "creating", identity_check=fresh_check())
    with pytest.raises(ManifestRefused, match="referência"):
        man.stage(iid, "created", identity_check=fresh_check())
    with pytest.raises(ManifestRefused, match="C16-IDENTITY"):
        man.stage(iid, "created", ref="x")


def test_stages_only_go_up(man):
    iid = intent(man)["intent_id"]
    chk = fresh_check()
    man.stage(iid, "creating", identity_check=chk)
    man.stage(iid, "created", identity_check=chk, ref="x")
    with pytest.raises(ManifestRefused, match="só sobem"):
        man.stage(iid, "creating", identity_check=chk)
    with pytest.raises(ManifestRefused, match="só sobem"):
        man.stage(iid, "created", identity_check=chk, ref="x")


def test_torn_tail_is_ignored_then_cut(man):
    iid = intent(man)["intent_id"]
    p = man.private / "run_manifest.jsonl"
    with open(p, "ab") as f:
        f.write(b'{"run_id": "RUN-9", "intent_id": "' + iid.encode() + b'", "sta')
    recs, probs = read_jsonl(p)
    assert probs == ["cauda_rasgada"] and all(r["stage"] == "intent" for r in recs)
    assert man.load()[iid].last == "intent"
    m2 = Manifest("SMOKE-AWS", man.public, man.private)
    m2.stage(iid, "creating", identity_check=fresh_check())  # corta a cauda antes do append
    recs, probs = read_jsonl(p)
    assert probs == [] and recs[-1]["stage"] == "creating"


def test_publish_rebuilds_public_after_split_write(man):
    iid = intent(man)["intent_id"]
    (man.public / "run_manifest.jsonl").write_text("")  # morte entre a cópia privada e a pública
    assert not man.public_consistent()
    man.publish()
    assert man.public_consistent()
    assert json.loads((man.public / "run_manifest.jsonl").read_text().splitlines()[0])["intent_id"] == iid


def test_private_inside_public_or_git_refused(work):
    with pytest.raises(ManifestRefused):
        Manifest("SMOKE-AWS", work / "pub", work / "pub" / "private")
    import subprocess
    subprocess.run(["git", "init", "-q", str(work / "repo")], check=True)
    with pytest.raises(ManifestRefused, match="git"):
        Manifest("SMOKE-AWS", work / "pub", work / "repo" / "private")


def test_supervisor_export_has_what_destroy_needs(man):
    iid = intent(man)["intent_id"]
    chk = fresh_check()
    man.stage(iid, "creating", identity_check=chk)
    man.stage(iid, "created", identity_check=chk, ref="ref-1")
    ex = man.export_for_supervisor()[0]
    assert ex["ref"] == "ref-1" and ex["run_tag"] == "b-aws-01" and ex["region"] == "us-east-1"
