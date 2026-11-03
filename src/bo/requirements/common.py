"""Caminhos, leitura e coleta do conteúdo do REQUIREMENTS."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

OUT_FILES = ("requirements.jsonl", "commitments.jsonl", "cq_spec.jsonl", "REQUIREMENTS.html")
KIND_FILE = {"requirements": "requirements.jsonl", "commitments": "commitments.jsonl", "cq_spec": "cq_spec.jsonl"}


def repo() -> Path:
    env = os.environ.get("BO_REPO")
    if env:
        return Path(env)
    return Path(__file__).resolve().parents[3]


def out_dir() -> Path:
    return repo() / "requirements"


def results_dir() -> Path:
    return repo() / "results" / "REQUIREMENTS"


def load_jsonl(path: Path) -> list[dict]:
    recs = []
    with open(path, encoding="utf-8") as fh:
        for n, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                recs.append(json.loads(line))
            except ValueError as e:
                raise SystemExit(f"{path}:{n}: JSON inválido: {e}")
    return recs


def dump_jsonl(recs: list[dict]) -> str:
    return "".join(json.dumps(r, ensure_ascii=False, sort_keys=False) + "\n" for r in recs)


def collect():
    """Conteúdo autoral: (requisitos, compromissos, CQs) na ordem de publicação."""
    from .content import c_bucket, c_db, c_firewall, c_general, c_iam, c_lb, c_nic, cqs, requirements
    cmts = []
    for mod in (c_bucket, c_nic, c_firewall, c_iam, c_lb, c_db, c_general):
        cmts.extend(mod.C)
    return list(requirements.R), cmts, list(cqs.Q)


def load_published(d: Path | None = None):
    d = d or out_dir()
    missing = [f for f in KIND_FILE.values() if not (d / f).is_file()]
    if missing:
        raise SystemExit(f"arquivos ausentes em {d}: {', '.join(missing)} (rode python -I -m bo.requirements.build)")
    return (load_jsonl(d / KIND_FILE["requirements"]), load_jsonl(d / KIND_FILE["commitments"]),
            load_jsonl(d / KIND_FILE["cq_spec"]))


def fail(msgs: list[str], title: str) -> int:
    print(f"{title}: REPROVADO ({len(msgs)} problema(s))", file=sys.stderr)
    for m in msgs[:200]:
        print("  - " + m, file=sys.stderr)
    return 1
