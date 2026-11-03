"""Caminhos, carimbo de tempo (America/Recife) e relatórios dos gates do TRANSFORMS."""

from __future__ import annotations

import datetime as _dt
import json
import os
from pathlib import Path
from zoneinfo import ZoneInfo

TZ = ZoneInfo("America/Recife")
MODULE = "TRANSFORMS"


def now() -> str:
    return _dt.datetime.now(TZ).isoformat(timespec="seconds")


def repo() -> Path:
    env = os.environ.get("BO_REPO")
    if env:
        return Path(env)
    return Path(__file__).resolve().parents[3]


def data() -> Path:
    return Path(os.environ.get("BO_DATA", "/Users/breno/doutorado/brevops-data"))


def tmp() -> Path:
    p = Path(os.environ.get("BO_TMP") or data() / "tmp" / MODULE)
    p.mkdir(parents=True, exist_ok=True)
    return p


def transforms_yaml() -> Path:
    return repo() / "transforms" / "transforms.yaml"


def grammar_json() -> Path:
    return repo() / "transforms" / "conditions.grammar.json"


def load_yaml(p: Path) -> dict:
    import yaml
    with open(p, encoding="utf-8") as f:
        return yaml.safe_load(f)


def report(name: str, obj: dict) -> Path:
    """Relatório de gate em $BO_DATA/TRANSFORMS/<name>.json, com carimbo (fora do git)."""
    out = data() / MODULE / f"{name}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    body = {"module": MODULE, "gate": name, "generated_at": now(), **obj}
    tmpf = out.with_name(out.name + ".tmp")
    with open(tmpf, "w", encoding="utf-8") as f:
        json.dump(body, f, ensure_ascii=False, indent=1, default=str)
        f.write("\n")
    os.replace(tmpf, out)
    return out


def say(msg: str) -> None:
    print(f"[{now()}] {msg}", flush=True)
