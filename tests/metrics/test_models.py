"""Contrastes pareados, assimetria, logística com efeitos fixos, McNemar, Turnbull, Gini, falso NONE."""
import math

import numpy as np
import pytest
from scipy.stats import binomtest

from bo.metrics import models as MD
from bo.metrics.spec import BINDINGS
from bo.metrics.units import Unit, mk_attrs
from conftest import synth

OP = BINDINGS["M-OPCOV-DEC"].table


def test_paired_contrast_requires_same_denominator():
    a = synth(n_fam=10, seed=1)
    with pytest.raises(MD.DenominatorMismatch):
        MD.paired_contrast(a, a[:-1], OP, OP)


def test_paired_contrast_point_and_ratio_and_bounds_pairing():
    a = synth(n_fam=40, seed=2, p_carried=0.7)
    b = [x.with_codes(["NO_REALIZATION"] if i % 4 == 0 else x.codes) for i, x in enumerate(a)]
    r = MD.paired_contrast(a, b, OP, OP, ratio=0.95, reps=500)["aws->google"]
    from bo.metrics import core
    ca, cb = core.bounds(a, OP), core.bounds(b, OP)
    assert r["point"]["lower"] == pytest.approx(ca.lower - 0.95 * cb.lower)
    assert r["point"]["upper"] == pytest.approx(ca.upper - 0.95 * cb.upper)
    assert r["point"]["ratio_lower"] == pytest.approx(ca.lower / cb.lower)
    lo, hi = r["ci"]["lower"]["two_sided"]
    assert lo <= r["point"]["lower"] <= hi
    pooled = MD.paired_contrast(a, b, OP, OP, pooled=True, reps=200)
    assert set(pooled) == {"all"}


def test_asymmetry_is_antisymmetric():
    us = synth(n_fam=30, dirs=(("aws", "google"), ("google", "aws")), seed=3)
    r = MD.asymmetry(us, OP, reps=300)
    assert set(r) == {"aws->google", "google->aws"}
    assert r["aws->google"]["point"]["lower"] == pytest.approx(-r["google->aws"]["point"]["lower"])
    lo, hi = r["aws->google"]["ci"]["upper"]["two_sided"]
    lo2, hi2 = r["google->aws"]["ci"]["upper"]["two_sided"]
    assert lo == pytest.approx(-hi2) and hi == pytest.approx(-lo2)


def _logit_units(n_fam=120, or_true=0.44, seed=5):
    rng = np.random.default_rng(seed)
    dirs = [("aws", "google"), ("google", "aws"), ("aws", "oci"), ("oci", "azurerm")]
    out = []
    base = {d: rng.normal(0, 0.4) for d in dirs}
    for f in range(n_fam):
        fe = rng.normal(0, 0.3)
        for i in range(8):
            d = dirs[(f + i) % 4]
            g = i % 2
            dom = ["CMP", "STO", "SEC", "NET"][i % 4]
            eta = 0.2 + base[d] + fe + g * math.log(or_true)
            p = 1 / (1 + math.exp(-eta))
            r = rng.random()
            code = "INFRA_ERROR" if r < 0.05 else ("carried" if rng.random() < p else "NO_UNIT")
            out.append(Unit(f"L{f:04d}{i}", f"F{f:04d}", f"R{f:04d}", d[0], d[1], codes=(code,),
                            attrs=mk_attrs(auth_edge=g, domain=dom)))
    return out


def test_fixed_effects_logit_recovers_odds_ratio_and_brackets_bounds():
    us = _logit_units()
    r = MD.fixed_effects_logit(us, OP, "auth_edge", ["pair", "direction", "domain"])
    assert r["lower"]["status"] == r["upper"]["status"] == "ok"
    for b in ("lower", "upper"):
        lo, hi = r[b]["ci_two_sided"]
        assert lo < 0.44 * 1.6 and hi > 0.44 / 1.6
        assert r[b]["upper_one_sided"] < r[b]["ci_two_sided"][1]
    assert r["clusters"] == 120


