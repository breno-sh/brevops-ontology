"""Átomos C01 de um schema histórico pela biblioteca única (bo.schema.core, SCHEMALIB).

A biblioteca faz tudo: caminho, block_path, tf_type cty, flags, o campo opcional 'write_only' do C01 2.1.0
(gravado como true só quando o schema o marca, desde o SCHEMALIB f8b5414), ordem por tipo e caminho e os bytes de
cada linha (json.dumps com chaves ordenadas, como core.write_jsonl). Aqui só se chama a biblioteca, se conta e se
comprime. É o mesmo caminho do SCHEMA-GCP, o que deixa os átomos do pin (8.9.0) comparáveis byte a byte com os dele.

Saída: atoms_<versão>.jsonl.gz = gzip determinístico (mtime 0) das linhas que core.write_jsonl gravaria.
"""

from __future__ import annotations

import json
from pathlib import Path

from bo.schema import core

from . import common as C


def jsonl_bytes(records) -> bytes:
    return "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in records).encode("utf-8")


def build_bytes(schema: Path, version: str, provider: str = C.PROVIDER) -> tuple[bytes, dict]:
    """(bytes do JSONL dos átomos, contagens) de um schema.json(.gz) extraído."""
    ps = core.providers(core.load(schema))
    if provider not in ps:
        raise SystemExit(f"atoms: o schema não traz o provedor {provider} (traz: {', '.join(ps)})")
    types = list(core.iter_types(ps[provider], provider, version))
    atoms = [a for ts in types for a in ts.atoms]
    wo = sum(1 for a in atoms if a.get("write_only"))
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
