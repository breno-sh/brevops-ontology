"""Caminhos do módulo (C00), entradas fixadas e carimbo America/Recife."""
from __future__ import annotations

import datetime as _dt
import hashlib
import os
from pathlib import Path
from zoneinfo import ZoneInfo

ID = "GOLD-MODS"
TZ = ZoneInfo("America/Recife")


def repo_dir() -> Path:
    return Path(os.environ.get("BO_REPO") or Path(__file__).resolve().parents[3])


def data_root() -> Path:
    return Path(os.environ.get("BO_DATA") or "/Users/breno/doutorado/brevops-data")


def data_dir() -> Path:
    return data_root() / ID


def staging_dir() -> Path:
    return data_dir() / ".staging"


def hcl_dir() -> Path:
    return data_root() / "HCL"


def symbolic_config() -> Path:
    return hcl_dir() / "symbolic_config.jsonl"


def symbolic_index() -> Path:
    return hcl_dir() / "symbolic_config.index.json"


def licenses_path() -> Path:
    return hcl_dir() / "licenses.json"


def tmp_dir() -> Path:
    p = Path(os.environ.get("BO_TMP") or data_root() / "tmp" / ID)
    p.mkdir(parents=True, exist_ok=True)
    return p


def results_dir() -> Path:
    return repo_dir() / "results" / ID


def now_iso() -> str:
    return _dt.datetime.now(TZ).replace(microsecond=0).isoformat()


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 22), b""):
            h.update(b)
    return h.hexdigest()
