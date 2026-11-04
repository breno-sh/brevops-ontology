"""Caminhos, hora (America/Recife), hashes e E/S canônica do BRIEFS."""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
from pathlib import Path
from zoneinfo import ZoneInfo

TZ = ZoneInfo("America/Recife")
MODULE = "BRIEFS"
MODEL_ID = "claude-opus-5-5"

# Versão dos briefs e data de congelamento: constantes (a regeneração tem de ser idêntica byte a byte).
# Mudar qualquer brief depois do FREEZE0 é emenda: nova versão aqui, motivo no CHANGELOG do brief e
# tools/invalidate.py check --apply para marcar os consumidores (PILOT-EXIT, E6).
BRIEF_VERSION = "1.3.0"
FROZEN_AT = "2026-11-04T13:00:00-03:00"

BRIEF_FILES = {  # papel -> brief (o mesmo de content.BRIEF_OF)
    "glossarist": "GLOSSARY_BRIEF.txt",
    "mapper": "MAPPER_BRIEF.txt",
    "hunter": "NONEHUNT_BRIEF.txt",
    "auditor": "AUDITOR_BRIEF.txt",
    "evaluator": "VALIDATOR_BRIEF.txt",
}
ROLES = tuple(BRIEF_FILES)
ROLE_PT = {"glossarist": "glossarista", "mapper": "mapeador", "hunter": "caçador de NONE",
           "auditor": "auditor do glossário", "evaluator": "avaliador"}


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


def briefs_dir() -> Path:
    return repo() / "briefs"


def results_dir() -> Path:
    return repo() / "results" / MODULE


def templates_dir() -> Path:
    return Path(__file__).resolve().parent / "templates"


def now() -> str:
    return _dt.datetime.now(TZ).replace(microsecond=0).isoformat()


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def sha256_file(p: Path) -> str:
    return sha256_bytes(Path(p).read_bytes())


def canon(obj) -> str:
    """JSON canônico de uma linha (chaves ordenadas, sem espaço supérfluo, UTF-8)."""
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(", ", ": "))


def pretty(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=1) + "\n"


def emit(msg: str) -> None:
    print(msg, flush=True)


def write_report(name: str, payload: dict) -> Path:
    p = data_dir() / f"{name}.json"
    body = {"module": MODULE, "generated_at": now()}
    body.update(payload)
    p.write_text(pretty(body), encoding="utf-8")
    return p
