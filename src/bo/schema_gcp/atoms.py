"""Átomos (C01 2.1.0) e tipos (C02) do schema do google pela biblioteca única (bo.schema.core).

A biblioteca faz tudo, inclusive o campo opcional 'write_only' (gravado como true só quando o schema o marca,
desde o SCHEMALIB f8b5414). Aqui só se chama a biblioteca e se contam os átomos write_only para o relatório.
"""

from __future__ import annotations

from pathlib import Path

from bo.schema import core


def build(schema: Path, version: str, atoms_out: Path, types_out: Path, provider: str = "google") -> dict:
    """Grava atoms.jsonl e types.jsonl ordenados; devolve contagens e o sha256 canônico do provider_schema."""
    ps = core.providers(core.load(schema))
    if provider not in ps:
        raise SystemExit(f"atoms: o schema não traz o provedor {provider} (traz: {', '.join(ps)})")
    types = list(core.iter_types(ps[provider], provider, version))
    wo = sum(1 for ts in types for a in ts.atoms if a.get("write_only"))
    na = core.write_jsonl(atoms_out, (a for ts in types for a in ts.atoms))
    nt = core.write_jsonl(types_out, (core.type_record(ts) for ts in types))
    return {"provider": provider, "provider_version": version, "types": nt, "atoms": na, "write_only": wo,
            "data_sources": len(ps[provider].get("data_source_schemas") or {}),
            "provider_schema_sha256": core.canonical_sha256(ps[provider])}
