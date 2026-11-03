"""Estimandos e testes do pré-registro que não são uma proporção simples.

  paired_contrast   diferença (ou razão) pareada por decisão entre duas métricas do mesmo denominador,
                    nos dois limites (inferior com inferior, superior com superior), bootstrap conjunto
                    por família (E-HUBLOSS, C-H6-COV, C-H7, C-LOPO, C-ABL, C-RQ5-TRANS, C-TOOL)
  asymmetry         E-ASYM: Y(A->B) - Y(B->A) por par, populações independentes, famílias reamostradas juntas
  fixed_effects_logit  E-OR-AUTH: logística por decisão com efeitos fixos (par, direção, domínio, grão, papel,
                    cardinalidade), erro-padrão robusto por família, ajustada no limite inferior e no superior;
                    'tipo de perda' e qualquer coisa derivada do desfecho não podem ser preditores
  mcnemar_exact     C-H9: McNemar exato unilateral pareado por caso
  turnbull_median   E-DRIFT-LAG: NPMLE de Turnbull com censura intervalar e truncamento à esquerda
  gini_range        E-GINI-BALANCE: Gini de 4 contagens, mínimo e máximo com as realizações AMBIGUOUS
  none_false        E-NONE-FALSE: taxa de falso NONE com pesos de inclusão (Hájek); UNDECIDED no intervalo
"""
from __future__ import annotations

import itertools
import math
from collections import defaultdict

import numpy as np
from scipy.stats import binom, norm

from . import policy as P
from .core import bounds
from .resample import ClusterTable, bound_stats, joint_bootstrap, multiplicities, percentile_ci
from .spec import LEVEL, N_BOOT, SEED_BOOT, direction_key
from .units import Unit


class ModelError(ValueError):
    pass


class DenominatorMismatch(ModelError):
    """As duas métricas de um contraste pareado não têm o mesmo conjunto de decisões."""


def _by_dir(u: Unit) -> str:
    return direction_key(u.source, u.target)


def _pooled(u: Unit) -> str:
    return "all"


# ------------------------------------------------------------------------------------------------- pareado
def paired_contrast(units_a, units_b, table_a: dict, table_b: dict, ratio: float = 1.0, pooled: bool = False,
                    cluster: str = "family", reps: int = N_BOOT, seed: int = SEED_BOOT,
                    level: float = LEVEL) -> dict:
    """D = Y_a - ratio·Y_b por célula (direção, ou todas juntas com pooled=True), em lower, upper e est.

    O denominador é o mesmo dos dois lados (fixado na origem): conjuntos de decisões diferentes reprovam."""
    ida = sorted(u.unit_id for u in units_a)
    idb = sorted(u.unit_id for u in units_b)
    if ida != idb:
        raise DenominatorMismatch(f"{len(set(ida) ^ set(idb))} decisão(ões) só de um lado")
    cell_of = _pooled if pooled else _by_dir
    tab = ClusterTable(cluster).add("a", units_a, table_a, cell_of).add("b", units_b, table_b, cell_of)
    cells = sorted({c for (_, c) in tab.keys()})
    point = {}
    for c in cells:
        sa = bound_stats(tab.matrix("a", c, tab.clusters()).sum(0))
        sb = bound_stats(tab.matrix("b", c, tab.clusters()).sum(0))
        point[c] = {k: _f(sa[k] - ratio * sb[k]) for k in ("lower", "upper", "est")}
        point[c].update({f"ratio_{k}": _f(_div(sa[k], sb[k])) for k in ("lower", "upper", "est")})

    def stat(get):
        out = {}
        for c in cells:
            sa, sb = bound_stats(get("a", c)), bound_stats(get("b", c))
            for k in ("lower", "upper", "est"):
                out[f"{c}|{k}"] = sa[k] - ratio * sb[k]
                out[f"{c}|ratio_{k}"] = _div(sa[k], sb[k])
        return out

    ci = joint_bootstrap(tab, stat, reps, seed, level)
    out = {}
    for c in cells:
        n = int(tab.matrix("a", c, tab.clusters())[:, 3].sum())
        out[c] = {"n": n, "ratio_coef": ratio, "point": point[c],
                  "ci": {k: ci[f"{c}|{k}"] for k in ("lower", "upper", "est", "ratio_lower", "ratio_upper",
                                                      "ratio_est")}}
    return out


