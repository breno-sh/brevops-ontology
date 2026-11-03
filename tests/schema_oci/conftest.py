"""Fixtures do SCHEMA-OCI: temporário em $BO_TMP (nunca /tmp) e um schema sintético mínimo do oci."""
import os
from pathlib import Path

import pytest

os.environ.setdefault("BO_DATA", "/Users/breno/doutorado/brevops-data")
os.environ.setdefault("BO_TMP", str(Path(os.environ["BO_DATA"]) / "tmp" / "SCHEMA-OCI"))
os.environ.setdefault("TMPDIR", os.environ["BO_TMP"])
Path(os.environ["BO_TMP"]).mkdir(parents=True, exist_ok=True)


def _attr(t, **flags):
    return {"type": t, "description_kind": "plain", **flags}


def schema_doc(write_only_flags=None):
    """Documento 'providers schema -json' com um tipo oci e um bloco aninhado."""
    wo = write_only_flags or {}
    return {
        "format_version": "1.0",
        "provider_schemas": {
            "registry.terraform.io/oracle/oci": {
                "provider": {"version": 0, "block": {}},
                "resource_schemas": {
                    "oci_exemplo_bucket": {"version": 0, "block": {
                        "attributes": {
                            "id": _attr("string", optional=True, computed=True),
                            "name": _attr("string", required=True),
                            "segredo": _attr("string", optional=True, sensitive=True, **wo.get("segredo", {})),
                        },
                        "block_types": {
                            "regra": {"nesting_mode": "list", "max_items": 2, "block": {
                                "attributes": {"dias": _attr("number", optional=True, **wo.get("regra.dias", {}))}}},
                        },
                    }},
                },
                "data_source_schemas": {"oci_exemplo_buckets": {"version": 0, "block": {}}},
            }
        },
    }


@pytest.fixture
def work(request):
    import shutil
    d = Path(os.environ["BO_TMP"]) / "pytest" / request.node.name
    if d.exists():
        shutil.rmtree(d)
    d.mkdir(parents=True)
    yield d
    shutil.rmtree(d, ignore_errors=True)
