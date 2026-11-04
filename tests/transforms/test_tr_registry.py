"""Registro fechado: exemplos, documento publicado, propriedades das inversas, tipagem e códigos de erro."""
import json
import random
from fractions import Fraction
from pathlib import Path

import pytest
import yaml

from bo.transforms import audit
from bo.transforms import registry as R
from bo.transforms import units as U
from bo.transforms.errors import VALUE_ERROR_CODES, DeclarationError, TransformError
from bo.transforms.examples import run_all, same_input

ROOT = Path(__file__).resolve().parents[2]


def test_every_example_passes():
    rows = run_all()
    assert len(rows) > 300
    assert [r for r in rows if not r["ok"]] == []


def test_published_document_equals_code():
    doc = yaml.safe_load((ROOT / "transforms/transforms.yaml").read_text(encoding="utf-8"))
    assert doc == R.document()
    assert {"schema", "contract", "contract_version", "module", "generated_at", "scalar", "combinators"} == set(doc)


def test_value_error_codes_are_c00_block_codes():
    c00 = json.loads((ROOT / "contracts/C00_conventions.schema.json").read_text(encoding="utf-8"))
    assert set(VALUE_ERROR_CODES) <= set(c00["$defs"]["block_code"]["enum"])


def test_c11_comparators_all_registered():
    c11 = json.loads((ROOT / "contracts/C11_cases.schema.json").read_text(encoding="utf-8"))
    enum = None
    for d in c11["$defs"].values():
        comp = (d.get("properties") or {}).get("comparator")
        if comp:
            enum = comp["properties"]["name"]["enum"]
    assert enum is not None
    assert {c.c11_name for c in R.COMBINATORS if c.c11_name} == set(enum)


def test_names_unique_and_closed():
    names = [t.name for t in R.SCALARS + R.COMBINATORS]
    assert len(names) == len(set(names)) == len(R.REGISTRY)
    with pytest.raises(DeclarationError):
        R.get("scale")
    with pytest.raises(DeclarationError):
        R.apply_scalar("split_cidr", "10.0.0.0/8")
    with pytest.raises(DeclarationError):
        R.apply_combinator("identity", {"value": 1})


def test_every_scalar_preserves_kind_declared():
    for s in R.SCALARS:
        assert s.domain["quantity_kind"] == s.codomain["quantity_kind"], s.name
        assert "tuple" not in (s.domain["datatype"], s.codomain["datatype"]), s.name


def test_every_combinator_structural():
    for c in R.COMBINATORS:
        ports = c.inputs + c.outputs
        assert (len(c.inputs), len(c.outputs)) != (1, 1) or any(p[1] == "tuple" for p in ports), c.name
        assert all(len(p[2]) >= 3 for p in ports), c.name


def test_markers_everywhere():
    for t in R.SCALARS:
        p = next(e.params for e in t.examples if e.err is None)
        with pytest.raises(TransformError) as e:
            R.apply_scalar(t.name, {"$not_read": True}, p)
        assert e.value.code == "UNKNOWN_INPUT"
        if t.name == "identity":
            assert R.apply_scalar(t.name, {"$symbolic": True}) == {"$symbolic": True}
        else:
            with pytest.raises(TransformError) as e:
                R.apply_scalar(t.name, {"$symbolic": True}, p)
            assert e.value.code == "UNKNOWN_SYMBOLIC_INPUT"
    for c in R.COMBINATORS:
        base = next(e.value for e in c.examples if e.err is None)
        k = c.inputs[0][0]
        with pytest.raises(TransformError) as e:
            R.apply_combinator(c.name, {**base, k: {"$not_read": True}})
        assert e.value.code == "UNKNOWN_INPUT"


def test_unknown_params_rejected():
    with pytest.raises(DeclarationError):
        R.apply_scalar("unit_convert_time", 1, {"from": "unit:SEC", "to": "unit:MIN", "factor": 2})
    with pytest.raises(DeclarationError):
        R.apply_scalar("unit_convert_time", 1, {"from": "unit:SEC"})


# ------------------------------------------------------------------ propriedades das inversas totais (partial=false)
rng = random.Random(7)


def _rat():
    return Fraction(rng.randint(-10**6, 10**6), rng.choice([1, 2, 4, 5, 8, 10, 1000]))


