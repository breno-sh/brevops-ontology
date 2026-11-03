"""Schema fixado: sha256 conferido contra universe/pins.json; recorte estrutural reprodutível."""
import json

import pytest

from bo.harness.aws import pins, schema as sch


def test_pinned_schema_matches_pins(schema):
    pin = pins.load_pin()
    assert schema.provider_version == pin.provider_version and schema.sha256 == pin.schema_sha256
    assert len(schema.types()) == 1746


def test_required_and_blocks_read_from_schema(schema):
    assert schema.resource("aws_subnet").attributes["vpc_id"].required
    v = schema.resource("aws_s3_bucket_versioning").blocks["versioning_configuration"]
    assert v.min_items == 1 and v.block.attributes["status"].required
    db = schema.resource("aws_db_instance").attributes
    assert db["password"].sensitive and db["password_wo"].write_only


def test_tampered_schema_is_refused(work, monkeypatch):
    p = work / "providers-schema.json"
    p.write_text(json.dumps({"provider_schemas": {}}))
    monkeypatch.setenv("BO_AWS_SCHEMA", str(p))
    with pytest.raises(pins.PinError, match="sha256"):
        pins.verified_schema_path()
    with pytest.raises(pins.PinError):
        sch.load(str(p))


def test_excerpt_roundtrip(work, schema):
    p = work / "excerpt.json"
    assert sch.main(["excerpt", "aws_vpc", "aws_subnet", "--out", str(p)]) == 0
    assert sch.main(["check-excerpt", str(p)]) == 0
    ex = sch.load(str(p))
    assert ex.types() == ["aws_subnet", "aws_vpc"] and ex.resource("aws_subnet").attributes["vpc_id"].required
    d = json.loads(p.read_text())
    d["provider_schemas"]["registry.terraform.io/hashicorp/aws"]["resource_schemas"]["aws_vpc"]["block"]["attributes"][
        "cidr_block"]["required"] = True
    p.write_text(json.dumps(d))
    assert sch.main(["check-excerpt", str(p)]) == 1


def test_tmp_root_refuses_tmp(monkeypatch):
    monkeypatch.setenv("BO_TMP", "/tmp/qualquer")
    with pytest.raises(pins.PinError):
        pins.tmp_root()
