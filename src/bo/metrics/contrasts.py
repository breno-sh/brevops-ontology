"""Os 15 contrastes pré-registrados (PREREG §6; prereg/power.json) e a regra de decisão de cada um.

Cada função recebe o que a análise calcula (intervalos por célula, contrastes pareados, modelo, testes) e
devolve o veredito com a evidência. Regras comuns:
  - julgado no limite declarado (H1 e H4 no superior, H8 no inferior, os demais nos dois);
  - nos dois limites: os dois sustentam = supported; os dois não = not_supported; discordam =
    indeterminate_by_unknown ('indeterminada pelo desconhecido');
  - regra de contagem (k de K) aplicada às unidades com poder; o rebaixamento a descritivo é da reestimação
    cega (STATS), não daqui;
  - Holm nas famílias que o pré-registro manda (C-ABL, C-RQ5-TRANS, C-TOOL); Bonferroni em H9.
"""
from __future__ import annotations

import json
import math

from .spec import repo_root

ALPHA = 0.05


def _both(lo: bool | None, up: bool | None) -> str:
    if lo is None or up is None:
        return "not_estimable"
    if lo and up:
        return "supported"
    if not lo and not up:
        return "not_supported"
    return "indeterminate_by_unknown"


def _lt(x, thr):
    return None if x is None else x < thr


def _gt(x, thr):
    return None if x is None else x > thr


def holm(pvals: dict, alpha: float = ALPHA) -> dict:
    """Holm-Bonferroni: rejeita em ordem crescente enquanto p_(i) <= alpha/(m - i)."""
    items = sorted((p if p is not None else 1.0, k) for k, p in pvals.items())
    m = len(items)
    out = {k: False for k in pvals}
    for i, (p, k) in enumerate(items):
        if p <= alpha / (m - i):
            out[k] = True
        else:
            break
    return out


# ------------------------------------------------------------------------------------------------- H1
def judge_h1(cells: dict, threshold: float = 0.70) -> dict:
    """cells: interval_cells de M-OPCOV-DEC por direção. Limite superior de confiança 95% (unilateral) do
    limite superior < 0,70 em TODAS as direções (interseção-união)."""
    per = {c: _lt(v["upper"]["upper_one_sided"], threshold) for c, v in sorted(cells.items())}
    ok = all(per.values()) and len(per) > 0
    return {"contrast": "C-H1", "bound": "upper", "per_unit": per,
            "verdict": "supported" if ok else ("not_estimable" if None in per.values() else "not_supported")}


# ------------------------------------------------------------------------------------------------- H2
def judge_h2(asym: dict, min_abs: float = 0.05, k: int = 4) -> dict:
    """asym: models.asymmetry. Por par: IC 95% exclui 0 e |estimativa| >= 0,05, mesmo sinal nos dois
    limites; H2 com pelo menos 4 dos 6 pares."""
    per = {}
    seen = set()
    for d, v in sorted(asym.items()):
        pair = frozenset(d.split("->"))
        if pair in seen:
            continue
        seen.add(pair)
        pair = "<->".join(sorted(pair))
        res = []
        for b in ("lower", "upper"):
            lo, up = v["ci"][b]["two_sided"]
            pt = v["point"][b]
            if lo is None or pt is None:
                res.append(None)
                continue
            res.append((lo > 0 or up < 0) and abs(pt) >= min_abs and math.copysign(1, pt))
        if None in res:
            per[pair] = "not_estimable"
        elif res[0] and res[1] and res[0] == res[1]:
            per[pair] = "supported"
        elif not res[0] and not res[1]:
            per[pair] = "not_supported"
        else:
            per[pair] = "indeterminate_by_unknown"
    n_sup = sum(1 for x in per.values() if x == "supported")
    n_possible = sum(1 for x in per.values() if x in ("supported", "indeterminate_by_unknown"))
    verdict = "supported" if n_sup >= k else ("indeterminate_by_unknown" if n_possible >= k else "not_supported")
    return {"contrast": "C-H2", "bound": "both", "per_unit": per, "count": n_sup, "required": k,
            "verdict": verdict}


# ------------------------------------------------------------------------------------------------- H3
def judge_h3(logit: dict) -> dict:
    """IC 95% superior (unilateral) da razão de chances < 1 nos dois limites."""
    lo = logit.get("lower", {})
    up = logit.get("upper", {})
    a = _lt(lo.get("upper_one_sided"), 1.0) if lo.get("status") == "ok" else None
    b = _lt(up.get("upper_one_sided"), 1.0) if up.get("status") == "ok" else None
    return {"contrast": "C-H3", "bound": "both", "per_bound": {"lower": a, "upper": b}, "verdict": _both(a, b)}


