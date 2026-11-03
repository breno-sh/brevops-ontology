"""Átomos (C01 2.1.0) e tipos (C02) do schema extraído, pela biblioteca única (bo.schema.build).

A bo.schema (SCHEMALIB) grava os campos do C01 2.0.0. O C01 2.1.0 acrescentou o campo opcional write_only
(ausente = false), que a biblioteca ainda não emite. Aqui só se acrescenta esse campo, lido do mesmo schema
pelo mesmo caminho do átomo, sem tocar em nenhum outro campo nem em contagem: write_only aparece (true)
apenas nos átomos que o schema marca com "write_only": true, como no stub do C01.
A regra C01-WRITEONLY (write_only implica configurable e não computed) é conferida; violação reprova.
"""

from __future__ import annotations

import json
from pathlib import Path

from bo.schema import build as libbuild
from bo.schema import core


def raw_attribute(block: dict, atom: dict) -> dict:
    """O atributo do schema cru que gerou o átomo, seguindo block_path e o último nome de path."""
    b = block
    for e in atom["block_path"]:
        b = ((b.get("block_types") or {})[e["block"]]).get("block") or {}
    name = atom["path"].rsplit(".", 1)[-1]
    return (b.get("attributes") or {})[name]


def write_only_pass(atoms_path: Path, provider_schema: dict) -> dict:
    """Acrescenta write_only aos átomos marcados no schema; reescreve o arquivo com a mesma serialização."""
    rs = provider_schema.get("resource_schemas") or {}
    out, n_wo, bad = [], 0, []
    with open(atoms_path, encoding="utf-8") as f:
        for line in f:
            a = json.loads(line)
            raw = raw_attribute(rs[a["resource_type"]].get("block") or {}, a)
            if raw.get("write_only"):
                if not a["configurable"] or a["computed"]:
                    bad.append(a["atom_id"])
                a["write_only"] = True
                n_wo += 1
            out.append(a)
    if bad:
        raise core.SchemaError(f"C01-WRITEONLY violada em {len(bad)} átomo(s): {bad[:5]}")
    core.write_jsonl(atoms_path, out)
    return {"write_only": n_wo}


def make(schema_gz: Path, version: str, atoms_out: Path, types_out: Path) -> dict:
    """bo.schema.build (C01 2.0.0 + C02) e depois a passada write_only (C01 2.1.0)."""
    r = libbuild.build(schema_gz, "aws", version, atoms_out, types_out)
    ps = core.providers(core.load(schema_gz))["aws"]
    r.update(write_only_pass(atoms_out, ps))
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
