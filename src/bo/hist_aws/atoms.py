"""Átomos C01 (2.1.0) de um schema histórico, pela biblioteca única (bo.schema.build, SCHEMALIB), em .jsonl.gz.

A bo.schema grava o C01 2.1.0 inteiro, inclusive write_only (só quando o schema o marca; a regra C01-WRITEONLY
é conferida lá): aqui nada é reinterpretado. Versões antigas não têm write_only no schema: o campo não aparece.
Conferência independente: nº de átomos == nº de entradas 'attributes' do schema cru, nº de tipos == resource_schemas.
Os tipos (C02) são gerados para contar, mas não são saída do módulo.

Saída determinística: linhas ordenadas por (tipo, caminho) com chaves ordenadas (bo.schema.core.write_jsonl),
comprimidas com gzip mtime 0, nível 9 e nome interno fixo; regenerar dá os mesmos bytes.
"""

from __future__ import annotations

import gzip
import json
import shutil
from pathlib import Path

from bo.schema import build as libbuild
from bo.schema import core

from . import common

FLAG_KEYS = ("required", "optional", "computed", "configurable", "sensitive", "deprecated", "write_only")


def count_schema_attributes(provider_schema: dict) -> int:
    """Nº de entradas 'attributes' em toda a profundidade dos resource_schemas (conferência independente)."""
    def walk(b: dict) -> int:
        return len(b.get("attributes") or {}) + sum(walk(bt.get("block") or {})
                                                     for bt in (b.get("block_types") or {}).values())
    return sum(walk(s.get("block") or {}) for s in (provider_schema.get("resource_schemas") or {}).values())


def gzip_det(src: Path, dest: Path, inner_name: str) -> None:
    """gzip determinístico (mtime 0, nível 9, nome interno fixo), atômico via .part."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + ".part")
    with open(src, "rb") as fin, open(part, "wb") as f:
        with gzip.GzipFile(filename=inner_name, mode="wb", fileobj=f, mtime=0, compresslevel=9) as g:
            shutil.copyfileobj(fin, g, 1 << 20)
    part.replace(dest)


def flag_totals(atoms_jsonl: Path) -> dict:
    tot = dict.fromkeys(FLAG_KEYS, 0)
    nested = 0
    with open(atoms_jsonl, encoding="utf-8") as f:
        for line in f:
            a = json.loads(line)
            for k in FLAG_KEYS:
                tot[k] += bool(a.get(k))
            nested += a["nesting"] != "none"
    tot["dentro_de_bloco"] = nested
    return tot


def make(schema_gz: Path, version: str, work: Path, dest: Path) -> dict:
    """schema.json.gz -> atoms.jsonl (C01 2.1.0, validado) -> dest (.jsonl.gz). Devolve contagens e hashes."""
    from bo.contracts import validate as V
    work.mkdir(parents=True, exist_ok=True)
    plain, types = work / "atoms.jsonl", work / "types.jsonl"
    r = libbuild.build(schema_gz, common.PROVIDER, version, plain, types)
    ps = core.providers(core.load(schema_gz))[common.PROVIDER]
    r["write_only"] = flag_totals(plain)["write_only"]
    n_attr = count_schema_attributes(ps)
    if n_attr != r["atoms"] or len(ps.get("resource_schemas") or {}) != r["types"]:
        raise core.SchemaError(f"{version}: {r['atoms']} átomos/{r['types']} tipos != {n_attr} 'attributes'/"
                               f"{len(ps.get('resource_schemas') or {})} resource_schemas do schema cru")
    r["data_sources"] = len(ps.get("data_source_schemas") or {})
    res = V.validate("C01_atoms", plain)
    if not res.ok:
        raise core.SchemaError(f"C01 não confere em {version}: {res.errors[:5]}")
    r["flags"] = flag_totals(plain)
    r["atoms_jsonl_sha256"] = common.sha256_file(plain)
    gzip_det(plain, dest, f"atoms_{version}.jsonl")
    r["atoms_gz_sha256"] = common.sha256_file(dest)
    r["atoms_gz_bytes"] = dest.stat().st_size
    r["c01_ok"] = True
    return r


def read_atoms(path: Path):
    """Itera os átomos de um atoms_<v>.jsonl.gz."""
    with gzip.open(path, "rt", encoding="utf-8") as f:
        for line in f:
            yield json.loads(line)