def _roundtrip(name, v, p, ctx=None):
    t = R.get(name)
    out = R.apply_scalar(name, v, p, ctx) if isinstance(t, R.Scalar) else R.apply_combinator(name, v, ctx)
    inv, ip = R.inverse_of(name, p)
    back = R.apply_scalar(inv, out, ip, ctx) if isinstance(t, R.Scalar) else R.apply_combinator(inv, out, ctx)
    return same_input(t, back, v)


def test_property_unit_convert_total():
    for key, kind in (("time", U.TIME), ("information", U.INFO), ("ratio", U.RATIO)):
        units = [u for u in U.units_of(kind) if U.UNITS[u].factor is not None]
        for _ in range(300):
            a, b = rng.choice(units), rng.choice(units)
            assert _roundtrip(f"unit_convert_{key}", _rat(), {"from": a, "to": b})


def test_property_number_to_duration_total():
    for _ in range(500):
        u = rng.choice(["unit:SEC", "unit:MIN", "unit:HR", "unit:DAY", "unit:MilliSEC"])
        v = Fraction(rng.randint(-10**7, 10**7), rng.choice([1, 2, 4, 5, 10]))
        try:
            ok = _roundtrip("number_to_duration", v, {"from": u})
        except TransformError as e:
            assert e.code == "TRANSFORM_OUT_OF_DOMAIN"
            continue
        assert ok
    for _ in range(100):
        assert _roundtrip("number_to_duration", rng.randint(0, 600), {"from": rng.choice(["unit:MO", "unit:YR"])})


def test_property_rate_window_total():
    ws = ["PT1S", "PT1M", "PT5M", "PT1H", "P1D", "PT90S"]
    for _ in range(300):
        p = {"from_window": rng.choice(ws), "to_window": rng.choice(ws), "statistic": rng.choice(["sum", "average"])}
        assert _roundtrip(rng.choice(["rate_window_convert_count", "rate_window_convert_information"]), _rat(), p)


def test_property_ports_alarm_tags_total():
    for _ in range(300):
        lo = rng.randint(0, 65535)
        hi = rng.randint(lo, 65535)
        assert _roundtrip("join_port_range", {"from_port": lo, "to_port": hi}, {})
    for _ in range(300):
        v = {"metric": rng.choice(["CPU", "Latency_ms", "Errors"]),
             "window": U.canonical_duration(U.Duration(0, Fraction(rng.choice([1, 60, 90, 300, 3600, 86400]) *
                                                                   rng.randint(1, 5)))),
             "statistic": rng.choice(["mean", "sum", "min", "max", "count"]),
             "operator": rng.choice(["gt", "ge", "lt", "le", "eq", "ne"]),
             "threshold": Fraction(rng.randint(-10**4, 10**4), rng.choice([1, 2, 4, 10, 100]))}
        assert _roundtrip("join_alarm_query", v, {})
    for _ in range(200):
        m = {f"k{rng.randint(0, 50)}": str(rng.randint(0, 9)) for _ in range(rng.randint(0, 6))}
        assert _roundtrip("tags_map_to_list", {"map": m}, {})


def test_property_seconds_text_canonical_total():
    for _ in range(300):
        secs = Fraction(rng.randint(-10**8, 10**8), rng.choice([1, 2, 4, 1000]))
        txt = R.apply_scalar("duration_to_seconds_text", U.canonical_duration(U.Duration(0, secs)))
        assert R.apply_scalar("duration_to_seconds_text", R.apply_scalar("seconds_text_to_duration", txt)) == txt


# ------------------------------------------------------------------ tipagem da cadeia
def test_check_chain_kind_and_unit():
    tin = {"datatype": "number", "quantity_kind": U.INFO, "unit": "unit:GibiBYTE"}
    chain = [{"name": "unit_convert_information", "params": {"from": "unit:GibiBYTE", "to": "unit:GigaBYTE"}},
             {"name": "round_information", "params": {"mode": "ceiling"}}]
    t = R.check_chain(chain, tin, {"quantity_kind": U.INFO, "unit": "unit:GigaBYTE"})
    assert t["datatype"] == "integer" and t["byte_convention"] == "SI"
    assert R.apply_chain(chain, 100) == 108
    with pytest.raises(DeclarationError):
        R.check_chain(chain, tin, {"quantity_kind": U.INFO, "unit": "unit:GibiBYTE"})
    with pytest.raises(DeclarationError):
        R.type_out("unit_convert_time", {"from": "unit:SEC", "to": "unit:BYTE"},
                   {"datatype": "number", "quantity_kind": U.TIME, "unit": "unit:SEC"})


