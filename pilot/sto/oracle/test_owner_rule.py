"""Regra de dono única (DIAG_T3 F6, classe MC-DEC-SCOPE): o dono de uma configuração sai de um fato de dono FORA da
camada Terraform no SERVICE-EVIDENCE; tipo sem esse fato decide UNKNOWN em qualquer fixture, de calibração ou
retida. Casos sintéticos: concessão separada com e sem fato de dono na API."""
import json
import os
from pathlib import Path

import pytest

import sto_oracle as o

SE = Path(os.environ.get("BO_DATA", "/Users/breno/doutorado/brevops-data")) / "SERVICE-EVIDENCE" / "service_evidence.jsonl"


def fx(provider, resources):
    return {"fixture_id": "SYN", "provider": provider, "terraform": {"resource": resources}, "context": {},
            "read": {"completeness": "complete", "not_read": []}}


def _gcs_with_grant():
    return fx("google", {
        "google_storage_bucket": {"b": {"name": "fx-b", "location": "US", "uniform_bucket_level_access": True}},
        "google_storage_bucket_iam_member": {"g": {"bucket": "${google_storage_bucket.b.name}",
                                                   "role": "roles/storage.objectViewer", "member": "allUsers"}}})


def test_owner_rule_is_one_function_over_the_evidence_table():
    assert o.owner_rule("google", "google_storage_bucket_iam_member.g")["class"] == "TERRAFORM_ONLY"
    assert o.owner_rule("google", "google_storage_bucket_iam_binding.g")["class"] == "TERRAFORM_ONLY"
    assert o.owner_rule("google", "google_storage_bucket_acl.g")["class"] == "UNDOCUMENTED"
    assert o.owner_rule("aws", "aws_s3_bucket_versioning.v")["class"] == "API"
    assert o.owner_rule("aws", "aws_s3_bucket.b/grant")["class"] == "TERRAFORM_ONLY"
    # atributo: campo do próprio objeto de API do recurso (dono self na API)
    assert o.owner_rule("google", "google_storage_bucket.b/public_access_prevention")["class"] == "API"
    # caminho fora da tabela nunca vira dono conhecido
    assert o.owner_rule("aws", "aws_s3_bucket.b/nao_existe")["class"] == "NOT_IN_TABLE"


def test_separate_grant_without_api_owner_is_unknown():
    units = o.decompose(_gcs_with_grant())
    assert "setting:access_grant@container:google_storage_bucket.b" not in units
    u = units["setting:access_grant@NO-API-OWNER:google_storage_bucket_iam_member.g"]
    assert {k: u[k] for k in o.NO_API_OWNER_EXPECT} == o.NO_API_OWNER_EXPECT
    assert u["kind"] == "UNKNOWN" and u["owner"] == "UNKNOWN" and u["rules"] == ["DEC-NO-API-OWNER"]


def test_separate_grant_unresolved_stays_unknown():
    f = _gcs_with_grant()
    f["terraform"]["resource"]["google_storage_bucket_iam_member"]["g"]["bucket"] = "${var.bucket_name}"
    u = o.decompose(f)["setting:access_grant@UNRESOLVED:google_storage_bucket_iam_member.g"]
    assert u["kind"] == "UNKNOWN" and u["owner"] == "UNKNOWN"


def test_separate_facet_with_api_owner_stays_facet():
    f = fx("aws", {"aws_s3_bucket": {"b": {"bucket": "fx-b"}},
                   "aws_s3_bucket_versioning": {"b": {"bucket": "${aws_s3_bucket.b.id}",
                                                      "versioning_configuration": [{"status": "Enabled"}]}}})
    u = o.decompose(f)["setting:versioning@container:aws_s3_bucket.b"]
    assert u["kind"] == "FACET" and u["owner"] == "container:aws_s3_bucket.b"


def test_same_type_same_evidence_same_answer_resolved_or_not_in_any_split():
    # a mesma concessão, com nomes diferentes (como uma retida sorteada), dá a mesma resposta
    a = o.decompose(_gcs_with_grant())
    f = _gcs_with_grant()
    f["terraform"]["resource"]["google_storage_bucket_iam_member"] = {
        "zz_q": f["terraform"]["resource"]["google_storage_bucket_iam_member"]["g"]}
    b = o.decompose(f)
    ka = [k for k in a if k.startswith("setting:access_grant@")]
    kb = [k for k in b if k.startswith("setting:access_grant@")]
    assert len(ka) == len(kb) == 1
    assert o.neutral_decomposition(a)[ka[0]] == o.neutral_decomposition(b)[kb[0]]


@pytest.mark.skipif(not SE.is_file(), reason="SERVICE-EVIDENCE ausente")
def test_owner_table_matches_frozen_service_evidence():
    facts = {}
    for line in SE.open(encoding="utf-8"):
        r = json.loads(line)
        if r["fact_kind"] == "owner" and r["terraform_resource_type"] in o.OWNER_TYPES:
            facts.setdefault((r["terraform_resource_type"], r.get("block_path")), []).append(r)
    assert o.owner_table_from_facts(facts) == o.OWNER_EVIDENCE
