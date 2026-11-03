"""Limites, est e leituras (PREREG §3, §4).

  lower = Σw·S / Σw          (todo desconhecido como falha)
  upper = Σw·(S+B) / Σw      (todo desconhecido como sucesso)
  est   = Σw·S / Σw·(S+F)    (caso completo; nulo quando não há caso com desfecho conhecido)
  n     = número de unidades no denominador (fixado no lado de origem)

Somas com math.fsum, em ordem de unit_id: o resultado não depende da ordem dos registros (teste de
reordenação). Pesos: 1 (uniform) ou o peso do caso (inverse_probability, estimador de Hájek).
"""
from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass

from scipy.stats import norm

from . import policy as P
from .spec import BINDINGS, Binding, LEVEL, direction_key
from .units import Unit


class MetricError(ValueError):
    pass


@dataclass(frozen=True)
class Bounds:
    lower: float
    upper: float
    est: float | None
    n: int
    s: float = 0.0          # somas ponderadas por classe
    f: float = 0.0
    b: float = 0.0

    def as_dict(self) -> dict:
        return {"lower": self.lower, "upper": self.upper, "est": self.est, "n": self.n}

    def at(self, bound: str) -> float | None:
        return {"lower": self.lower, "upper": self.upper, "est": self.est}[bound]


EMPTY = Bounds(0.0, 1.0, None, 0)


def bounds_from_sums(s: float, f: float, b: float, n: int) -> Bounds:
    tot = s + f + b
    if n == 0 or tot == 0:
        return Bounds(0.0, 1.0, None, n, s, f, b)
    known = s + f
    est = s / known if known > 0 else None
    return Bounds(s / tot, (s + b) / tot, est, n, s, f, b)


def classes_of(units, table: dict) -> list[str]:
    return [P.classify_all(u.codes, table) for u in units]


def sums(units, table: dict, weighted: bool) -> tuple[float, float, float, int]:
    acc = {P.SUCCESS: [], P.FAILURE: [], P.BOUNDED: []}
    for u in sorted(units, key=lambda x: x.unit_id):
        w = u.weight if weighted else 1.0
        if w < 0 or not math.isfinite(w):
            raise MetricError(f"{u.unit_id}: peso inválido {w}")
        acc[P.classify_all(u.codes, table)].append(w)
    return (math.fsum(acc[P.SUCCESS]), math.fsum(acc[P.FAILURE]), math.fsum(acc[P.BOUNDED]),
            len(acc[P.SUCCESS]) + len(acc[P.FAILURE]) + len(acc[P.BOUNDED]))


def bounds(units, table: dict, weighted: bool = False) -> Bounds:
    s, f, b, n = sums(units, table, weighted)
    return bounds_from_sums(s, f, b, n)


def _check_unique(units):
    seen = set()
    for u in units:
        if u.unit_id in seen:
            raise MetricError(f"unidade repetida no denominador: {u.unit_id}")
        seen.add(u.unit_id)


def cell_key(u: Unit, binding: Binding) -> str:
    return direction_key(u.source, u.target if binding.directional else None)


def reading(metric_id: str, units, exclude_pilot_exposed: bool = False) -> dict[str, Bounds]:
    """Leitura de uma métrica por célula (direção A->B, ou provedor A nas não direcionais).

    exclude_pilot_exposed=True é a leitura de sensibilidade sem as unidades expostas nos pilotos."""
    b = BINDINGS[metric_id]
    if b.kind == "complex_fraction":
        raise MetricError("use complex_fraction()")
    if b.kind == "product":
        raise MetricError("use combined_reading()")
    units = [u for u in units if not (exclude_pilot_exposed and u.pilot_exposed)]
    _check_unique(units)
    if b.only_oci:
        units = [u for u in units if "oci" in (u.source, u.target)]
    cells = defaultdict(list)
    for u in units:
        cells[cell_key(u, b)].append(u)
    weighted = b.weights == "inverse_probability"
    return {k: bounds(cells[k], b.table, weighted) for k in sorted(cells)}


def mean_of_directions(cells: dict[str, Bounds]) -> Bounds:
    """Leitura secundária: média das direções com pesos iguais (células com n = 0 ficam fora e são contadas)."""
    xs = [c for c in cells.values() if c.n > 0]
    if not xs:
        return EMPTY
    lo = math.fsum(c.lower for c in xs) / len(xs)
    up = math.fsum(c.upper for c in xs) / len(xs)
    ests = [c.est for c in xs]
    est = None if any(e is None for e in ests) else math.fsum(ests) / len(xs)
    return Bounds(lo, up, est, sum(c.n for c in xs))


