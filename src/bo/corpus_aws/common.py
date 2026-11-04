"""Caminhos, parâmetros e escrita canônica do CORPUS-AWS."""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
from pathlib import Path
from zoneinfo import ZoneInfo

MODULE = "CORPUS-AWS"
PROVIDER = "aws"
TZ = ZoneInfo("America/Recife")

OUT_FILES = ("usage.jsonl", "atom_totals.jsonl", "build_report.json", "counts.json")
# limiar de publicação de nomes no relatório: um par (tipo, caminho) não casado ou um tipo fora do schema só
# aparece por nome se ocorre em >= N famílias (o resto entra só no total), como o vocabulário do HCL
NAME_MIN_FAMILIES = 5
TOP_N = 50


def bo_data() -> Path:
    return Path(os.environ.get("BO_DATA", "/Users/breno/doutorado/brevops-data"))


def bo_repo() -> Path:
    return Path(os.environ.get("BO_REPO", "/Users/breno/doutorado/brevops-ontology"))


def out_dir() -> Path:
    return bo_data() / MODULE


def staging_dir() -> Path:
    return out_dir() / ".staging"


def tmp_dir() -> Path:
    p = Path(os.environ.get("BO_TMP") or (bo_data() / "tmp" / MODULE))
    p.mkdir(parents=True, exist_ok=True)
    return p


def results_dir() -> Path:
    return bo_repo() / "results" / MODULE


def inputs() -> dict[str, Path]:
    d = bo_data()
    return {"resources": d / "HCL" / "resources.parquet",
            "symbolic_config": d / "HCL" / "symbolic_config.jsonl",
            "symbolic_index": d / "HCL" / "symbolic_config.index.json",
            "atoms": d / "SCHEMA-AWS" / "atoms.jsonl"}


def portable(p: Path) -> str:
    s = str(p)
    for var, root in (("$BO_DATA", str(bo_data())), ("$BO_REPO", str(bo_repo()))):
        if s == root or s.startswith(root + "/"):
            return var + s[len(root):]
    return s


def now() -> str:
    return _dt.datetime.now(TZ).replace(microsecond=0).isoformat()


def sha256_file(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 22), b""):
            h.update(b)
    return h.hexdigest()


def write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".part")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=1) + "\n", encoding="utf-8")
    os.replace(tmp, path)
