"""Posse, trava global, varredura de todas as regiões e tipos, dry-run sem CLI, resíduo esperado."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading

import pytest

from bo.safety import locks, providers, residue, skus, sweep
from bo.safety.common import bo_repo
from bo.safety.fakecloud import FakeCloud, modes_from_table
from bo.safety.manifest import Manifest
from bo.safety.ownership import OwnershipRefused, cleanup, complete, delete_candidates, owned, reconcile
from safety_helpers import fresh_check


@pytest.fixture
def env(work):
    t = skus.load_table()
    fc = FakeCloud(work / "cloud.json", "aws", ["us-east-1", "eu-west-1", "ap-southeast-7"],
                   modes_from_table(t, "aws"), ["aws_s3_bucket"])
    man = Manifest("SMOKE-AWS", work / "public", work / "private")
    return t, fc, man


def make(man, fc, t, rtype, region="us-east-1"):
    f = skus.intent_fields(t, "aws", rtype)
    it = man.record_intent(provider="aws", batch_id="B-AWS-01", resource_type=rtype, identity_check=fresh_check(),
                           ttl_hours=2, table_fields=f, region=region, run_tag="b-aws-01")
    man.stage(it["intent_id"], "creating", identity_check=fresh_check())
    ref = fc.create(rtype, region, it["logical_name"], it.get("tags"))
    man.stage(it["intent_id"], "created", identity_check=fresh_check(), ref=ref)
    return ref, it


def test_owned_by_tag_ref_or_manifest_name_only(env):
    t, fc, man = env
    ref, it = make(man, fc, t, "aws_kms_alias")
    st = man.load()
    assert owned({"ref": ref, "type": "aws_kms_alias", "name": "x", "tags": {}}, "b-aws-01", st) == "manifesto:ref"
    assert owned({"ref": "z", "type": "aws_kms_alias", "name": "alias/" + it["logical_name"], "tags": {},
                  "region": "us-east-1"}, "b-aws-01", st) == "manifesto:nome"
    assert owned({"ref": "z", "type": "aws_sqs_queue", "name": it["logical_name"], "tags": {}}, "b-aws-01", st) is None
    assert owned({"ref": "z", "type": "aws_s3_bucket", "tags": {"bo-run": "b-aws-01"}}, "b-aws-01", st) == "tag"
    assert owned({"ref": "z", "type": "aws_s3_bucket", "tags": {"bo-run": "b-aws-02"}}, "b-aws-01", st) is None


def test_baseline_diff_list_is_refused():
    with pytest.raises(OwnershipRefused, match="baseline"):
        delete_candidates([{"ref": "x"}])


def test_cleanup_deletes_only_owned_across_all_regions(env, work):
    t, fc, man = env
    mine = [make(man, fc, t, x)[0] for x in ("aws_s3_bucket", "aws_sqs_queue", "aws_db_instance", "aws_kms_key")]
    alien = [fc.create("aws_sqs_queue", "ap-southeast-7", "bo-aws-01-0099", {}, owner="terceiro"),
             fc.create("aws_db_instance", "eu-west-1", "prod", {}, owner="terceiro")]
    leak = fc.create("aws_sqs_queue", "ap-southeast-7", "vazou", {"bo-run": "b-aws-01"})
    rep = cleanup(man, fc, "b-aws-01", fresh_check(), owner="t", lock_root=work / "locks",
                  wait_fn=lambda s: fc.advance(3600), poll_s=3600)
    items = fc.items()
    assert all(a in items for a in alien) and not fc.foreign_deletes()
    assert leak not in items and rep.untracked_seen  # achado na região exótica e relatado
    assert [items[m]["state"] for m in mine if m in items] == ["pending_deletion"]  # só o KMS agendado
    res = residue.load()
    ok, why = complete(rep, man, lambda it: residue.owned_expected(res, "aws", it))
    assert not ok and any("sem intenção" in w for w in why)  # o vazamento sem intenção reprova


def test_cleanup_without_identity_or_with_busy_lock_refused(env, work):
    t, fc, man = env
    ref, _ = make(man, fc, t, "aws_s3_bucket")
    with pytest.raises(OwnershipRefused):
        cleanup(man, fc, "b-aws-01", None, owner="t", lock_root=work / "locks")
    locks.acquire(locks.CLEANUP, "outro", root=work / "locks")
    with pytest.raises(locks.LockBusy):
        cleanup(man, fc, "b-aws-01", fresh_check(), owner="t", lock_root=work / "locks")
    assert ref in fc.items()
    with pytest.raises(locks.LockBusy):
        locks.release(locks.CLEANUP, "t", root=work / "locks")  # só o dono solta
    locks.release(locks.CLEANUP, "outro", root=work / "locks")


def test_parallel_cleanups_serialize_on_global_lock(env, work):
    t, fc, man = env
    for x in ("aws_s3_bucket", "aws_sqs_queue", "aws_sns_topic"):
        make(man, fc, t, x)
    errs, done = [], []

    def go(name):
        try:
            cleanup(Manifest("SMOKE-AWS", work / "public", work / "private"), fc, "b-aws-01", fresh_check(),
                    owner=name, lock_root=work / "locks", wait_lock_s=30, wait_fn=lambda s: None, poll_s=0)
            done.append(name)
        except Exception as e:  # noqa: BLE001
            errs.append(repr(e))
    th = [threading.Thread(target=go, args=(f"limpeza-{i}",)) for i in range(3)]
    for x in th:
        x.start()
    for x in th:
        x.join()
    assert not errs and len(done) == 3
    assert all(s.last == "absent" for s in man.load().values())


def test_reconcile_adopts_resource_created_before_runner_died(env):
    t, fc, man = env
    f = skus.intent_fields(t, "aws", "aws_s3_bucket")
    it = man.record_intent(provider="aws", batch_id="B-AWS-01", resource_type="aws_s3_bucket",
                           identity_check=fresh_check(), ttl_hours=2, table_fields=f, run_tag="b-aws-01")
    man.stage(it["intent_id"], "creating", identity_check=fresh_check())
    fc.create("aws_s3_bucket", "us-east-1", it["logical_name"], it["tags"])  # morreu antes de gravar created
    rep = reconcile(man, fc.list_all(), "b-aws-01", fresh_check())
    assert rep.adopted == [it["intent_id"]] and len(rep.owned_live) == 1
    assert "reconciliado" in man.load()[it["intent_id"]].runs[-1]["note"]


# ------------------------------------------------------------------------------------------------ varredura
def test_dry_run_calls_no_cloud_cli_and_prints_four_providers(work):
    fake_bin = work / "bin"
    fake_bin.mkdir()
    marker = work / "chamou"
    for b in ("aws", "gcloud", "az", "oci", "terraform"):
        p = fake_bin / b
        p.write_text(f"#!/bin/sh\necho {b} >> {marker}\nexit 0\n")
        p.chmod(0o755)
    envv = dict(os.environ, PATH=f"{fake_bin}:{os.environ['PATH']}")
    r = subprocess.run(["bash", str(bo_repo() / "deploy/safety/sweep_all.sh"), "--dry-run"], capture_output=True,
                       text=True, env=envv)
    assert r.returncode == 0, r.stderr
    assert not marker.exists(), "dry-run chamou CLI de nuvem"
    for p in ("[aws]", "[google]", "[azurerm]", "[oci]"):
        assert p in r.stdout
    assert r.stdout.count("regiões: lidas da conta") == 4 and "4/4 provedores OK" in r.stdout
    assert "describe-regions" in r.stdout and "region-subscription list" in r.stdout


def test_real_sweep_refused_without_go(work):
    r = subprocess.run(["bash", str(bo_repo() / "deploy/safety/sweep_aws.sh"), "--run", "SMOKE-AWS"],
                       capture_output=True, text=True, env={k: v for k, v in os.environ.items() if k != "BO_CLOUD_GO"})
    assert r.returncode == 2 and "GO" in r.stderr
    r = subprocess.run(["bash", str(bo_repo() / "deploy/safety/teardown_oci.sh"), "--apply", "--run", "X"],
                       capture_output=True, text=True, env={k: v for k, v in os.environ.items() if k != "BO_CLOUD_GO"})
    assert r.returncode == 2


def test_coverage_hole_fails_dry_run(monkeypatch):
    t = skus.load_table()
    assert sweep.dry_run("aws", t)[0] == 0
    monkeypatch.setitem(providers.SOURCES, "aws", {**providers.SOURCES["aws"], "region": [
        s for s in providers.SOURCES["aws"]["region"] if s[0] != "kms_aliases"]})
    rc, lines = sweep.dry_run("aws", t)
    assert rc == 1 and "aws_kms_alias" in lines[-1]


def _fixture(regions, per_region, globals_):
    m = {" ".join(providers.REGION_CMD["aws"]): {"out": {"Regions": [{"RegionName": r} for r in regions]}}}
    for name, argv, _, _ in providers.SOURCES["aws"]["region"]:
        for r in regions:
            m[" ".join(providers.render(argv, {"region": r}))] = {"out": per_region.get((name, r), {})}
    for name, argv, _, _ in providers.SOURCES["aws"]["global"]:
        m[" ".join(argv)] = {"out": globals_.get(name, {})}
    return m


def test_sweep_reads_regions_from_account_and_flags_forgotten_instance(work, monkeypatch):
    regions = ["us-east-1", "me-central-1", "ap-southeast-7"]  # inclui região que nenhuma lista fixa teria
    inst = {"Reservations": [{"Instances": [{"InstanceId": "i-esquecida", "State": {"Name": "running"},
                                              "Tags": [{"Key": "Name", "Value": "w21"}]}]}]}
    fx = work / "fx.json"
    fx.write_text(json.dumps(_fixture(regions, {("ec2_instances", "ap-southeast-7"): inst}, {})))
    man = Manifest("SMOKE-AWS", work / "public")  # canal privado = $BO_PRIVATE_DIR/SMOKE-AWS (o do sweep)
    (man.private / "baseline_aws.json").write_text(json.dumps({"refs": []}))
    report = work / "rep.json"
    rc = sweep.main(["--provider", "aws", "--fixture", str(fx), "--run", "SMOKE-AWS", "--expect-empty",
                     "--batch", "B-AWS-01", "--report", str(report)])
    rep = json.loads(report.read_text())
    assert rc == 1 and rep["regions_read_from_account"] == sorted(regions) and rep["counts"] == {"investigar": 1}
    assert "i-esquecida" not in report.read_text()  # relatório público só com contagens
    assert "i-esquecida" in (man.private / "sweep_detail.json").read_text()


def test_sweep_failing_source_is_not_zero(work):
    fx = _fixture(["us-east-1"], {}, {})
    fx.pop(" ".join(providers.render(providers.SOURCES["aws"]["region"][0][1], {"region": "us-east-1"})))
    p = work / "fx.json"
    p.write_text(json.dumps(fx))
    assert sweep.main(["--provider", "aws", "--fixture", str(p)]) == 1


def test_expect_empty_without_baseline_fails(work):
    p = work / "fx.json"
    p.write_text(json.dumps(_fixture(["us-east-1"], {}, {})))
    assert sweep.main(["--provider", "aws", "--fixture", str(p), "--run", "SMOKE-AWS", "--expect-empty",
                       "--report", str(work / "r.json")]) == 1


def test_expected_residue_classification():
    res = residue.load()
    assert residue.classify(res, "aws", {"type": "aws_kms_key", "state": "pending_deletion"}, "tag", set()) == \
        "residuo_esperado"
    assert residue.classify(res, "aws", {"type": "aws_kms_key", "state": "active"}, "tag", set()) == \
        "residuo_inesperado"
    assert residue.classify(res, "azurerm", {"type": "Microsoft.Network/networkWatchers", "name": "NetworkWatcher_eastus"},
                            None, set()) == "plataforma"
    assert residue.classify(res, "aws", {"ref": "r1", "type": "aws_vpc"}, None, {"r1"}) == "baseline"
    assert residue.classify(res, "aws", {"ref": "r2", "type": "aws_vpc"}, None, {"r1"}) == "investigar"
    kinds = {(r["provider"], r["resource_type"]) for r in res["owned"]}
    assert ("aws", "aws_kms_key") in kinds and ("azurerm", "azurerm_key_vault") in kinds
    assert ("google", "google_kms_key_ring") in kinds and ("oci", "oci_kms_vault") in kinds


def test_every_allowlisted_type_has_a_delete_path():
    t = skus.load_table()
    for p, pv in t["providers"].items():
        for rtype, e in pv["types"].items():
            st = providers.delete_steps(p, rtype)
            assert st is not None, rtype
            if e["trace"] == "ref":
                assert st in ("cascade",) or isinstance(st, list), rtype
            if isinstance(st, list):
                for s in st:
                    assert all(isinstance(a, str) and ";" not in a and "|" not in a for a in s), rtype


def test_teardown_dry_run_lists_every_type(work):
    r = subprocess.run(["bash", str(bo_repo() / "deploy/safety/teardown_google.sh"), "--dry-run"],
                       capture_output=True, text=True)
    assert r.returncode == 0
    for rtype in skus.load_table()["providers"]["google"]["types"]:
        assert rtype in r.stdout
    assert sys.executable


def test_native_types_map_to_terraform_for_name_ownership(work):
    """Rede GCP sem rótulo, vista pelo Cloud Asset Inventory: só o nome sintético + manifesto provam a posse."""
    t = skus.load_table()
    man = Manifest("SMOKE-GCP", work / "public", work / "private")
    f = skus.intent_fields(t, "google", "google_compute_network")
    it = man.record_intent(provider="google", batch_id="B-GCP-01", resource_type="google_compute_network",
                           identity_check=fresh_check("google"), ttl_hours=2, table_fields=f, region="global",
                           run_tag="b-gcp-01")
    man.stage(it["intent_id"], "creating", identity_check=fresh_check("google"))
    rows = providers.p_gcp_asset([
        {"name": "//compute.googleapis.com/projects/p/global/networks/" + it["logical_name"],
         "assetType": "compute.googleapis.com/Network", "location": "global", "displayName": it["logical_name"]},
        {"name": "//compute.googleapis.com/projects/p/global/networks/bo-gcp-01-0099",
         "assetType": "compute.googleapis.com/Network", "location": "global", "displayName": "bo-gcp-01-0099"}], "global")
    assert rows[0]["type"] == "google_compute_network"
    st = man.load()
    assert owned(rows[0], "b-gcp-01", st) == "manifesto:nome" and owned(rows[1], "b-gcp-01", st) is None


def test_oci_deleted_compartment_is_absence_not_residue(work):
    rows = providers.p_oci_search({"data": {"items": [
        {"identifier": "c1", "resource-type": "Compartment", "display-name": "bo-x", "lifecycle-state": "DELETED",
         "freeform-tags": {"bo-run": "b-oci-01"}}]}}, "sa-saopaulo-1")
    assert rows[0]["type"] == "oci_identity_compartment" and rows[0]["state"] == "gone"
    man = Manifest("SMOKE-OCI", work / "public", work / "private")
    rep = reconcile(man, rows, "b-oci-01", fresh_check("oci"))
    assert not (rep.owned_live or rep.owned_pending or rep.owned_scheduled or rep.untracked_owned)
    assert residue.platform_match(residue.load(), "oci", rows[0]) == "deleted_compartment"
