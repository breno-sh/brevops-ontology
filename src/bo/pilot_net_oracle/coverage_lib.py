"""Contagens de cobertura (caso obrigatório × polaridade × partição; direção × polaridade) e as regras do gate."""
from __future__ import annotations

from collections import Counter

from .spec import CASES, DIRECTIONS

POLS = ("positive", "negative", "unknown")
MIN_RETAINED = 0.30
FIXTURE_CASES = [c for c in CASES if c != "NET-C10"]


def summarize(fixtures: list, translations: list) -> dict:
    fc = Counter((f["case"], f["polarity"]) for f in fixtures if f["case"] in CASES)
    tc = Counter((t["direction"], t["polarity"]) for t in translations)
    prov = Counter(f["provider"] for f in fixtures)
    return {
        "fixtures_total": len(fixtures),
        "fixtures_in_cases": sum(fc.values()),
        "flows_total": sum(len(f["flows"]) for f in fixtures),
        "translations_total": len(translations),
        "by_case": {c: {p: fc.get((c, p), 0) for p in POLS} for c in FIXTURE_CASES},
        "by_direction": {d: {p: tc.get((d, p), 0) for p in POLS} for d in DIRECTIONS},
        "by_provider": dict(sorted(prov.items())),
    }


def check(calib: dict, retained: dict) -> list:
    """Erros das regras do G2 (vazio = ok)."""
    errs = []
    for c in FIXTURE_CASES:
        for part, s in (("calibração", calib), ("retidas", retained)):
            for p in POLS:
                if s["by_case"][c][p] < 1:
                    errs.append(f"{c}: sem fixture {p} em {part}")
        n_cal, n_ret = sum(calib["by_case"][c].values()), sum(retained["by_case"][c].values())
        if n_ret / max(1, n_cal + n_ret) < MIN_RETAINED:
            errs.append(f"{c}: retidas {n_ret}/{n_cal + n_ret} < 30%")
    for d in DIRECTIONS:
        for p in POLS:
            if calib["by_direction"][d][p] < 1:
                errs.append(f"{d}: tradução {p} ausente na calibração")
        if retained["by_direction"][d]["negative"] < 1:
            errs.append(f"{d}: nenhum contraexemplo retido")
        if sum(retained["by_direction"][d].values()) < 1:
            errs.append(f"{d}: nenhuma tradução retida")
    for key in ("fixtures_in_cases", "translations_total"):
        tot = calib[key] + retained[key]
        if retained[key] / max(1, tot) < MIN_RETAINED:
            errs.append(f"{key}: retidas {retained[key]}/{tot} < 30%")
    # NET-C10 (tradução) também precisa das 3 polaridades nas duas partições
    for part, s in (("calibração", calib), ("retidas", retained)):
        for p in POLS:
            if sum(s["by_direction"][d][p] for d in DIRECTIONS) < 1:
                errs.append(f"NET-C10: sem tradução {p} em {part}")
    return errs
