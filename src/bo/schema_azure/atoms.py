"""Átomos (C01 2.1.0) e tipos (C02) do schema extraído, só pela biblioteca única (bo.schema.build).

A bo.schema grava o campo write_only do C01 2.1.0 (só quando o schema o marca) e confere a regra
C01-WRITEONLY; aqui não há passada própria: só se contam as flags para o relatório.
"""

from __future__ import annotations

import json
from pathlib import Path

from bo.schema import build as libbuild
from bo.schema import core

from . import common


def make(schema_gz: Path, version: str, atoms_out: Path, types_out: Path) -> dict:
    """bo.schema.build (C01 2.1.0 + C02) e as contagens que o relatório usa."""
    r = libbuild.build(schema_gz, common.PROVIDER, version, atoms_out, types_out)
    ps = core.providers(core.load(schema_gz))[common.PROVIDER]
    with open(atoms_out, encoding="utf-8") as f:
        wo = [a["atom_id"] for a in map(json.loads, f) if a.get("write_only")]
    r["write_only"] = len(wo)
    r["write_only_atoms"] = wo
    r["data_sources"] = len(ps.get("data_source_schemas") or {})
    r["outras_familias"] = {k: len(ps.get(k) or {}) for k in sorted(ps)
                            if k.endswith("_schemas") and k not in ("resource_schemas", "data_source_schemas")}
    return r


def flag_totals(atoms_path: Path) -> dict:
    keys = ("required", "optional", "computed", "configurable", "sensitive", "deprecated", "write_only")
    tot = dict.fromkeys(keys, 0)
    nested = 0
    with open(atoms_path, encoding="utf-8") as f:
        for line in f:
            a = json.loads(line)
            for k in keys:
                tot[k] += bool(a.get(k))
            nested += a["nesting"] != "none"
    tot["dentro_de_bloco"] = nested
    return tot
