"""Índice offline do schema fixado de cada provider (saídas dos SCHEMA-*: types.jsonl e atoms.jsonl, C01/C02).

Usado para conferir evidência de NOT_APPLICABLE (tipo ou atributo ausente no schema fixado) e para conferir
que todo tipo e atributo do main.tf existe no provider fixado. Só leitura.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache

from . import PROVIDER_SCHEMA_DIR, data_root


def _dir(provider: str):
    return data_root() / PROVIDER_SCHEMA_DIR[provider]


@lru_cache(maxsize=None)
def resource_types(provider: str) -> frozenset:
    out = set()
    with open(_dir(provider) / "types.jsonl", encoding="utf-8") as f:
        for ln in f:
            out.add(json.loads(ln)["resource_type"])
    return frozenset(out)


@lru_cache(maxsize=None)
def provider_version(provider: str) -> str:
    with open(_dir(provider) / "types.jsonl", encoding="utf-8") as f:
        return json.loads(f.readline())["provider_version"]


_ATOMS: dict = {}


def atoms(provider: str, rtypes: set) -> dict:
    """{resource_type: {path: atom}} para os tipos pedidos (lê o atoms.jsonl uma vez por conjunto novo)."""
    cache = _ATOMS.setdefault(provider, {})
    need = {t for t in rtypes if t not in cache}
    if need:
        keys = {f'"resource_type": "{t}"': t for t in need}
        for t in need:
            cache[t] = {}
        with open(_dir(provider) / "atoms.jsonl", encoding="utf-8") as f:
            for ln in f:
                if '"resource_type": "' not in ln:
                    continue
                i = ln.find('"resource_type": "')
                j = ln.find('"', i + 18)
                t = ln[i + 18:j]
                if t in need:
                    a = json.loads(ln)
                    cache[t][a["path"]] = a
        del keys
    return {t: cache[t] for t in rtypes}


def check_evidence(ev: dict) -> str | None:
    """Confere uma evidência; devolve None se confere, ou o motivo da reprovação."""
    k = ev.get("kind")
    if k == "schema_type_absent":
        pat = re.compile(ev["pattern"])
        hits = sorted(t for t in resource_types(ev["provider"]) if pat.search(t))
        return None if not hits else f"padrão {ev['pattern']!r} casa tipos do schema: {hits[:5]}"
    if k == "schema_attr_absent":
        rt = ev["resource_type"]
        if rt not in resource_types(ev["provider"]):
            return f"tipo {rt} não existe no schema fixado (evidência mal formada)"
        pat = re.compile(ev["pattern"])
        hits = sorted(p for p in atoms(ev["provider"], {rt})[rt] if pat.search(p))
        return None if not hits else f"padrão {ev['pattern']!r} casa atributos de {rt}: {hits[:5]}"
    if k == "schema_attr_present":
        rt = ev["resource_type"]
        if rt not in resource_types(ev["provider"]):
            return f"tipo {rt} não existe no schema fixado"
        return None if ev["path"] in atoms(ev["provider"], {rt})[rt] else f"{rt}.{ev['path']} não existe"
    if k == "doc_citation":
        if not str(ev.get("url", "")).startswith("https://") or len(str(ev.get("claim", ""))) < 20:
            return "citação sem URL https ou sem afirmação"
        if ev.get("evidence_state") != "INTERPRETED":
            return "citação precisa de evidence_state INTERPRETED"
        return None
    return f"tipo de evidência desconhecido: {k!r}"
