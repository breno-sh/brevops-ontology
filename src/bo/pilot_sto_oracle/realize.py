"""Realizações sintéticas por provedor (sintaxe JSON do Terraform) usadas pelas fixtures do oráculo STO.

Cada função devolve um pedaço de configuração e o endereço do contêiner. Nomes são sintéticos ("fx-..."), sem
id de conta, projeto, ARN ou recurso real. Variáveis (namespace, compartimento, grupo de recursos) ficam
simbólicas.
"""
from __future__ import annotations

import json

PROVIDERS = ("aws", "google", "azurerm", "oci")
SHORT = {"aws": "AWS", "google": "GCP", "azurerm": "AZ", "oci": "OCI"}
VARS = {"oci": ["namespace", "compartment_id"], "azurerm": ["resource_group_name"]}


def merge(*parts):
    out = {}
    for p in parts:
        for rt, insts in p.items():
            out.setdefault(rt, {}).update(insts)
    return out


def tf(provider, resources, extra_vars=()):
    doc = {"resource": resources}
    vs = sorted(set(VARS.get(provider, []) + list(extra_vars)))
    if vs:
        doc["variable"] = {v: {"type": "string"} for v in vs}
    return doc


# ------------------------------------------------------------------ contêiner com versionamento
def container(p, n, *, versioning=None, aws_form="separate", access=None, account=None, account_attrs=None,
              cname=None, account_ref=None, objlock=False):
    """versioning: None (não declarado) | True | False | valor nativo (AWS separado / OCI).
    access: None | 'read' | 'read_list' | 'none' (realização mínima do eixo público).
    Azure: account = nome do recurso da conta (criada aqui se account_attrs não for None)."""
    if p == "aws":
        b = f"aws_s3_bucket.{n}"
        body = {"bucket": f"fx-{n.replace('_', '-')}"}
        if objlock:
            body["object_lock_enabled"] = True
        r = {"aws_s3_bucket": {n: body}}
        if versioning is not None:
            if aws_form == "inline":
                body["versioning"] = [{"enabled": bool(versioning in (True, "Enabled"))}]
            else:
                st = versioning if isinstance(versioning, str) else ("Enabled" if versioning else "Disabled")
                r["aws_s3_bucket_versioning"] = {n: {"bucket": f"${{{b}.id}}", "versioning_configuration": [{"status": st}]}}
        if access is not None:
            r = merge(r, aws_public(n, access))
        return r, b
    if p == "google":
        b = f"google_storage_bucket.{n}"
        body = {"name": f"fx-{n.replace('_', '-')}", "location": "US", "uniform_bucket_level_access": True,
                "public_access_prevention": "inherited"}
        if versioning is not None:
            body["versioning"] = [{"enabled": bool(versioning)}]
        r = {"google_storage_bucket": {n: body}}
        if access in ("read", "read_list"):
            role = "roles/storage.legacyObjectReader" if access == "read" else "roles/storage.objectViewer"
            r["google_storage_bucket_iam_member"] = {f"{n}_public": {"bucket": f"${{{b}.name}}", "role": role, "member": "allUsers"}}
        return r, b
    if p == "azurerm":
        acct = account or f"{n}_acct"
        c = f"azurerm_storage_container.{n}"
        r = {}
        if account_attrs is not None:
            a = {"name": f"fx{acct.replace('_', '')}"[:24], "resource_group_name": "${var.resource_group_name}",
                 "location": "eastus", "account_tier": "Standard", "account_replication_type": "LRS",
                 "allow_nested_items_to_be_public": False}
            a.update(account_attrs)
            if versioning is not None:
                a["blob_properties"] = [{"versioning_enabled": bool(versioning)}]
            r["azurerm_storage_account"] = {acct: a}
        cbody = {"name": cname or n.replace("_", "-"),
                 "storage_account_id": account_ref or f"${{azurerm_storage_account.{acct}.id}}",
                 "container_access_type": {"read": "blob", "read_list": "container"}.get(access, "private")}
        r["azurerm_storage_container"] = {n: cbody}
        if access in ("read", "read_list") and account_attrs is not None:
            r["azurerm_storage_account"][acct]["allow_nested_items_to_be_public"] = True
        return r, c
    if p == "oci":
        b = f"oci_objectstorage_bucket.{n}"
        body = {"name": f"fx-{n.replace('_', '-')}", "namespace": "${var.namespace}",
                "compartment_id": "${var.compartment_id}"}
        if versioning is not None:
            body["versioning"] = versioning if isinstance(versioning, str) else ("Enabled" if versioning else "Disabled")
        body["access_type"] = {"read": "ObjectReadWithoutList", "read_list": "ObjectRead"}.get(access, "NoPublicAccess")
        return {"oci_objectstorage_bucket": {n: body}}, b
    raise ValueError(p)


