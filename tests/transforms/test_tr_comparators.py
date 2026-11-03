"""Comparadores da leitura de volta (nomes do C11) com tolerância declarada."""
from fractions import Fraction

import pytest

from bo.transforms import comparators as CMP
from bo.transforms.errors import DeclarationError, OutOfDomain, TransformError

ABSENT = {"$absent": True}


def test_exact():
    assert CMP.compare({"name": "exact"}, 80, 80.0)
    assert not CMP.compare({"name": "exact"}, "80", 80)
    assert not CMP.compare({"name": "exact"}, True, 1)
    assert CMP.compare({"name": "exact"}, {"a": [1, 2]}, {"a": [1, 2.0]})
    assert not CMP.compare({"name": "exact"}, [1, 2], [2, 1])
    assert CMP.compare({"name": "exact"}, ABSENT, ABSENT)
    assert not CMP.compare({"name": "exact"}, ABSENT, None)
    assert CMP.compare({"name": "exact", "tolerance": 0}, 1, 1)
    with pytest.raises(DeclarationError):
        CMP.compare({"name": "exact", "tolerance": 0.5}, 1, 1)


def test_numeric_tolerance_declared_and_absolute():
    c = {"name": "numeric_tolerance", "tolerance": "0.5"}
    assert CMP.compare(c, 100, "100.5") and CMP.compare(c, 100, 99.5)
    assert not CMP.compare(c, 100, "100.51")
    assert CMP.compare({"name": "numeric_tolerance", "tolerance": 0}, 0.3, Fraction(3, 10))
    with pytest.raises(DeclarationError):
        CMP.compare({"name": "numeric_tolerance"}, 1, 1)
    with pytest.raises(DeclarationError):
        CMP.compare({"name": "numeric_tolerance", "tolerance": -1}, 1, 1)
    with pytest.raises(OutOfDomain):
        CMP.compare(c, True, 1)
    with pytest.raises(DeclarationError):
        CMP.compare(c, 1, 1, expected_type={"unit": "unit:SEC"})


def test_numeric_tolerance_with_unit_types():
    c = {"name": "numeric_tolerance", "tolerance": 0}
    assert CMP.compare(c, 1, 1024, expected_type="unit:GibiBYTE", observed_type="unit:MebiBYTE")
    assert not CMP.compare(c, 1, 1, expected_type="unit:GibiBYTE", observed_type="unit:GigaBYTE")
    assert CMP.compare({"name": "numeric_tolerance", "tolerance": "0.074"}, 1, 1,
                       expected_type="unit:GibiBYTE", observed_type="unit:GigaBYTE")
    assert CMP.compare(c, 300, 60, expected_type={"unit": "unit:NUM", "rate_window": "PT5M"},
                       observed_type={"unit": "unit:NUM", "rate_window": "PT1M"})
    with pytest.raises(DeclarationError):
        CMP.compare(c, 1, 1, expected_type={"unit": "unit:NUM", "rate_window": "PT1M"}, observed_type="unit:NUM")
    with pytest.raises(TransformError) as e:
        CMP.compare(c, 1, 1, expected_type="UNKNOWN", observed_type="unit:BYTE")
    assert e.value.code == "NO_UNIT"


def test_set_and_string_and_cidr():
    assert CMP.compare({"name": "set_equal"}, ["a", "b"], ["b", "a", "a"])
    assert CMP.compare({"name": "set_equal"}, [{"k": 1}], [{"k": 1.0}])
    assert not CMP.compare({"name": "set_equal"}, [1], [True])
    assert CMP.compare({"name": "normalized_string"}, "a  b", " a b ")
    assert not CMP.compare({"name": "normalized_string"}, "A", "a")
    assert CMP.compare({"name": "cidr_equal"}, "2001:db8::/32", "2001:DB8:0000::/32")
    assert not CMP.compare({"name": "cidr_equal"}, "10.0.0.0/8", "10.0.0.0/16")
    with pytest.raises(OutOfDomain):
        CMP.compare({"name": "cidr_equal"}, "10.0.0.1/8", "10.0.0.0/8")


def test_duration_equal_value_space():
    c = {"name": "duration_equal"}
    assert CMP.compare(c, "P1Y", "P12M") and CMP.compare(c, "PT1H", "PT60M") and CMP.compare(c, "P1D", "PT24H")
    assert not CMP.compare(c, "P1M", "P30D")
    assert not CMP.compare(c, "P1M", "P31D")
    assert CMP.compare(c, "P1M", "P31D", {"calendar": {"anchor": "2026-01-10T00:00:00-03:00"}})
    with pytest.raises(OutOfDomain):
        CMP.compare(c, "PT1H", "3600s")


def test_markers_and_unknown_comparator():
    with pytest.raises(TransformError) as e:
        CMP.compare({"name": "exact"}, 1, {"$not_read": True})
    assert e.value.code == "UNKNOWN_INPUT"
    with pytest.raises(TransformError) as e:
        CMP.compare({"name": "cidr_equal"}, {"$symbolic": True}, "10.0.0.0/8")
    assert e.value.code == "UNKNOWN_SYMBOLIC_INPUT"
    with pytest.raises(DeclarationError):
        CMP.compare({"name": "fuzzy"}, 1, 1)
    with pytest.raises(DeclarationError):
        CMP.compare({"name": "exact", "mode": "x"}, 1, 1)
