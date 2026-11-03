"""Apoio comum dos comandos bo.metrics.<cmd> ID: catálogo, pastas do módulo, carimbo de hora."""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .spec import repo_root

CATALOG_DEFAULT = "/Users/breno/doutorado/pesquisa/superficie/reports/brevops_ontology/modulos.json"


def now() -> str:
    return datetime.now(ZoneInfo("America/Recife")).isoformat(timespec="seconds")


def say(msg: str):
    print(f"[{now()}] {msg}")


def catalog() -> dict:
    p = os.environ.get("BO_MODULES") or CATALOG_DEFAULT
    try:
        return {m["stable_id"]: m for m in json.load(open(p, encoding="utf-8"))["modules"]}
    except OSError:
        own = repo_root() / "modules" / "owners.json"
        d = json.load(open(own, encoding="utf-8"))
        mods = d.get("modules", d)
        return {k: v for k, v in (mods.items() if isinstance(mods, dict) else [(m["stable_id"], m) for m in mods])}


def expand(path: str) -> Path:
    return Path(path.replace("$BO_REPO", str(repo_root())).replace(
        "$BO_DATA", os.environ.get("BO_DATA", "/Users/breno/doutorado/brevops-data")))


def results_dir(mid: str) -> Path:
    return repo_root() / "results" / mid


def packages_of(mid: str, cat: dict) -> list[str]:
    """Pacotes src/bo/<pkg>/ do owns do módulo, em ordem; fallback: stable_id em minúsculas."""
    out = []
    for o in cat.get(mid, {}).get("owns", []):
        if o.startswith("$BO_REPO/src/bo/") and o.endswith("/"):
            rel = o[len("$BO_REPO/src/bo/"):-1]
            if "/" not in rel:
                out.append(rel)
    return out or [mid.lower().replace("-", "_")]
