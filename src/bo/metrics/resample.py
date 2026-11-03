"""Reamostragem por cluster e intervalos (PREREG §5).

  primária        bootstrap por família (cluster de topo), 4000 réplicas, percentil, SEED-BOOT
  sensibilidade   por repositório, por grafo; na persistência também por recurso
  conjunta        métricas do mesmo contraste reamostradas com as MESMAS famílias (mesma matriz de
                  multiplicidades), o que propaga a incerteza entre cobertura e persistência
  < 30 famílias   IC t com erro robusto por cluster, correção CR2 (Bell-McCaffrey), gl = G - 1; marcado
  permutação      rótulos de direção trocados dentro do par no nível da família, 10000, SEED-PERM

O gerador depende só da semente e do número de clusters; os clusters entram em ordem de id. Renomear
provedores ou reordenar registros não muda nenhum número.
"""
from __future__ import annotations

import math
from collections import defaultdict

import numpy as np
from scipy.stats import t as tdist

from . import policy as P
from .spec import LEVEL, N_BOOT, N_PERM, SEED_BOOT, SEED_PERM, SMALL_CLUSTER

CLUSTERS = {"family": "family_id", "repository": "repo_id", "graph": "graph_id", "resource": "resource_id"}
IDX = {P.SUCCESS: 0, P.FAILURE: 1, P.BOUNDED: 2}


class ResampleError(ValueError):
    pass


def cluster_of(u, cluster: str) -> str:
    v = getattr(u, CLUSTERS[cluster])
    if v is None:
        raise ResampleError(f"{u.unit_id}: sem rótulo de cluster {cluster}")
    return v


def multiplicities(n_clusters: int, reps: int = N_BOOT, seed: int = SEED_BOOT) -> np.ndarray:
    """Matriz reps x G de quantas vezes cada cluster entra em cada réplica (sorteio com reposição)."""
    if n_clusters == 0:
        return np.zeros((reps, 0), dtype=np.int64)
    rng = np.random.Generator(np.random.PCG64(seed))
    draws = rng.integers(0, n_clusters, size=(reps, n_clusters))
    out = np.zeros((reps, n_clusters), dtype=np.int64)
    np.add.at(out, (np.repeat(np.arange(reps), n_clusters), draws.ravel()), 1)
    return out


class ClusterTable:
    """Somas ponderadas (S, F, B, n) por cluster e por célula, de um ou mais conjuntos de unidades."""

    def __init__(self, cluster: str = "family"):
        self.cluster = cluster
        self.data: dict[tuple, dict[str, list]] = {}   # (nome, célula) -> {cluster: [S, F, B, n]}

    def add(self, name: str, units, table: dict, cell_of, weighted: bool = False):
        for u in units:
            c = P.classify_all(u.codes, table)
            w = u.weight if weighted else 1.0
            row = self.data.setdefault((name, cell_of(u)), {}).setdefault(cluster_of(u, self.cluster),
                                                                          [[], [], [], 0])
            row[IDX[c]].append(w)
            row[3] += 1
        return self

    def add_values(self, name: str, units, value_of, cell_of):
        """Valores contínuos por unidade (ex.: diferença pareada): guarda [Σy, 0, 0, n]."""
        for u in units:
            row = self.data.setdefault((name, cell_of(u)), {}).setdefault(cluster_of(u, self.cluster),
                                                                          [[], [], [], 0])
            row[0].append(float(value_of(u)))
            row[3] += 1
        return self

    def clusters(self) -> list[str]:
        return sorted({g for d in self.data.values() for g in d})

    def matrix(self, name: str, cell: str, clusters: list[str]) -> np.ndarray:
        d = self.data.get((name, cell), {})
        out = np.zeros((len(clusters), 4))
        for i, g in enumerate(clusters):
            if g in d:
                r = d[g]
                out[i] = [math.fsum(r[0]), math.fsum(r[1]), math.fsum(r[2]), r[3]]
        return out

    def keys(self):
        return sorted(self.data)


def _ratio(num, den):
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(den > 0, num / np.where(den > 0, den, 1), np.nan)


