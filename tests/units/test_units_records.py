"""Registro C05 por átomo: datatype, NOT_APPLICABLE ≠ UNKNOWN, unidade, enum, faixa, formato, duração."""
import json

from conftest import atom, build_record, fact

from bo.units.rules import NA, UNK


def test_string_and_bool_are_not_applicable():
    for tf in ("string", "bool", ["list", "string"], ["map", "string"], "dynamic"):
        r = build_record(atom("name", tf))
        assert (r["quantity_kind"], r["unit_qudt"], r["byte_convention"], r["rate_window"]) == (NA, NA, NA, None)


def test_number_without_evidence_is_unknown_not_na():
    r = build_record(atom("size"))
    assert r["datatype"] == {"kind": "scalar", "scalar": "decimal"}
    assert (r["quantity_kind"], r["unit_qudt"]) == (UNK, UNK)
    assert r["evidence"][0]["ref"] == "UNITS-UNK-01"


def test_identifier_number_is_na():
    r = build_record(atom("from_port"))
    assert (r["quantity_kind"], r["unit_qudt"]) == (NA, NA)


def test_published_unit_fact():
    f = fact("unit", "GiB", "Size of created volumes in GiB.")
    r = build_record(atom("volume_size"), [f])
    assert (r["quantity_kind"], r["unit_qudt"], r["byte_convention"]) == (
        "quantitykind:AmountOfData", "unit:GibiBYTE", "IEC")
    assert r["evidence"][0]["ref"] == f["id"] and r["evidence"][0]["level"] == "published"


def test_unknown_unit_fact_stays_unknown():
    f = fact("unit", None, "Allocated storage size in gigabytes (GB).", status="unknown", ur="ambiguous")
    r = build_record(atom("allocated"), [f])
    assert (r["quantity_kind"], r["unit_qudt"]) == (UNK, UNK)


def test_conflicting_sources():
    a = fact("unit", "second", "Timeout in seconds.")
    b = fact("unit", "minute", "Timeout in minutes.")
    r = build_record(atom("timeout"), [a, b])
    assert r["quantity_kind"] == "quantitykind:Time" and r["unit_qudt"] == UNK
    c = fact("unit", "GiB", "in GiB")
    r = build_record(atom("thing"), [a, c])
    assert (r["quantity_kind"], r["unit_qudt"]) == (UNK, UNK)


def test_name_window_completes_doc_unit():
    f = fact("unit", "byte", "Number of bytes.")
    r = build_record(atom("bytes_per_second"), [f])
    assert (r["unit_qudt"], r["rate_window"]) == ("unit:BYTE", "PT1S")


def test_enum_from_allowed_values():
    f = fact("allowed_values", ["ENABLED", "DISABLED", "ENABLED"], "Valid values are ENABLED or DISABLED.")
    r = build_record(atom("status", "string"), [f])
    assert r["datatype"] == {"kind": "scalar", "scalar": "enum"} and r["enum"] == ["ENABLED", "DISABLED"]
    assert r["quantity_kind"] == NA
    g = fact("allowed_values", {"closed": False, "values": ["A"]}, "Possible values include A.")
    assert "enum" not in build_record(atom("x", "string"), [g])


def test_enum_on_number_is_not_written():
    f = fact("allowed_values", [0, 1, 5, 60], "Valid values: 0, 1, 5, 60.")
    r = build_record(atom("interval"), [f])
    assert "enum" not in r and r["datatype"]["scalar"] == "decimal"


def test_range_value_only_and_in_atom_unit():
    u = fact("unit", "day", "Number of days, between 7 and 30.")
    rv = fact("range", {"min": 7, "max": 30, "of": "value"}, "between 7 and 30 days")
    rl = fact("range", {"max": 64, "of": "length"}, "at most 64 characters")
    r = build_record(atom("retention"), [u, rv, rl])
    assert r["range"] == {"min": 7, "max": 30}
    s = build_record(atom("name", "string"), [rl])
    assert "range" not in s


def test_range_converted_to_atom_unit():
    u = fact("unit", "second", "in seconds")
    rv = fact("range", {"min": 5, "of": "value", "unit": "minutes"}, "at least 5 minutes")
    r = build_record(atom("window"), [u, rv])
    assert r["range"] == {"min": 300}


def test_conflicting_ranges_are_dropped():
    u = fact("unit", "day", "days")
    r1 = fact("range", {"min": 1, "max": 30, "of": "value"}, "1 to 30")
    r2 = fact("range", {"min": 1, "max": 35, "of": "value"}, "1 to 35")
    assert "range" not in build_record(atom("days"), [u, r1, r2])


def test_timeouts_are_go_durations():
    a = atom("timeouts.create", "string", block_path=[{"block": "timeouts", "nesting_mode": "single"}])
    r = build_record(a)
    assert r["datatype"] == {"kind": "scalar", "scalar": "duration"}
    assert (r["quantity_kind"], r["unit_qudt"], r["format"]) == ("quantitykind:Time", "unit:SEC", "go_duration")


def test_protobuf_and_iso_durations():
    p = fact("format", {"aspect": "duration", "standard": "google.protobuf.Duration", "suffix": "s"},
             "A duration in seconds with up to nine fractional digits, terminated by 's'.")
    r = build_record(atom("ttl", "string"), [p])
    assert r["datatype"]["scalar"] == "duration" and r["unit_qudt"] == "unit:SEC"
    i = fact("format", "ISO8601_duration", "an ISO 8601 duration like P1D")
    r = build_record(atom("period", "string"), [i])
    assert r["datatype"]["scalar"] == "duration"
    assert (r["quantity_kind"], r["unit_qudt"]) == ("quantitykind:Time", UNK)


def test_format_and_json_tree():
    f = fact("format", "ARN", "ARN of the thing.")
    assert build_record(atom("arn", "string"), [f])["format"] == "arn"
    j = fact("format", "JSON", "JSON policy document.")
    r = build_record(atom("policy", "string"), [j])
    assert r["datatype"] == {"kind": "tree", "format": "policy_document"} and "format" not in r


def test_object_tuple_and_tree():
    r = build_record(atom("obj", ["object", {"min": "number", "max": "number"}]))
    assert r["datatype"]["kind"] == "tuple" and r["quantity_kind"] == UNK
    r = build_record(atom("obj", ["object", {"a": "string", "b": "string"}]))
    assert r["datatype"]["kind"] == "tuple" and r["quantity_kind"] == NA


def test_inherited_shared_fact_is_derived():
    f = dict(fact("unit", "GiB", "in GiB"), inh="aws:aws_x:canon")
    r = build_record(atom("size"), [f])
    e = r["evidence"][0]
    assert e["level"] == "derived" and "UNITS-SHARED-01" in e["note"]


def test_synthetic_records_pass_c05(tmpdir_units):
    from bo.contracts import validate
    recs = [build_record(atom("a"), [fact("unit", "GiB", "in GiB")]),
            build_record(atom("b", "string")),
            build_record(atom("c")),
            build_record(atom("d"), [fact("unit", "Mbps", "in Mbps")]),
            build_record(atom("timeouts.read", "string", block_path=[{"block": "timeouts"}]))]
    p = tmpdir_units / "value_space.jsonl"
    p.write_text("".join(json.dumps(r) + "\n" for r in recs), encoding="utf-8")
    res = validate.validate("value_space", p)
    assert res.ok, res.errors
