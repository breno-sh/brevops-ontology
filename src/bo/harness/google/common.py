"""Caminhos, carimbo (America/Recife), JSON canônico e leitura/validação de arquivos de contrato."""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
import re
from pathlib import Path
from zoneinfo import ZoneInfo

TZ = ZoneInfo("America/Recife")
MODULE = "HARNESS-GCP"
PROVIDER = "google"
PROVIDER_SOURCE = "registry.terraform.io/hashicorp/google"


def now() -> str:
    return _dt.datetime.now(TZ).isoformat(timespec="seconds")


def repo() -> Path:
    env = os.environ.get("BO_REPO")
    return Path(env) if env else Path(__file__).resolve().parents[4]


def data() -> Path:
    return Path(os.environ.get("BO_DATA", "/Users/breno/doutorado/brevops-data"))


_MODULE_TMP = re.compile(r"^[A-Z][A-Z0-9]*(-[A-Z0-9]+)*$")


def tmp() -> Path:
    """$BO_TMP do módulo que roda o processo (N8): $BO_DATA/tmp/<ID>, um nível só, nunca /tmp.

    Sem BO_TMP é o do HARNESS-GCP. Quem reusa o renderizador (pilotos) roda com o próprio $BO_DATA/tmp/<ID> e não
    precisa trocar esta função; o harness só escreve dentro dele (achado do PILOT-STO-E2E, controls.json).
    """
    root = (data() / "tmp").resolve()
    p = Path(os.environ.get("BO_TMP") or root / MODULE).resolve()
    if p.parent != root or not _MODULE_TMP.match(p.name):
        raise SystemExit(f"BO_TMP fora de $BO_DATA/tmp/<ID do módulo>: {p}")
    p.mkdir(parents=True, exist_ok=True)
    return p


def module_data() -> Path:
    p = data() / MODULE
    p.mkdir(parents=True, exist_ok=True)
    return p


def templates() -> Path:
    return repo() / "deploy" / "fixtures" / "google" / "_templates"


def pins() -> dict:
    return json.loads((repo() / "universe" / "pins.json").read_text(encoding="utf-8"))


def provider_pin() -> dict:
    for p in pins()["providers"]:
        if p["provider"] == PROVIDER:
            return p
    raise SystemExit("universe/pins.json sem o provider google")


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def canon(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def dump(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=1, sort_keys=True) + "\n"


def read_jsonl(p: Path) -> list[dict]:
    out = []
    for i, line in enumerate(Path(p).read_text(encoding="utf-8").splitlines(), 1):
        if line.strip():
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError as e:
                raise ValueError(f"{p}:{i}: JSON inválido: {e}") from e
    return out


def write_jsonl(p: Path, recs) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("".join(canon(r) + "\n" for r in recs), encoding="utf-8")


def validate(alias: str, path: Path) -> list[str]:
    """Validador único do CONTRACTS (schema + regras semânticas); devolve a lista de erros."""
    from bo.contracts import validate as V
    return list(V.validate(alias, Path(path)).errors)


def slug(s: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in s).lower()
