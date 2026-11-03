"""Fonte real fixada (Libcloud 3.9.1): fatos conhecidos, regeneração idêntica e validador C09."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from bo.gold_libcloud import build as B
from bo.gold_libcloud import source as S


@pytest.fixture(scope="module")
def res():
    S.verify()
    return B.build(S.pkg_root())


def find(res, subj_end, obj):
    return [r for r in res["records"] if r["subject_id"].endswith(subj_end) and r["object_id"] == obj]


def test_source_pinned():
    v = S.verify()
    assert v["sha256"] == S.SHA256 and v["py_files"] == 372
    assert (S.download_dir() / "SOURCE.txt").read_text().count(S.SHA256) == 1


@pytest.mark.parametrize("subj,obj,rule", [
    ("ec2:BaseEC2NodeDriver._to_node/element/instanceId", "lcm:compute.Node.id", "R1"),
    ("ec2:BaseEC2NodeDriver._to_node/element/launchTime", "lcm:compute.Node.created_at", "R2"),
    ("ec2:BaseEC2NodeDriver._to_node/element/instanceState/name", "lcm:compute.Node.state", "R3"),
    ("gce:GCENodeDriver._to_node/node/status", "lcm:compute.Node.state", "R3"),
    ("gce:GCENodeDriver._to_node/node/networkInterfaces/*/accessConfigs/*/natIP", "lcm:compute.Node.public_ips", "R1"),
    ("s3:BaseS3StorageDriver._to_obj/element/Key", "lcm:storage.Object.name", "R1"),
    ("s3:BaseS3StorageDriver._to_obj/element/Size", "lcm:storage.Object.size", "R2"),
    ("route53:Route53DNSDriver._to_record/elem/TTL", "lcm:dns.Record.ttl", "R2"),
    ("google:GoogleDNSDriver._to_zone/r/dnsName", "lcm:dns.Zone.domain", "R1"),
    ("elb:ElasticLBDriver._to_balancer/el/LoadBalancerName", "lcm:loadbalancer.LoadBalancer.name", "R1"),
    ("azure_arm:AzureNodeDriver._to_node/response.object@ex_get_public_ip/properties/ipAddress",
     "lcm:compute.Node.public_ips", "R1"),
])
def test_known_facts(res, subj, obj, rule):
    hits = find(res, subj, obj)
    assert len(hits) == 1 and hits[0]["curation_rule"] == rule, [(h["subject_id"], h["curation_rule"]) for h in hits]


def test_ec2_state_table_from_source(res):
    """A tabela é a do código, não a que se esperaria: em 3.9.1 'stopped'/'stopping' não estão no mapa e caem
    no except KeyError -> NodeState.UNKNOWN (sentinela declarada)."""
    r = find(res, "ec2:BaseEC2NodeDriver._to_node/element/instanceState/name", "lcm:compute.Node.state")[0]
    t = r["translation_fn"]["params"]["table"]
    assert t == {"pending": "pending", "running": "running", "shutting-down": "unknown", "terminated": "terminated"}
    assert "stopped" not in t and r["semantic_relation"] == "close"
    assert any(x["kind"] == "sentinel" and x["map"] == {"*": "unknown"} for x in r["loss_contract"])


def test_route53_name_is_derived(res):
    r = find(res, "route53:Route53DNSDriver._to_record/elem/Name", "lcm:dns.Record.name")[0]
    assert r["curation_rule"] == "R5"   # o código corta o sufixo da zona


def test_no_oci_driver(res):
    assert "oci" not in {r["subject_category"] for r in res["records"]}


def test_claim_ids_unique_and_stable(res):
    ids = [r["claim_id"] for r in res["records"]]
    assert len(ids) == len(set(ids))
    again = B.build(S.pkg_root())
    assert [r["claim_id"] for r in again["records"]] == ids


def test_regeneration_identical_to_disk(res):
    for name, text in B.render(res).items():
        assert (B.out_dir() / name).read_text(encoding="utf-8") == text, name


def test_official_validator_on_published_file():
    env = dict(os.environ)
    r = subprocess.run([sys.executable, "-I", "-m", "bo.contracts.validate", "correspondences",
                        str(B.out_dir() / "libcloud.sssom.tsv")], capture_output=True, text=True, env=env,
                       cwd=os.environ["BO_TMP"])
    assert r.returncode == 0, r.stdout + r.stderr


def test_registry_sites_exist(res):
    for g in res["registry"]:
        for s in g["sites"]:
            p = S.tree_root() / s["file"]
            assert p.is_file() and s["line"] <= len(p.read_text(encoding="utf-8").splitlines())
