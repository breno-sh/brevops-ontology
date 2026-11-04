"""O avaliador reproduz os exemplos documentados de cada provedor (docs fixados do provider Terraform).

Cada teste monta, em sintaxe JSON do Terraform, o exemplo ou a frase da documentação fixada e confere o estado
efetivo. test_rule_evidence_is_in_pinned_docs prova que toda frase citada em RULES está na linha declarada do
arquivo baixado (aws 6.71.0, google 8.9.0, azurerm 5.12.0, oci 9.11.0).
"""
import json
import os
from pathlib import Path

import pytest

import sto_oracle as o

DOCS = Path(os.environ.get("BO_DATA", "/Users/breno/doutorado/brevops-data")) / "downloads"


def fx(provider, resources, *, context=None, timeline=None, read=None, variables=()):
    tf = {"resource": resources}
    if variables:
        tf["variable"] = {v: {"type": "string"} for v in variables}
    return {"fixture_id": "DOC", "provider": provider, "terraform": tf, "context": context or {},
            "read": read or {"completeness": "complete", "not_read": []}, **({"timeline": timeline} if timeline else {})}


def tl(c, T, events):
    return {"container": c, "eval_day": T, "events": events}


# ---------------------------------------------------------------- evidência
def test_rule_evidence_is_in_pinned_docs():
    missing = []
    n = 0
    for rid, r in o.RULES.items():
        assert r["level"] in ("published", "derived", "interpreted"), rid
        if r["level"] == "interpreted" or r["level"] == "derived":
            assert r.get("basis"), f"{rid}: regra {r['level']} sem base declarada"
        if r["level"] == "published":
            assert r["evidence"], f"{rid}: regra publicada sem citação"
        for e in r["evidence"]:
            n += 1
            lines = (DOCS / e["file"]).read_text(encoding="utf-8").split("\n")
            if e["needle"] not in lines[e["line"] - 1]:
                missing.append(f"{rid}: {e['file']}:{e['line']}")
    assert n >= 60
    assert not missing, missing


def test_every_rule_used_is_declared():
    import re
    src = Path(o.__file__).read_text(encoding="utf-8")
    used = set(re.findall(r'"((?:AWS|GCP|AZ|OCI|DEC|WRITE|DELETE|READ|REF)-[A-Z0-9-]+|UNSUPPORTED)"', src))
    assert used <= set(o.RULES), sorted(used - set(o.RULES))


# ---------------------------------------------------------------- AWS
def test_aws_versioning_cannot_return_to_unversioned():
    # s3_bucket_versioning.html.markdown:103-104 — Enabled/Suspended -> Disabled dá erro na API
    r = {"aws_s3_bucket": {"b": {"bucket": "fx-b"}},
         "aws_s3_bucket_versioning": {"b": {"bucket": "${aws_s3_bucket.b.id}", "versioning_configuration": [{"status": "Disabled"}]}}}
    f = fx("aws", r, timeline=tl("aws_s3_bucket.b", 2, [{"day": 0, "op": "set_versioning", "value": "Enabled"},
                                                       {"day": 1, "op": "set_versioning", "value": "Disabled"}]))
    assert o.versioning(f, "aws_s3_bucket.b")["value"] == "INVALID_TRANSITION"
    # 'Disabled' só para criar contêiner não versionado (linha 109)
    f2 = fx("aws", r)
    assert o.versioning(f2, "aws_s3_bucket.b")["value"] == "DISABLED"


def test_aws_inline_versioning_false_after_enabled_is_suspended():
    # s3_bucket.html.markdown:289 — nunca volta a não versionado; pode suspender
    r = {"aws_s3_bucket": {"b": {"bucket": "fx-b", "versioning": [{"enabled": False}]}}}
    f = fx("aws", r, timeline=tl("aws_s3_bucket.b", 2, [{"day": 0, "op": "set_versioning", "value": True},
                                                       {"day": 1, "op": "set_versioning", "value": False}]))
    assert o.versioning(f, "aws_s3_bucket.b")["value"] == "SUSPENDED"