def bound_stats(sums: np.ndarray) -> dict[str, np.ndarray]:
    """sums: (..., 4) = S, F, B, n -> lower, upper, est (nan quando indefinido)."""
    s, f, b = sums[..., 0], sums[..., 1], sums[..., 2]
    tot = s + f + b
    return {"lower": _ratio(s, tot), "upper": _ratio(s + b, tot), "est": _ratio(s, s + f)}


def percentile_ci(reps: np.ndarray, level: float = LEVEL) -> dict:
    ok = reps[np.isfinite(reps)]
    a = 1 - level
    if ok.size == 0:
        return {"two_sided": [None, None], "upper_one_sided": None, "lower_one_sided": None,
                "p_zero_two_sided": None, "undefined_replicates": int(reps.size)}
    q = np.quantile(ok, [a / 2, 1 - a / 2, 1 - a, a], method="linear")
    p0 = min(1.0, 2 * min(float((ok <= 0).mean()), float((ok >= 0).mean())))
    return {"two_sided": [float(q[0]), float(q[1])], "upper_one_sided": float(q[2]),
            "lower_one_sided": float(q[3]), "p_zero_two_sided": p0,
            "undefined_replicates": int(reps.size - ok.size)}


def joint_bootstrap(table: ClusterTable, stat, reps: int = N_BOOT, seed: int = SEED_BOOT,
                    level: float = LEVEL) -> dict:
    """stat(get) -> {nome: array(reps)}; get(nome, célula) devolve as somas reamostradas (reps, 4).

    Todas as séries usam a mesma matriz de multiplicidades: incerteza conjunta."""
    clusters = table.clusters()
    M = multiplicities(len(clusters), reps, seed)
    cache = {}

    def get(name, cell):
        k = (name, cell)
        if k not in cache:
            cache[k] = M @ table.matrix(name, cell, clusters)
        return cache[k]

    out = stat(get)
    return {k: percentile_ci(np.asarray(v, dtype=float), level) for k, v in sorted(out.items())}


def bootstrap_cells(name: str, table: ClusterTable, reps: int = N_BOOT, seed: int = SEED_BOOT,
                    level: float = LEVEL) -> dict:
    """IC percentil de lower, upper e est de cada célula de um conjunto (reamostragem conjunta das células)."""
    cells = [c for (n, c) in table.keys() if n == name]

    def stat(get):
        out = {}
        for c in cells:
            for k, v in bound_stats(get(name, c)).items():
                out[f"{c}|{k}"] = v
        return out

    flat = joint_bootstrap(table, stat, reps, seed, level)
    res = defaultdict(dict)
    for k, v in flat.items():
        c, b = k.rsplit("|", 1)
        res[c][b] = v
    return dict(res)


# ------------------------------------------------------------------------------------------------- CR2
def cr2_mean(y, w, g, level: float = LEVEL) -> dict:
    """Média ponderada (razão Σw·y/Σw) com variância robusta por cluster CR2 e IC t com G - 1 gl.

    No modelo só com intercepto, (I - H_gg)^(-1/2) aplicado ao resíduo do cluster g multiplica a soma
    ponderada dos resíduos por 1/sqrt(1 - W_g/W); V = Σ_g (Σ_{i∈g} w_i e_i)^2 / (1 - W_g/W) / W^2."""
    y = np.asarray(y, dtype=float)
    w = np.asarray(w, dtype=float)
    g = np.asarray(g)
    W = w.sum()
    if W <= 0:
        return {"mean": None, "se": None, "df": 0, "two_sided": [None, None], "upper_one_sided": None,
                "lower_one_sided": None}
    mu = float((w * y).sum() / W)
    e = y - mu
    groups = sorted(set(g.tolist()))
    G = len(groups)
    if G < 2:
        return {"mean": mu, "se": None, "df": 0, "two_sided": [None, None], "upper_one_sided": None,
                "lower_one_sided": None}
    v = 0.0
    for k in groups:
        m = g == k
        Wg = w[m].sum()
        adj = 1.0 - Wg / W
        if adj <= 1e-12:
            return {"mean": mu, "se": None, "df": G - 1, "two_sided": [None, None], "upper_one_sided": None,
                    "lower_one_sided": None}
        v += float((w[m] * e[m]).sum()) ** 2 / adj
    v /= W * W
    se = math.sqrt(v)
    df = G - 1
    a = 1 - level
    t2 = float(tdist.ppf(1 - a / 2, df))
    t1 = float(tdist.ppf(1 - a, df))
    return {"mean": mu, "se": se, "df": df, "two_sided": [mu - t2 * se, mu + t2 * se],
            "upper_one_sided": mu + t1 * se, "lower_one_sided": mu - t1 * se}