def _div(a, b):
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(np.asarray(b) > 0, np.asarray(a) / np.where(np.asarray(b) > 0, b, 1), np.nan)


def _f(x):
    x = float(x)
    return x if math.isfinite(x) else None


# ------------------------------------------------------------------------------------------------- assimetria
def asymmetry(units, table: dict, reps: int = N_BOOT, seed: int = SEED_BOOT, level: float = LEVEL,
              cluster: str = "family") -> dict:
    """E-ASYM: para cada direção A->B com a inversa presente, Y(A->B) - Y(B->A) nos dois limites.

    As duas orientações de cada par aparecem (antissimétricas): a saída não depende de que provedor tem o
    nome menor, o que mantém o teste de renomeação byte a byte. As famílias das duas direções são reamostradas
    juntas (uma família pode ter as duas origens)."""
    tab = ClusterTable(cluster).add("m", units, table, _by_dir)
    dirs = {c for (_, c) in tab.keys()}
    ordered = sorted(d for d in dirs if "->".join(reversed(d.split("->"))) in dirs)
    cl = tab.clusters()

    def inv(d):
        return "->".join(reversed(d.split("->")))

    point = {}
    for d in ordered:
        sa = bound_stats(tab.matrix("m", d, cl).sum(0))
        sb = bound_stats(tab.matrix("m", inv(d), cl).sum(0))
        point[d] = {k: _f(sa[k] - sb[k]) for k in ("lower", "upper", "est")}

    def stat(get):
        out = {}
        for d in ordered:
            sa, sb = bound_stats(get("m", d)), bound_stats(get("m", inv(d)))
            for k in ("lower", "upper", "est"):
                out[f"{d}|{k}"] = sa[k] - sb[k]
        return out

    ci = joint_bootstrap(tab, stat, reps, seed, level)
    return {d: {"minus": inv(d), "point": point[d], "ci": {k: ci[f"{d}|{k}"] for k in ("lower", "upper", "est")}}
            for d in ordered}


# ------------------------------------------------------------------------------------------------- logística
FORBIDDEN_PREDICTORS = frozenset({"loss_type", "tipo_de_perda", "block_code", "result", "outcome", "codes",
                                  "emitted", "carried"})


