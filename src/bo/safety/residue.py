"""Resíduo esperado (deploy/safety/EXPECTED_RESIDUE.json) e classificação de cada item da varredura.

Classes de item:
  residuo_esperado    da execução, em estado de remoção previsto para o tipo (agendado, soft delete, retido), dentro
                      do prazo de expurgo e com custo residual máximo declarado
  residuo_inesperado  da execução, vivo ou em estado não previsto: reprova
  plataforma          criado pelo próprio provedor ao lado do que criamos (ex.: NetworkWatcherRG), custo zero
  baseline            alheio que já existia antes do lote: só relatado
  investigar          alheio que não estava no baseline: reprova o --expect-empty e é investigado, NUNCA apagado
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from .common import PROVIDERS, deploy_dir

SCHEMA = "bo.safety.expected_residue/1"
STATE_OF_MODE = {"scheduled": ["pending_deletion"], "soft_delete": ["soft_deleted"], "retained": ["retained"],
                 "async": ["deleting"]}

PLATFORM = [
    {"provider": "aws", "kind": "default_vpc", "match": {"tag_or_name": "^default$|default-vpc", "is_default": True},
     "why": "VPC padrão de cada região (e suas sub-redes, IGW, tabela de rotas, SG e NACL): existe antes do lote",
     "max_residual_usd": 0.0},
    {"provider": "google", "kind": "default_network", "match": {"name": "^default$|^default-allow-"},
     "why": "rede default e regras default-allow-* de projeto novo", "max_residual_usd": 0.0},
    {"provider": "google", "kind": "service_agent", "match": {"type": "^google_service_account$",
                                                              "name": "compute@developer|gserviceaccount"},
     "why": "contas de serviço padrão e agentes de serviço criados ao ligar uma API", "max_residual_usd": 0.0},
    {"provider": "azurerm", "kind": "network_watcher", "match": {"name": "^NetworkWatcherRG$|^NetworkWatcher_"},
     "why": "grupo e Network Watcher criados pela Azure ao criar a primeira VNet da região", "max_residual_usd": 0.0},
    {"provider": "oci", "kind": "deleted_compartment", "match": {"type": "^oci_identity_compartment$",
                                                                 "lifecycle": "^DELETED$"},
     "why": "compartment apagado continua listado em DELETED (sem custo)", "max_residual_usd": 0.0},
]


def build(table: dict) -> dict:
    owned = []
    for p in PROVIDERS:
        for t, e in sorted(table["providers"][p]["types"].items()):
            rm = e["removal"]
            if rm["mode"] in ("scheduled", "soft_delete", "retained"):
                owned.append({"provider": p, "resource_type": t, "states": STATE_OF_MODE[rm["mode"]],
                              "removal_mode": rm["mode"], "purge_days": rm["purge_days"],
                              "max_residual_usd": rm["max_residual_usd"],
                              "why": {"scheduled": "exclusão agendada pelo provedor; some no fim do prazo",
                                      "soft_delete": "soft delete; o teardown expurga (purge) e confere vazio",
                                      "retained": "o provedor não apaga o tipo; fica com custo zero"}[rm["mode"]]})
    return {"schema": SCHEMA, "owned": owned, "platform": PLATFORM,
            "rule": "item fora desta lista reprova o gate e é investigado, não apagado às cegas (§10.3)"}


def path() -> Path:
    return deploy_dir() / "EXPECTED_RESIDUE.json"


def load(p: Path | None = None) -> dict:
    d = json.loads(Path(p or path()).read_text(encoding="utf-8"))
    if d.get("schema") != SCHEMA:
        raise ValueError("EXPECTED_RESIDUE.json sem schema")
    return d


def owned_expected(res: dict, provider: str, item: dict) -> bool:
    for r in res["owned"]:
        if r["provider"] == provider and r["resource_type"] == item.get("type") and item.get("state") in r["states"]:
            return True
    return False


def platform_match(res: dict, provider: str, item: dict) -> str | None:
    for r in res["platform"]:
        if r["provider"] != provider:
            continue
        m = r["match"]
        ok = True
        for k, rx in m.items():
            if k == "is_default":
                ok &= bool(item.get("is_default")) == rx
            elif k == "tag_or_name":
                ok &= bool(re.search(rx, str(item.get("name") or ""))) or bool(item.get("is_default"))
            else:
                ok &= bool(re.search(rx, str(item.get(k) or "")))
        if ok:
            return r["kind"]
    return None


def classify(res: dict, provider: str, item: dict, owner_reason: str | None, baseline_refs: set) -> str:
    if owner_reason:
        return "residuo_esperado" if owned_expected(res, provider, item) else "residuo_inesperado"
    if platform_match(res, provider, item):
        return "plataforma"
    if item.get("ref") in baseline_refs:
        return "baseline"
    return "investigar"
