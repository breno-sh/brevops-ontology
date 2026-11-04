"""Átomos (C01 2.1.0) e tipos (C02) de uma versão histórica, pela biblioteca única (bo.schema.build).

A bo.schema (SCHEMALIB) grava os campos do C01 2.0.0. O C01 2.1.0 acrescentou o campo opcional write_only
(ausente = false). Aqui só se acrescenta esse campo, lido do mesmo schema pelo mesmo caminho do átomo, sem
tocar em nenhum outro campo nem em contagem: write_only aparece (true) apenas nos átomos que o schema marca
com "write_only": true. Versões antigas não têm a marca e saem sem o campo. A regra C01-WRITEONLY (write_only
implica configurable e não computed) é conferida aqui; violação reprova.

Saída: atoms_<v>.jsonl.gz e types_<v>.jsonl.gz, cada um o JSONL da biblioteca (uma linha por registro,
chaves ordenadas, ordem (tipo, caminho)) em gzip determinístico: regenerar dá os mesmos bytes.
"""

from __future__ import annotations

import json
from pathlib import Path

from bo.schema import build as libbuild
from bo.schema import core

from . import common


def raw_attribute(block: dict, atom: dict) -> dict:
    """O atributo do schema cru que gerou o átomo, seguindo block_path e o último nome de path."""
    b = block
    for e in atom["block_path"]:
        b = ((b.get("block_types") or {})[e["block"]]).get("block") or {}
    name = atom["path"].rsplit(".", 1)[-1]
    return (b.get("attributes") or {})[name]


def write_only_pass(atoms_path: Path, provider_schema: dict) -> dict:
    """Acrescenta write_only aos átomos marcados no schema; reescreve com a serialização da biblioteca."""
    rs = provider_schema.get("resource_schemas") or {}
    out, wo, bad = [], [], []
    with open(atoms_path, encoding="utf-8") as f:
        for line in f:
            a = json.loads(line)
            raw = raw_attribute(rs[a["resource_type"]].get("block") or {}, a)
            if raw.get("write_only"):
                if not a["configurable"] or a["computed"]:
                    bad.append(a["atom_id"])
                a["write_only"] = True
                wo.append(a["atom_id"])
            out.append(a)
    if bad:
        raise core.SchemaError(f"C01-WRITEONLY violada em {len(bad)} átomo(s): {bad[:5]}")
    core.write_jsonl(atoms_path, out)
    return {"write_only": len(wo)}


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


def make(schema_gz: Path, version: str, work: Path, atoms_gz: Path, types_gz: Path,
         validate: bool = True) -> dict:
    """bo.schema.build (C01 2.0.0 + C02) + passada write_only (C01 2.1.0) + validação + gzip determinístico."""
    work.mkdir(parents=True, exist_ok=True)
    aj, tj = work / "atoms.jsonl", work / "types.jsonl"
    r = libbuild.build(schema_gz, common.PROVIDER, version, aj, tj)
    ps = core.providers(core.load(schema_gz))[common.PROVIDER]
    r.update(write_only_pass(aj, ps))
    r["data_sources"] = len(ps.get("data_source_schemas") or {})
    r["flags"] = flag_totals(aj)
    if validate:
        from bo.contracts import validate as V
        for alias, p in (("C01_atoms", aj), ("C02_types", tj)):
            res = V.validate(alias, p)
            if not res.ok:
                raise core.SchemaError(f"{alias} de {version} não confere: {res.errors[:5]}")
        r["validated"] = ["C01_atoms", "C02_types"]
    r["atoms_jsonl_sha256"] = common.sha256_file(aj)
    r["types_jsonl_sha256"] = common.sha256_file(tj)
    common.write_gz(aj, atoms_gz, f"atoms_{version}.jsonl")
    common.write_gz(tj, types_gz, f"types_{version}.jsonl")
    r["atoms_gz_sha256"] = common.sha256_file(atoms_gz)
    r["types_gz_sha256"] = common.sha256_file(types_gz)
    aj.unlink()
    tj.unlink()
    return r
