"""Caminhos, hora (America/Recife), hash e E/S canônica do árbitro (ARBITERLIB)."""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
from pathlib import Path
from zoneinfo import ZoneInfo

TZ = ZoneInfo("America/Recife")
MODULE = "ARBITERLIB"


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


def arbiter_dir() -> Path:
    return repo() / "arbiter"


def results_dir() -> Path:
    return repo() / "results" / MODULE


def now() -> str:
    return _dt.datetime.now(TZ).replace(microsecond=0).isoformat()


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def sha256_file(p: Path) -> str:
    return sha256_bytes(Path(p).read_bytes())


def canon(obj) -> str:
    """JSON canônico (chaves ordenadas, sem espaços): base de igualdade e de hash."""
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def dump_json(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=1, sort_keys=True, default=str) + "\n"


def dump_jsonl(recs) -> str:
    return "".join(json.dumps(r, ensure_ascii=False, sort_keys=True, default=str) + "\n" for r in recs)


def load_jsonl(path: Path) -> list[dict]:
    out = []
    with open(path, encoding="utf-8") as fh:
        for n, line in enumerate(fh, 1):
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except ValueError as e:
                    raise SystemExit(f"{path}:{n}: JSON inválido: {e}")
    return out


def emit(msg: str) -> None:
    print(msg, flush=True)


def write_report(name: str, obj: dict) -> Path:
    """Relatório de execução (com hora) em $BO_DATA/ARBITERLIB/<name>.json."""
    p = data_dir() / f"{name}.json"
    obj = dict(obj)
    obj.setdefault("generated_at", now())
    obj.setdefault("timezone", "America/Recife")
    p.write_text(dump_json(obj), encoding="utf-8")
    return p


def provider_of(atom_id: str) -> str:
    """Prefixo CURIE (pa:x) ou provedor do C01 (aws:tipo:caminho): o que o árbitro chama de provedor."""
    return str(atom_id).split(":", 1)[0]


def base_claim_id(cid: str) -> str:
    """Id da alegação afirmada por trás de uma perna (sem o sufixo ~inv da inversa)."""
    return cid[:-4] if cid.endswith("~inv") else cid
