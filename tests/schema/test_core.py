"""bo.schema.core: átomos (C01) e tipos (C02) do schema sintético, contas feitas à mão."""
import gzip
import json
from pathlib import Path

import pytest

from bo.contracts import validate as V
from bo.schema import core

from conftest import ADDR, schema_doc

REPO = Path(__file__).resolve().parents[2]


def widget():
    ps = core.providers(schema_doc())["provider_a"]
    return core.type_schema("provider_a", "1.0.0", "provider_a_widget", ps["resource_schemas"]["provider_a_widget"]["block"])


def by_path(ts):
    return {a["path"]: a for a in ts.atoms}


def test_short_names():
    assert core.short_name("registry.terraform.io/hashicorp/aws") == "aws"
    assert core.short_name("registry.terraform.io/oracle/oci") == "oci"
    assert core.short_name(ADDR) == "provider_a"


def test_atom_set_and_order():
    ts = widget()
    paths = [a["path"] for a in ts.atoms]
    # pré-ordem: atributos do bloco (nomes ordenados), depois cada bloco (nomes ordenados) e o que há dentro
    assert paths == [
        "access_ref", "arn", "bootstrap_value", "endpoint", "id", "legacy_mode", "listeners", "name", "region",
        "size_gb", "status", "tags", "tags_all",
        "group_opts.flag", "labels.text",
        "rule.enabled", "rule.id", "rule.expiration.days",
        "selector.key", "selector.values", "selector.match.pattern", "timeouts.create",
    ]
    assert [b.path for b in ts.blocks] == [("empty_marker",), ("group_opts",), ("labels",), ("rule",),
                                           ("rule", "expiration"), ("selector",), ("selector", "match"),
                                           ("timeouts",)]


def test_nested_atom_block_path():
    a = by_path(widget())["rule.expiration.days"]
    assert a == {
        "atom_id": "provider_a:provider_a_widget:rule.expiration.days", "provider": "provider_a",
        "provider_version": "1.0.0", "resource_type": "provider_a_widget", "path": "rule.expiration.days",
        "block_path": [{"block": "rule", "nesting_mode": "list", "min_items": 1},
                       {"block": "expiration", "nesting_mode": "list", "max_items": 1}],
        "tf_type": "number", "nesting": "list", "required": False, "optional": True, "computed": False,
        "sensitive": False, "deprecated": False, "configurable": True,
    }


def test_flags_are_raw_schema_flags():
    a = by_path(widget())
    assert (a["id"]["optional"], a["id"]["computed"], a["id"]["configurable"]) == (True, True, True)
    assert (a["arn"]["optional"], a["arn"]["computed"], a["arn"]["configurable"]) == (False, True, False)
    assert a["name"]["required"] and not a["name"]["computed"]
    assert a["access_ref"]["sensitive"] and a["legacy_mode"]["deprecated"]
    assert a["group_opts.flag"]["nesting"] == "group" and a["labels.text"]["nesting"] == "map"
    assert a["selector.key"]["nesting"] == "set" and a["timeouts.create"]["nesting"] == "single"
    assert a["name"]["nesting"] == "none" and a["name"]["block_path"] == []
    # nesting é o modo do ÚLTIMO bloco (set -> single), não do primeiro
    assert a["selector.match.pattern"]["nesting"] == "single"
    assert [b["nesting_mode"] for b in a["selector.match.pattern"]["block_path"]] == ["set", "single"]


def test_nested_type_is_one_atom_with_cty_type():
    a = by_path(widget())
    assert a["endpoint"]["tf_type"] == ["object", {"host": "string", "port": "number"}]
    assert a["listeners"]["tf_type"] == ["list", ["object", {"port": "number"}]]
    assert "endpoint.host" not in a and "listeners.port" not in a
    assert core.nested_type_to_cty({"attributes": {"x": {"type": "bool"}}, "nesting_mode": "set"}) == \
        ["set", ["object", {"x": "bool"}]]
    with pytest.raises(core.SchemaError):
        core.nested_type_to_cty({"attributes": {}, "nesting_mode": "tuple"})


def test_type_record_counts_by_hand():
    ts = widget()
    t = core.type_record(ts)
    assert t["type_id"] == "provider_a:provider_a_widget"
    assert t["counts"] == {"attributes": 22, "blocks": 8, "required": 3, "optional": 16, "computed": 7,
                           "configurable": 19, "sensitive": 1, "deprecated": 1}
    assert t["max_depth"] == 2
    assert t["block_sha256"] == core.canonical_sha256(ts.block)


