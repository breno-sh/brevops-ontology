"""Fixtures do bo.schema: pasta de trabalho em $BO_TMP (nunca /tmp) e um schema sintético (provider_a)."""
import copy
import os
import shutil
from pathlib import Path

import pytest

os.environ.setdefault("BO_DATA", "/Users/breno/doutorado/brevops-data")
os.environ.setdefault("BO_TMP", str(Path(os.environ["BO_DATA"]) / "tmp" / "SCHEMALIB"))
os.environ.setdefault("TMPDIR", os.environ["BO_TMP"])
Path(os.environ["BO_TMP"]).mkdir(parents=True, exist_ok=True)

ADDR = "registry.terraform.io/example/provider_a"


def _attr(t, **flags):
    return {"type": t, "description_kind": "plain", **flags}


#: um tipo com tudo o que a biblioteca trata: atributos de topo, os nomes da régua (id, arn, tags_all, region),
#: computed puro, sensitive, deprecated, write_only, nested_type (single e list) e blocos list/set/single/map/group
#: com min_items/max_items, inclusive um bloco sem atributos e um bloco dentro de bloco.
WIDGET = {
    "version": 0,
    "block": {
        "attributes": {
            "id": _attr("string", optional=True, computed=True),
            "arn": _attr("string", computed=True),
            "name": _attr("string", required=True),
            "size_gb": _attr("number", optional=True),
            "tags": _attr(["map", "string"], optional=True),
            "tags_all": _attr(["map", "string"], optional=True, computed=True),
            "region": _attr("string", optional=True, computed=True),
            "status": _attr("string", computed=True),
            "access_ref": _attr("string", optional=True, sensitive=True),
            "legacy_mode": _attr("bool", optional=True, deprecated=True),
            "bootstrap_value": _attr("string", optional=True, write_only=True),
            "endpoint": {"nested_type": {"attributes": {"host": _attr("string", required=True),
                                                        "port": _attr("number", optional=True)},
                                         "nesting_mode": "single"},
                         "optional": True, "description_kind": "plain"},
            "listeners": {"nested_type": {"attributes": {"port": _attr("number", required=True)},
                                          "nesting_mode": "list"},
                          "computed": True, "description_kind": "plain"},
        },
        "block_types": {
            "rule": {
                "nesting_mode": "list", "min_items": 1,
                "block": {
                    "attributes": {"id": _attr("string", optional=True, computed=True),
                                   "enabled": _attr("bool", required=True)},
                    "block_types": {
                        "expiration": {"nesting_mode": "list", "max_items": 1,
                                       "block": {"attributes": {"days": _attr("number", optional=True)}}},
                    },
                },
            },
            "selector": {"nesting_mode": "set",
                         "block": {"attributes": {"key": _attr("string", required=True),
                                                  "values": _attr(["set", "string"], optional=True)},
                                   "block_types": {"match": {"nesting_mode": "single", "block": {
                                       "attributes": {"pattern": _attr("string", optional=True)}}}}}},
            "timeouts": {"nesting_mode": "single",
                         "block": {"attributes": {"create": _attr("string", optional=True)}}},
            "labels": {"nesting_mode": "map", "block": {"attributes": {"text": _attr("string", optional=True)}}},
            "group_opts": {"nesting_mode": "group", "block": {"attributes": {"flag": _attr("bool", optional=True)}}},
            "empty_marker": {"nesting_mode": "single", "max_items": 1, "block": {}},
        },
        "description_kind": "plain",
    },
}

GADGET = {"version": 0, "block": {"attributes": {"id": _attr("string", computed=True),
                                                 "label": _attr("string", required=True)},
                                  "description_kind": "plain"}}


def schema_doc():
    return {"format_version": "1.0",
            "provider_schemas": {ADDR: {"provider": {"version": 0, "block": {"description_kind": "plain"}},
                                        "resource_schemas": {"provider_a_widget": copy.deepcopy(WIDGET),
                                                             "provider_a_gadget": copy.deepcopy(GADGET)},
                                        "data_source_schemas": {"provider_a_gadget": copy.deepcopy(GADGET)}}}}


@pytest.fixture
def work(request):
    d = Path(os.environ["BO_TMP"]) / "pytest" / request.node.name.replace("[", "_").replace("]", "")
    if d.exists():
        shutil.rmtree(d)
    d.mkdir(parents=True)
    return d


@pytest.fixture
def doc():
    return schema_doc()
