"""Caminhos, hora (America/Recife) e E/S JSON canônica do SEMANTICS."""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
from pathlib import Path
from zoneinfo import ZoneInfo

TZ = ZoneInfo("America/Recife")
MODULE = "SEMANTICS"


def repo() -> Path:
    env = os.environ.get("BO_REPO")
    if env:
        return Path(env)
    return Path(__file__).resolve().parents[3]


def data_root() -> Path:
    return Path(os.environ.get("BO_DATA", "/Users/breno/doutorado/brevops-data"))


def data_dir() -> Path:
    return data_root() / MODULE


def tmp_dir() -> Path:
    d = Path(os.environ.get("BO_TMP") or (data_root() / "tmp" / MODULE))
    d.mkdir(parents=True, exist_ok=True)
    return d


def semantics_dir() -> Path:
    return repo() / "semantics"


def results_dir() -> Path:
    return repo() / "results" / MODULE


def skos_schema_path() -> Path:
    return data_root() / "downloads" / "skos" / "skos.rdf"


# sha256 do core.rdf do W3C baixado (ver $BO_DATA/downloads/skos/SOURCE.txt). Se o arquivo mudar, o gate reprova.
SKOS_SHA256 = "e79633b8d0564816cee8a99f5c9acf9a0e6fc7257c7209acd684ecad53a89dd6"


def now() -> str:
    return _dt.datetime.now(TZ).replace(microsecond=0).isoformat()


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def sha256_file(p: Path) -> str:
    return sha256_bytes(Path(p).read_bytes())


def canon(obj) -> str:
    """JSON canônico (chaves ordenadas, sem espaços): base de igualdade e de hash."""
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def dump_json(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=1, sort_keys=True) + "\n"


def dump_jsonl(recs) -> str:
    return "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in recs)


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
    """Relatório de execução (com hora) em $BO_DATA/SEMANTICS/<name>.json."""
    d = data_dir()
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{name}.json"
    obj = dict(obj)
    obj.setdefault("generated_at", now())
    obj.setdefault("timezone", "America/Recife")
    p.write_text(dump_json(obj), encoding="utf-8")
    return p
