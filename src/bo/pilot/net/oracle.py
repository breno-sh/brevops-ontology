"""Ponte para o oráculo congelado do PILOT-NET-ORACLE (pilot/net/oracle/net_oracle, só biblioteca padrão).

O código do oráculo não é copiado nem alterado: é importado da árvore do repositório, como o ORACLE.html manda, e o
sha256 de cada arquivo dele vai para o resultado (o PILOT-EXIT confere que o oráculo usado é o congelado).
"""

from __future__ import annotations

import hashlib
import importlib
import json
import os
import sys
from pathlib import Path


def repo() -> Path:
    return Path(os.environ.get("BO_REPO") or Path(__file__).resolve().parents[4])


def oracle_dir() -> Path:
    return repo() / "pilot" / "net" / "oracle"


def load():
    d = str(oracle_dir())
    if d not in sys.path:
        sys.path.insert(0, d)
    return importlib.import_module("net_oracle")


def catalog() -> dict:
    return json.loads((oracle_dir() / "directions.json").read_text(encoding="utf-8"))


def fingerprint() -> dict:
    out = {}
    for p in sorted(oracle_dir().rglob("*")):
        if p.is_file() and "__pycache__" not in p.parts and p.suffix in (".py", ".json", ".html"):
            out[str(p.relative_to(repo()))] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


def fixtures(dirpath: Path | None = None, split: str = "calib") -> list:
    d = dirpath or (repo() / "pilot" / "net" / "fixtures_calib")
    out = []
    for p in sorted(d.glob("*.json")):
        fx = json.loads(p.read_text(encoding="utf-8"))
        if fx.get("schema") != "bo.pilot_net.fixture/1":
            continue
        if split and fx.get("split") != split:
            raise SystemExit(f"{p.name}: split {fx.get('split')!r}, esperado {split!r} (retidas não entram aqui)")
        out.append(fx)
    return out


def translation_cases(dirpath: Path | None = None) -> list:
    d = (dirpath or (repo() / "pilot" / "net" / "fixtures_calib")) / "translations"
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(d.glob("*.json"))] if d.exists() else []