def test_aws_object_lock_enables_versioning_and_forbids_suspend():
    # s3_bucket.html.markdown:154-155
    r = {"aws_s3_bucket": {"b": {"bucket": "fx-b", "object_lock_enabled": True}}}
    assert o.versioning(fx("aws", r), "aws_s3_bucket.b")["value"] == "ENABLED"
    r["aws_s3_bucket_versioning"] = {"b": {"bucket": "${aws_s3_bucket.b.id}", "versioning_configuration": [{"status": "Suspended"}]}}
    f = fx("aws", r, timeline=tl("aws_s3_bucket.b", 1, [{"day": 0, "op": "set_versioning", "value": "Enabled"},
                                                       {"day": 1, "op": "set_versioning", "value": "Suspended"}]))
    assert o.versioning(f, "aws_s3_bucket.b")["value"] == "INVALID_TRANSITION"


def test_aws_public_read_acl_example():
    # s3_bucket_acl.html.markdown "With public-read ACL": propriedade BucketOwnerPreferred, bloqueios desligados,
    # depends_on; "all bucket objects become publicly exposed"
    r = {"aws_s3_bucket": {"example": {"bucket": "my-tf-example-bucket"}},
         "aws_s3_bucket_ownership_controls": {"example": {"bucket": "${aws_s3_bucket.example.id}", "rule": [{"object_ownership": "BucketOwnerPreferred"}]}},
         "aws_s3_bucket_public_access_block": {"example": {"bucket": "${aws_s3_bucket.example.id}", "block_public_acls": False,
                                                           "block_public_policy": False, "ignore_public_acls": False,
                                                           "restrict_public_buckets": False}},
         "aws_s3_bucket_acl": {"example": {"depends_on": ["aws_s3_bucket_ownership_controls.example", "aws_s3_bucket_public_access_block.example"],
                                           "bucket": "${aws_s3_bucket.example.id}", "acl": "public-read"}}}
    f = fx("aws", r, context={"account_public_access_block": {"status": "none_configured"}})
    ax = o.public_access(f, "aws_s3_bucket.example")["axes"]
    assert ax["anonymous_read"] is True and ax["anonymous_list"] is True
    # BucketOwnerEnforced: "ACLs no longer affect permissions"
    r["aws_s3_bucket_ownership_controls"]["example"]["rule"][0]["object_ownership"] = "BucketOwnerEnforced"
    assert o.public_access(f, "aws_s3_bucket.example")["axes"]["anonymous_read"] is False
    # ignore_public_acls da conta: "ignores all public ACLs on buckets in this account"
    r["aws_s3_bucket_ownership_controls"]["example"]["rule"][0]["object_ownership"] = "BucketOwnerPreferred"
    f3 = fx("aws", r, context={"account_public_access_block": {"status": "declared", "ignore_public_acls": True}})
    assert o.public_access(f3, "aws_s3_bucket.example")["axes"]["anonymous_read"] is False


