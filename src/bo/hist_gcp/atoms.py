"""Átomos C01 de um schema histórico pela biblioteca única (bo.schema.core, SCHEMALIB).

A biblioteca faz tudo (caminho, block_path, tf_type cty, flags, ordem por tipo e caminho, bytes de cada linha).
O único acréscimo é o campo opcional 'write_only' da emenda 2.1.0 do C01, gravado como "write_only": true só nos
átomos cujo atributo traz write_only no schema (ausente = false), achado pelo mesmo percurso da biblioteca
(core._walk) e conferido átomo a átomo; se a biblioteca já gravar o campo, nada é acrescentado. É a mesma regra do
SCHEMA-GCP, o que deixa os átomos do pin (8.9.0) comparáveis byte a byte com os dele.

Saída: atoms_<versão>.jsonl.gz = gzip determinístico (mtime 0) das linhas que core.write_jsonl gravaria.
"""

from __future__ import annotations

import json
from pathlib import Path

from bo.schema import core

from . import common as C


def annotate_write_only(ts: core.TypeSchema) -> int:
    """Marca write_only nos átomos do tipo; devolve quantos. Reprova se o percurso não casar com os átomos."""
    attrs = [(".".join(path), a) for kind, path, _bp, a in core._walk(ts.block, (), ()) if kind == "attr"]
    if len(attrs) != len(ts.atoms):
        raise core.SchemaError(f"{ts.type_id}: {len(attrs)} atributos no percurso, {len(ts.atoms)} átomos")
    n = 0
    for (path, a), atom in zip(attrs, ts.atoms):
        if atom["path"] != path:
            raise core.SchemaError(f"{ts.type_id}: percurso fora de ordem ({path} x {atom['path']})")
        if "write_only" in atom:
            n += bool(atom["write_only"])
            continue
        if a.get("write_only"):
            atom["write_only"] = True
            n += 1
    return n


def jsonl_bytes(records) -> bytes:
    return "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in records).encode("utf-8")


def build_bytes(schema: Path, version: str, provider: str = C.PROVIDER) -> tuple[bytes, dict]:
    """(bytes do JSONL dos átomos, contagens) de um schema.json(.gz) extraído."""
    ps = core.providers(core.load(schema))
    if provider not in ps:
        raise SystemExit(f"atoms: o schema não traz o provedor {provider} (traz: {', '.join(ps)})")
    types = list(core.iter_types(ps[provider], provider, version))
    wo = sum(annotate_write_only(ts) for ts in types)
    atoms = [a for ts in types for a in ts.atoms]
    raw = jsonl_bytes(atoms)
    counts = {
        "types": len(types),
        "atoms": len(atoms),
        "required": sum(a["required"] for a in atoms),
        "optional": sum(a["optional"] for a in atoms),
        "computed": sum(a["computed"] for a in atoms),
        "configurable": sum(a["configurable"] for a in atoms),
        "sensitive": sum(a["sensitive"] for a in atoms),
        "deprecated": sum(a["deprecated"] for a in atoms),
        "write_only": wo,
        "data_sources": len(ps[provider].get("data_source_schemas") or {}),
    }
    return raw, {**counts, "provider_schema_canonical_sha256": core.canonical_sha256(ps[provider])}


def write(schema: Path, version: str, dest: Path) -> dict:
    """Grava atoms_<versão>.jsonl.gz; devolve contagens e os sha256 (JSONL cru e gzip)."""
    raw, counts = build_bytes(schema, version)
    gz = C.gzip_bytes(raw, f"atoms_{version}.jsonl")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(gz)
    return {**counts, "jsonl_sha256": C.sha256_bytes(raw), "gz_sha256": C.sha256_bytes(gz), "jsonl_bytes": len(raw)}