# ------------------------------------------------------------------------------------------------- H4
def judge_h4(pers_interval: dict, threshold: float = 0.90) -> dict:
    """pers_interval: intervalo da precisão de persistência combinada (pesos do frame). Limite superior de
    confiança 95% do limite superior < 0,90."""
    x = pers_interval["upper"]["upper_one_sided"]
    r = _lt(x, threshold)
    return {"contrast": "C-H4", "bound": "upper", "value": x,
            "verdict": "not_estimable" if r is None else ("supported" if r else "not_supported")}


# ------------------------------------------------------------------------------------------------- H5
def judge_h5(median_fit: dict, months: float = 6.0) -> dict:
    x = median_fit["lower_one_sided"]
    return {"contrast": "C-H5", "bound": "n/a", "value": x,
            "verdict": "supported" if x is not None and x > months else "not_supported"}


# ------------------------------------------------------------------------------------------------- H6
def judge_h6_cov(paired_pooled: dict, margin: float = 0.02) -> dict:
    """paired_pooled: paired_contrast(completo, ablado AWS+crus, pooled=True). Limite inferior 95% de
    (completo - ablado) > -0,02 nos dois limites."""
    v = paired_pooled["all"]["ci"]
    a = _gt(v["lower"]["lower_one_sided"], -margin)
    b = _gt(v["upper"]["lower_one_sided"], -margin)
    return {"contrast": "C-H6-COV", "bound": "both", "per_bound": {"lower": a, "upper": b}, "verdict": _both(a, b)}


def judge_h6_gini(full: dict, ablated: dict) -> dict:
    """Descritivo: Gini (mínimo e máximo) do artefato completo e do ablado; nenhum teste."""
    return {"contrast": "C-H6-GINI", "bound": "n/a", "verdict": "descriptive", "full": full, "ablated": ablated,
            "lower_in_full": full["gini_max"] < ablated["gini_min"]}


# ------------------------------------------------------------------------------------------------- H7, LOPO
def _count_paired(paired: dict, k: int, contrast: str) -> dict:
    per = {}
    for c, v in sorted(paired.items()):
        a = _gt(v["ci"]["lower"]["lower_one_sided"], 0.0)
        b = _gt(v["ci"]["upper"]["lower_one_sided"], 0.0)
        per[c] = _both(a, b)
    n_sup = sum(1 for x in per.values() if x == "supported")
    n_possible = sum(1 for x in per.values() if x in ("supported", "indeterminate_by_unknown"))
    verdict = "supported" if n_sup >= k else ("indeterminate_by_unknown" if n_possible >= k else "not_supported")
    return {"contrast": contrast, "bound": "both", "per_unit": per, "count": n_sup, "required": k,
            "verdict": verdict}


def judge_h7(paired: dict, k: int = 10) -> dict:
    """paired: paired_contrast(ontologia, direto, ratio=0.95) por direção; limite inferior 95% de
    (Y_ont - 0,95·Y_dir) > 0 nos dois limites em pelo menos 10 das 12 direções."""
    return _count_paired(paired, k, "C-H7")


def judge_lopo(paired: dict, k: int = 4) -> dict:
    """paired: paired_contrast(ontologia de 3, de 4, ratio=0.90) nas 6 direções com OCI."""
    return _count_paired({c: v for c, v in paired.items() if "oci" in c}, k, "C-LOPO")


# ------------------------------------------------------------------------------------------------- H8
def judge_h8(complex_interval: dict, threshold: float = 0.10) -> dict:
    """Limite inferior de confiança 95% da fração (no limite inferior) >= 0,10."""
    x = complex_interval["lower"]["lower_one_sided"]
    return {"contrast": "C-H8", "bound": "lower", "value": x,
            "verdict": "not_estimable" if x is None else ("supported" if x >= threshold else "not_supported")}


# ------------------------------------------------------------------------------------------------- H9
def judge_h9(by_family: dict, n_families: int = 7) -> dict:
    """by_family: {família: {'c2': mcnemar_exact(c3 x c2), 'c1': mcnemar_exact(c3 x c1)}}; os dois com
    p <= 0,05/7 em pelo menos uma família (Bonferroni nas 7, interseção-união nos 2 controles)."""
    a = ALPHA / n_families
    per = {f: (v["c2"]["p_one_sided"] <= a and v["c1"]["p_one_sided"] <= a) for f, v in sorted(by_family.items())}
    return {"contrast": "C-H9", "bound": "n/a", "alpha_per_test": a, "per_unit": per,
            "verdict": "supported" if any(per.values()) else "not_supported"}


