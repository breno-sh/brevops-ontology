"""Controle positivo do caminho de lowering: alegações e fixtures SINTÉTICAS (não são do estudo).

Com o mapeamento real quase tudo pode ficar bloqueado; os gates de render (no_silent_insert, tf_validate) não podem
passar por vacuidade. O canário traduz, nas 12 direções, um contêiner mínimo (nome + versionamento) com alegações
sintéticas de nome e de versionamento e entrega planos para os quatro renderizadores. Tudo é inventado: nomes
"bo-canary-*", nenhum dado real. As saídas do canário nunca entram em controls.json nem em oracle_calib.json.
"""

from __future__ import annotations

from . import claims as CL
from . import common as C

NAMES = {"aws": "aws:aws_s3_bucket:bucket", "google": "google:google_storage_bucket:name",
         "azurerm": "azurerm:azurerm_storage_container:name", "oci": "oci:oci_objectstorage_bucket:name"}
VER = {"aws": "aws:aws_s3_bucket_versioning:versioning_configuration.status",
       "google": "google:google_storage_bucket:versioning.enabled",
       "azurerm": "azurerm:azurerm_storage_account:blob_properties.versioning_enabled",
       "oci": "oci:oci_objectstorage_bucket:versioning"}
PAIRS = (("aws", "google"), ("aws", "azurerm"), ("aws", "oci"), ("google", "azurerm"), ("google", "oci"), ("azurerm", "oci"))
E2B = {"name": "enum_to_bool", "params": {"true": ["Enabled"], "false": ["Suspended", "Disabled"]}}
B2E = {"name": "bool_to_enum", "params": {"true": "Enabled", "false": "Suspended"}}
VER_FN = {("aws", "google"): E2B, ("aws", "azurerm"): E2B, ("aws", "oci"): {"name": "identity", "params": {}},
          ("google", "azurerm"): {"name": "identity", "params": {}}, ("google", "oci"): B2E, ("azurerm", "oci"): B2E}
CONCEPT_NAME = "concept:object_container_name"
CONCEPT_VER = "concept:object_versioning_state"


def _row(cid, s, o, rel, fid, fn, loss, sc, oc, vdr):
    pred = {"exact": "skos:exactMatch", "close": "skos:closeMatch"}[rel]
    return {"subject_id": s, "predicate_id": pred, "object_id": o, "claim_id": cid, "claim_version_id": cid + "@1",
            "semantic_relation": rel, "transport_fidelity": fid,
            "value_domain_relation": {"orientation": "subject_to_object", "relation": vdr}, "guard": {"all": []},
            "translation_fn": fn, "loss_contract": loss, "subject_concept": sc, "object_concept": oc,
            "evidence_state": "DOC_SUPPORTED", "proof": {"type": "normalization", "synthetic": True}}


def rows(verdict: str = "OK") -> tuple[list, list]:
    out, ver = [], []
    for a, b in PAIRS:
        code = C.pair_key(a, b)
        cid = f"CLM-CANARY-{code}-NAME"
        out.append(_row(cid, NAMES[a], NAMES[b], "exact", "lossless", {"name": "identity", "params": {}}, [],
                        CONCEPT_NAME, CONCEPT_NAME, "unknown"))
        ver.append({"claim_id": cid, "claim_version_id": cid + "@1", "cycle": 1, "verdict": "OK"})
        cid = f"CLM-CANARY-{code}-VER"
        fn = VER_FN[(a, b)]
        lossy = fn["name"] != "identity"
        loss = [{"kind": "not_expressible", "why": "sintético: suspenso e nunca ligado não se distinguem"}] if lossy else []
        out.append(_row(cid, VER[a], VER[b], "close" if lossy else "exact", "declared_loss" if lossy else "lossless",
                        fn, loss, CONCEPT_VER, CONCEPT_VER, "equal"))
        ver.append({"claim_id": cid, "claim_version_id": cid + "@1", "cycle": 1, "verdict": verdict})
    return out, ver


def claimset() -> CL.ClaimSet:
    r, v = rows()
    return CL.synthetic(r, v, concepts={**{a: CONCEPT_NAME for a in NAMES.values()}, **{a: CONCEPT_VER for a in VER.values()}})


def source(provider: str) -> dict:
    """Contêiner mínimo com versionamento ligado, por provedor (só atributos com alegação sintética)."""
    if provider == "aws":
        res = {"aws_s3_bucket": {"c": {"bucket": "bo-canary-a"}},
               "aws_s3_bucket_versioning": {"c": {"bucket": "${aws_s3_bucket.c.id}",
                                                  "versioning_configuration": [{"status": "Enabled"}]}}}
    elif provider == "google":
        res = {"google_storage_bucket": {"c": {"name": "bo-canary-g", "versioning": [{"enabled": True}]}}}
    elif provider == "azurerm":
        res = {"azurerm_storage_account": {"a": {"blob_properties": [{"versioning_enabled": True}]}},
               "azurerm_storage_container": {"c": {"name": "bo-canary-z", "storage_account_id": "${azurerm_storage_account.a.id}"}}}
    else:
        res = {"oci_objectstorage_bucket": {"c": {"name": "bo-canary-o", "versioning": "Enabled"}}}
    return {"schema": "bo.pilot.sto.fixture/1", "fixture_id": f"CANARY-{C.PAIR_CODE[provider]}", "provider": provider,
            "provider_version": {"aws": "6.71.0", "google": "8.9.0", "azurerm": "5.12.0", "oci": "9.11.0"}[provider],
            "context": {}, "read": {"completeness": "complete", "not_read": [], "withheld": []}, "summary": "canário",
            "terraform": {"resource": res}}


def entries() -> list[dict]:
    out = []
    for d in C.DIRECTIONS:
        a, b = d.split("->")
        out.append({"entry_id": f"CANARY-{C.PAIR_CODE[a]}-{C.PAIR_CODE[b]}", "direction": d, "family": "CANARY",
                    "variant": "canary", "source": source(a), "target": {"context": {}}})
    return out
