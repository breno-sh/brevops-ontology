"""Limites, est, leituras, fração complexa, combinada, escada, Wilson."""
import math

import pytest

from bo.metrics import core, policy as P
from bo.metrics.spec import BINDINGS
from bo.metrics.units import Unit, mk_attrs
from conftest import synth


def u(i, codes, src="aws", dst="google", fam=None, w=1.0, **attrs):
    return Unit(f"U{i:04d}", fam or f"F{i}", f"R{i}", src, dst, codes=tuple(codes), weight=w, attrs=mk_attrs(**attrs))


def test_bounds_formulas_operational():
    us = [u(0, ["carried"]), u(1, ["carried"]), u(2, ["omitted"]), u(3, ["NO_REALIZATION"]),
          u(4, ["UNKNOWN_SYMBOLIC_INPUT"]), u(5, ["INFRA_ERROR"]), u(6, ["CONDITION_FALSE"]), u(7, ["UNKNOWN_INPUT"])]
    b = core.reading("M-OPCOV-DEC", us)["aws->google"]
    assert (b.n, b.lower, b.upper) == (8, 2 / 8, 5 / 8)
    assert b.est == pytest.approx(2 / 5)       # emitidas / (n - desconhecidas)
    assert b.lower <= b.est <= b.upper


def test_outcome_never_changes_denominator():
    base = [u(i, ["carried"]) for i in range(10)]
    for code in ("omitted", "INFRA_ERROR", "NO_UNIT", "UNKNOWN_INPUT"):
        alt = [x.with_codes([code]) if i < 5 else x for i, x in enumerate(base)]
        assert core.reading("M-OPCOV-DEC", alt)["aws->google"].n == 10


def test_unit_combination_failure_dominates():
    t = BINDINGS["M-OPCOV-GRAPH"].table
    assert P.classify_all(["carried", "INFRA_ERROR"], t) == P.BOUNDED
    assert P.classify_all(["carried", "INFRA_ERROR", "REF_OTHER_TARGET"], t) == P.FAILURE
    assert P.classify_all(["carried", "REF_SAME_TARGET"], t) == P.SUCCESS
    with pytest.raises(P.OutcomeError):
        P.classify_all([], t)
    with pytest.raises(P.OutcomeError):
        P.classify_all(["PERSISTED"], t)


def test_complete_unit_unknown_input_is_failure_but_bounded_elsewhere():
    ut = BINDINGS["M-OPCOV-UNIT"].table
    assert P.classify_all(["carried", "UNKNOWN_INPUT"], ut) == P.FAILURE
    assert P.classify_all(["carried", "CONDITION_INDETERMINATE", "COMPLETE"], ut) == P.BOUNDED
    assert P.classify_all(["carried", "COMPLETE"], ut) == P.SUCCESS


def test_persistence_weighted_hajek_and_bounds():
    us = [u(0, ["PERSISTED"], w=10), u(1, ["ALTERED"], w=30), u(2, ["NOT_READABLE"], w=20), u(3, ["PERSISTED"], w=40)]
    b = core.reading("M-PERS-DEC", us)["aws->google"]
    assert b.lower == pytest.approx(50 / 100) and b.upper == pytest.approx(70 / 100)
    assert b.est == pytest.approx(50 / 80) and b.n == 4


def test_empty_and_all_unknown_cells():
    assert core.bounds([], BINDINGS["M-OPCOV-DEC"].table) == core.EMPTY
    b = core.reading("M-PERS-DEC", [u(0, ["UNKNOWN"]), u(1, ["INFRA_ERROR"])])["aws->google"]
    assert (b.lower, b.upper, b.est, b.n) == (0.0, 1.0, None, 2)


def test_duplicate_units_and_bad_weights_rejected():
    with pytest.raises(core.MetricError):
        core.reading("M-OPCOV-DEC", [u(0, ["carried"]), u(0, ["omitted"])])
    with pytest.raises(core.MetricError):
        core.reading("M-PERS-DEC", [u(0, ["PERSISTED"], w=-1)])


