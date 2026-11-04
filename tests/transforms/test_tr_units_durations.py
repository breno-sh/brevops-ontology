"""Unidades, tipo de unidade (janela e convenção de byte) e xsd:duration com e sem calendário."""
from fractions import Fraction

import pytest

from bo.transforms import units as U
from bo.transforms.errors import DeclarationError, NoUnit, OutOfDomain


@pytest.mark.parametrize("s,months,secs", [
    ("PT1M", 0, 60), ("P1M", 1, 0), ("P1Y2M", 14, 0), ("P1DT1H1M1.5S", 0, Fraction(180123, 2)),
    ("-P1M", -1, 0), ("P0M1D", 0, 86400), ("PT0S", 0, 0), ("P12M", 12, 0)])
def test_parse_duration_value_space(s, months, secs):
    d = U.parse_duration(s)
    assert (d.months, d.seconds) == (months, secs)


@pytest.mark.parametrize("s", ["P", "PT", "P1DT", "1h", "PT1.5M", "P1.5D", "P1W", "+P1D", "P-1D", "", "PT1H2", 3600])
def test_parse_duration_rejects_non_xsd(s):
    with pytest.raises(OutOfDomain):
        U.parse_duration(s)


@pytest.mark.parametrize("secs,canon", [(0, "PT0S"), (3600, "PT1H"), (90061, "P1DT1H1M1S"), (Fraction(3, 2), "PT1.5S"),
                                        (-30, "-PT30S"), (86400, "P1D")])
def test_canonical_duration(secs, canon):
    assert U.canonical_duration(U.Duration(0, Fraction(secs))) == canon
    d = U.parse_duration(canon)
    assert d.seconds == secs


def test_canonical_months():
    assert U.canonical_duration(U.Duration(18, Fraction(0))) == "P1Y6M"
    assert U.canonical_duration(U.Duration(1, Fraction(1))) == "P1MT1S"
    with pytest.raises(OutOfDomain):
        U.canonical_duration(U.Duration(0, Fraction(1, 3)))


@pytest.mark.parametrize("s", ["P1M", "P1Y", "-P1M", "P1MT1S", "P0Y1M"])
def test_months_to_seconds_needs_calendar(s):
    with pytest.raises(OutOfDomain) as e:
        U.duration_seconds(s)
    assert e.value.code == "TRANSFORM_OUT_OF_DOMAIN"


def test_months_with_anchor_pins_day():
    assert U.duration_seconds("P1M", {"calendar": {"anchor": "2026-01-31T10:00:00-03:00"}}) == 28 * 86400
    assert U.duration_seconds("P1M", {"calendar": {"anchor": "2024-01-31T10:00:00-03:00"}}) == 29 * 86400
    assert U.duration_seconds("P1Y", {"calendar": {"anchor": "2024-02-29T00:00:00+00:00"}}) == 365 * 86400


def test_months_with_convention():
    ctx = {"calendar": {"seconds_per_month": "2629746", "source": "mês gregoriano médio"}}
    assert U.duration_seconds("P2M", ctx) == 2 * 2629746
    assert U.months_to_seconds(Fraction(1, 2), ctx, "x") == Fraction(2629746, 2)
    anchor = {"calendar": {"anchor": "2026-01-01T00:00:00-03:00"}}
    with pytest.raises(OutOfDomain):
        U.months_to_seconds(Fraction(1, 2), anchor, "x")


@pytest.mark.parametrize("cal", [{"anchor": "2026-01-01"}, {"anchor": 5}, {"seconds_per_month": -1, "source": "abc"},
                                 {"seconds_per_month": 1}, {}, {"anchor": "2026-01-01T00:00:00Z", "seconds_per_month": 1}])
def test_bad_calendar_context(cal):
    with pytest.raises(DeclarationError):
        U.duration_seconds("P1M", {"calendar": cal})


def test_seconds_to_months_inverse_with_anchor():
    ctx = {"calendar": {"anchor": "2026-01-31T00:00:00-03:00"}}
    assert U.seconds_to_months(28 * 86400, ctx, "x") == 1
    with pytest.raises(OutOfDomain):
        U.seconds_to_months(29 * 86400, ctx, "x")


def test_byte_convention_is_part_of_type():
    assert U.UnitType.of("unit:GibiBYTE").byte_convention == "IEC"
    assert U.UnitType.of("unit:GigaBYTE").byte_convention == "SI"
    with pytest.raises(DeclarationError):
        U.UnitType.of({"unit": "unit:GigaBYTE", "byte_convention": "IEC"})
    with pytest.raises(DeclarationError):
        U.UnitType.of({"unit": "unit:BYTE", "byte_convention": "SI"})
    assert U.convert(1, "unit:GibiBYTE", "unit:GigaBYTE") == Fraction(2**30, 10**9)
    assert U.UnitType.of("unit:GibiBYTE").signature() != U.UnitType.of("unit:GigaBYTE").signature()


def test_rate_window_is_part_of_type():
    per_min = U.UnitType.of({"unit": "unit:NUM", "rate_window": "PT1M"})
    per_sec = U.UnitType.of({"unit": "unit:NUM", "rate_window": "PT1S"})
    assert per_min.signature() != per_sec.signature()
    assert U.convert(60, per_min, per_sec) == 1
    with pytest.raises(DeclarationError):
        U.convert(1, per_min, "unit:NUM")       # taxa x quantidade
    with pytest.raises(DeclarationError):
        U.UnitType.of({"unit": "unit:NUM", "rate_window": "P1M"})
    with pytest.raises(DeclarationError):
        U.UnitType.of({"unit": "unit:NUM", "rate_window": "PT0S"})


def test_units_registry_and_markers():
    with pytest.raises(NoUnit):
        U.unit("UNKNOWN")
    with pytest.raises(NoUnit):
        U.unit("NOT_APPLICABLE")
    with pytest.raises(NoUnit):
        U.unit("unit:FURLONG")
    with pytest.raises(DeclarationError):
        U.convert(1, "unit:SEC", "unit:BYTE")
    for u in U.UNITS.values():
        assert u.iri.startswith("unit:") and u.kind in U.KINDS.values()
        if u.byte_convention:
            assert u.kind == U.INFO


def test_frac_exact():
    assert U.frac(0.1) + U.frac(0.2) == U.frac("0.3")
    for bad in (True, "1e3", float("nan"), float("inf"), None, [1]):
        with pytest.raises(OutOfDomain):
            U.frac(bad)
    assert U.jnum(Fraction(3, 2)) == "3/2" and U.jnum(4) == 4
