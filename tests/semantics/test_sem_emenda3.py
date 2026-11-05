"""Emenda 3 (ciclo v4): wrap_list / unwrap_single do registro fechado entre escalar e lista tipada do C09 3.2.0."""
import copy

import pytest

pytest.importorskip("bo.transforms.registry")

from bo.semantics import transforms as T                      # noqa: E402
from bo.semantics.content import examples as E                # noqa: E402
from bo.semantics.obligations import assess                   # noqa: E402
from bo.semantics.transport import transport                  # noqa: E402


def test_positional_single_port_and_named_inputs():
    assert T.apply({"name": "wrap_list", "params": {}}, "logs/") == ["logs/"]
    assert T.apply({"name": "unwrap_single", "params": {}}, ["logs/"]) == "logs/"
    assert T.apply({"name": "wrap_list", "params": {}}, {"value": "x"}) == {"list": ["x"]}    # nomeada continua
    assert T.apply({"name": "wrap_list", "params": {}}, {"k": 1}) == [{"k": 1}]              # dict solto é valor
    with pytest.raises(T.OutOfDomain):
        T.apply({"name": "unwrap_single", "params": {}}, ["a/", "b/"])


def test_wrap_list_is_exact_on_domain_with_subset():
    a = assess(E.WRAP_PREFIX)
    assert a.verdict == "OK" and a.computed["vdr"] == "subset"
    assert transport(E.WRAP_PREFIX, "logs/")["value"] == ["logs/"]
    assert transport(E.WRAP_PREFIX, ["logs/"], direction="inverse")["value"] == "logs/"
    assert transport(E.WRAP_PREFIX, ["a/", "b/"], direction="inverse")["code"] == "TRANSFORM_OUT_OF_DOMAIN"
    eq = copy.deepcopy(E.WRAP_PREFIX)
    eq["value_domain_relation"]["relation"] = "equal"                  # destino admite mais de um item
    assert "VDR-COMPUTED" in assess(eq).rules


def test_unwrap_single_is_partial():
    a = assess(E.UNWRAP_PREFIX)
    assert a.verdict == "OK" and a.computed["vdr"] == "superset"
    assert transport(E.UNWRAP_PREFIX, ["a/"])["value"] == "a/"
    assert transport(E.UNWRAP_PREFIX, [])["code"] == "TRANSFORM_OUT_OF_DOMAIN"
    lossless = copy.deepcopy(E.UNWRAP_PREFIX)
    lossless["transport_fidelity"] = "lossless"
    assert "FID-COHERENT" in assess(lossless).rules


def test_list_and_set_count_as_structured_side():
    for c in (E.WRAP_PREFIX, E.UNWRAP_PREFIX):
        assert "KIND-TUPLE" not in assess(c).rules and "EXACT-TESTS" not in assess(c).rules


def test_shape_and_element_kind():
    s2s = copy.deepcopy(E.WRAP_PREFIX)
    s2s["object_value_type"] = E.T("string")
    assert "KIND-COLL" in assess(s2s).rules
    k = copy.deepcopy(E.WRAP_PREFIX)
    k["subject_value_type"] = E.DAYS(1, 30)
    k["object_value_type"] = E.T("list", item_type=E.T("integer", quantity_kind="quantitykind:Count", unit="unit:NUM"))
    k["proof"]["tests"] = [{"input": 3, "expected": [3]}]
    assert "KIND-EQ" in assess(k).rules
