"""Alegações SINTÉTICAS para testar o caminho inteiro sem depender do PILOT-STO-MAP.

Não são correspondências do estudo: servem para exercitar transporte, inversa, guarda, perda declarada, alcance de
namespace (c3 × c2), lowering, render e julgamento. Formato = linhas SSSOM já decodificadas (C09) + vereditos C21.
"""

from __future__ import annotations

from bo.pilot.sto import claims as CL

NAMES = {"aws": "aws:aws_s3_bucket:bucket", "google": "google:google_storage_bucket:name",
         "azurerm": "azurerm:azurerm_storage_container:name", "oci": "oci:oci_objectstorage_bucket:name"}
CODE = {"aws": "AWS", "google": "GCP", "azurerm": "AZ", "oci": "OCI"}
PAIRS = (("aws", "google"), ("aws", "azurerm"), ("aws", "oci"), ("google", "azurerm"), ("google", "oci"), ("azurerm", "oci"))
VER = {"aws": "aws:aws_s3_bucket_versioning:versioning_configuration.status",
       "google": "google:google_storage_bucket:versioning.enabled",
       "azurerm": "azurerm:azurerm_storage_account:blob_properties.versioning_enabled",
       "oci": "oci:oci_objectstorage_bucket:versioning"}
CONCEPT_NAME = "concept:object_container_name"
CONCEPT_VER = "concept:object_versioning_state"


def row(cid, s, o, rel, fid, fn=None, loss=None, guard=None, sc=None, oc=None, vdr="equal"):
    pred = {"exact": "skos:exactMatch", "close": "skos:closeMatch", "related": "skos:relatedMatch"}[rel]
    return {"subject_id": s, "predicate_id": pred, "object_id": o, "claim_id": cid, "claim_version_id": cid + "@1",
            "semantic_relation": rel, "transport_fidelity": fid,
            "value_domain_relation": {"orientation": "subject_to_object", "relation": vdr},
            "guard": guard or {"all": []}, "translation_fn": fn or {"name": "identity", "params": {}},
            "loss_contract": loss or [], "subject_concept": sc or "bo:UNGLOSSED", "object_concept": oc or "bo:UNGLOSSED",
            "evidence_state": "DOC_SUPPORTED", "proof": {"type": "normalization"}}


def rows(include_versioning=True, verdict="OK"):
    out, ver = [], []
    for a, b in PAIRS:
        cid = f"CLM-SYN-{CODE[a]}{CODE[b]}-NAME"
        out.append(row(cid, NAMES[a], NAMES[b], "exact", "lossless", sc=CONCEPT_NAME, oc=CONCEPT_NAME, vdr="unknown"))
        ver.append({"claim_id": cid, "claim_version_id": cid + "@1", "cycle": 1, "verdict": "OK"})
    if include_versioning:
        e2b = {"name": "enum_to_bool", "params": {"true": ["Enabled"], "false": ["Suspended", "Disabled"]}}
        for b in ("google", "azurerm"):
            cid = f"CLM-SYN-AWS{CODE[b]}-VER"
            loss = [{"kind": "not_expressible", "why": "sintético: Suspended e Disabled viram false"}]
            out.append(row(cid, VER["aws"], VER[b], "close", "declared_loss", fn=e2b, loss=loss, sc=CONCEPT_VER, oc=CONCEPT_VER))
            ver.append({"claim_id": cid, "claim_version_id": cid + "@1", "cycle": 1, "verdict": verdict})
        cid = "CLM-SYN-AWSOCI-VER"
        out.append(row(cid, VER["aws"], VER["oci"], "exact", "lossless", sc=CONCEPT_VER, oc=CONCEPT_VER))
        ver.append({"claim_id": cid, "claim_version_id": cid + "@1", "cycle": 1, "verdict": verdict})
        cid = "CLM-SYN-GCPAZ-VER"
        out.append(row(cid, VER["google"], VER["azurerm"], "exact", "lossless", sc=CONCEPT_VER, oc=CONCEPT_VER))
        ver.append({"claim_id": cid, "claim_version_id": cid + "@1", "cycle": 1, "verdict": verdict})
    return out, ver


def claimset(**kw):
    r, v = rows(**kw)
    return CL.synthetic(r, v, concepts=CL.glossary_anchors())
