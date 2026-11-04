"""Schema do provider fixado: saída de `terraform providers schema -json` do binário assinado do pin (D1), na
pré-busca $BO_DATA/downloads/prefetch/<provedor>/<versão>/providers-schema.json, a mesma que os HARNESS-* usam.
O sha256 do arquivo tem de ser o schema_sha256 de universe/pins.json (PINS); senão nada é conferido."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from .common import ProbeError, data, pins_path, sha256_file
from .templates import PROVIDER_SOURCE


def pins() -> dict:
    d = json.loads(pins_path().read_text(encoding="utf-8"))
    return {e["provider"]: e for e in d["providers"]} | {"_terraform": d["terraform"]}


def schema_path(provider: str) -> Path:
    v = pins()[provider]["version"]
    return data() / "downloads" / "prefetch" / provider / v / "providers-schema.json"


@lru_cache(maxsize=4)
def _load(provider: str) -> dict:
    pin = pins()[provider]
    p = schema_path(provider)
    if not p.is_file():
        raise ProbeError(f"schema fixado do {provider} ausente: {p.name}", "SCHEMA")
    sha = sha256_file(p)
    if sha != pin["schema_sha256"]:
        raise ProbeError(f"schema do {provider} não é o fixado (sha256 {sha[:12]}…)", "SCHEMA")
    doc = json.loads(p.read_text(encoding="utf-8"))
    return doc["provider_schemas"][PROVIDER_SOURCE[provider]]["resource_schemas"]


def resource_block(provider: str, rtype: str) -> dict | None:
    r = _load(provider).get(rtype)
    return r["block"] if r else None


def info(provider: str) -> dict:
    pin = pins()[provider]
    return {"provider": provider, "version": pin["version"], "schema_sha256": pin["schema_sha256"],
            "path": f"$BO_DATA/downloads/prefetch/{provider}/{pin['version']}/providers-schema.json"}
