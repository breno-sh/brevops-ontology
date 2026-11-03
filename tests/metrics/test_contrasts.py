"""Regras de decisão dos 15 contrastes."""
import pytest

from bo.metrics import contrasts as CT, models as MD, resample as RS
from bo.metrics.spec import BINDINGS
from conftest import synth

OP = BINDINGS["M-OPCOV-DEC"].table


def ci(lo1=None, up1=None, two=(None, None), p=None):
    return {"lower_one_sided": lo1, "upper_one_sided": up1, "two_sided": list(two), "p_zero_two_sided": p}


def test_holm():
    assert CT.holm({"a": 0.001, "b": 0.02, "c": 0.04}) == {"a": True, "b": True, "c": True}
    assert CT.holm({"a": 0.001, "b": 0.04, "c": 0.04}) == {"a": True, "b": False, "c": False}


def test_h1_all_directions_required():
    cells = {f"d{i}": {"upper": ci(up1=0.6)} for i in range(12)}
    assert CT.judge_h1(cells)["verdict"] == "supported"
    cells["d3"]["upper"]["upper_one_sided"] = 0.71
    assert CT.judge_h1(cells)["verdict"] == "not_supported"


def test_h1_on_synthetic_data_end_to_end():
    us = synth(n_fam=40, p_carried=0.3, p_unknown=0.05, seed=8)
    cells = RS.interval_cells(us, OP, lambda u: f"{u.source}->{u.target}", reps=500)
    assert CT.judge_h1(cells)["verdict"] == "supported"
    hi = synth(n_fam=40, p_carried=0.9, seed=8)
    assert CT.judge_h1(RS.interval_cells(hi, OP, lambda u: f"{u.source}->{u.target}", reps=500))["verdict"] \
        == "not_supported"


def test_h2_count_and_same_sign_and_indeterminate():
    def entry(pl, pu, cl, cu):
        return {"point": {"lower": pl, "upper": pu}, "ci": {"lower": ci(two=cl), "upper": ci(two=cu)}}
    asym = {}
    pairs = [("a", "b"), ("a", "c"), ("a", "d"), ("b", "c"), ("b", "d"), ("c", "d")]
    for i, (x, y) in enumerate(pairs):
        e = entry(0.1, 0.12, (0.02, 0.2), (0.03, 0.2)) if i < 4 else entry(0.01, 0.0, (-0.1, 0.1), (-0.1, 0.1))
        asym[f"{x}->{y}"] = e
        asym[f"{y}->{x}"] = entry(-0.1, -0.12, (-0.2, -0.02), (-0.2, -0.03))
    r = CT.judge_h2(asym)
    assert r["count"] == 4 and r["verdict"] == "supported"
    asym["a->b"] = entry(0.1, -0.1, (0.02, 0.2), (-0.2, -0.02))   # sinais opostos nos dois limites
    r = CT.judge_h2(asym)
    assert r["per_unit"]["a<->b"] == "indeterminate_by_unknown"


def test_both_bounds_rule():
    assert CT._both(True, True) == "supported"
    assert CT._both(False, False) == "not_supported"
    assert CT._both(True, False) == "indeterminate_by_unknown"


def test_h3_h4_h5_h6_h8_h9():
    assert CT.judge_h3({"lower": {"status": "ok", "upper_one_sided": 0.8},
                        "upper": {"status": "ok", "upper_one_sided": 1.2}})["verdict"] == "indeterminate_by_unknown"
    assert CT.judge_h4({"upper": ci(up1=0.85)})["verdict"] == "supported"
    assert CT.judge_h5({"lower_one_sided": 7.0})["verdict"] == "supported"
    assert CT.judge_h6_cov({"all": {"ci": {"lower": ci(lo1=-0.01), "upper": ci(lo1=-0.015)}}})["verdict"] == "supported"
    assert CT.judge_h8({"lower": ci(lo1=0.09)})["verdict"] == "not_supported"
    fam = {"f1": {"c2": {"p_one_sided": 0.001}, "c1": {"p_one_sided": 0.0001}},
           "f2": {"c2": {"p_one_sided": 0.01}, "c1": {"p_one_sided": 0.0001}}}
    r = CT.judge_h9(fam)
    assert r["per_unit"] == {"f1": True, "f2": False} and r["verdict"] == "supported"


def test_h7_and_lopo_counting_with_real_paired_contrast():
    dirs = [(a, b) for a in ("aws", "google", "azurerm", "oci") for b in ("aws", "google", "azurerm", "oci") if a != b]
    ont = synth(n_fam=35, per_fam=4, p_carried=0.6, dirs=dirs, seed=12)
    direct = [u.with_codes(["carried"] if u.codes == ("carried",) else u.codes) for u in ont]
    p = MD.paired_contrast(ont, direct, OP, OP, ratio=0.95, reps=400)
    r = CT.judge_h7(p)
    assert r["required"] == 10 and r["count"] >= 10 and r["verdict"] == "supported"
    lo = CT.judge_lopo(MD.paired_contrast(ont, direct, OP, OP, ratio=0.90, reps=400))
    assert set(lo["per_unit"]) == {d for d in p if "oci" in d} and len(lo["per_unit"]) == 6


def test_abl_effect_equivalence_inconclusive():
    def arm(p, lo1, up1):
        c = ci(lo1=lo1, up1=up1, p=p)
        return {"all": {"ci": {"lower": c, "upper": c}}}
    r = CT.judge_abl({"eff": arm(0.0001, 0.05, 0.1), "eq": arm(0.6, -0.01, 0.01), "inc": arm(0.3, -0.05, 0.08)})
    assert r["per_unit"] == {"eff": "effect", "eq": "hygiene_equivalent", "inc": "inconclusive"}
