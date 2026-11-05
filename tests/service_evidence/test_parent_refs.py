"""Rodada v4-r2 (DIAG_T3 F1/F2 + GRAIN 0.2.4, T03): o campo que aponta para o conjunto-pai em todo tipo de regra
ou configuração separada das fatias NET e STO tem `reference_target` resolvido, com evidência fixada; sem fonte, o
campo fica UNKNOWN (nenhum alvo inventado).

O esperado aqui é o conhecimento do teste (fonte lida à mão na página e na spec do pin), não a saída do módulo.
"""

import json

import pytest

from bo.service_evidence import common

# (provedor, tipo, campo do pai) -> tipo-alvo esperado; None = sem fonte, tem de ficar UNKNOWN
EXPECTED = {
    # NET: regras separadas
    ("aws", "aws_security_group_rule", "security_group_id"): "aws_security_group",
    ("aws", "aws_vpc_security_group_ingress_rule", "security_group_id"): "aws_security_group",
    ("aws", "aws_vpc_security_group_egress_rule", "security_group_id"): "aws_security_group",
    ("google", "google_compute_firewall", "network"): "google_compute_network",
    ("azurerm", "azurerm_network_security_rule", "network_security_group_name"): "azurerm_network_security_group",
    ("oci", "oci_core_network_security_group_security_rule", "network_security_group_id"):
        "oci_core_network_security_group",
    # STO: configurações e políticas separadas do contêiner (ou da conta)
    ("aws", "aws_s3_bucket_versioning", "bucket"): "aws_s3_bucket",
    ("aws", "aws_s3_bucket_lifecycle_configuration", "bucket"): "aws_s3_bucket",
    ("aws", "aws_s3_bucket_server_side_encryption_configuration", "bucket"): "aws_s3_bucket",
    ("aws", "aws_s3_bucket_public_access_block", "bucket"): "aws_s3_bucket",
    ("aws", "aws_s3_bucket_acl", "bucket"): "aws_s3_bucket",
    ("aws", "aws_s3_bucket_policy", "bucket"): "aws_s3_bucket",
    ("aws", "aws_s3_bucket_ownership_controls", "bucket"): "aws_s3_bucket",
    ("aws", "aws_s3_account_public_access_block", "account_id"): None,
    ("google", "google_storage_bucket_acl", "bucket"): "google_storage_bucket",
    ("google", "google_storage_bucket_access_control", "bucket"): "google_storage_bucket",
    ("google", "google_storage_bucket_iam_policy", "bucket"): "google_storage_bucket",
    ("google", "google_storage_bucket_iam_binding", "bucket"): "google_storage_bucket",
    ("google", "google_storage_bucket_iam_member", "bucket"): "google_storage_bucket",
    ("azurerm", "azurerm_storage_management_policy", "storage_account_id"): "azurerm_storage_account",
    ("azurerm", "azurerm_storage_account_customer_managed_key", "storage_account_id"): "azurerm_storage_account",
    ("azurerm", "azurerm_storage_encryption_scope", "storage_account_id"): "azurerm_storage_account",
    ("oci", "oci_objectstorage_object_lifecycle_policy", "bucket"): "oci_objectstorage_bucket",
    ("oci", "oci_objectstorage_namespace_metadata", "namespace"): None,
}


def _records():
    st = common.out_dir() / ".staging" / "service_evidence.jsonl"  # geração ainda não promovida, se houver
    path = st if st.exists() else common.out_dir() / "service_evidence.jsonl"
    types = {t for _p, t, _a in EXPECTED}
    out, ids = {}, {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            ids[r["evidence_id"]] = r
            if r.get("terraform_resource_type") in types:
                out.setdefault(r["terraform_resource_type"], []).append(r)
    return out, ids


def _targets(recs, attr):
    return [r for r in recs if r["status"] == "stated" and not r.get("block_path")
            and (r.get("value") or {}).get("aspect") == "reference_target"
            and r["value"].get("attribute") == attr]


def _grounded(r, ids, seen=None):
    """Toda cadeia derivada termina em fato PUBLICADO com citação literal (doc ou citação da fonte fixada)."""
    seen = seen or set()
    if r["evidence_id"] in seen:
        return False
    seen.add(r["evidence_id"])
    if r["level"] == "published":
        return bool(r.get("doc") or (r.get("citation") or {}).get("sentence"))
    if r["level"] != "derived":
        return False
    return any(_grounded(ids[d], ids, seen) for d in r.get("derived_from") or [] if d in ids)


@pytest.mark.parametrize("key", sorted(EXPECTED, key=str))
def test_parent_field_has_reference_target(key):
    p, T, attr = key
    out, ids = _records()
    tg = _targets(out.get(T, []), attr)
    want = EXPECTED[key]
    if want is None:
        assert not [r for r in tg if r["value"].get("resolved")], f"{T}.{attr}: alvo sem fonte (tem de ficar UNKNOWN)"
        return
    res = [r for r in tg if r["value"].get("resolved")]
    assert res, f"{T}.{attr}: sem reference_target resolvido"
    assert {r["value"]["resolved"] for r in res} == {want}, [r["value"] for r in res]
    for r in res:
        assert r["level"] in ("published", "derived") and r["provider"] == p
        assert _grounded(r, ids), f"{T}.{attr}: cadeia sem fato publicado"


def test_parent_refs_report_lists_every_checked_type():
    rep = json.loads((common.results_dir() / "parent_refs.json").read_text(encoding="utf-8"))
    rows = {(x["provider"], x["terraform_resource_type"], x["attribute"]): x for x in rep["checked"]}
    assert set(EXPECTED) <= set(rows)
    for k, want in EXPECTED.items():
        x = rows[k]
        if want is None:
            assert x["status"] == "UNKNOWN" and x["reason"]
        else:
            assert x["target"] == want and x["status"] in ("já tinha", "publicado") and x["level"]
    n = rep["totals"]
    assert n["checked"] == len(rows) and n["unknown"] == sum(1 for x in rows.values() if x["status"] == "UNKNOWN")


def test_grain_decides_component_for_the_separate_aws_rule():
    """Fecha o F1 na camada de esquema: com o alvo tipado do campo do pai, o GRAIN (T03) dá COMPONENT do grupo."""
    from bo.grain import realdata as RD
    st = common.out_dir() / ".staging" / "service_evidence.jsonl"
    recs = RD.load_evidence(st if st.exists() else None)
    rep = RD.run({"aws": ["aws_security_group", "aws_security_group_rule"]}, records=recs)
    d = rep["providers"]["aws"]["_res"].decisions["aws_security_group_rule"]
    assert d.grain == "COMPONENT" and d.parent == "aws_security_group", (d.grain, d.rule, d.missing)