# ------------------------------------------------------------------------------------------------- ABL, RQ5, TOOL
def _holm_both(arms: dict, contrast: str, equivalence_margin: float | None = None) -> dict:
    per = {}
    for b in ("lower", "upper"):
        pv = {k: v["all"]["ci"][b]["p_zero_two_sided"] for k, v in arms.items()}
        rej = holm(pv)
        for k, v in arms.items():
            ci = v["all"]["ci"][b]
            eq = None
            if equivalence_margin is not None and ci["lower_one_sided"] is not None:
                eq = ci["lower_one_sided"] > -equivalence_margin and ci["upper_one_sided"] < equivalence_margin
            per.setdefault(k, {})[b] = {"effect": rej[k], "equivalent": eq, "p": pv[k]}
    out = {}
    for k, r in sorted(per.items()):
        if r["lower"]["effect"] and r["upper"]["effect"]:
            out[k] = "effect"
        elif r["lower"]["equivalent"] and r["upper"]["equivalent"]:
            out[k] = "hygiene_equivalent"
        elif r["lower"]["effect"] != r["upper"]["effect"]:
            out[k] = "indeterminate_by_unknown"
        else:
            out[k] = "inconclusive"
    return {"contrast": contrast, "bound": "both", "per_unit": out, "detail": per, "verdict": "per_unit"}


def judge_abl(arms: dict) -> dict:
    """arms: {braço: paired_contrast(completo, braço, pooled=True)} nos 7 braços. Efeito: IC exclui 0 com
    Holm; equivalência: TOST ±0,03; nenhum dos dois: inconclusivo."""
    return _holm_both(arms, "C-ABL", equivalence_margin=0.03)


def judge_rq5(comparators: dict) -> dict:
    return _holm_both(comparators, "C-RQ5-TRANS")


def judge_tool(diffs: dict) -> dict:
    return _holm_both(diffs, "C-TOOL")


def judge_behav(wilson_cells: dict) -> dict:
    return {"contrast": "C-BEHAV", "bound": "both", "verdict": "descriptive", "per_probe_type": wilson_cells}


# ------------------------------------------------------------------------------------------------- registro
REGISTRY = {
    "C-H1": (["M-OPCOV-DEC"], judge_h1),
    "C-H2": (["M-OPCOV-DEC"], judge_h2),
    "C-H3": (["M-OPCOV-DEC"], judge_h3),
    "C-H4": (["M-PERS-DEC"], judge_h4),
    "C-H5": ([], judge_h5),
    "C-H6-COV": (["M-OPCOV-DEC", "M-ABL-AWSRAW-DEC"], judge_h6_cov),
    "C-H6-GINI": ([], judge_h6_gini),
    "C-H7": (["M-OPCOV-DEC", "M-OPCOV-DEC-DIRECT"], judge_h7),
    "C-H8": (["M-OPCOV-DEC-COMPLEX"], judge_h8),
    "C-H9": (["M-OPCOV-DEC-C1", "M-OPCOV-DEC-C2", "M-OPCOV-DEC"], judge_h9),
    "C-LOPO": (["M-LOPO-OPCOV-DEC", "M-OPCOV-DEC"], judge_lopo),
    "C-ABL": (["M-OPCOV-DEC", "M-ABL-SEEDAWS-DEC", "M-ABL-THR-ALT1-DEC", "M-ABL-THR-ALT2-DEC",
               "M-ABL-RAWTYPES-DEC", "M-ABL-NOGUARD-DEC", "M-OPCOV-DEC-C1", "M-OPCOV-DEC-C2"], judge_abl),
    "C-RQ5-TRANS": (["M-OPCOV-DEC", "M-H2H-TRANS-DEC"], judge_rq5),
    "C-TOOL": (["M-OPCOV-DEC", "M-OPCOV-DEC-DIRECT", "M-TOOL-LLM-DEC"], judge_tool),
    "C-BEHAV": (["M-BEHAV-DEC"], judge_behav),
}

ESTIMANDS = {"E-HUBLOSS": "models.paired_contrast(ratio=1) e ratio_*", "E-ASYM": "models.asymmetry",
             "E-OR-AUTH": "models.fixed_effects_logit", "E-GINI-BALANCE": "models.gini_range",
             "E-DRIFT-LAG": "models.turnbull_median", "E-NONE-FALSE": "models.none_false"}


def check_power(path=None) -> list[str]:
    """Os contrastes do registro são exatamente os de prereg/power.json, com as mesmas métricas."""
    p = path or (repo_root() / "prereg" / "power.json")
    doc = json.loads(open(p, encoding="utf-8").read())
    errs = []
    cs = {c["contrast_id"]: c for c in doc["data"]["contrasts"]}
    for cid in sorted(set(cs) ^ set(REGISTRY)):
        errs.append(f"{cid}: só de um lado (power.json x biblioteca)")
    for cid in sorted(set(cs) & set(REGISTRY)):
        if cs[cid]["metrics"] != REGISTRY[cid][0]:
            errs.append(f"{cid}: métricas {REGISTRY[cid][0]} na biblioteca, {cs[cid]['metrics']} no power.json")
    return errs