def fixed_effects_logit(units, table: dict, group_attr: str, fixed_effects: list[str],
                        cluster: str = "family", level: float = LEVEL) -> dict:
    """Razão de chances de emissão (grupo 1 contra grupo 0) com efeitos fixos, ajustada duas vezes.

    units: decisões com attr group_attr em {0, 1} (outras ficam fora) e os attrs de efeito fixo. O desfecho no
    limite inferior trata desconhecido como 0; no superior, como 1."""
    import pandas as pd
    import statsmodels.api as sm

    bad = FORBIDDEN_PREDICTORS & ({group_attr} | set(fixed_effects))
    if bad:
        raise ModelError(f"preditor proibido (recodifica o desfecho): {sorted(bad)}")
    rows = []
    for u in sorted(units, key=lambda x: x.unit_id):
        g = u.attr(group_attr)
        if g not in (0, 1):
            continue
        c = P.classify_all(u.codes, table)
        rows.append({"y_lower": int(c == P.SUCCESS), "y_upper": int(c != P.FAILURE), "group": int(g),
                     "cluster": {"family": u.family_id, "repository": u.repo_id}[cluster],
                     **{fe: str(u.attr(fe) if fe not in ("pair", "direction") else
                               _fe_value(u, fe)) for fe in fixed_effects}})
    if not rows:
        raise ModelError("nenhuma decisão nos dois grupos")
    df = pd.DataFrame(rows)
    X = pd.DataFrame({"const": 1.0, "group": df["group"].astype(float)})
    for fe in fixed_effects:
        levels = sorted(df[fe].unique())
        for lv in levels[1:]:
            X[f"{fe}={lv}"] = (df[fe] == lv).astype(float)
    # efeito fixo aninhado em outro (par dentro de direção) é colinear: a coluna redundante sai, em ordem fixa
    keep, dropped = [], []
    for col in X.columns:
        trial = X[keep + [col]].to_numpy()
        if np.linalg.matrix_rank(trial) > len(keep):
            keep.append(col)
        else:
            dropped.append(col)
    if "group" not in keep:
        raise ModelError("grupo colinear com os efeitos fixos")
    X = X[keep]
    groups = pd.factorize(df["cluster"], sort=True)[0]
    out = {"n": len(df), "clusters": int(len(set(groups))), "fixed_effects": list(fixed_effects),
           "collinear_dropped": dropped}
    z2 = norm.ppf(1 - (1 - level) / 2)
    z1 = norm.ppf(level)
    for bound in ("lower", "upper"):
        y = df[f"y_{bound}"].astype(float)
        if y.nunique() < 2:
            out[bound] = {"status": "degenerate", "odds_ratio": None}
            continue
        try:
            import warnings
            with warnings.catch_warnings():
                warnings.simplefilter("error")
                res = sm.GLM(y, X, family=sm.families.Binomial()).fit(cov_type="cluster",
                                                                     cov_kwds={"groups": groups})
            b, se = float(res.params["group"]), float(res.bse["group"])
            if not (math.isfinite(b) and math.isfinite(se)):
                raise FloatingPointError("não finito")
            out[bound] = {"status": "ok", "log_odds": b, "se_cluster": se, "odds_ratio": math.exp(b),
                          "ci_two_sided": [math.exp(b - z2 * se), math.exp(b + z2 * se)],
                          "upper_one_sided": math.exp(b + z1 * se)}
        except Exception as e:  # separação perfeita, matriz singular: relatado, nunca forçado
            out[bound] = {"status": "not_estimable", "reason": type(e).__name__, "odds_ratio": None}
    return out


def _fe_value(u: Unit, fe: str) -> str:
    if fe == "direction":
        return f"{u.source}->{u.target}"
    return "|".join(sorted((u.source, u.target)))   # par não ordenado, sem depender do nome do C00


# ------------------------------------------------------------------------------------------------- McNemar
def mcnemar_exact(pairs) -> dict:
    """pairs: [(c3_correto, controle_correto)] por caso -> p unilateral (c3 melhor) exato."""
    b = sum(1 for x, y in pairs if x and not y)
    c = sum(1 for x, y in pairs if y and not x)
    n = b + c
    p = float(binom.sf(b - 1, n, 0.5)) if n else 1.0
    return {"n_cases": len(pairs), "c3_only": b, "control_only": c, "p_one_sided": p}


# ------------------------------------------------------------------------------------------------- Turnbull
def turnbull(intervals, truncation=None, tol: float = 1e-10, max_iter: int = 20000) -> dict:
    """NPMLE de Turnbull (1976) para eventos em (L, R] com R = inf (censura à direita) e truncamento à
    esquerda: o evento i só é observável se for maior que truncation[i]. Devolve os intervalos mais internos
    e as massas."""
    L = np.asarray([x[0] for x in intervals], dtype=float)
    R = np.asarray([x[1] for x in intervals], dtype=float)
    if np.any(L >= R):
        raise ModelError("intervalo com L >= R")
    T = np.full_like(L, -np.inf) if truncation is None else np.asarray(truncation, dtype=float)
    if np.any(T > L):
        raise ModelError("truncamento depois do início do intervalo")
    # intervalos mais internos (q, p]: um L seguido imediatamente de um R na ordem (R antes de L no empate,
    # porque (L, R] exclui L)
    pts = sorted([(x, 1) for x in L] + [(x, 0) for x in R])
    inner = []
    for (x1, k1), (x2, k2) in zip(pts, pts[1:]):
        if k1 == 1 and k2 == 0 and x1 < x2:
            inner.append((x1, x2))
    inner = sorted(set(inner))
    q = np.array([a for a, _ in inner])
    p = np.array([b for _, b in inner])
    alpha = ((q[None, :] >= L[:, None]) & (p[None, :] <= R[:, None])).astype(float)
    beta = (q[None, :] >= T[:, None]).astype(float)
    m = len(inner)
    s = np.full(m, 1.0 / m)
    for _ in range(max_iter):
        a_den = alpha @ s
        b_den = beta @ s
        mu = alpha * s / a_den[:, None]
        nu = (1 - beta) * s / b_den[:, None]
        tot = mu.sum(0) + nu.sum(0)
        s_new = tot / tot.sum()
        if np.max(np.abs(s_new - s)) < tol:
            s = s_new
            break
        s = s_new
    return {"intervals": [[float(a), float(b)] for a, b in inner], "mass": [float(x) for x in s]}