def test_aws_block_public_policy_rejects_put_and_restrict_blocks_existing():
    pol = json.dumps({"Statement": [{"Effect": "Allow", "Principal": "*", "Action": "s3:GetObject", "Resource": "${aws_s3_bucket.b.arn}/*"}]})
    base = {"aws_s3_bucket": {"b": {"bucket": "fx-b"}},
            "aws_s3_bucket_public_access_block": {"b": {"bucket": "${aws_s3_bucket.b.id}", "block_public_policy": True}},
            "aws_s3_bucket_policy": {"b": {"bucket": "${aws_s3_bucket.b.id}", "policy": pol,
                                           "depends_on": ["aws_s3_bucket_public_access_block.b"]}}}
    f = fx("aws", base, context={"account_public_access_block": {"status": "none_configured"}})
    pa = o.public_access(f, "aws_s3_bucket.b")
    assert pa["axes"]["anonymous_read"] is False
    assert [x["what"] for x in pa["apply_rejections"]] == ["policy"]
    # sem ordem: "Enabling this setting does not affect the existing bucket policy" -> depende da ordem
    base["aws_s3_bucket_policy"]["b"].pop("depends_on")
    assert o.public_access(f, "aws_s3_bucket.b")["axes"]["anonymous_read"] == o.Unk("ORDER_DEPENDENT", "")
    # restrict_public_buckets: "only the bucket owner and AWS services can access this bucket if it has a public policy"
    base["aws_s3_bucket_public_access_block"]["b"] = {"bucket": "${aws_s3_bucket.b.id}", "restrict_public_buckets": True}
    assert o.public_access(f, "aws_s3_bucket.b")["axes"]["anonymous_read"] is False


def test_aws_lifecycle_versioned_example_with_tags_and_transitions():
    # s3_bucket_lifecycle_configuration.html.markdown "Creating a Lifecycle Configuration for a bucket with versioning", regra 'log'
    r = {"aws_s3_bucket": {"bucket": {"bucket": "my-bucket"}},
         "aws_s3_bucket_lifecycle_configuration": {"bucket-config": {"bucket": "${aws_s3_bucket.bucket.bucket}", "rule": [{
             "id": "log", "status": "Enabled", "expiration": [{"days": 90}],
             "filter": [{"and": [{"prefix": "log/", "tags": {"rule": "log", "autoclean": "true"}}]}],
             "transition": [{"days": 30, "storage_class": "STANDARD_IA"}, {"days": 60, "storage_class": "GLACIER"}]}]}}}
    ev = [{"day": 0, "op": "put", "key": "log/a", "tags": {"rule": "log", "autoclean": "true"}},
          {"day": 0, "op": "put", "key": "log/b"}, {"day": 0, "op": "put", "key": "other/c", "tags": {"rule": "log", "autoclean": "true"}}]
    s60 = o.simulate(fx("aws", r, timeline=tl("aws_s3_bucket.bucket", 60, ev)))
    assert s60["versions"]["log/a#1"] == {"state": "CURRENT", "since": 0, "tier": "GLACIER"}
    assert "tier" not in s60["versions"]["log/b#1"] and "tier" not in s60["versions"]["other/c#1"]
    s90 = o.simulate(fx("aws", r, timeline=tl("aws_s3_bucket.bucket", 90, ev)))
    assert s90["versions"]["log/a#1"]["state"] == "DELETED"
    assert s90["versions"]["log/b#1"]["state"] == "CURRENT"


def test_aws_expired_object_delete_marker_and_noncurrent_retention():
    # lifecycle_configuration:404 (marcador sem versões não correntes) e 422-423 (retenção e dias não corrente)
    r = {"aws_s3_bucket": {"b": {"bucket": "fx-b"}},
         "aws_s3_bucket_versioning": {"b": {"bucket": "${aws_s3_bucket.b.id}", "versioning_configuration": [{"status": "Enabled"}]}},
         "aws_s3_bucket_lifecycle_configuration": {"b": {"bucket": "${aws_s3_bucket.b.id}", "rule": [
             {"id": "nc", "status": "Enabled", "filter": [{}], "noncurrent_version_expiration": [{"noncurrent_days": 5}]},
             {"id": "dm", "status": "Enabled", "filter": [{}], "expiration": [{"expired_object_delete_marker": True}]}]}}}
    ev = [{"day": 0, "op": "put", "key": "k"}, {"day": 2, "op": "delete", "key": "k"}]
    s = o.simulate(fx("aws", r, timeline=tl("aws_s3_bucket.b", 6, ev)))
    assert s["versions"]["k#1"]["state"] == "NONCURRENT" and s["markers"]["k#2"]["state"] == "CURRENT"
    s = o.simulate(fx("aws", r, timeline=tl("aws_s3_bucket.b", 9, ev)))
    assert s["versions"]["k#1"]["state"] == "DELETED"
    assert s["markers"]["k#2"]["state"] == "DELETED"   # removido depois que não sobrou versão não corrente
    # regra com status Disabled não age (linha 389)
    r["aws_s3_bucket_lifecycle_configuration"]["b"]["rule"][0]["status"] = "Disabled"
    s = o.simulate(fx("aws", r, timeline=tl("aws_s3_bucket.b", 9, ev)))
    assert s["versions"]["k#1"]["state"] == "NONCURRENT"


