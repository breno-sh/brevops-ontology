"""Átomos (C01 2.1.0) e tipos (C02) do schema do google pela biblioteca única (bo.schema.core).

A biblioteca faz tudo (caminho, block_path, tf_type cty, flags, contagens, block_sha256, ordem e bytes).
O único acréscimo é o campo opcional 'write_only' da emenda 2.1.0 do C01, que a biblioteca ainda não grava:
ele entra como "write_only": true só nos átomos cujo atributo traz write_only no schema (ausente = false, como no
stub do CONTRACTS). O atributo é achado pelo mesmo percurso da biblioteca (core._walk), conferindo o caminho
átomo a átomo; os demais átomos saem byte a byte iguais aos do bo.schema.build.
"""

from __future__ import annotations

from pathlib import Path

from bo.schema import core


def annotate_write_only(ts: core.TypeSchema) -> int:
    """Marca write_only nos átomos do tipo; devolve quantos. Reprova se o percurso não casar com os átomos."""
    attrs = [(".".join(path), a) for kind, path, _bp, a in core._walk(ts.block, (), ()) if kind == "attr"]
    if len(attrs) != len(ts.atoms):
        raise core.SchemaError(f"{ts.type_id}: {len(attrs)} atributos no percurso, {len(ts.atoms)} átomos")
    n = 0
    for (path, a), atom in zip(attrs, ts.atoms):
        if atom["path"] != path:
            raise core.SchemaError(f"{ts.type_id}: percurso fora de ordem ({path} x {atom['path']})")
        if a.get("write_only"):
            atom["write_only"] = True
            n += 1
    return n


def build(schema: Path, version: str, atoms_out: Path, types_out: Path, provider: str = "google") -> dict:
    """Grava atoms.jsonl e types.jsonl ordenados; devolve contagens e o sha256 canônico do provider_schema."""
    ps = core.providers(core.load(schema))
    if provider not in ps:
        raise SystemExit(f"atoms: o schema não traz o provedor {provider} (traz: {', '.join(ps)})")
    types = list(core.iter_types(ps[provider], provider, version))
    wo = sum(annotate_write_only(ts) for ts in types)
    na = core.write_jsonl(atoms_out, (a for ts in types for a in ts.atoms))
    nt = core.write_jsonl(types_out, (core.type_record(ts) for ts in types))
    return {"provider": provider, "provider_version": version, "types": nt, "atoms": na, "write_only": wo,
            "data_sources": len(ps[provider].get("data_source_schemas") or {}),
            "provider_schema_sha256": core.canonical_sha256(ps[provider])}
