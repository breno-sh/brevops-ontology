"""Regras de extração do DOCS-AZURE sobre frases sintéticas (sem rede, sem dado real)."""
from bo.docs_azure import extract as X


def atom(path, tf="string"):
    return {"path": path, "tf_type": tf}


def kinds(fs, k):
    return [f for f in fs if f["kind"] == k]


def test_sentences_respect_backticks_and_abbrev():
    s = X.sentences("Use `a.b` here. Possible values are `X`, e.g. `Y`. Done.")
    assert [x[1] for x in s] == ["Use `a.b` here.", "Possible values are `X`, e.g. `Y`.", "Done."]


def test_default_typed_by_tf_type():
    f = kinds(X.extract("(Optional) Enable it? Defaults to `false`.", atom("x", "bool"), set()), "default")
    assert f[0]["status"] == "stated" and f[0]["value"] is False
    f = kinds(X.extract("(Optional) Days. Defaults to `7`.", atom("days", "number"), set()), "default")
    assert f[0]["value"] == 7


def test_default_without_literal_is_unknown_with_sentence():
    f = kinds(X.extract("(Optional) Tenant. Defaults to the current tenant id.", atom("t"), set()), "default")
    assert f[0]["status"] == "unknown" and f[0]["reason"] == "ambiguous" and "current tenant" in f[0]["s"]


def test_two_different_defaults_are_ambiguous():
    t = "(Optional) Mode. Defaults to `A` for Linux. Defaults to `B` for Windows."
    f = kinds(X.extract(t, atom("m"), set()), "default")
    assert len(f) == 1 and f[0]["status"] == "unknown"


def test_number_default_with_text_is_not_invented():
    f = kinds(X.extract("(Optional) Size. Defaults to `auto`.", atom("size", "number"), set()), "default")
    assert f[0]["status"] == "unknown"


def test_allowed_values_cut_at_when():
    t = "Possible values are `Hot` and `Cool` when `kind` is `StorageV2`."
    f = kinds(X.extract(t, atom("tier"), {"kind"}), "allowed_values")
    assert f[0]["value"] == ["Hot", "Cool"]


def test_possible_values_between_is_range_not_enum():
    t = "Possible values are between `1` and `365` days."
    fs = X.extract(t, atom("days", "number"), set())
    assert not kinds(fs, "allowed_values")
    assert kinds(fs, "range")[0]["value"] == {"min": 1, "max": 365, "applies_to": "value"}
    assert kinds(fs, "unit")[0]["value"]["unit"] == "day"


def test_range_length_and_items():
    f = kinds(X.extract("Must be between 3 and 24 characters long.", atom("name"), set()), "range")
    assert f[0]["value"]["applies_to"] == "length"
    f = kinds(X.extract("A maximum of `25` values may be defined.", atom("v", ["list", "string"]), set()), "range")
    assert f[0]["value"] == {"max": 25, "applies_to": "items"}


def test_unit_name_rules_skip_calendar_positions_and_min():
    assert X.name_unit("retention_in_days") == ("day", "days")
    assert X.name_unit("timeout_seconds") == ("second", "seconds")
    for n in ("day_of_week", "start_hour", "hours_of_day", "port_range_min", "week"):
        assert X.name_unit(n) is None, n


def test_unit_only_for_numeric_atoms():
    assert not kinds(X.extract("The duration in days.", atom("d", "string"), set()), "unit")
    f = kinds(X.extract("The duration in days.", atom("d", "number"), set()), "unit")
    assert f[0]["value"] == {"unit": "day", "literal": "days"} and f[0]["level"] == "published"


def test_name_unit_is_derived():
    f = kinds(X.extract("(Optional) How long.", atom("ttl_in_seconds", "number"), set()), "unit")
    assert f[0]["level"] == "derived" and f[0]["value"]["from"] == "name"


def test_published_units_that_disagree_add_contradictory_unknown():
    f = kinds(X.extract("The size in GB. Must be a number of bytes.", atom("size", "number"), set()), "unit")
    assert {x["status"] for x in f} == {"stated", "unknown"}
    assert [x for x in f if x["status"] == "unknown"][0]["reason"] == "contradictory"


def test_format_ignores_keyword_inside_backticks():
    assert not kinds(X.extract("Allowed values: `CSV` and `JSON`.", atom("fmt"), set()), "format")
    f = kinds(X.extract("The time duration in ISO 8601 format.", atom("t"), set()), "format")
    assert f[0]["value"] == "ISO8601_duration"


def test_forces_replacement_and_required_when():
    fs = X.extract("Changing this forces a new resource to be created. Required when `type` is `A`.",
                   atom("x"), {"type"})
    assert kinds(fs, "forces_replacement")[0]["value"] is True
    assert kinds(fs, "required_when")[0]["value"].startswith("Required when")


def test_conflicts_only_with_siblings():
    fs = X.extract("Conflicts with `b` and `zzz`.", atom("a"), {"a", "b"})
    assert kinds(fs, "conflicts_with")[0]["value"] == ["b"]


def test_deprecation_scope():
    v = kinds(X.extract("`Standard` and `WAF` values are deprecated.", atom("tier"), set()), "deprecation")
    assert v[0]["value"]["scope"] == "values" and v[0]["value"]["values"] == ["Standard", "WAF"]
    v = kinds(X.extract("This field is deprecated in favour of `new_x`.", atom("x"), {"new_x"}), "deprecation")
    assert v[0]["value"]["scope"] == "attribute" and v[0]["value"]["replaced_by"] == "new_x"
    assert not kinds(X.extract("`old_y` is deprecated.", atom("x"), {"old_y"}), "deprecation")
    assert not kinds(X.extract("Skips checking for deprecated API usage.", atom("x"), set()), "deprecation")


def test_example_skips_sibling_and_index():
    f = kinds(X.extract("Users (e.g. `admin[0].login`) or `b`.", atom("x"), {"b"}), "example")
    assert not f
    f = kinds(X.extract("Product type, such as `Standard` or `WildCard`.", atom("p"), set()), "example")
    assert f[0]["value"] == ["Standard", "WildCard"]


def test_timeouts_default_literal():
    f = kinds(X.extract("(Defaults to 30 minutes) Used when creating.", atom("create"), set(), timeouts=True),
              "default")
    assert f[0]["value"] == "30 minutes"