def test_aws_lifecycle_inline_and_separate_cannot_mix():
    # s3_bucket.html.markdown:98 — lifecycle_rule cannot be mixed with aws_s3_bucket_lifecycle_configuration
    r = {"aws_s3_bucket": {"b": {"bucket": "fx-b", "lifecycle_rule": [{"enabled": True, "expiration": [{"days": 3}]}]}},
         "aws_s3_bucket_lifecycle_configuration": {"b": {"bucket": "${aws_s3_bucket.b.id}", "rule": [
             {"id": "x", "status": "Enabled", "expiration": [{"days": 5}]}]}}}
    assert o.lifecycle_rules(fx("aws", r), "aws_s3_bucket.b") == o.Unk("UNRESOLVED", "")


def test_aws_account_block_scope_is_all_buckets():
    # s3_account_public_access_block.html.markdown:13 — uma configuração por conta, vale para os contêineres dela
    r = {"aws_s3_bucket": {"a": {"bucket": "fx-a"}, "b": {"bucket": "fx-b"}},
         "aws_s3_account_public_access_block": {"this": {"block_public_acls": True}}}
    u = o.decompose(fx("aws", r))["setting:public_access_block@account:context"]
    assert u["effective_scope"] == {"all_in": "account:context", "known": ["container:aws_s3_bucket.a", "container:aws_s3_bucket.b"]}


# ---------------------------------------------------------------- Google
def test_google_lifecycle_example_age_3():
    # storage_bucket.html.markdown "Life cycle settings for storage bucket objects": Delete com age = 3
    r = {"google_storage_bucket": {"auto-expire": {"name": "auto-expiring-bucket", "location": "US", "force_destroy": True,
                                                   "lifecycle_rule": [{"condition": [{"age": 3}], "action": [{"type": "Delete"}]},
                                                                      {"condition": [{"age": 1}], "action": [{"type": "AbortIncompleteMultipartUpload"}]}]}}}
    s = o.simulate(fx("google", r, timeline=tl("google_storage_bucket.auto-expire", 5,
                                               [{"day": 0, "op": "put", "key": "a"}, {"day": 3, "op": "put", "key": "b"}])))
    assert s["versions"]["a#1"]["state"] == "DELETED" and s["versions"]["a#1"]["since"] == 3   # idade mínima: no dia 3
    assert s["versions"]["b#1"]["state"] == "CURRENT"


def test_google_send_age_if_zero_example_only_noncurrent():
    # exemplo com send_age_if_zero = false e days_since_noncurrent_time = 3; versionamento ligado para haver não correntes
    r = {"google_storage_bucket": {"no-age-enabled": {"name": "no-age-enabled-bucket", "location": "US", "versioning": [{"enabled": True}],
                                                      "lifecycle_rule": [{"action": [{"type": "Delete"}],
                                                                          "condition": [{"days_since_noncurrent_time": 3, "send_age_if_zero": False}]}]}}}
    ev = [{"day": 0, "op": "put", "key": "k"}, {"day": 1, "op": "put", "key": "k"}]
    s = o.simulate(fx("google", r, timeline=tl("google_storage_bucket.no-age-enabled", 10, ev)))
    assert s["versions"]["k#1"]["state"] == "DELETED" and s["versions"]["k#1"]["since"] == 4
    assert s["versions"]["k#2"]["state"] == "CURRENT"   # 'Relevant only for versioned objects': a viva fica


