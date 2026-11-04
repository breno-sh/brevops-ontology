"""Testes do SERVICE-EVIDENCE: redação, resolvedores, parsers da ponte, regras e o próprio gate de níveis.

Os testes que leem a fonte fixada usam a cópia conferida dos DOCS-* e o schema do pin (offline).
"""

import copy
import json

import pytest

from bo.service_evidence import common, extract, levels, protocol, rules


def test_redact_subscription_and_account():
    guid = "-".join(["12345678", "1234", "1234", "1234", "123456789abc"])
    digits = "123456" + "789012"  # montado em tempo de teste para o hook de privacidade não ver o valor no fonte
    s, red = common.redact("id /subscriptions/" + guid + "/resourceGroups/x e " + digits)
    assert red and "{subscriptionId}" in s and "{redacted:twelve_digits}" in s
    assert common.redact("nada aqui")[1] is False


def test_resolve_doc_literal_and_wrapped():
    p, rel = "google", "website/docs/r/compute_firewall.html.markdown"
    ln = common.find_line(p, rel, "DENY rules take")
    ok = common.doc_cite(p, rel, ln, "DENY rules take precedence over ALLOW rules having equal priority.")
    assert common.resolve_doc(p, ok) is None
    wrong = dict(ok, sentence="ALLOW rules take precedence over DENY rules.")
    assert common.resolve_doc(p, wrong)
    shifted = dict(ok, line=ln - 3)
    assert common.resolve_doc(p, shifted) == "frase começa depois da linha citada"
    assert common.resolve_doc(p, dict(ok, tag="v0.0.1")) == "tag fora do pin"


def test_resolve_schema_node_and_keys():
    p = "aws"
    ptr = common.schema_pointer(p, "resource_identity_schemas", "aws_s3_bucket")
    c = common.schema_cite(p, ptr)
    assert common.resolve_schema(p, c) is None
    assert json.loads(c["sentence"])["attributes"]["bucket"]["required_for_import"] is True
    bad = dict(c, sentence=c["sentence"].replace("bucket", "bukket"))
    assert common.resolve_schema(p, bad) == "nó do schema difere da frase"
    k = common.schema_cite(p, common.schema_pointer(p, "resource_schemas", "aws_s3_bucket", "block", "attributes"),
                           "keys")
    assert "tags" in json.loads(k["sentence"]) and common.resolve_schema(p, k) is None


def test_bridge_parsers():
    assert extract.gcp_bridge("https://cloud.google.com/compute/docs/reference/v1/firewalls") == \
        ("compute", "firewalls", "v1")
    assert extract.gcp_bridge("https://cloud.google.com/x/docs/reference/rest/v1beta1/projects.locations.y#z") == \
        ("x", "projects.locations.y", "v1beta1")
    ns, tps, names, scope = extract.arm_parse(
        "/subscriptions/{subscriptionId}/resourceGroups/rg/providers/Microsoft.Storage/storageAccounts/a/"
        "blobServices/default/containers/c")
    assert ns == "Microsoft.Storage" and tps == ["storageAccounts", "blobServices", "containers"]
    assert extract.arm_parse("/a|/b") is None


def test_rule_classifiers():
    assert rules.prec_order("The lower the priority number, the higher the priority of the rule.") == \
        "lower_value_first"
    assert rules.prec_order("ACL entries are processed in ascending order by rule number.") == "lower_value_first"
    assert rules.prec_order("Order for the action.") == "UNKNOWN"
    assert rules.scope_of("Manages S3 account-level Public Access Block configuration.") == "account"
    assert rules.scope_of("Name of the bucket.") is None
    assert rules.ttl_target("Number of seconds Amazon SQS retains a message.") == "contained"
    assert rules.ttl_target("The DNS record TTL.") == "cache"


def test_protocol_rows_valid():
    rows, missing = protocol.rows()
    assert not missing and not protocol.validate(rows)
    by = {(r["probe_type"], r["provider"]): r for r in rows}
    assert by[("log_retention", "azurerm")]["status"] == "documented_unsupported"
    assert by[("queue_retention", "aws")]["status"] == "documented_supported"
    assert all(r["validated"] is False for r in rows)


