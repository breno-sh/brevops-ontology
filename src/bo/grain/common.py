"""Caminhos, hora (America/Recife), JSON canônico e hash do GRAIN."""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
from pathlib import Path
from zoneinfo import ZoneInfo

TZ = ZoneInfo("America/Recife")
MODULE = "GRAIN"
MODEL_ID = "claude-opus-5-5"


def repo() -> Path:
    env = os.environ.get("BO_REPO")
    if env:
        return Path(env)
    return Path(__file__).resolve().parents[3]


def data_root() -> Path:
    return Path(os.environ.get("BO_DATA", "/Users/breno/doutorado/brevops-data"))


def data_dir() -> Path:
    d = data_root() / MODULE
    d.mkdir(parents=True, exist_ok=True)
    return d


def tmp_dir() -> Path:
    d = Path(os.environ.get("BO_TMP") or (data_root() / "tmp" / MODULE))
    d.mkdir(parents=True, exist_ok=True)
    return d


def rules_path() -> Path:
    return repo() / "grain" / "grain_rules.yaml"


def results_dir() -> Path:
    return repo() / "results" / MODULE


def now() -> str:
    return _dt.datetime.now(TZ).replace(microsecond=0).isoformat()


def canon(obj) -> str:
    """JSON canônico (chaves ordenadas, sem espaços): base de igualdade e de hash."""
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def sha256_file(p) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def dump_json(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=1, sort_keys=True) + "\n"


def dump_jsonl(recs) -> str:
    return "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in recs)


def load_jsonl(path) -> list[dict]:
    out = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def stamp(msg: str) -> str:
    return f"[{now()}] {msg}"
