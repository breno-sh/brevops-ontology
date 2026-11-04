"""Regra pré-declarada dos 3 controles (reasoning_controls_rule do prereg/pilot_exit.yaml), em contagem descritiva.

Entrada por caso retido: {case_id, family, polarity, c1, c2, c3} com cada controle em
  correct | incorrect | absent   (consequência correta, consequência incorreta, nenhuma consequência)
e, para c3, se as consequências contadas trazem justifying_axioms separados de consulted_metadata.
Correto = igual à resposta esperada independente (oráculo/compromissos), nunca a opinião de quem avalia.

Saída: contagens por controle e polaridade, McNemar exato por família (bo.metrics.models.mcnemar_exact, a mesma
função do C-H9), a linha R-CTRL que se aplica e a consequência pré-declarada copiada do yaml.
Nos pilotos a leitura é só descritiva: nenhuma decisão sobre H9 sai daqui.
"""
from __future__ import annotations

from collections import Counter, defaultdict

CONTROLS = ("c1_table", "c2_taxonomy", "c3_full")
SHORT = {"c1_table": "c1", "c2_taxonomy": "c2", "c3_full": "c3"}
OUTCOMES = ("correct", "incorrect", "absent")
POLARITIES = ("positive", "negative", "unknown")


def counts(cases: list[dict]) -> dict:
    out = {c: {p: Counter() for p in POLARITIES} for c in SHORT.values()}
    for k in cases:
        for c in SHORT.values():
            out[c][k["polarity"]][k[c]] += 1
    return {c: {p: {o: out[c][p][o] for o in OUTCOMES} for p in POLARITIES} for c in out}


def by_family(cases: list[dict]) -> dict:
    from bo.metrics.models import mcnemar_exact
    fam = defaultdict(list)
    for k in cases:
        fam[k["family"]].append(k)
    res = {}
    for f, ks in sorted(fam.items()):
        res[f] = {"n_cases": len(ks),
                  "c3_vs_c1": mcnemar_exact([(k["c3"] == "correct", k["c1"] == "correct") for k in ks]),
                  "c3_vs_c2": mcnemar_exact([(k["c3"] == "correct", k["c2"] == "correct") for k in ks]),
                  "c2_vs_c1": mcnemar_exact([(k["c2"] == "correct", k["c1"] == "correct") for k in ks])}
    return res


def r_ctrl(cases: list[dict], n_required: int, n_families: int = 7, alpha: float = 0.05) -> dict:
    """Linha R-CTRL aplicada, mecanicamente, na ordem do yaml. R-CTRL-5 e R-CTRL-6 são linhas próprias, somadas
    à linha principal (1 a 4), nunca no lugar dela."""
    a = alpha / n_families
    fam = by_family(cases)
    eligible = {f: v for f, v in fam.items() if v["n_cases"] >= n_required}
    sig3 = {f for f, v in fam.items() if v["c3_vs_c1"]["p_one_sided"] <= a and v["c3_vs_c2"]["p_one_sided"] <= a}
    sig3_elig = sorted(sig3 & set(eligible))
    sig21 = sorted(f for f, v in eligible.items() if v["c2_vs_c1"]["p_one_sided"] <= a)
    sig32 = sorted(f for f, v in eligible.items() if v["c3_vs_c2"]["p_one_sided"] <= a)
    all_elig = bool(fam) and len(eligible) == len(fam)
    if sig3_elig:
        main, why = "R-CTRL-1", f"c3 supera c1 e c2 com n suficiente em {sig3_elig}"
    elif all_elig and not sig32 and sig21:
        main, why = "R-CTRL-2", f"c3 não supera c2; c2 supera c1 em {sig21}"
    elif all_elig and not sig32 and not sig21 and not sig3:
        main, why = "R-CTRL-3", "nenhuma diferença com n por família suficiente"
    else:
        main = "R-CTRL-4"
        why = (f"n por família abaixo de {n_required} em {len(fam) - len(eligible)} de {len(fam)} família(s); "
               f"nenhuma família elegível significativa")
        if sig3 - set(eligible):
            why += f" (significância só em família com n abaixo do necessário: {sorted(sig3 - set(eligible))}, não elegível)"
    regress = [k["case_id"] for k in cases if k["c3"] == "incorrect" and (k["c1"] != "incorrect" or k["c2"] != "incorrect")]
    detect = [k["case_id"] for k in cases if k["polarity"] == "negative" and k.get("c3_rejects")
              and not (k.get("c1_rejects") and k.get("c2_rejects")) and not k.get("transport_changed")]
    extra = []
    if regress:
        extra.append({"id": "R-CTRL-5", "cases": len(regress)})
    if detect:
        extra.append({"id": "R-CTRL-6", "cases": len(detect)})
    return {"alpha_per_test": a, "n_required_per_family": n_required, "families": fam, "main": main, "why": why,
            "extra": extra, "regression_cases": sorted(regress), "error_detection_cases": sorted(detect)}


def justified(c3_traces: list[dict], c3_consequences: list[dict]) -> dict:
    """Toda consequência de c3 CONTADA (as do caso) traz axiomas; em todo traço c3, justifying_axioms e
    consulted_metadata são disjuntos (C23-SEP). Valor descido por codec de realização não é consequência de
    axioma: traço dele pode ter justifying_axioms vazio."""
    n = sep = 0
    for t in c3_traces:
        if t.get("result") != "carried":
            continue
        n += 1
        ja, cm = t.get("justifying_axioms"), t.get("consulted_metadata")
        if not isinstance(ja, list) or not isinstance(cm, list) or set(ja) & set(cm):
            sep += 1
    noax = sum(1 for c in c3_consequences if not c.get("axioms"))
    return {"c3_carried": n, "c3_sep_violations": sep, "c3_consequences": len(c3_consequences),
            "c3_consequences_without_axioms": noax, "c3_bad_justification": sep + noax}


def n_required(root) -> int:
    """n por família exigido pelo C-H9 (prereg/power.json, result.n_cases_per_family)."""
    import json
    from pathlib import Path
    p = json.loads((Path(root) / "prereg" / "power.json").read_text(encoding="utf-8"))
    for c in p["data"]["contrasts"]:
        if c["contrast_id"] == "C-H9":
            return int(c["result"]["n_cases_per_family"])
    raise KeyError("C-H9 ausente do power.json")