def aws_public(n, access, *, pab=None, depends=True, policy_condition=False):
    b = f"aws_s3_bucket.{n}"
    pab = pab or {}
    r = {"aws_s3_bucket_public_access_block": {n: {"bucket": f"${{{b}.id}}",
                                                   "block_public_acls": pab.get("block_public_acls", False),
                                                   "block_public_policy": pab.get("block_public_policy", False),
                                                   "ignore_public_acls": pab.get("ignore_public_acls", False),
                                                   "restrict_public_buckets": pab.get("restrict_public_buckets", False)}}}
    if access in ("read", "read_list"):
        stmts = [{"Sid": "PublicRead", "Effect": "Allow", "Principal": "*", "Action": ["s3:GetObject"],
                  "Resource": f"${{{b}.arn}}/*"}]
        if access == "read_list":
            stmts.append({"Sid": "PublicList", "Effect": "Allow", "Principal": "*", "Action": ["s3:ListBucket"],
                          "Resource": f"${{{b}.arn}}"})
        if policy_condition:
            for s in stmts:
                s["Condition"] = {"Bool": {"aws:SecureTransport": "true"}}
        body = {"bucket": f"${{{b}.id}}", "policy": json.dumps({"Version": "2012-10-17", "Statement": stmts}, sort_keys=True)}
        if depends:
            body["depends_on"] = [f"aws_s3_bucket_public_access_block.{n}"]
        r["aws_s3_bucket_policy"] = {n: body}
    return r


def aws_acl(n, acl, ownership="BucketOwnerPreferred"):
    b = f"aws_s3_bucket.{n}"
    r = {"aws_s3_bucket_acl": {n: {"bucket": f"${{{b}.id}}", "acl": acl,
                                   "depends_on": [f"aws_s3_bucket_public_access_block.{n}"]}}}
    if ownership:
        r["aws_s3_bucket_ownership_controls"] = {n: {"bucket": f"${{{b}.id}}", "rule": [{"object_ownership": ownership}]}}
        r["aws_s3_bucket_acl"][n]["depends_on"].append(f"aws_s3_bucket_ownership_controls.{n}")
    return r


# ------------------------------------------------------------------ ciclo de vida
def expire_current(p, n, eligible, *, prefix=None, enabled=True, acct=None, cname=None):
    """Regra que expira a versão corrente a partir da idade 'eligible' (em dias), na unidade nativa."""
    if p == "aws":
        rule = {"id": "expire", "status": "Enabled" if enabled else "Disabled", "filter": [{"prefix": prefix or ""}],
                "expiration": [{"days": eligible}]}
        return {"aws_s3_bucket_lifecycle_configuration": {n: {"bucket": f"${{aws_s3_bucket.{n}.id}}", "rule": [rule]}}}
    if p == "google":
        cond = {"age": eligible, "with_state": "LIVE"}
        if prefix:
            cond["matches_prefix"] = [prefix]
        return {"_inline_google_lifecycle": {n: [{"action": [{"type": "Delete"}], "condition": [cond]}]}}
    if p == "azurerm":
        f = {"blob_types": ["blockBlob"]}
        if prefix is not None:
            f["prefix_match"] = [f"{cname}/{prefix}"]
        rule = {"name": "expire", "enabled": enabled, "filters": [f],
                "actions": [{"base_blob": [{"delete_after_days_since_modification_greater_than": eligible - 1}]}]}
        return {"azurerm_storage_management_policy": {f"{acct}_policy": {"storage_account_id": f"${{azurerm_storage_account.{acct}.id}}", "rule": [rule]}}}
    if p == "oci":
        rule = {"name": "expire", "action": "DELETE", "is_enabled": enabled, "time_amount": eligible, "time_unit": "DAYS",
                "target": "objects"}
        if prefix:
            rule["object_name_filter"] = [{"inclusion_prefixes": [prefix]}]
        return {"oci_objectstorage_object_lifecycle_policy": {n: {"bucket": f"${{oci_objectstorage_bucket.{n}.name}}",
                                                                  "namespace": "${var.namespace}", "rules": [rule]}}}
    raise ValueError(p)


def noncurrent_rule(p, n, eligible, *, acct=None):
    """Regra de exclusão de versão não corrente com idade mínima 'eligible' no RELÓGIO NATIVO do provedor
    (aws/google: desde que virou não corrente; azurerm/oci: desde a criação da versão)."""
    if p == "aws":
        rule = {"id": "noncurrent", "status": "Enabled", "filter": [{"prefix": ""}],
                "noncurrent_version_expiration": [{"noncurrent_days": eligible}]}
        return {"aws_s3_bucket_lifecycle_configuration": {n: {"bucket": f"${{aws_s3_bucket.{n}.id}}", "rule": [rule]}}}
    if p == "google":
        return {"_inline_google_lifecycle": {n: [{"action": [{"type": "Delete"}],
                                                   "condition": [{"days_since_noncurrent_time": eligible, "with_state": "ARCHIVED"}]}]}}
    if p == "azurerm":
        rule = {"name": "noncurrent", "enabled": True, "filters": [{"blob_types": ["blockBlob"]}],
                "actions": [{"version": [{"delete_after_days_since_creation": eligible - 1}]}]}
        return {"azurerm_storage_management_policy": {f"{acct}_policy": {"storage_account_id": f"${{azurerm_storage_account.{acct}.id}}", "rule": [rule]}}}
    if p == "oci":
        rule = {"name": "noncurrent", "action": "DELETE", "is_enabled": True, "time_amount": eligible, "time_unit": "DAYS",
                "target": "previous-object-versions"}
        return {"oci_objectstorage_object_lifecycle_policy": {n: {"bucket": f"${{oci_objectstorage_bucket.{n}.name}}",
                                                                  "namespace": "${var.namespace}", "rules": [rule]}}}
    raise ValueError(p)


def finalize(p, resources):
    """Embute as regras de ciclo de vida do Google no bloco do contêiner."""
    inl = resources.pop("_inline_google_lifecycle", None)
    if inl:
        for n, rules in inl.items():
            resources["google_storage_bucket"][n].setdefault("lifecycle_rule", []).extend(rules)
    return resources
