"""Átomos (C01 2.1.0) e tipos (C02) do schema extraído, pela biblioteca única (bo.schema.build).

A bo.schema (SCHEMALIB, desde f8b5414) grava o campo write_only do C01 2.1.0 só nos átomos que o schema
marca, e reprova C01-WRITEONLY (write_only exige configurable e não computed). Aqui não se acrescenta nem se
reinterpreta nada: a saída é a da biblioteca, mais as contagens que o relatório do módulo usa.
"""

from __future__ import annotations

import json
from pathlib import Path

from bo.schema import build as libbuild
from bo.schema import core


def make(schema_gz: Path, version: str, atoms_out: Path, types_out: Path) -> dict:
    """bo.schema.build (C01 2.1.0 + C02); devolve o relatório da biblioteca com write_only e data_sources."""
    r = libbuild.build(schema_gz, "aws", version, atoms_out, types_out)
    ps = core.providers(core.load(schema_gz))["aws"]
    r["write_only"] = flag_totals(atoms_out)["write_only"]
    r["data_sources"] = len(ps.get("data_source_schemas") or {})
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
