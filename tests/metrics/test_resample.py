"""Bootstrap por cluster (conjunto), CR2, permutação."""
import numpy as np
import pytest

from bo.metrics import policy as P, resample as RS
from bo.metrics.spec import BINDINGS
from bo.metrics.units import Unit
from conftest import synth

OP = BINDINGS["M-OPCOV-DEC"].table


def dir_cell(u):
    return f"{u.source}->{u.target}"


def test_multiplicities_are_resamples_and_deterministic():
    M = RS.multiplicities(17, reps=200, seed=5)
    assert M.shape == (200, 17) and (M.sum(1) == 17).all()
    assert (RS.multiplicities(17, reps=200, seed=5) == M).all()
    assert not (RS.multiplicities(17, reps=200, seed=6) == M).all()


def test_bootstrap_cells_brackets_point_and_respects_clusters():
    us = synth(n_fam=60, per_fam=8, seed=11, fam_sd=0.35)
    tab = RS.ClusterTable("family").add("m", us, OP, dir_cell)
    ci = RS.bootstrap_cells("m", tab, reps=1000)["aws->google"]
    pt = RS.bound_stats(tab.matrix("m", "aws->google", tab.clusters()).sum(0))
    for k in ("lower", "upper", "est"):
        lo, hi = ci[k]["two_sided"]
        assert lo <= float(pt[k]) <= hi
    # cluster de unidade (cada decisão sozinha) subestima a incerteza com efeito de família
    tab_u = RS.ClusterTable("resource").add("m", us, OP, dir_cell)
    ci_u = RS.bootstrap_cells("m", tab_u, reps=1000)["aws->google"]
    w_fam = np.diff(ci["lower"]["two_sided"])[0]
    w_unit = np.diff(ci_u["lower"]["two_sided"])[0]
    assert w_fam > w_unit


def test_joint_bootstrap_shares_draws():
    a = synth(n_fam=40, seed=1, prefix="A")
    tab = RS.ClusterTable("family").add("a", a, OP, dir_cell).add("b", a, OP, dir_cell)

    def stat(get):
        la = RS.bound_stats(get("a", "aws->google"))["lower"]
        lb = RS.bound_stats(get("b", "aws->google"))["lower"]
        return {"diff": la - lb}
    out = RS.joint_bootstrap(tab, stat, reps=500)
    assert out["diff"]["two_sided"] == [0.0, 0.0]   # mesmas famílias nas duas séries: diferença exata 0


def _cr2_bruteforce(y, w, g):
    y, w, g = map(np.asarray, (y, w, g))
    W = np.diag(w)
    X = np.ones((len(y), 1))
    XtWX = X.T @ W @ X
    beta = np.linalg.solve(XtWX, X.T @ W @ y)
    e = y - X @ beta
    meat = np.zeros((1, 1))
    for k in sorted(set(g.tolist())):
        m = g == k
        Xg, Wg, eg = X[m], np.diag(w[m]), e[m]
        Xt = np.sqrt(Wg) @ Xg
        H = Xt @ np.linalg.inv(XtWX) @ Xt.T
        vals, vecs = np.linalg.eigh(np.eye(len(eg)) - H)
        A = vecs @ np.diag(vals ** -0.5) @ vecs.T
        s = Xt.T @ A @ np.sqrt(Wg) @ eg
        meat += np.outer(s, s)
    V = np.linalg.inv(XtWX) @ meat @ np.linalg.inv(XtWX)
    return float(beta[0]), float(np.sqrt(V[0, 0]))


def test_cr2_matches_matrix_formula():
    rng = np.random.default_rng(3)
    y = rng.integers(0, 2, 60).astype(float)
    w = rng.uniform(0.5, 3, 60)
    g = rng.integers(0, 9, 60)
    r = RS.cr2_mean(y, w, g)
    mu, se = _cr2_bruteforce(y, w, g)
    assert r["mean"] == pytest.approx(mu) and r["se"] == pytest.approx(se, rel=1e-9)
    assert r["df"] == len(set(g.tolist())) - 1


def test_small_cells_use_cr2_and_are_flagged():
    us = synth(n_fam=12, per_fam=5, seed=4)
    out = RS.interval_cells(us, OP, dir_cell, reps=300)["aws->google"]
    assert out["method"] == "cr2_t" and out["small_cluster"] and out["clusters"] == 12
    big = RS.interval_cells(synth(n_fam=35, per_fam=3, seed=4), OP, dir_cell, reps=300)["aws->google"]
    assert big["method"] == "bootstrap_percentile" and not big["small_cluster"]


def test_cr2_single_cluster_is_not_estimable():
    r = RS.cr2_mean([1, 0, 1], [1, 1, 1], ["a", "a", "a"])
    assert r["se"] is None and r["two_sided"] == [None, None]


def test_permutation_test_null_and_effect():
    ab = synth(n_fam=30, p_carried=0.5, dirs=(("aws", "google"),), seed=21, prefix="X")
    ba = synth(n_fam=30, p_carried=0.5, dirs=(("google", "aws"),), seed=22, prefix="Y")
    null = RS.direction_permutation_test(ab, ba, OP, "lower", perms=2000)
    ba_hi = synth(n_fam=30, p_carried=0.9, dirs=(("google", "aws"),), seed=22, prefix="Y")
    eff = RS.direction_permutation_test(ab, ba_hi, OP, "lower", perms=2000)
    assert null["p_two_sided"] > 0.05 and eff["p_two_sided"] < 0.01
    again = RS.direction_permutation_test(list(reversed(ab)), ba_hi, OP, "lower", perms=2000)
    assert again == eff


def test_missing_cluster_label_is_error():
    with pytest.raises(RS.ResampleError):
        RS.ClusterTable("graph").add("m", [Unit("u", "F", "R", "aws", "google", codes=("carried",))], OP, dir_cell)