def test_google_multiple_conditions_all_must_match():
    # storage_bucket.html.markdown:289 — "an object has to match all of the conditions"
    r = {"google_storage_bucket": {"b": {"name": "fx-b", "location": "US", "lifecycle_rule": [
        {"action": [{"type": "Delete"}], "condition": [{"age": 2, "matches_prefix": ["tmp/"]}]}]}}}
    s = o.simulate(fx("google", r, timeline=tl("google_storage_bucket.b", 5, [{"day": 0, "op": "put", "key": "tmp/x"},
                                                                              {"day": 0, "op": "put", "key": "keep/y"}])))
    assert s["versions"]["tmp/x#1"]["state"] == "DELETED" and s["versions"]["keep/y#1"]["state"] == "CURRENT"


def test_google_public_access_prevention_example():
    # "Enabling public access prevention": public_access_prevention = "enforced"; allUsers = qualquer um na internet
    r = {"google_storage_bucket": {"no-public-access": {"name": "no-public-access-bucket", "location": "US", "force_destroy": True,
                                                        "public_access_prevention": "enforced"}},
         "google_storage_bucket_iam_member": {"m": {"bucket": "${google_storage_bucket.no-public-access.name}",
                                                    "role": "roles/storage.objectViewer", "member": "allUsers"}}}
    c = "google_storage_bucket.no-public-access"
    assert o.public_access(fx("google", r), c)["axes"]["anonymous_read"] is False
    r[c.split(".")[0]]["no-public-access"]["public_access_prevention"] = "inherited"
    assert o.public_access(fx("google", r, context={"org_policy_public_access_prevention": False}), c)["axes"]["anonymous_read"] is True
    assert o.public_access(fx("google", r, context={"org_policy_public_access_prevention": True}), c)["axes"]["anonymous_read"] is False
    assert o.public_access(fx("google", r), c)["axes"]["anonymous_read"] == o.Unk("INCOMPLETE_READ", "")


def test_google_versioning_enabled_true():
    # storage_bucket.html.markdown:333 — "While set to true, versioning is fully enabled"
    r = {"google_storage_bucket": {"b": {"name": "fx-b", "location": "US", "versioning": [{"enabled": True}]}}}
    assert o.versioning(fx("google", r), "google_storage_bucket.b")["value"] == "ENABLED"


# ---------------------------------------------------------------- Azure
def _az_account(extra=None):
    a = {"name": "storageaccountname", "resource_group_name": "${var.rg}", "location": "westeurope", "account_tier": "Standard",
         "account_replication_type": "LRS", "account_kind": "BlobStorage"}
    a.update(extra or {})
    return {"azurerm_storage_account": {"example": a}}


