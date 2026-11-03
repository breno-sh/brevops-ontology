"""Caminhos, hora e E/S comuns do harness azurerm (C00: BO_REPO, BO_DATA, BO_TMP; fuso America/Recife)."""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
from pathlib import Path
from zoneinfo import ZoneInfo

MODULE = "HARNESS-AZURE"
PROVIDER = "azurerm"
TZ = ZoneInfo("America/Recife")
PKG = Path(__file__).resolve().parent


class HarnessError(Exception):
    """Erro de uso ou de entrada (saída 2 nos comandos)."""


def repo() -> Path:
    r = os.environ.get("BO_REPO")
    return Path(r) if r else PKG.parents[3]


def data_root() -> Path:
    return Path(os.environ.get("BO_DATA") or "/Users/breno/doutorado/brevops-data")


def data_dir() -> Path:
    return data_root() / MODULE


def tmp_dir() -> Path:
    """$BO_TMP exclusivo do módulo (nunca /tmp)."""
    p = Path(os.environ.get("BO_TMP") or (data_root() / "tmp" / MODULE))
    p.mkdir(parents=True, exist_ok=True)
    return p


def templates_dir() -> Path:
    return repo() / "deploy" / "fixtures" / "azurerm" / "_templates"


def results_dir() -> Path:
    return repo() / "results" / MODULE


def now() -> str:
    return _dt.datetime.now(TZ).replace(microsecond=0).isoformat()


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def read_jsonl(p: Path) -> list[dict]:
    out = []
    with open(p, encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError as e:
                raise HarnessError(f"{p}:{i}: JSON inválido: {e}") from None
    return out


def dumps(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=1, sort_keys=True) + "\n"


def jsonl(recs) -> str:
    return "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in recs)


def portable(p: Path) -> str:
    """Caminho portátil ($BO_REPO/..., $BO_DATA/..., $BO_TMP/...) quando possível."""
    p = Path(p).resolve()
    for var, base in (("$BO_TMP", tmp_dir()), ("$BO_REPO", repo()), ("$BO_DATA", data_root())):
        try:
            rel = p.relative_to(Path(base).resolve())
        except ValueError:
            continue
        return var if str(rel) == "." else f"{var}/{rel}"
    return str(p)
