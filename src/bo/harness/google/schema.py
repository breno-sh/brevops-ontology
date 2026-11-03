"""Acesso ao schema do google fixado: índice compacto (_templates/schema_index.json) ou providers-schema.json inteiro."""

from __future__ import annotations

import json
from pathlib import Path

from . import common as C
from .schema_index import compact_block, from_disk


class Schema:
    def __init__(self, resources: dict, data_sources: dict, version: str, source: str, sha256: str):
        self.resources, self.data_sources = resources, data_sources
        self.version, self.source, self.sha256 = version, source, sha256

    @classmethod
    def load(cls, full_schema: Path | None = None) -> "Schema":
        if full_schema is None:
            d = json.loads((C.templates() / "schema_index.json").read_text(encoding="utf-8"))
            pin = C.provider_pin()
            if d["version"] != pin["version"] or d["schema_sha256"] != pin["schema_sha256"]:
                raise SystemExit(f"schema_index.json é do google {d['version']}, mas o fixado é {pin['version']}; "
                                 "regenere com python -I -m bo.harness.google.schema_index")
            return cls({t: from_disk(b) for t, b in d["resources"].items()},
                       {t: from_disk(b) for t, b in d["data_sources"].items()},
                       d["version"], d["source"], d["schema_sha256"])
        pin = C.provider_pin()
        sha = C.sha256_file(full_schema)
        if sha != pin["schema_sha256"]:
            raise SystemExit(f"{full_schema}: sha256 diferente do schema fixado do google {pin['version']}")
        ps = json.loads(full_schema.read_text(encoding="utf-8"))["provider_schemas"][C.PROVIDER_SOURCE]
        return _Lazy(ps, pin["version"], pin["source"], sha)

    def block(self, kind: str, rtype: str) -> dict | None:
        return (self.resources if kind == "resource" else self.data_sources).get(rtype)


class _Lazy(Schema):
    def __init__(self, ps: dict, version: str, source: str, sha: str):
        super().__init__({}, {}, version, source, sha)
        self._ps = ps

    def block(self, kind: str, rtype: str) -> dict | None:
        cache = self.resources if kind == "resource" else self.data_sources
        if rtype not in cache:
            src = self._ps["resource_schemas" if kind == "resource" else "data_source_schemas"].get(rtype)
            if src is None:
                return None
            cache[rtype] = compact_block(src["block"])
        return cache[rtype]


def attr_at(block: dict, segments: list[str]) -> tuple[dict | None, list[str]]:
    """Desce por blocos (índices numéricos de instância são pulados) até o atributo do caminho de campo.

    Devolve (atributo, resto): resto são as chaves dentro de um atributo mapa/objeto. (None, []) se não existe.
    """
    node = block
    i = 0
    while i < len(segments):
        s = segments[i]
        if s.isdigit():
            i += 1
            continue
        if s in node["attributes"]:
            return node["attributes"][s], segments[i + 1:]
        if s in node["blocks"]:
            node = node["blocks"][s]["block"]
            i += 1
            continue
        return None, []
    return None, []


def is_settable(attr: dict) -> bool:
    f = attr["flags"]
    return "required" in f or "optional" in f