def test_azure_management_policy_example():
    # storage_management_policy.html.markdown "Example Usage": rule1 tem filtro por índice de tag (fora do modelo:
    # UNKNOWN); sem ele, delete_after_days_since_modification_greater_than = 100 só apaga com idade > 100
    pol = {"storage_account_id": "${azurerm_storage_account.example.id}", "rule": [
        {"name": "rule1", "enabled": True,
         "filters": [{"prefix_match": ["container1/prefix1"], "blob_types": ["blockBlob"],
                      "match_blob_index_tag": [{"name": "tag1", "operation": "==", "value": "val1"}]}],
         "actions": [{"base_blob": [{"tier_to_cool_after_days_since_modification_greater_than": 10,
                                     "tier_to_archive_after_days_since_modification_greater_than": 50,
                                     "delete_after_days_since_modification_greater_than": 100}],
                      "snapshot": [{"delete_after_days_since_creation_greater_than": 30}]}]},
        {"name": "rule2", "enabled": False, "filters": [{"prefix_match": ["container2/prefix1", "container2/prefix2"], "blob_types": ["blockBlob"]}],
         "actions": [{"base_blob": [{"delete_after_days_since_modification_greater_than": 101}]}]}]}
    r = dict(_az_account(), azurerm_storage_management_policy={"example": pol},
             azurerm_storage_container={"c1": {"name": "container1", "storage_account_id": "${azurerm_storage_account.example.id}"},
                                        "c2": {"name": "container2", "storage_account_id": "${azurerm_storage_account.example.id}"}})
    ev = [{"day": 0, "op": "put", "key": "prefix1/a"}, {"day": 1, "op": "put", "key": "prefix1/b"}, {"day": 0, "op": "put", "key": "other/c"}]
    f = fx("azurerm", r, timeline=tl("azurerm_storage_container.c1", 101, ev), variables=["rg"])
    assert o.simulate(f) == o.Unk("UNSUPPORTED_BY_ORACLE", "")
    pol["rule"][0]["filters"][0].pop("match_blob_index_tag")
    s = o.simulate(f)
    assert s["versions"]["prefix1/a#1"]["state"] == "DELETED"      # idade 101 > 100
    assert s["versions"]["prefix1/b#1"]["state"] == "CURRENT"      # idade 100, não > 100
    assert s["versions"]["other/c#1"]["state"] == "CURRENT"        # fora do prefixo container1/prefix1
    # rule2 está desligada: nada em container2
    f2 = fx("azurerm", r, timeline=tl("azurerm_storage_container.c2", 200, [{"day": 0, "op": "put", "key": "prefix1/z"}]), variables=["rg"])
    assert o.simulate(f2)["versions"]["prefix1/z#1"]["state"] == "CURRENT"


def test_azure_nested_public_default_false_and_container_levels():
    # storage_account.html.markdown:123 (padrão false) e storage_container.html.markdown:48 (blob, container, private)
    r = dict(_az_account(), azurerm_storage_container={"c": {"name": "c", "storage_account_id": "${azurerm_storage_account.example.id}",
                                                             "container_access_type": "container"}})
    c = "azurerm_storage_container.c"
    assert o.public_access(fx("azurerm", r), c)["axes"]["anonymous_read"] is False
    r["azurerm_storage_account"]["example"]["allow_nested_items_to_be_public"] = True
    ax = o.public_access(fx("azurerm", r), c)["axes"]
    assert ax["anonymous_read"] is True and ax["anonymous_list"] is True
    r["azurerm_storage_container"]["c"]["container_access_type"] = "blob"
    ax = o.public_access(fx("azurerm", r), c)["axes"]
    assert ax["anonymous_read"] is True and ax["anonymous_list"] is False
    r["azurerm_storage_container"]["c"].pop("container_access_type")    # padrão private
    assert o.public_access(fx("azurerm", r), c)["axes"]["anonymous_read"] is False


def test_azure_account_versioning_default_false_and_scope():
    # storage_account.html.markdown:209 — versioning_enabled padrão false; vale para os contêineres da conta
    r = dict(_az_account(), azurerm_storage_container={
        "c1": {"name": "c1", "storage_account_id": "${azurerm_storage_account.example.id}"},
        "c2": {"name": "c2", "storage_account_id": "${azurerm_storage_account.example.id}"}})
    assert o.versioning(fx("azurerm", r), "azurerm_storage_container.c1")["value"] == "DISABLED"
    r["azurerm_storage_account"]["example"]["blob_properties"] = [{"versioning_enabled": True}]
    f = fx("azurerm", r)
    assert o.versioning(f, "azurerm_storage_container.c2")["value"] == "ENABLED"
    u = o.decompose(f)["setting:versioning@namespace:azurerm_storage_account.example"]
    assert u["effective_scope"] == ["container:azurerm_storage_container.c1", "container:azurerm_storage_container.c2"]


