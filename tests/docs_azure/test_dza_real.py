"""Fatos reais conhecidos do pin (azurerm 5.12.0): conferidos contra o arquivo gerado e a cópia da doc."""
import json

import pytest

from bo.docs_azure import source as SRC

FACTS = SRC.bo_data() / "DOCS-AZURE" / "docs_facts.jsonl"
TYPES = SRC.bo_data() / "DOCS-AZURE" / "type_subcategory.jsonl"
pytestmark = pytest.mark.skipif(not FACTS.exists(), reason="docs_facts.jsonl ainda não gerado")


def load():
    by = {}
    for ln in open(FACTS, encoding="utf-8"):
        r = json.loads(ln)
        by.setdefault((r["atom_id"], r["fact_kind"], r["status"]), []).append(r)
    return by


def test_storage_account_known_facts():
    by = load()
    sa = "azurerm:azurerm_storage_account:"
    av = by[(sa + "account_kind", "allowed_values", "stated")][0]
    assert av["value"] == ["BlobStorage", "BlockBlobStorage", "FileStorage", "Storage", "StorageV2"]
    assert by[(sa + "account_kind", "default", "stated")][0]["value"] == "StorageV2"
    assert by[(sa + "name", "forces_replacement", "stated")][0]["value"] is True
    rng = by[(sa + "blob_properties.delete_retention_policy.days", "range", "stated")][0]
    assert rng["value"]["min"] == 1 and rng["value"]["max"] == 365


def test_source_line_holds_the_sentence():
    by = load()
    r = by[("azurerm:azurerm_storage_account:account_kind", "default", "stated")][0]
    p = SRC.docs_root() / r["source"]["file"]
    line = p.read_text(encoding="utf-8").splitlines()[r["source"]["line"] - 1]
    assert "Defaults to `StorageV2`" in line and r["source"]["tag"] == SRC.tag()


def test_type_subcategory_and_import():
    recs = {json.loads(x)["resource_type"]: json.loads(x) for x in open(TYPES, encoding="utf-8")}
    sa = recs["azurerm_storage_account"]
    assert sa["subcategory"]["value"] == "Storage"
    assert sa["import"]["value"][0].startswith("/subscriptions/{subscriptionId}/resourceGroups/")