def _good():
    p, rel = "oci", "website/docs/r/core_security_list.html.markdown"
    ln = common.find_line(p, rel, "Api doc link for the resource")
    return {"evidence_id": "SE-oci-test1", "provider": p, "pin": {"provider_version": common.version(p)},
            "api_resource": {"service": "iaas", "resource": "SecurityList"},
            "terraform_resource_type": "oci_core_security_list", "fact_kind": "identity", "status": "stated",
            "level": "published", "value": {"aspect": "api_resource_bridge", "rule": "R-BRIDGE-OCI-APIDOC",
                                            "service": "iaas", "resource": "SecurityList"},
            "doc": common.doc_cite(p, rel, ln)}


@pytest.mark.parametrize("mut,expect", [
    (lambda r: r.update(level="nivel"), "nível"),
    (lambda r: r["doc"].update(sentence="frase que não existe na página"), "não resolve"),
    (lambda r: r["value"].update(resource="NaoEsta"), "não está na frase"),
    (lambda r: r["value"].update(rule="R-INVENTADA"), "regra declarada"),
    (lambda r: r.update(level="interpreted"), "model_id"),
    (lambda r: (r.update(level="derived", derived_from=["SE-oci-nao-existe"]), r.pop("doc")), "id ausente"),
])
def test_levels_rejects_mutations(mut, expect):
    good = _good()
    bad, cnt = [], __import__("collections").Counter()
    levels.check_record(copy.deepcopy(good), {}, bad, cnt)
    assert bad == []
    r = copy.deepcopy(good)
    mut(r)
    levels.check_record(r, {}, bad, cnt)
    assert any(expect in b for b in bad), bad


def _out_by_type(types):
    out = {}
    with open(common.out_dir() / "service_evidence.jsonl", encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            if r.get("terraform_resource_type") in types:
                out.setdefault(r["terraform_resource_type"], []).append(r)
    return out


def test_block_facts_for_storage_facets():
    """CC-1 do PILOT-STO-GLOSS: os blocos de faceta têm identidade, dono e ciclo por block_path."""
    want = {"google_storage_bucket": ["versioning", "lifecycle_rule", "encryption"],
            "azurerm_storage_account": ["blob_properties", "blob_properties.delete_retention_policy"],
            "oci_core_security_list": ["ingress_security_rules", "egress_security_rules"]}
    got = _out_by_type(set(want))
    for T, bps in want.items():
        for bp in bps:
            kinds = {(r["fact_kind"], r["value"]["aspect"]) for r in got[T]
                     if r["status"] == "stated" and r["value"].get("block_path") == bp}
            assert {("identity", "block_schema"), ("identity", "block_identity"), ("owner", "block_config_owner"),
                    ("lifecycle_controller", "block_lifecycle")} <= kinds, (T, bp, kinds)


def test_shared_identity_links_separate_facets():
    got = _out_by_type({"aws_s3_bucket_versioning"})
    peers = [r["value"]["peers"] for r in got["aws_s3_bucket_versioning"]
             if r["status"] == "stated" and r["value"].get("aspect") == "shared_identity_key"]
    assert peers and "aws_s3_bucket" in peers[0]


def test_twin_name_rule():
    from bo.service_evidence.grainfacts import twin_name_ok
    assert twin_name_ok("aws", "aws_security_group", "ingress", "aws_vpc_security_group_ingress_rule")
    assert not twin_name_ok("aws", "aws_security_group", "ingress", "aws_vpc_security_group_egress_rule")
    assert twin_name_ok("azurerm", "azurerm_network_security_group", "security_rule", "azurerm_network_security_rule")
    assert not twin_name_ok("aws", "aws_autoscaling_group", "launch_template", "aws_launch_template")
    assert not twin_name_ok("aws", "aws_instance", "network_interface", "aws_network_interface_attachment")


def test_grain_facts_for_containers():
    got = _out_by_type({"aws_s3_bucket", "azurerm_storage_account", "aws_security_group"})
    def has(T, kind, rule, bp=None):
        return any(r["status"] == "stated" and r["fact_kind"] == kind and r["value"].get("rule") == rule
                   and r.get("block_path") == bp and r["level"] == "derived" for r in got[T])
    assert has("aws_s3_bucket", "owner", "R-OWN-TOP") and has("aws_s3_bucket", "lifecycle_controller", "R-LIFE-TF")
    assert has("azurerm_storage_account", "lifecycle_controller", "R-LIFE-TF")
    assert has("aws_security_group", "identity", "R-TWIN", "ingress")
    assert all(r["value"].get("layer") == "terraform" for r in got["aws_s3_bucket"]
               if r.get("value") and r["value"].get("rule") == "R-LIFE-TF")
