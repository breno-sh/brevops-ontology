"""Regra de dono única (contrato do oráculo 1.4.0, DEC-NO-API-OWNER; DIAG_T3 F6), por casos sintéticos.

Sem fato de dono fora da camada Terraform no SERVICE-EVIDENCE, a configuração é a unidade NO-API-OWNER:<by>, UNKNOWN,
com o pai resolvido ou não pela referência; sem pai resolvido continua UNRESOLVED:<by>. Vale para bloco embutido,
recurso separado e conta. Nada aqui lê fixture retida nem importa o oráculo.
"""
from bo.pilot.sto import lift as L

NO_API = {"kind": "UNKNOWN", "owner": "UNKNOWN", "effective_scope": "UNKNOWN", "lifecycle_controller": "UNKNOWN",
          "missing_evidence": ["owner"]}


def _fx(provider, resources, variables=None):
    tf = {"resource": resources}
    if variables:
        tf["variable"] = variables
    return {"fixture_id": "FX-SYN-OWNER", "provider": provider, "split": "calib", "polarity": "unknown",
            "read": {"completeness": "complete", "not_read": [], "withheld": []}, "context": {}, "terraform": tf}


def _sub(u, keys=NO_API):
    return {k: u.get(k) for k in keys}


def test_owner_rule_classes_from_service_evidence(ev):
    # exemplos que o próprio contrato cita (RULES.json DEC-NO-API-OWNER) e o par API correspondente
    assert ev.owner_rule("google_storage_bucket_iam_member")["class"] == "TERRAFORM_ONLY"
    assert ev.owner_rule("aws_s3_bucket", "grant")["class"] == "TERRAFORM_ONLY"
    assert ev.owner_rule("google_storage_bucket_acl")["class"] == "UNDOCUMENTED"
    assert ev.owner_rule("aws_s3_bucket", "versioning")["class"] == "API"
    assert ev.owner_rule("aws_s3_account_public_access_block")["class"] == "API"       # identidade do objeto remoto
    assert ev.owner_rule("azurerm_storage_management_policy")["class"] == "API"
    # atributo de topo herda o fato do recurso
    assert ev.owner_rule("aws_s3_bucket")["class"] == "API"


def test_separate_grant_without_api_owner_resolved_parent(syn, ev):
    fx = _fx("google", {
        "google_storage_bucket": {"data": {"name": "fx-data", "location": "US", "uniform_bucket_level_access": True}},
        "google_storage_bucket_iam_member": {"g": {"bucket": "${google_storage_bucket.data.name}", "member": "allUsers",
                                                   "role": "roles/storage.objectViewer"}}})
    dec = L.decomposition(L.lift(fx, syn, ev))
    uid = "setting:access_grant@NO-API-OWNER:google_storage_bucket_iam_member.g"
    assert uid in dec, sorted(dec)
    assert _sub(dec[uid]) == NO_API
    assert not any(k.startswith("setting:access_grant@container:") for k in dec)
    assert not any("UNRESOLVED" in k for k in dec)


def test_separate_grant_without_api_owner_unresolved_parent(syn, ev):
    fx = _fx("google", {
        "google_storage_bucket": {"data": {"name": "fx-data", "location": "US"}},
        "google_storage_bucket_iam_member": {"g": {"bucket": "${var.bucket_name}", "member": "allUsers",
                                                   "role": "roles/storage.objectViewer"}}},
        variables={"bucket_name": {"type": "string"}})
    dec = L.decomposition(L.lift(fx, syn, ev))
    uid = "setting:access_grant@UNRESOLVED:google_storage_bucket_iam_member.g"
    assert uid in dec and _sub(dec[uid], ("kind", "owner", "missing_evidence")) == {
        "kind": "UNKNOWN", "owner": "UNKNOWN", "missing_evidence": ["owner"]}
    assert not any("NO-API-OWNER" in k for k in dec)


def test_inline_block_without_api_owner(syn, ev):
    fx = _fx("aws", {"aws_s3_bucket": {"b": {
        "bucket": "fx-b",
        "grant": [{"type": "Group", "uri": "http://acs.amazonaws.com/groups/global/AllUsers", "permissions": ["READ"]}],
        "versioning": [{"enabled": True}]}}})
    dec = L.decomposition(L.lift(fx, syn, ev))
    assert _sub(dec["setting:access_grant@NO-API-OWNER:aws_s3_bucket.b/grant"]) == NO_API
    assert not any(k.startswith("setting:access_grant@container:") for k in dec)
    # o bloco irmão com fato de dono na API continua faceta do contêiner
    v = dec["setting:versioning@container:aws_s3_bucket.b"]
    assert v["kind"] == "FACET" and v["owner"] == "container:aws_s3_bucket.b"