# ---------------------------------------------------------------- OCI
def _oci_bucket(extra=None):
    b = {"name": "my-new-bucket1", "namespace": "${var.namespace}", "compartment_id": "${var.compartment_id}"}
    b.update(extra or {})
    return {"oci_objectstorage_bucket": {"b": b}}


def test_oci_access_type_semantics():
    # objectstorage_bucket.html.markdown:57
    c = "oci_objectstorage_bucket.b"
    assert o.public_access(fx("oci", _oci_bucket()), c)["axes"]["anonymous_read"] is False     # NoPublicAccess por padrão
    ax = o.public_access(fx("oci", _oci_bucket({"access_type": "ObjectRead"})), c)["axes"]
    assert ax["anonymous_read"] and ax["anonymous_list"]
    ax = o.public_access(fx("oci", _oci_bucket({"access_type": "ObjectReadWithoutList"})), c)["axes"]
    assert ax["anonymous_read"] and not ax["anonymous_list"]


def test_oci_versioning_create_and_update_values():
    # objectstorage_bucket.html.markdown:76 — Create: Enabled, Disabled; Update: Enabled, Suspended
    c = "oci_objectstorage_bucket.b"
    assert o.versioning(fx("oci", _oci_bucket()), c)["value"] == "DISABLED"
    f = fx("oci", _oci_bucket({"versioning": "Suspended"}))
    assert o.versioning(f, c)["value"] == "INVALID_TRANSITION"      # Suspended não é valor de criação
    f = fx("oci", _oci_bucket({"versioning": "Suspended"}), timeline=tl(c, 1, [{"day": 0, "op": "set_versioning", "value": "Enabled"},
                                                                             {"day": 1, "op": "set_versioning", "value": "Suspended"}]))
    assert o.versioning(f, c)["value"] == "SUSPENDED"
    f = fx("oci", _oci_bucket({"versioning": "Disabled"}), timeline=tl(c, 1, [{"day": 0, "op": "set_versioning", "value": "Enabled"},
                                                                            {"day": 1, "op": "set_versioning", "value": "Disabled"}]))
    assert o.versioning(f, c)["value"] == "INVALID_TRANSITION"      # Disabled não é valor de atualização


def _oci_policy(rule):
    return {"oci_objectstorage_object_lifecycle_policy": {"p": {"bucket": "${oci_objectstorage_bucket.b.name}",
                                                                 "namespace": "${var.namespace}", "rules": [rule]}}}


def test_oci_lifecycle_years_round_up_and_last_modified():
    # objectstorage_object_lifecycle_policy.html.markdown:74-75 — idade pelo Last-Modified; ano = 365.2425 dias, arredondado para cima
    rule = {"name": "r", "action": "DELETE", "is_enabled": True, "time_amount": 1, "time_unit": "YEARS", "target": "objects"}
    r = dict(_oci_bucket(), **_oci_policy(rule))
    ev = [{"day": 0, "op": "put", "key": "a"}, {"day": 1, "op": "put", "key": "b"}]
    s = o.simulate(fx("oci", r, timeline=tl("oci_objectstorage_bucket.b", 366, ev)))
    assert s["versions"]["a#1"]["state"] == "DELETED" and s["versions"]["a#1"]["since"] == 366
    assert s["versions"]["b#1"]["state"] == "CURRENT"     # idade 365 < 366


