"""Perfil semântico por provedor (semantics_profile.json) e leitura por nível de evidência."""
from __future__ import annotations

import json
from pathlib import Path

PROFILE_PATH = Path(__file__).resolve().parent.parent / "semantics_profile.json"
_cache: dict = {}


def profile() -> dict:
    if "p" not in _cache:
        _cache["p"] = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
    return _cache["p"]


def levels(reading: str) -> list:
    return profile()["readings"][reading]


class Param:
    """Valor de um parâmetro sob uma leitura: known=True com value, ou known=False com os valores possíveis."""

    def __init__(self, provider: str, name: str, known: bool, value=None, values=None, level=None, evidence=None):
        self.provider, self.name, self.known = provider, name, known
        self.value, self.values = value, list(values or [])
        self.level, self.evidence = level, list(evidence or [])


def param(provider: str, name: str, reading: str = "default", values=None) -> Param:
    p = profile()["params"].get(provider, {}).get(name)
    if p is None:
        return Param(provider, name, False, values=values or [], level="absent")
    ok = p["level"] in levels(reading) and p.get("value") is not None
    if ok:
        return Param(provider, name, True, value=p["value"], level=p["level"], evidence=p.get("evidence"))
    vals = p.get("values") or values or []
    if not vals:
        raise ValueError(f"parâmetro {provider}.{name} sem valor na leitura {reading} e sem valores possíveis")
    return Param(provider, name, False, values=vals, level=p["level"], evidence=p.get("evidence"))


def evidence_ids() -> list:
    """Todos os evidence_id do SERVICE-EVIDENCE citados no perfil (os C24:* são compromissos/requisitos)."""
    out = []
    for prov in profile()["params"].values():
        for k, v in prov.items():
            if isinstance(v, dict):
                out.extend(e for e in v.get("evidence", []) if e.startswith("SE-"))
    return sorted(set(out))
