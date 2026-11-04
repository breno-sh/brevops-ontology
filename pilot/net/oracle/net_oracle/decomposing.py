"""Comparação de decomposição (E2): unidades esperadas (gabarito) × unidades produzidas pelo pipeline.

Unidade: {"domain_unit", "kind", "accepted_kinds"?, "parent", "occurrence": {...}, "tf": {...}}. Duas unidades
são a mesma se domain_unit, parent e occurrence coincidem; a camada Terraform (tf) é ignorada, para que regra
embutida e regra em recurso separado contem como a mesma unidade (CMT-FW-P01).
"""
from __future__ import annotations

import json


def _key(u: dict) -> str:
    return json.dumps([u["domain_unit"], u.get("parent"), u.get("occurrence", {})], sort_keys=True)


def normalize(units: list) -> dict:
    return {_key(u): u for u in units}


def compare(expected: list, actual: list) -> dict:
    e, a = normalize(expected), normalize(actual)
    missing = sorted(set(e) - set(a))
    extra = sorted(set(a) - set(e))
    wrong_kind = []
    for k in sorted(set(e) & set(a)):
        acc = e[k].get("accepted_kinds") or [e[k]["kind"]]
        if a[k]["kind"] not in acc:
            wrong_kind.append({"unit": k, "expected": acc, "actual": a[k]["kind"]})
    return {"equal": not (missing or extra or wrong_kind), "missing": missing, "extra": extra,
            "wrong_kind": wrong_kind}


def invariant(units_a: list, units_b: list) -> bool:
    """As duas embalagens dão as mesmas unidades a menos da camada Terraform?"""
    strip = lambda us: sorted((_key(u), u["kind"]) for u in us)
    return strip(units_a) == strip(units_b)