def test_oci_exclusion_precedence_and_previous_versions():
    # :60 "Exclusion patterns take precedence over inclusion patterns"; :73 alvo previous-object-versions
    rule = {"name": "r", "action": "DELETE", "is_enabled": True, "time_amount": 2, "time_unit": "DAYS", "target": "objects",
            "object_name_filter": [{"inclusion_patterns": ["logs/*"], "exclusion_patterns": ["logs/*.keep"]}]}
    r = dict(_oci_bucket(), **_oci_policy(rule))
    ev = [{"day": 0, "op": "put", "key": "logs/a.txt"}, {"day": 0, "op": "put", "key": "logs/b.keep"}]
    s = o.simulate(fx("oci", r, timeline=tl("oci_objectstorage_bucket.b", 5, ev)))
    assert s["versions"]["logs/a.txt#1"]["state"] == "DELETED" and s["versions"]["logs/b.keep#1"]["state"] == "CURRENT"
    rule2 = {"name": "r", "action": "DELETE", "is_enabled": True, "time_amount": 10, "time_unit": "DAYS", "target": "previous-object-versions"}
    r2 = dict(_oci_bucket({"versioning": "Enabled"}), **_oci_policy(rule2))
    ev2 = [{"day": 0, "op": "put", "key": "k"}, {"day": 9, "op": "put", "key": "k"}]
    s = o.simulate(fx("oci", r2, timeline=tl("oci_objectstorage_bucket.b", 10, ev2)))
    assert s["versions"]["k#1"]["state"] == "DELETED"   # idade pelo Last-Modified (dia 0), não desde que virou anterior (dia 9)


def test_oci_delete_current_in_versioned_bucket_is_unknown():
    # :56 "permanently delete objects from buckets" não trata a versão corrente de contêiner versionado
    rule = {"name": "r", "action": "DELETE", "is_enabled": True, "time_amount": 1, "time_unit": "DAYS", "target": "objects"}
    r = dict(_oci_bucket({"versioning": "Enabled"}), **_oci_policy(rule))
    s = o.simulate(fx("oci", r, timeline=tl("oci_objectstorage_bucket.b", 3, [{"day": 0, "op": "put", "key": "k"}])))
    assert s["unknown_keys"]["k"]["code"] == "MISSING_EVIDENCE" and "k#1" not in s["versions"]


# ---------------------------------------------------------------- julgamento
def test_never_coverable_losses_cannot_be_declared_away():
    src = fx("oci", _oci_bucket({"access_type": "ObjectReadWithoutList"}))
    tgt = fx("oci", _oci_bucket({"access_type": "ObjectRead"}))
    j = o.judge(src, tgt, declared_losses=["PUBLIC_WIDENED"], container_map={"oci_objectstorage_bucket.b": "oci_objectstorage_bucket.b"})
    assert j["verdict"] == "REJECT" and j["code"] == "PUBLIC_WIDENED"


def test_silent_loss_is_rejected_and_declared_loss_accepted():
    src = fx("oci", _oci_bucket({"access_type": "ObjectRead"}))
    tgt = fx("oci", _oci_bucket({"access_type": "ObjectReadWithoutList"}))
    m = {"oci_objectstorage_bucket.b": "oci_objectstorage_bucket.b"}
    assert o.judge(src, tgt, (), m)["code"] == "SILENT_LOSS"
    assert o.judge(src, tgt, ["ACCESS_NARROWED"], m)["verdict"] == "ACCEPT_WITH_DECLARED_LOSS"


@pytest.mark.parametrize("p", ["aws", "google", "azurerm", "oci"])
def test_unknown_never_becomes_default(p):
    # nível que decide e não foi lido: UNKNOWN, nunca o padrão
    c = {"aws": "aws_s3_bucket.b", "google": "google_storage_bucket.b", "azurerm": "azurerm_storage_container.b",
         "oci": "oci_objectstorage_bucket.b"}[p]
    r = {"aws": {"aws_s3_bucket": {"b": {"bucket": "fx-b"}}},
         "google": {"google_storage_bucket": {"b": {"name": "fx-b", "location": "US"}}},
         "azurerm": {"azurerm_storage_container": {"b": {"name": "b", "storage_account_id": "${var.acct}"}}},
         "oci": _oci_bucket()}[p]
    f = fx(p, r, read={"completeness": "partial", "not_read": [{"of": c, "what": "versioning"}]})
    assert o.is_unk(o.versioning(f, c))
