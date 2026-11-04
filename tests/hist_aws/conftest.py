"""Fixtures do HIST-AWS: temporário em $BO_TMP (nunca /tmp) e um schema aws sintético pequeno."""
import gzip
import json
import os
import shutil
from pathlib import Path

import pytest

os.environ.setdefault("BO_DATA", "/Users/breno/doutorado/brevops-data")
os.environ.setdefault("BO_TMP", str(Path(os.environ["BO_DATA"]) / "tmp" / "HIST-AWS"))
os.environ.setdefault("TMPDIR", os.environ["BO_TMP"])
Path(os.environ["BO_TMP"]).mkdir(parents=True, exist_ok=True)

ADDR = "registry.terraform.io/hashicorp/aws"


def _attr(t, **flags):
    return {"type": t, "description_kind": "plain", **flags}


#: dois tipos; write_only no topo e dentro de bloco; bloco list com bloco single dentro
SCHEMA = {
    "format_version": "1.0",
    "provider_schemas": {ADDR: {
        "provider": {"version": 0, "block": {}},
        "resource_schemas": {
            "aws_exemplo_segredo": {"version": 0, "block": {
                "attributes": {
                    "id": _attr("string", optional=True, computed=True),
                    "name": _attr("string", required=True),
                    "value_wo": _attr("string", optional=True, sensitive=True, write_only=True),
                },
                "block_types": {
                    "config": {"nesting_mode": "list", "max_items": 1, "block": {
                        "attributes": {"token_wo": _attr("string", optional=True, write_only=True),
                                       "mode": _attr("string", optional=True)},
                        "block_types": {"inner": {"nesting_mode": "single", "block": {
                            "attributes": {"n": _attr("number", required=True)}}}},
                    }},
                },
            }},
            "aws_exemplo_simples": {"version": 0, "block": {
                "attributes": {"arn": _attr("string", computed=True),
                               "tags": _attr(["map", "string"], optional=True)},
            }},
        },
        "data_source_schemas": {"aws_exemplo_segredo": {"version": 0, "block": {}}},
    }},
}


def write_schema_gz(p: Path, doc: dict) -> bytes:
    raw = json.dumps(doc).encode()
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "wb") as f, gzip.GzipFile(filename="schema.json", mode="wb", fileobj=f, mtime=0) as g:
        g.write(raw)
    return raw


@pytest.fixture
def work(request):
    d = Path(os.environ["BO_TMP"]) / "pytest" / request.node.name
    if d.exists():
        shutil.rmtree(d)
    d.mkdir(parents=True)
    yield d
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def schema_gz(work):
    p = work / "schema.json.gz"
    write_schema_gz(p, SCHEMA)
    return p


@pytest.fixture
def schema_doc():
    return json.loads(json.dumps(SCHEMA))