# ------------------------------------------------------------------------------------------------- fração complexa
def complex_fraction(units) -> dict[str, Bounds]:
    """M-OPCOV-DEC-COMPLEX. Base = decisões emitidas no limite inferior de M-OPCOV-DEC (E); C = emitidas com
    correspondência complexa (attr complex=True: bo_group_id ou guarda não vazia no C09); U = desconhecidas.
    est = C/E; limite inferior = C/(E+U) (desconhecidas tratadas como emitidas simples); limite superior =
    (C+U)/(E+U) (tratadas como emitidas complexas). n = E. As falhas definidas não entram."""
    table = BINDINGS["M-OPCOV-DEC"].table
    cells = defaultdict(lambda: [0, 0, 0])
    _check_unique(units)
    for u in sorted(units, key=lambda x: x.unit_id):
        k = direction_key(u.source, u.target)
        c = P.classify_all(u.codes, table)
        cell = cells[k]
        if c == P.SUCCESS:
            cell[0] += 1
            cx = u.attr("complex")
            if cx is None:
                raise MetricError(f"{u.unit_id}: decisão emitida sem o atributo complex")
            cell[1] += int(bool(cx))
        elif c == P.BOUNDED:
            cell[2] += 1
    out = {}
    for k in sorted(cells):
        e, c, unk = cells[k]
        if e + unk == 0:
            out[k] = Bounds(0.0, 1.0, None, 0)
            continue
        out[k] = Bounds(c / (e + unk), (c + unk) / (e + unk), (c / e) if e else None, e, c, e - c, unk)
    return out


# ------------------------------------------------------------------------------------------------- combinada
def combined(opcov: Bounds, pers: Bounds) -> Bounds:
    """M-OPCOV-PERS-DEC: lower = lower × lower; upper = upper × upper; est = est × est (PREREG)."""
    est = None if opcov.est is None or pers.est is None else opcov.est * pers.est
    return Bounds(opcov.lower * pers.lower, opcov.upper * pers.upper, est, opcov.n)


def combined_reading(opcov_units, pers_units) -> dict[str, Bounds]:
    """Por direção A->B. A persistência vem dos casos de deploy da direção (pesos do frame); direção sem
    caso de deploy dá persistência vazia (0..1), nunca 1."""
    oc = reading("M-OPCOV-DEC", opcov_units)
    pc = reading("M-PERS-DEC", pers_units)
    return {k: combined(oc[k], pc.get(k, EMPTY)) for k in sorted(oc)}


# ------------------------------------------------------------------------------------------------- escada
LADDER = ("representability", "transportability", "operational", "persistence", "behavior")


def ladder(readings: dict[str, dict[str, Bounds]]) -> dict:
    """Escada dos cinco eixos por célula: cada eixo medido à parte (nada inferido do outro).

    readings: {metric_id: {célula: Bounds}} com uma métrica por eixo. Devolve, por célula, os eixos em ordem e
    as inversões (eixo posterior com limite inferior acima do limite superior do anterior), relatadas como
    achado, nunca corrigidas."""
    by_axis = {}
    for mid, cells in readings.items():
        ax = BINDINGS[mid].axis
        if ax in by_axis:
            raise MetricError(f"dois indicadores para o eixo {ax}")
        by_axis[ax] = (mid, cells)
    out = {}
    cells = sorted({c for _, cs in by_axis.values() for c in cs})
    for c in cells:
        row, inv = [], []
        prev = None
        for ax in LADDER:
            if ax not in by_axis:
                continue
            mid, cs = by_axis[ax]
            key = c if c in cs else c.split("->")[0]
            bd = cs.get(key)
            if bd is None:
                continue
            row.append({"axis": ax, "metric_id": mid, **bd.as_dict()})
            if prev is not None and bd.n and prev[1].n and bd.lower > prev[1].upper + 1e-12:
                inv.append(f"{ax} > {prev[0]}")
            prev = (ax, bd)
        out[c] = {"axes": row, "inversions": inv}
    return out


# ------------------------------------------------------------------------------------------------- Wilson
def wilson(k: float, n: float, level: float = LEVEL) -> tuple[float, float]:
    if n <= 0:
        return 0.0, 1.0
    z = norm.ppf(1 - (1 - level) / 2)
    p = k / n
    den = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / den
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return max(0.0, centre - half), min(1.0, centre + half)


def wilson_bounds(units, metric_id: str = "M-BEHAV-DEC", level: float = LEVEL) -> dict:
    """IC de Wilson do tamanho real (contagens, não pesos) para o limite inferior (S) e o superior (S+B)."""
    b = BINDINGS[metric_id]
    cells = defaultdict(list)
    for u in units:
        cells[u.attr("probe_type", "all")].append(u)
    out = {}
    for k in sorted(cells):
        s, f, bd, n = sums(cells[k], b.table, weighted=False)
        out[k] = {"n": n, "lower_ci": wilson(s, n, level), "upper_ci": wilson(s + bd, n, level),
                  "point": bounds_from_sums(s, f, bd, n).as_dict()}
    return out