def _median_from(fit: dict) -> float:
    """Mediana conservadora: extremo esquerdo do intervalo mais interno onde a acumulada passa de 0,5."""
    acc = 0.0
    for (a, b), w in zip(fit["intervals"], fit["mass"]):
        acc += w
        if acc >= 0.5 - 1e-12:
            return a
    return math.inf


def turnbull_median(intervals, truncation=None, reps: int = N_BOOT, seed: int = SEED_BOOT,
                    level: float = LEVEL) -> dict:
    fit = turnbull(intervals, truncation)
    med = _median_from(fit)
    n = len(intervals)
    M = multiplicities(n, reps, seed)
    meds = []
    for row in M:
        idx = np.repeat(np.arange(n), row)
        try:
            f = turnbull([intervals[i] for i in idx], None if truncation is None else [truncation[i] for i in idx])
            meds.append(_median_from(f))
        except ModelError:
            meds.append(np.nan)
    meds = np.asarray(meds, dtype=float)
    meds[~np.isfinite(meds)] = np.inf  # mediana além da última versão: censurada à direita
    q = float(np.quantile(meds, 1 - level, method="lower"))
    return {"median": med, "lower_one_sided": q, "n_events": n, "fit": fit}


# ------------------------------------------------------------------------------------------------- Gini
def gini(counts) -> float:
    x = np.asarray(counts, dtype=float)
    if x.sum() == 0:
        return 0.0
    n = len(x)
    return float(np.abs(x[:, None] - x[None, :]).sum() / (2 * n * n * x.mean()))


def gini_range(counts: dict, ambiguous: dict | None = None, max_grid: int = 2_000_000) -> dict:
    """Gini das contagens de classes realizadas por provedor; cada realização AMBIGUOUS conta ou não para o
    seu provedor (os dois sentidos): mínimo e máximo exatos por enumeração da grade inteira."""
    provs = sorted(counts)
    amb = {p: int((ambiguous or {}).get(p, 0)) for p in provs}
    size = math.prod(amb[p] + 1 for p in provs)
    if size > max_grid:
        raise ModelError(f"grade de AMBIGUOUS grande demais ({size})")
    grids = np.array(list(itertools.product(*[range(amb[p] + 1) for p in provs])), dtype=float)
    base = np.array([counts[p] for p in provs], dtype=float)
    X = grids + base
    n = len(provs)
    tot = X.sum(1)
    num = np.abs(X[:, :, None] - X[:, None, :]).sum((1, 2))
    g = np.where(tot > 0, num / (2 * n * np.where(tot > 0, tot, 1)), 0.0)
    return {"providers": provs, "gini_unambiguous": gini(base), "gini_min": float(g.min()),
            "gini_max": float(g.max()), "label": "equilíbrio de contagens (nunca neutralidade)"}


# ------------------------------------------------------------------------------------------------- falso NONE
def none_false(units) -> dict:
    """E-NONE-FALSE por direção: códigos FALSE_NONE (existe alvo correto em B), TRUE_NONE, UNDECIDED; pesos de
    inclusão do DISPUTE-SAMPLE. Nunca somada à cobertura."""
    table = P.none_audit_table()
    cells = defaultdict(list)
    for u in units:
        cells[_by_dir(u)].append(u)
    return {k: bounds(cells[k], table, weighted=True).as_dict() for k in sorted(cells)}
