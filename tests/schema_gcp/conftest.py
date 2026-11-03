"""Fixtures do bo.schema_gcp: pasta de trabalho em $BO_TMP (nunca /tmp) e um schema sintético com write_only."""
import json
import os
import shutil
import uuid
from pathlib import Path

import pytest

os.environ.setdefault("BO_DATA", "/Users/breno/doutorado/brevops-data")
os.environ.setdefault("BO_TMP", str(Path(os.environ["BO_DATA"]) / "tmp" / "SCHEMA-GCP"))
os.environ.setdefault("TMPDIR", os.environ["BO_TMP"])
Path(os.environ["BO_TMP"]).mkdir(parents=True, exist_ok=True)

ADDR = "registry.terraform.io/hashicorp/google"


def _attr(t, **flags):
    return {"type": t, "description_kind": "plain", **flags}


SCHEMA = {
    "format_version": "1.0",
    "provider_schemas": {ADDR: {"resource_schemas": {
        "google_widget": {"version": 0, "block": {
            "attributes": {
                "id": _attr("string", optional=True, computed=True),
                "name": _attr("string", required=True),
                "secret_wo": _attr("string", optional=True, sensitive=True, write_only=True),
                "secret_wo_version": _attr("number", optional=True),
            },
            "block_types": {"conf": {"nesting_mode": "list", "max_items": 1, "block": {"attributes": {
                "key_wo": _attr("string", optional=True, write_only=True),
                "label": _attr("string", optional=True)}}}},
            "description_kind": "plain"}},
        "google_plain": {"version": 0, "block": {"attributes": {"id": _attr("string", computed=True)},
                                                 "description_kind": "plain"}},
    }}},
}


@pytest.fixture
def work():
    d = Path(os.environ["BO_TMP"]) / "pytest" / uuid.uuid4().hex[:8]
    d.mkdir(parents=True)
    yield d
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def schema_file(work):
    p = work / "schema.json"
    p.write_text(json.dumps(SCHEMA), encoding="utf-8")
    return p