def test_fixed_effects_forbid_outcome_predictors_and_report_separation():
    us = _logit_units(n_fam=20)
    with pytest.raises(MD.ModelError):
        MD.fixed_effects_logit(us, OP, "auth_edge", ["pair", "loss_type"])
    sep = [Unit(f"S{i}", f"F{i % 5}", "R", "aws", "google", codes=("carried" if i % 2 else "NO_UNIT",),
                attrs=mk_attrs(g=i % 2)) for i in range(40)]
    r = MD.fixed_effects_logit(sep, OP, "g", ["direction"])
    assert r["lower"]["status"] == "not_estimable" and r["lower"]["odds_ratio"] is None


def test_mcnemar_exact_matches_binomtest():
    pairs = [(1, 0)] * 9 + [(0, 1)] * 2 + [(1, 1)] * 20 + [(0, 0)] * 5
    r = MD.mcnemar_exact(pairs)
    assert (r["c3_only"], r["control_only"]) == (9, 2)
    assert r["p_one_sided"] == pytest.approx(binomtest(9, 11, 0.5, alternative="greater").pvalue)


def test_turnbull_right_censored_equals_kaplan_meier():
    rng = np.random.default_rng(9)
    t = np.round(rng.exponential(9, 60), 1) + 0.1
    obs = rng.random(60) < 0.75
    iv = [(float(x) - 1e-6, float(x)) if o else (float(x), math.inf) for x, o in zip(t, obs)]
    fit = MD.turnbull(iv)

    def km(x):  # Kaplan-Meier de referência, escrito à mão
        s = 1.0
        for tt in sorted(set(t[obs])):
            if tt > x:
                break
            d = int(((t == tt) & obs).sum())
            n = int((t >= tt).sum())
            s *= 1 - d / n
        return s
    cum = np.cumsum(fit["mass"])
    checked = 0
    for (a, b), c in zip(fit["intervals"], cum):
        if math.isfinite(b):
            assert 1 - c == pytest.approx(km(b), abs=1e-6)
            checked += 1
    assert checked > 10


def test_turnbull_truncation_and_median_ci():
    iv = [(0, 3), (3, 6), (6, 9), (9, 12), (12, math.inf), (3, 6), (6, 9), (9, 12)]
    fit = MD.turnbull(iv)
    assert sum(fit["mass"]) == pytest.approx(1.0)
    tr = MD.turnbull(iv, truncation=[0, 0, 0, 0, 0, 3, 6, 9])
    assert tr["mass"] != fit["mass"]
    m = MD.turnbull_median(iv, reps=200)
    assert m["median"] == 6 and m["lower_one_sided"] <= m["median"]
    with pytest.raises(MD.ModelError):
        MD.turnbull([(5, 5)])
    with pytest.raises(MD.ModelError):
        MD.turnbull([(1, 5)], truncation=[2])


def test_gini_values_and_ambiguous_range():
    assert MD.gini([5, 5, 5, 5]) == 0.0
    assert MD.gini([0, 0, 0, 8]) == pytest.approx(0.75)
    r = MD.gini_range({"aws": 10, "google": 8, "azurerm": 8, "oci": 4}, {"oci": 4, "aws": 1})
    assert r["gini_min"] <= r["gini_unambiguous"] <= r["gini_max"]
    assert r["gini_min"] == pytest.approx(MD.gini([10, 8, 8, 8]))
    assert r["gini_max"] == pytest.approx(MD.gini([11, 8, 8, 4]))
    assert "nunca neutralidade" in r["label"]


def test_none_false_weighted_bounds():
    us = [Unit("N1", "F1", "R1", "aws", "oci", codes=("FALSE_NONE",), weight=2),
          Unit("N2", "F2", "R2", "aws", "oci", codes=("TRUE_NONE",), weight=6),
          Unit("N3", "F3", "R3", "aws", "oci", codes=("UNDECIDED",), weight=2)]
    r = MD.none_false(us)["aws->oci"]
    assert (r["lower"], r["upper"], r["est"], r["n"]) == pytest.approx((0.2, 0.4, 0.25, 3))