def test_resolve_kernel():
    assert R.resolve_kernel("unit_convert", {"from": "unit:HR", "to": "unit:MIN"})[0] == "unit_convert_time"
    assert R.resolve_kernel("split_cidr")[0] == "split_cidr"
    for n in ("scale", "rate_window_convert"):
        with pytest.raises(DeclarationError):
            R.resolve_kernel(n, {})


def test_kernel_names_kept():
    from bo.semantics import transforms as K
    kept = set(K.REGISTRY) - {"unit_convert", "scale", "rate_window_convert"}
    assert kept <= set(R.REGISTRY)
    from bo.semantics import projections as P
    for name, (ins, outs) in P.SIGNATURES.items():
        if name in R.REGISTRY and isinstance(R.REGISTRY[name], R.Combinator):
            c = R.REGISTRY[name]
            assert tuple(p[0] for p in c.inputs) == ins and tuple(p[0] for p in c.outputs) == outs, name


# ------------------------------------------------------------------ o audit não passa por vacuidade
def _item(name):
    return next(i for i in R.document()["scalar"] + R.document()["combinators"] if i["name"] == name)


def test_audit_catches_false_partial_flag():
    from dataclasses import replace
    t = replace(R.REGISTRY["enum_map"], partial=False)
    errs = audit.check_item(_item("enum_map"), set(R.REGISTRY), t)
    assert any("partial=false" in e for e in errs)
    t = replace(R.REGISTRY["join_port_range"], partial=True)
    errs = audit.check_item(_item("join_port_range"), set(R.REGISTRY), t)
    assert any("parcialidade" in e for e in errs)


def test_audit_catches_undeclared_error_and_bad_fields():
    from dataclasses import replace
    t = R.REGISTRY["split_cidr"]
    t2 = replace(t, errors=tuple(e for e in t.errors if e[0] != "TRANSFORM_OUT_OF_DOMAIN"))
    assert any("não declarado" in e for e in audit.check_item(_item("split_cidr"), set(R.REGISTRY), t2))
    it = dict(_item("identity"), loss="perda: x", error="QUEBROU: sempre", inverse={"name": "nada", "partial": False})
    errs = audit.check_item(it, set(R.REGISTRY), R.REGISTRY["identity"])
    assert any("loss_contract" in e for e in errs) and any("fora do registro" in e for e in errs)
    assert any("não declarada" in e for e in errs)
    it = dict(_item("identity"), precondition="TODO")
    assert any("marcador" in e for e in audit.check_item(it, set(R.REGISTRY), R.REGISTRY["identity"]))


def test_error_field_roundtrip():
    for t in R.REGISTRY.values():
        it = R.to_item(t)
        assert R.parse_error_field(it["error"]) == [tuple(e) for e in t.errors]
        assert R.parse_loss_field(it["loss"]) == list(t.loss)


# ------------------------------------------------------------------ emenda 1.1.0: domínio finito (STO-MAP CC-9)
def test_finite_domain_and_image_enum_to_bool():
    p = {"true": ["Enabled"], "false": ["Disabled", "Suspended"]}
    assert R.finite_domain("enum_to_bool", p) == {"Enabled", "Disabled", "Suspended"}
    assert R.finite_image("enum_to_bool", p) == {True, False}
    assert R.finite_image("enum_to_bool", p, ["Disabled"]) == {False}
    with pytest.raises(TransformError):
        R.finite_image("enum_to_bool", p, ["Paused"])
    with pytest.raises(DeclarationError):
        R.finite_domain("enum_to_bool", {"true": ["A"], "false": ["A"]})


def test_finite_domain_bijection_both_ways():
    p = {"true": "Enabled", "false": "Disabled"}
    assert R.finite_domain("bool_to_enum", p) == {True, False}
    assert R.finite_image("bool_to_enum", p) == {"Enabled", "Disabled"}
    inv, ip = R.inverse_of("bool_to_enum", p)
    assert R.finite_domain(inv, ip) == R.finite_image("bool_to_enum", p)
    assert R.finite_image(inv, ip) == R.finite_domain("bool_to_enum", p)
    t = {"gp3": "Premium_LRS", "standard": "Standard_LRS"}
    assert R.finite_domain("enum_map", {"table": t}) == set(t)
    assert R.finite_image("enum_map", {"table": t}) == set(t.values())


