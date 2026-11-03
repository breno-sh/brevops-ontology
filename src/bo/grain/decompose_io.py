"""E/S comum dos verificadores usados pelo DECOMPOSE (coverage, permutation, relations).

Entradas padrão (as do DECOMPOSE no plano): $BO_DATA/SCHEMA-*/atoms.jsonl (C01),
$BO_DATA/SERVICE-EVIDENCE/service_evidence.jsonl (C25), $BO_DATA/ROLES/roles.jsonl (C04, opcional),
$BO_DATA/DECOMPOSE/canonical_units.jsonl e canonical_atoms.jsonl (C19). Com --fixtures, os verificadores
rodam sobre os mundos sintéticos do GRAIN (e sobre controles quebrados de propósito, que têm de reprovar).
"""

from __future__ import annotations

import glob
import sys
from pathlib import Path

from .common import data_root, load_jsonl


class MissingInput(SystemExit):
    pass


def need(path: Path, what: str) -> Path:
    if not Path(path).is_file():
        print(f"entrada ausente ({what}): {path}", file=sys.stderr)
        raise MissingInput(2)
    return Path(path)


def schema_atoms(pattern: str | None = None) -> dict[str, list[dict]]:
    pat = pattern or str(data_root() / "SCHEMA-*" / "atoms.jsonl")
    files = sorted(glob.glob(pat))
    if not files:
        print(f"entrada ausente (átomos C01): {pat}", file=sys.stderr)
        raise MissingInput(2)
    by: dict[str, list[dict]] = {}
    for f in files:
        for a in load_jsonl(f):
            by.setdefault(a["provider"], []).append(a)
    return by


def service_evidence(path: str | None = None) -> list[dict]:
    p = Path(path) if path else data_root() / "SERVICE-EVIDENCE" / "service_evidence.jsonl"
    return load_jsonl(need(p, "evidência de serviço C25"))


def roles(path: str | None = None) -> dict:
    p = Path(path) if path else data_root() / "ROLES" / "roles.jsonl"
    if not p.is_file():
        return {}
    return {r["atom_id"]: r["role"] for r in load_jsonl(p)}


def c19(units: str | None = None, atoms: str | None = None) -> tuple[list[dict], list[dict]]:
    d = data_root() / "DECOMPOSE"
    pu = need(Path(units) if units else d / "canonical_units.jsonl", "C19 canonical_units")
    pa = need(Path(atoms) if atoms else d / "canonical_atoms.jsonl", "C19 canonical_atoms")
    return load_jsonl(pu), load_jsonl(pa)


def arg(argv: list, name: str, default=None):
    if name in argv:
        i = argv.index(name)
        if i + 1 < len(argv):
            return argv[i + 1]
    return default