def test_non_directional_and_only_oci_and_pilot_sensitivity():
    us = [u(0, ["REPRESENTED"], dst="google"), u(1, ["UNGLOSSED"], dst="oci"),
          u(2, ["REPRESENTED"], src="oci", dst="aws")]
    r = core.reading("M-REPR-DEC", us)
    assert set(r) == {"aws", "oci"} and r["aws"].n == 2
    lo = core.reading("M-LOPO-OPCOV-DEC", [u(0, ["carried"]), u(1, ["carried"], src="oci", dst="aws")])
    assert set(lo) == {"oci->aws"}
    ex = [u(0, ["carried"]), Unit("U9", "F9", "R9", "aws", "google", codes=("omitted",), pilot_exposed=True)]
    assert core.reading("M-OPCOV-DEC", ex)["aws->google"].n == 2
    assert core.reading("M-OPCOV-DEC", ex, exclude_pilot_exposed=True)["aws->google"].n == 1


def test_complex_fraction_bounds():
    us = [u(0, ["carried"], complex=True), u(1, ["carried"], complex=False), u(2, ["carried"], complex=False),
          u(3, ["INFRA_ERROR"]), u(4, ["NO_UNIT"])]
    b = core.complex_fraction(us)["aws->google"]
    assert b.n == 3 and b.est == pytest.approx(1 / 3)
    assert b.lower == pytest.approx(1 / 4) and b.upper == pytest.approx(2 / 4)
    with pytest.raises(core.MetricError):
        core.complex_fraction([u(0, ["carried"])])


def test_combined_is_product_of_bounds():
    oc = core.Bounds(0.4, 0.6, 0.5, 10)
    pe = core.Bounds(0.7, 0.9, 0.8, 5)
    c = core.combined(oc, pe)
    assert (c.lower, c.upper, c.est, c.n) == pytest.approx((0.28, 0.54, 0.4, 10))
    r = core.combined_reading([u(0, ["carried"])], [])
    assert r["aws->google"].lower == 0.0 and r["aws->google"].upper == 1.0   # sem deploy: 0..1, nunca 1


def test_mean_of_directions_and_ladder():
    us = synth(n_fam=5, dirs=(("aws", "google"), ("google", "aws")), seed=1)
    cells = core.reading("M-OPCOV-DEC", us)
    m = core.mean_of_directions(cells)
    assert m.lower == pytest.approx((cells["aws->google"].lower + cells["google->aws"].lower) / 2)
    lad = core.ladder({"M-OPCOV-DEC": {"aws->google": core.Bounds(0.2, 0.3, 0.25, 9)},
                       "M-PERS-DEC": {"aws->google": core.Bounds(0.5, 0.6, 0.55, 3)},
                       "M-REPR-DEC": {"aws": core.Bounds(0.9, 1.0, 0.95, 9)}})
    assert [a["axis"] for a in lad["aws->google"]["axes"]] == ["representability", "operational", "persistence"]
    assert lad["aws->google"]["inversions"] == ["persistence > operational"]


def test_wilson_matches_formula_and_ten_of_ten():
    lo, hi = core.wilson(10, 10)
    assert lo == pytest.approx(0.7225, abs=1e-3) and hi == pytest.approx(1.0)      # PREREG: 10 em 10 dão ≈ 0,72
    us = [u(i, ["OBSERVATIONS_MATCH_UNDER_PROTOCOL"], probe_type="item_ttl") for i in range(8)] + \
         [u(8, ["NOT_OBSERVED_IN_WINDOW"], probe_type="item_ttl"), u(9, ["OBSERVATIONS_DIFFER_UNDER_PROTOCOL"],
                                                                     probe_type="item_ttl")]
    w = core.wilson_bounds(us)["item_ttl"]
    assert w["n"] == 10 and w["lower_ci"] == core.wilson(8, 10) and w["upper_ci"] == core.wilson(9, 10)
