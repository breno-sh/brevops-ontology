"""Átomos C01 (2.1.0) de uma versão histórica, pela biblioteca única (bo.schema.build).

A bo.schema (SCHEMALIB) grava o C01 2.1.0 inteiro, inclusive write_only (só quando o schema o marca, e a regra
C01-WRITEONLY é conferida lá); aqui nada é reinterpretado: só se conferem as contagens contra o schema cru.
É a mesma biblioteca do SCHEMA-OCI, para que o átomo do pin seja comparável ao da versão histórica.
Os tipos (C02) são gerados para contar e conferir, mas não são saída do módulo.
"""

from __future__ import annotations

import json
from pathlib import Path

from bo.schema import build as libbuild
from bo.schema import core

from . import common


def count_schema_attributes(provider_schema: dict) -> int:
    """Nº de entradas 'attributes' em toda a profundidade dos resource_schemas (conferência independente)."""
    def walk(b: dict) -> int:
        return len(b.get("attributes") or {}) + sum(walk(bt.get("block") or {})
                                                     for bt in (b.get("block_types") or {}).values())
    return sum(walk(s.get("block") or {}) for s in (provider_schema.get("resource_schemas") or {}).values())


def make(schema_gz: Path, version: str, atoms_out: Path, types_out: Path) -> dict:
    """bo.schema.build (C01 2.1.0 + C02); confere as contagens contra o schema cru."""
    r = libbuild.build(schema_gz, common.PROVIDER, version, atoms_out, types_out)
    ps = core.providers(core.load(schema_gz))[common.PROVIDER]
    r["write_only"] = flag_totals(atoms_out)["write_only"]
    r["data_sources"] = len(ps.get("data_source_schemas") or {})
    r["resource_schemas"] = len(ps.get("resource_schemas") or {})
    r["schema_attributes"] = count_schema_attributes(ps)
    if r["schema_attributes"] != r["atoms"]:
        raise core.SchemaError(f"{r['atoms']} átomos != {r['schema_attributes']} entradas 'attributes' do schema")
    if r["resource_schemas"] != r["types"]:
        raise core.SchemaError(f"{r['types']} tipos != {r['resource_schemas']} resource_schemas")
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
