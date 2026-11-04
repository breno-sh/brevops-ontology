"""Átomos (C01 2.1.0) e tipos (C02) de uma versão histórica, pela biblioteca única (bo.schema.build).

O campo write_only do C01 2.1.0 vem da própria biblioteca (bo.schema.core.make_atom): só aparece, true, nos
átomos que o schema marca, e a biblioteca reprova a violação de C01-WRITEONLY. Versões antigas não têm a
marca e saem sem o campo. Aqui nada é acrescentado aos átomos: só se conta, valida e comprime.

Saída: atoms_<v>.jsonl.gz e types_<v>.jsonl.gz, cada um o JSONL da biblioteca (uma linha por registro,
chaves ordenadas, ordem (tipo, caminho)) em gzip determinístico: regenerar dá os mesmos bytes.
"""

from __future__ import annotations

import json
from pathlib import Path

from bo.schema import build as libbuild
from bo.schema import core

from . import common


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
    """bo.schema.build (C01 2.1.0 + C02) + contagens + validação + gzip determinístico."""
    work.mkdir(parents=True, exist_ok=True)
    aj, tj = work / "atoms.jsonl", work / "types.jsonl"
    r = libbuild.build(schema_gz, common.PROVIDER, version, aj, tj)
    ps = core.providers(core.load(schema_gz))[common.PROVIDER]
    r["data_sources"] = len(ps.get("data_source_schemas") or {})
    r["flags"] = flag_totals(aj)
    r["write_only"] = r["flags"]["write_only"]
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