def cr2_bounds(units, table: dict, cluster: str = "family", weighted: bool = False,
               level: float = LEVEL) -> dict:
    """CR2 para lower (y = S), upper (y = S ou B) e est (só casos conhecidos, y = S)."""
    cls = [P.classify_all(u.codes, table) for u in units]
    w = [u.weight if weighted else 1.0 for u in units]
    g = [cluster_of(u, cluster) for u in units]
    out = {"lower": cr2_mean([c == P.SUCCESS for c in cls], w, g, level),
           "upper": cr2_mean([c != P.FAILURE for c in cls], w, g, level)}
    known = [i for i, c in enumerate(cls) if c != P.BOUNDED]
    out["est"] = cr2_mean([cls[i] == P.SUCCESS for i in known], [w[i] for i in known], [g[i] for i in known],
                          level)
    return out


def interval_cells(units, table: dict, cell_of, cluster: str = "family", weighted: bool = False,
                   reps: int = N_BOOT, seed: int = SEED_BOOT, level: float = LEVEL) -> dict:
    """Intervalo por célula com a regra do pré-registro: bootstrap percentil por cluster; célula com menos de
    30 clusters usa CR2 e é marcada (small_cluster = True)."""
    by_cell = defaultdict(list)
    for u in units:
        by_cell[cell_of(u)].append(u)
    tab = ClusterTable(cluster).add("m", units, table, cell_of, weighted)
    boot = bootstrap_cells("m", tab, reps, seed, level)
    out = {}
    for c in sorted(by_cell):
        G = len({cluster_of(u, cluster) for u in by_cell[c]})
        if G < SMALL_CLUSTER:
            out[c] = {"method": "cr2_t", "small_cluster": True, "clusters": G,
                      **cr2_bounds(by_cell[c], table, cluster, weighted, level)}
        else:
            out[c] = {"method": "bootstrap_percentile", "small_cluster": False, "clusters": G, **boot[c]}
    return out


# ------------------------------------------------------------------------------------------------- permutação
def direction_permutation_test(units_ab, units_ba, table: dict, bound: str = "lower", perms: int = N_PERM,
                               seed: int = SEED_PERM) -> dict:
    """Teste de permutação da assimetria de um par (sensibilidade de H2): estatística Y(A->B) - Y(B->A) no
    limite pedido; sob a nula, os rótulos de direção são trocáveis dentro da família (troca em bloco)."""
    if bound not in ("lower", "upper", "est"):
        raise ResampleError(bound)
    tab = ClusterTable("family").add("ab", units_ab, table, lambda u: "c").add("ba", units_ba, table,
                                                                               lambda u: "c")
    fams = tab.clusters()
    A = tab.matrix("ab", "c", fams)
    B = tab.matrix("ba", "c", fams)

    def stat(a, b):
        sa, sb = bound_stats(a)[bound], bound_stats(b)[bound]
        return sa - sb

    obs = float(stat(A.sum(0), B.sum(0)))
    rng = np.random.Generator(np.random.PCG64(seed))
    Z = rng.integers(0, 2, size=(perms, len(fams))).astype(float)
    pa = (1 - Z) @ A + Z @ B
    pb = (1 - Z) @ B + Z @ A
    null = stat(pa, pb)
    ok = np.isfinite(null)
    if not math.isfinite(obs) or not ok.any():
        return {"statistic": None, "p_two_sided": None, "permutations": perms, "families": len(fams)}
    extreme = int((np.abs(null[ok]) >= abs(obs) - 1e-12).sum())
    return {"statistic": obs, "p_two_sided": (1 + extreme) / (1 + int(ok.sum())), "permutations": perms,
            "families": len(fams)}
