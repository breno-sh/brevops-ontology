"""Confere a configuração de cada fixture contra o schema do provider FIXADO (saída gravada de
'terraform providers schema -json' em $BO_DATA/downloads/prefetch/<provider>/<versão>/providers-schema.json).

Tipo de recurso existe; todo atributo e bloco da fixture existe no schema; atributo obrigatório presente;
bloco 'single' é objeto e os demais são lista. Só leitura do arquivo gravado: nenhum binário roda aqui.

  python -I -m bo.pilot_sto_oracle.schema_check [DIR ...]   (padrão: $BO_REPO/pilot/sto/fixtures_calib)
"""
from __future__ import annotations

import json
import os
import sys
from functools import lru_cache
from pathlib import Path

META = {"depends_on", "count", "for_each", "lifecycle", "provider"}
PIN = {"aws": "6.71.0", "google": "8.9.0", "azurerm": "5.12.0", "oci": "9.11.0"}


def data_root() -> Path:
    return Path(os.environ.get("BO_DATA", "/Users/breno/doutorado/brevops-data"))


@lru_cache(maxsize=None)
def schema(provider: str) -> dict:
    p = data_root() / "downloads" / "prefetch" / provider / PIN[provider] / "providers-schema.json"
    doc = json.loads(p.read_text(encoding="utf-8"))
    return next(iter(doc["provider_schemas"].values()))["resource_schemas"]


def _check_block(body, block, where, errs):
    attrs = block.get("attributes", {})
    btypes = block.get("block_types", {})
    for k, v in body.items():
        if k in META:
            continue
        if k in attrs:
            a = attrs[k]
            if a.get("computed") and not a.get("optional") and not a.get("required"):
                errs.append(f"{where}.{k}: atributo só calculado")
            continue
        if k in btypes:
            bt = btypes[k]
            mode = bt["nesting_mode"]
            items = [v] if mode == "single" else v
            if mode == "single" and not isinstance(v, dict):
                errs.append(f"{where}.{k}: bloco single precisa ser objeto")
                continue
            if mode != "single" and not isinstance(v, list):
                errs.append(f"{where}.{k}: bloco {mode} precisa ser lista")
                continue
            if "max_items" in bt and len(items) > bt["max_items"]:
                errs.append(f"{where}.{k}: mais de {bt['max_items']} blocos")
            for i, it in enumerate(items):
                _check_block(it, bt["block"], f"{where}.{k}[{i}]", errs)
            continue
        errs.append(f"{where}.{k}: não existe no schema fixado")
    for k, a in attrs.items():
        if a.get("required") and k not in body:
            errs.append(f"{where}.{k}: obrigatório ausente")
    for k, bt in btypes.items():
        if bt.get("min_items", 0) > 0 and k not in body:
            errs.append(f"{where}.{k}: bloco obrigatório ausente")


def check_fixture(fx: dict) -> list[str]:
    errs = []
    rs = schema(fx["provider"])
    for rtype, insts in (fx.get("terraform", {}).get("resource") or {}).items():
        if rtype not in rs:
            errs.append(f"{rtype}: tipo inexistente no provider {fx['provider']} {PIN[fx['provider']]}")
            continue
        for name, body in insts.items():
            _check_block(body, rs[rtype]["block"], f"{fx['fixture_id']}:{rtype}.{name}", errs)
    for v in (fx.get("terraform", {}).get("variable") or {}):
        if not v.replace("_", "").isalnum():
            errs.append(f"variável com nome inválido: {v}")
    return errs


def iter_fixture_files(root: Path):
    for f in sorted(root.rglob("*.json")):
        doc = json.loads(f.read_text(encoding="utf-8"))
        if doc.get("schema") == "bo.pilot.sto.fixture/1":
            yield f, [doc]
        elif doc.get("schema") == "bo.pilot.sto.direction_entry/1":
            yield f, [doc["source"], doc["target"]]


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    repo = Path(os.environ.get("BO_REPO", "/Users/breno/doutorado/brevops-ontology"))
    roots = [Path(a) for a in argv] or [repo / "pilot" / "sto" / "fixtures_calib"]
    n, bad = 0, []
    for root in roots:
        for f, fxs in iter_fixture_files(root):
            for fx in fxs:
                n += 1
                bad += check_fixture(fx)
    for e in bad[:50]:
        print("  ERRO", e)
    print(f"schema_check: {n} configuração(ões) conferida(s) contra o schema fixado; {len(bad)} erro(s)")
    return 1 if bad or n == 0 else 0


if __name__ == "__main__":
    sys.exit(main())
