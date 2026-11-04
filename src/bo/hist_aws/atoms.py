"""Átomos C01 (2.1.0) de um schema histórico, pela biblioteca única (bo.schema.build, SCHEMALIB), em .jsonl.gz.

A bo.schema grava os campos do C01 2.0.0. O C01 2.1.0 acrescentou write_only (opcional; ausente = false), que
a biblioteca ainda não emite: aqui só se acrescenta esse campo, lido do mesmo schema pelo mesmo caminho do
átomo, nos átomos que o schema marca com "write_only": true. Nenhum outro campo nem contagem muda.
Versões antigas não têm write_only no schema: nelas o campo simplesmente não aparece.
A regra C01-WRITEONLY (write_only implica configurable e não computed) é conferida; violação reprova.

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


def raw_attribute(block: dict, atom: dict) -> dict:
    """O atributo do schema cru que gerou o átomo, seguindo block_path e o último nome de path."""
    b = block
    for e in atom["block_path"]:
        b = ((b.get("block_types") or {})[e["block"]]).get("block") or {}
    name = atom["path"].rsplit(".", 1)[-1]
    return (b.get("attributes") or {})[name]


def write_only_pass(atoms_path: Path, provider_schema: dict) -> int:
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
    return n_wo


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
    r["write_only"] = write_only_pass(plain, ps)
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
