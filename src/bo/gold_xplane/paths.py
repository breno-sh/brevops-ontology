"""Caminhos do módulo (C00) e carimbo de hora America/Recife."""
from __future__ import annotations

import datetime as _dt
import os
from pathlib import Path
from zoneinfo import ZoneInfo

ID = "GOLD-XPLANE"
TZ = ZoneInfo("America/Recife")


def repo_dir() -> Path:
    return Path(os.environ.get("BO_REPO") or Path(__file__).resolve().parents[3])


def data_root() -> Path:
    return Path(os.environ.get("BO_DATA") or "/Users/breno/doutorado/brevops-data")


def data_dir() -> Path:
    return data_root() / ID


def downloads_dir() -> Path:
    return data_root() / "downloads" / "crossplane"


def tmp_dir() -> Path:
    p = Path(os.environ.get("BO_TMP") or data_root() / "tmp" / ID)
    p.mkdir(parents=True, exist_ok=True)
    return p


def results_dir() -> Path:
    return repo_dir() / "results" / ID


def now_iso() -> str:
    return _dt.datetime.now(TZ).replace(microsecond=0).isoformat()