def test_finite_domain_absent_where_not_declared():
    assert R.finite_domain("identity") is None
    assert R.finite_domain("unit_convert_time", {"from": "unit:SEC", "to": "unit:MIN"}) is None
    assert R.finite_image("unit_convert_time", {"from": "unit:SEC", "to": "unit:MIN"}, [60, 120]) == {1, 2}
    with pytest.raises(DeclarationError):
        R.finite_image("identity")
    with pytest.raises(DeclarationError):
        R.finite_domain("split_cidr")


def test_enum_to_bool_domain_declared_in_yaml():
    doc = yaml.safe_load((ROOT / "transforms/transforms.yaml").read_text(encoding="utf-8"))
    e2b = next(s for s in doc["scalar"] if s["name"] == "enum_to_bool")
    assert {k: v["part_of"] for k, v in e2b["params"].items()} == {"true": "domain", "false": "domain"}
    assert "true ∪ false" in e2b["precondition"]


# ------------------------------------------------------------------ emenda 1.2.0: coleções (STO-MAP CC-6)
def test_wrap_unwrap_and_set_list():
    assert R.apply_combinator("wrap_list", {"value": "logs/"}) == {"list": ["logs/"]}
    assert R.apply_combinator("unwrap_single", {"list": ["logs/"]}) == {"value": "logs/"}
    with pytest.raises(TransformError):
        R.apply_combinator("unwrap_single", {"list": ["a", "b"]})
    assert R.apply_combinator("list_to_set", {"list": [3, 1, 3, 2]}) == {"set": [1, 2, 3]}
    assert R.apply_combinator("set_to_list", {"set": ["b", "a"]}) == {"list": ["a", "b"]}
    with pytest.raises(TransformError):
        R.apply_combinator("set_to_list", {"set": ["a", "a"]})
    doc = R.document()
    l2s = next(c for c in doc["combinators"] if c["name"] == "list_to_set")
    assert l2s["loss"].startswith("not_expressible") and l2s["inverse"] == {"name": "set_to_list", "partial": True}


def test_map_elements_and_inverse():
    gib = {"fn": "unit_convert_information", "params": {"from": "unit:GibiBYTE", "to": "unit:MebiBYTE"}}
    out = R.apply_combinator("map_list", {"list": [1, 2], **gib})
    assert out == {"list": [1024, 2048]}
    name, ins = R.invert("map_list", None, {"list": [1, 2], **gib}, out)
    assert R.apply_combinator(name, ins) == {"list": [1, 2]}
    assert R.apply_combinator("map_values", {"map": {"a": 1}, **gib}) == {"map": {"a": 1024}}
    noninj = {"fn": "enum_map", "params": {"table": {"a": "x", "b": "x"}}}
    assert R.apply_combinator("map_set", {"set": ["a", "b"], **noninj}) == {"set": ["x"]}
    assert R.invert("map_set", None, {"set": ["a", "b"], **noninj}, {"set": ["x"]}) is None
    with pytest.raises(TransformError) as e:
        R.apply_combinator("map_list", {"list": ["10.0.0.0/8"], "fn": "split_cidr", "params": {}})
    assert e.value.code == "DECLARATION_ERROR"


def test_collection_types_c09_3_2_0():
    gib = {"datatype": "number", "quantity_kind": U.INFO, "unit": "unit:GibiBYTE"}
    t = R.collection_type_out("map_list", {"datatype": "list", "item_type": gib}, "unit_convert_information",
                              {"from": "unit:GibiBYTE", "to": "unit:MebiBYTE"})
    assert t == {"datatype": "list", "item_type": {**gib, "unit": "unit:MebiBYTE", "byte_convention": "IEC"}}
    assert R.collection_type_out("wrap_list", {"datatype": "string", "quantity_kind": "NOT_APPLICABLE"}) == {
        "datatype": "list", "item_type": {"datatype": "string", "quantity_kind": "NOT_APPLICABLE"}}
    assert R.collection_type_out("list_to_set", {"datatype": "list", "item_type": gib})["datatype"] == "set"
    with pytest.raises(DeclarationError):      # elemento mudaria de grandeza
        R.collection_type_out("map_list", {"datatype": "list", "item_type": gib}, "unit_convert_time",
                              {"from": "unit:SEC", "to": "unit:MIN"})
    with pytest.raises(DeclarationError):      # C09-COLL: coleção sem item_type
        R.collection_type_out("list_to_set", {"datatype": "list"})
    with pytest.raises(DeclarationError):
        R.collection_type_out("unwrap_single", {"datatype": "set", "item_type": gib})
