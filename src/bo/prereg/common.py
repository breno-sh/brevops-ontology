"""Caminhos, leitura e utilidades comuns do PREREG."""

from __future__ import annotations

import hashlib
import json
import os
import runpy
from pathlib import Path

import yaml

REPO = Path(os.environ.get("BO_REPO") or Path(__file__).resolve().parents[3])
DATA = Path(os.environ.get("BO_DATA") or "/Users/breno/doutorado/brevops-data")
PREREG = REPO / "prereg"
RESULTS = REPO / "results" / "PREREG"
OUT_DATA = DATA / "PREREG"

FILES = {
    "html": PREREG / "PREREG.html",
    "metrics_spec": PREREG / "metrics_spec.yaml",
    "probe_types": PREREG / "probe_types.yaml",
    "h2h_fairness": PREREG / "h2h_fairness.yaml",
    "power_py": PREREG / "power.py",
    "power_json": PREREG / "power.json",
    "seeds": PREREG / "SEEDS.txt",
    "pilot_exit": PREREG / "pilot_exit.yaml",
}
OSF_FILE = RESULTS / "OSF_ID.txt"
MANIFEST = RESULTS / "MANIFEST.sha256"
SUMMARY = RESULTS / "summary.json"
CQ_SPEC = REPO / "requirements" / "cq_spec.jsonl"
C00_SCHEMA = REPO / "contracts" / "C00_conventions.schema.json"
CLAUSES = ["Definição", "População", "Direção", "Unidade", "Denominador", "Desconhecido"]
SEP = " | "


def sha_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def sha_file(p: Path) -> str:
    return sha_bytes(p.read_bytes())


def portable(p: Path) -> str:
    """$BO_REPO/... para caminhos dentro do repositório (vale no principal e em qualquer worktree)."""
    return "$BO_REPO/" + p.resolve().relative_to(REPO.resolve()).as_posix()


def yaml_dump(doc) -> str:
    return yaml.safe_dump(doc, allow_unicode=True, sort_keys=False, width=100000, default_flow_style=False)


def yaml_load(p: Path):
    return yaml.safe_load(p.read_text(encoding="utf-8"))


def json_dump(doc) -> str:
    return json.dumps(doc, ensure_ascii=False, indent=1) + "\n"


def power_module(path: Path | None = None) -> dict:
    """Carrega prereg/power.py (autocontido, fora do pacote) como módulo."""
    return runpy.run_path(str(path or FILES["power_py"]), run_name="bo_prereg_power")


def parse_definition(text: str) -> dict:
    """Separa as seis cláusulas rotuladas da definição de uma métrica do metrics_spec.yaml."""
    out: dict[str, str] = {}
    for part in text.split(SEP):
        label, _, body = part.partition(": ")
        out[label.strip()] = body.strip()
    return out