def test_block_sha256_ignores_key_order():
    b1 = {"attributes": {"a": {"type": "string", "optional": True}, "b": {"type": "number", "required": True}}}
    b2 = {"attributes": {"b": {"required": True, "type": "number"}, "a": {"optional": True, "type": "string"}}}
    assert core.canonical_sha256(b1) == core.canonical_sha256(b2)
    b3 = {"attributes": {"a": {"type": "string", "optional": True}, "b": {"type": "number", "optional": True}}}
    assert core.canonical_sha256(b1) != core.canonical_sha256(b3)


def test_max_depth_zero_without_blocks():
    ps = core.providers(schema_doc())["provider_a"]
    ts = core.type_schema("provider_a", "1.0.0", "provider_a_gadget", ps["resource_schemas"]["provider_a_gadget"]["block"])
    assert core.type_record(ts)["max_depth"] == 0 and core.type_record(ts)["counts"]["blocks"] == 0


def test_only_resource_schemas():
    ps = core.providers(schema_doc())["provider_a"]
    assert [t.resource_type for t in core.iter_types(ps, "provider_a", "1.0.0")] == \
        ["provider_a_gadget", "provider_a_widget"]


@pytest.mark.parametrize("flags", [{"required": True, "optional": True}, {"required": True, "computed": True}])
def test_contradictory_flags_rejected(flags):
    with pytest.raises(core.SchemaError):
        core.type_schema("provider_a", "1.0.0", "provider_a_x", {"attributes": {"v": {"type": "string", **flags}}})


def test_unknown_nesting_mode_rejected():
    with pytest.raises(core.SchemaError):
        core.type_schema("provider_a", "1.0.0", "provider_a_x",
                         {"block_types": {"b": {"nesting_mode": "tuple", "block": {}}}})


def test_attribute_without_type_rejected():
    with pytest.raises(core.SchemaError):
        core.type_schema("provider_a", "1.0.0", "provider_a_x", {"attributes": {"v": {"optional": True}}})


def test_load_json_and_gz_and_format_version(work):
    d = schema_doc()
    (work / "s.json").write_text(json.dumps(d), encoding="utf-8")
    with gzip.open(work / "s.json.gz", "wb") as f:
        f.write(json.dumps(d).encode())
    assert core.load(work / "s.json") == core.load(work / "s.json.gz") == d
    d["format_version"] = "2.0"
    (work / "bad.json").write_text(json.dumps(d), encoding="utf-8")
    with pytest.raises(core.SchemaError):
        core.load(work / "bad.json")


def test_duplicate_short_name_rejected():
    d = schema_doc()
    d["provider_schemas"]["registry.example.com/other/provider_a"] = d["provider_schemas"][ADDR]
    with pytest.raises(core.SchemaError):
        core.providers(d)


def test_generated_files_pass_contracts(work):
    ps = core.providers(schema_doc())["provider_a"]
    types = list(core.iter_types(ps, "provider_a", "1.0.0"))
    core.write_jsonl(work / "atoms.jsonl", (a for t in types for a in t.atoms))
    core.write_jsonl(work / "types.jsonl", (core.type_record(t) for t in types))
    for alias, f in (("C01_atoms", "atoms.jsonl"), ("C02_types", "types.jsonl")):
        r = V.validate(alias, work / f)
        assert r.ok, r.errors[:5]
    assert r.n == 2


def test_contract_stub_atoms_are_reproduced():
    """Os dois átomos do stub C01 saem da biblioteca, byte a byte, de um schema que os descreve."""
    doc = {"format_version": "1.0", "provider_schemas": {"registry.terraform.io/hashicorp/aws": {
        "resource_schemas": {
            "aws_db_instance": {"block": {"attributes": {
                "backup_retention_period": {"type": "number", "optional": True, "computed": True}}}},
            "aws_s3_bucket_lifecycle_configuration": {"block": {"block_types": {"rule": {
                "nesting_mode": "list", "min_items": 1, "block": {"block_types": {"expiration": {
                    "nesting_mode": "list", "max_items": 1,
                    "block": {"attributes": {"days": {"type": "number", "optional": True}}}}}}}}}},
        }}}}
    ps = core.providers(doc)["aws"]
    got = [json.dumps(a, sort_keys=True) for t in core.iter_types(ps, "aws", "6.0.0") for a in t.atoms]
    stub = (REPO / "contracts" / "stubs" / "C01" / "atoms.jsonl").read_text(encoding="utf-8").splitlines()
    assert got == [json.dumps(json.loads(s), sort_keys=True) for s in stub]
