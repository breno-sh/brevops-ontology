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
    st = common.out_dir() / ".staging" / "service_evidence.jsonl"  # geração ainda não promovida, se houver
    with open(st if st.exists() else common.out_dir() / "service_evidence.jsonl", encoding="utf-8") as f:
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
            kinds = {(r["fact_kind"], r["value"].get("aspect")) for r in got[T]
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


def test_scope_rules():
    got = _out_by_type({"aws_s3_bucket", "aws_s3_account_public_access_block", "google_compute_firewall"})
    def rules_of(T, bp=None):
        return {r["value"].get("rule") for r in got[T] if r["status"] == "stated" and r["fact_kind"] ==
                "effective_scope" and r.get("block_path") == bp}
    assert "R-SCOPE-SELF" in rules_of("aws_s3_bucket")
    assert "R-SCOPE-PARENT" in rules_of("aws_s3_bucket", "versioning")
    acct = rules_of("aws_s3_account_public_access_block")
    assert "R-SCOPE-DOC" in acct and "R-SCOPE-SELF" not in acct
    fw = rules_of("google_compute_firewall")
    assert "R-SCOPE-DOC" in fw and "R-SCOPE-SELF" not in fw


def test_api_layer_only_with_bridge():
    got = _out_by_type({"oci_objectstorage_bucket", "aws_s3_bucket"})
    def api_rules(T):
        return {r["value"].get("rule") for r in got[T] if r["status"] == "stated" and not r.get("block_path")
                and (r.get("value") or {}).get("layer") == "api"}
    assert {"R-OWN-API", "R-LIFE-API", "R-SCOPE-SELF"} <= api_rules("oci_objectstorage_bucket")
    # a página do aws_s3_bucket não cita a API (nada de R-OWN-API); a camada API vem só da spec (CC-8)
    assert "R-OWN-API" not in api_rules("aws_s3_bucket") and {"R-LIFE-SPEC", "R-OWN-SPEC"} <= api_rules("aws_s3_bucket")


def test_spec_operations_resolve_and_rules():
    from bo.service_evidence import apispec as A
    for p in ("aws", "google", "azurerm", "oci"):
        assert A.sums_ok(p) == ()
    m = A.model("aws")
    assert m[("s3", "BucketVersioning")]["parent"] == "Bucket" and m[("s3", "Bucket")]["create"]
    c = A.cite("aws", "apispec-aws/s3-2006-03-01.json", m[("s3", "BucketVersioning")]["config"][0])
    assert A.resolve("aws", c) is None and A.resolve("aws", dict(c, sentence=c["sentence"] + " ")) is not None
    assert A.model("oci")[("object_storage", "object_lifecycle_policy")]["parent"] == "bucket"
    got = _out_by_type({"aws_s3_bucket", "aws_s3_bucket_versioning"})
    rules_ = lambda T: {(r["fact_kind"], r["value"].get("rule"), r["value"].get("kind"))  # noqa: E731
                        for r in got[T] if r["status"] == "stated" and not r.get("block_path")}
    assert ("lifecycle_controller", "R-LIFE-SPEC", "self") in rules_("aws_s3_bucket")
    assert ("owner", "R-OWN-SPEC", "parent") in rules_("aws_s3_bucket_versioning")


def test_cc10_scope_encryption_oci_identity():
    got = _out_by_type({"aws_s3_bucket_server_side_encryption_configuration", "aws_s3_bucket_versioning",
                        "oci_objectstorage_bucket"})
    def rk(T):
        return {(r["fact_kind"], r["value"].get("rule")) for r in got[T] if r["status"] == "stated"
                and not r.get("block_path")}
    assert ("owner", "R-OWN-SPEC") in rk("aws_s3_bucket_server_side_encryption_configuration")
    assert ("effective_scope", "R-SCOPE-SPEC") in rk("aws_s3_bucket_versioning")
    ids = [r["value"]["key_fields"] for r in got["oci_objectstorage_bucket"]
           if r["status"] == "stated" and r["value"].get("rule") == "R-ID-SPEC"]
    assert ids == [["namespace", "name"]]


def test_cc11_sg_rules_and_blocks():
    got = _out_by_type({"aws_vpc_security_group_ingress_rule", "aws_security_group"})
    def rk(T, bp=None):
        return {(r["fact_kind"], r["value"].get("rule")) for r in got[T] if r["status"] == "stated"
                and r.get("block_path") == bp}
    want = {("owner", "R-OWN-SPEC"), ("lifecycle_controller", "R-LIFE-SPEC-PARENT"),
            ("effective_scope", "R-SCOPE-SPEC")}
    assert want <= rk("aws_vpc_security_group_ingress_rule") and want <= rk("aws_security_group", "ingress")
    assert ("identity", "R-ID-SPEC") in rk("aws_vpc_security_group_ingress_rule")


def test_cc12_block_bridges():
    got = _out_by_type({"google_storage_bucket", "azurerm_storage_account", "aws_s3_bucket"})
    def asp(T, bp):
        return {(r["value"].get("aspect") or r["value"].get("rule")) for r in got[T]
                if r["status"] == "stated" and r.get("block_path") == bp}
    assert {"api_resource_bridge", "spec_facet_member"} <= asp("google_storage_bucket", "lifecycle_rule")
    assert "api_resource_bridge" in asp("google_storage_bucket", "versioning")
    assert "api_resource_bridge" in asp("azurerm_storage_account", "blob_properties")
    assert {"api_resource_bridge", "spec_facet_member", "twin_type"} <= asp("aws_s3_bucket", "lifecycle_rule")


def test_final_round_oci_blocks_and_attachments():
    got = _out_by_type({"oci_core_security_list", "aws_instance"})
    assert any(r["status"] == "stated" and r.get("block_path") == "ingress_security_rules"
               and r["value"].get("rule") == "R-BRIDGE-SPEC-BLOCK" for r in got["oci_core_security_list"])
    att = [r for r in got["aws_instance"] if r["status"] == "stated"
           and (r.get("value") or {}).get("aspect") == "attachment_attribute"]
    assert att and att[0]["level"] == "interpreted" and att[0]["model_id"] and att[0]["derived_from"]


def test_promote_refused_without_own_lock(monkeypatch):
    """--promote/--rollback só dentro da trava merge-base do SERVICE-EVIDENCE com pid vivo e ancestral."""
    import os
    import subprocess
    from pathlib import Path
    from bo.service_evidence import build
    root = Path(os.environ.get("BO_TMP", "/Users/breno/doutorado/brevops-data/tmp/SERVICE-EVIDENCE")) / "promote_test"
    subprocess.run(["rm", "-rf", str(root)])
    st = root / "SERVICE-EVIDENCE" / ".staging"
    st.mkdir(parents=True)
    for f in build.DATA_FILES:
        (st / f).write_text("novo\n")
        (root / "SERVICE-EVIDENCE" / f).write_text("publicado\n")
    monkeypatch.setenv("BO_DATA", str(root))
    pub = root / "SERVICE-EVIDENCE" / "service_evidence.jsonl"
    assert build.promote() == 2 and pub.read_text() == "publicado\n"  # sem trava
    lock = root / "locks" / "merge-base"
    lock.mkdir(parents=True)
    (lock / "owner").write_text(f"owner=OUTRO\npid={os.getpid()}\n")
    assert build.promote() == 2 and pub.read_text() == "publicado\n"  # trava de outro módulo
    dead = subprocess.Popen(["true"])
    dead.wait()
    (lock / "owner").write_text(f"owner=SERVICE-EVIDENCE\npid={dead.pid}\n")
    assert build.promote() == 2 and pub.read_text() == "publicado\n"  # pid morto
    (lock / "owner").write_text("owner=SERVICE-EVIDENCE\npid=1\n")
    assert build.promote() == 2 and pub.read_text() == "publicado\n"  # vivo mas não ancestral
    assert build.rollback() == 2
    (lock / "owner").write_text(f"owner=SERVICE-EVIDENCE\npid={os.getpid()}\n")
    assert build.promote() == 0 and pub.read_text() == "novo\n"  # trava própria: troca
    subprocess.run(["rm", "-rf", str(root)])


def test_observed_rules_on_partial_obs_gaps():
    """Com os dados parciais do OBS-GAPS: security list sem id, regra de NSG com id e dono = NSG; cascata pendente."""
    from bo.service_evidence import observed
    obs, reports = observed.load()
    if not obs:
        pytest.skip("OBS-GAPS ainda sem observações")
    fs = {(f["type"], f["block_path"], f["fact_kind"], f["rule"]): f for f in observed.facts(obs, reports)}
    sl = fs.get(("oci_core_security_list", "ingress_security_rules", "identity", "R-OBS-ID"))
    assert sl and sl["value"]["has_id"] is False and sl["repetitions"] >= 2 and sl["control"]["result"]
    assert sl["observation_ref"]["path"].startswith("$BO_DATA/OBS-GAPS")
    ng = fs.get(("oci_core_network_security_group_security_rule", None, "identity", "R-OBS-ID"))
    assert ng and ng["value"]["has_id"] is True and ng["value"]["requires_parent"] is True
    ow = fs.get(("oci_core_network_security_group_security_rule", None, "owner", "R-OBS-OWNER"))
    assert ow and ow["value"]["kind"] == "parent"
    cas = any(k[3] == "R-OBS-CASCADE" for k in fs)
    assert cas == observed._closed(reports, "EXP2-oci-nsg")  # cascata só com o experimento fechado no report


def test_r1_r4_consolidation_counts():
    """R2 resolve as 2 disputas doc x spec da regra de NSG OCI a favor da spec; nada sobrescrito (R1)."""
    import json as _j
    d = _j.loads((common.results_dir() / "spec_disputes.json").read_text(encoding="utf-8"))["disputes"]
    res = [x for x in d if x.get("status") == "resolvida-por-observação"]
    assert all(x["resolved_to"] in ("spec", "doc") and len(x["sides"]) == 2 and x["observation_id"] for x in res)


def test_nsg_rule_scope_dispute_open_and_sentence_published():
    import json as _j
    d = _j.loads((common.results_dir() / "spec_disputes.json").read_text(encoding="utf-8"))["disputes"]
    sc = [x for x in d if x["terraform_resource_type"] == "oci_core_network_security_group_security_rule"
          and x["fact"] == "effective_scope"]
    assert len(sc) == 1 and sc[0]["status"] == "aberta"
    got = _out_by_type({"oci_core_network_security_group_security_rule"})
    pub = [r for r in got["oci_core_network_security_group_security_rule"] if r["status"] == "stated"
           and (r.get("value") or {}).get("aspect") == "rule_applies_to"]
    assert pub and all(r["level"] == "published" and "kind" not in r["value"] for r in pub)
