"""Construtores de plano, contexto e identidade sintéticos para os testes do SAFETY."""

from __future__ import annotations

import json

from bo.safety import common, identity


def fresh_check(provider="aws", canon=None):
    canon = canon or {"aws": "aws|account=" + "1" * 6 + "2" * 6}.get(provider, f"{provider}|sintetico")
    return {"identity_sha256": identity.identity_hash(canon), "checked_at": common.now(), "matches_allowlist": True}


def rc(address, rtype, after, actions=("create",), provider="aws", unknown=None, sensitive=None):
    full = {"aws": "registry.terraform.io/hashicorp/aws", "google": "registry.terraform.io/hashicorp/google",
            "azurerm": "registry.terraform.io/hashicorp/azurerm", "oci": "registry.terraform.io/oracle/oci"}[provider]
    return {"address": address, "mode": "managed", "type": rtype, "name": address.split(".")[-1],
            "provider_name": full,
            "change": {"actions": list(actions), "before": None, "after": after, "after_unknown": unknown or {},
                       "after_sensitive": sensitive or {}}}


def plan(*changes, provider="aws", provider_expr=None):
    expr = provider_expr if provider_expr is not None else {
        "aws": {"region": {"references": ["var.bo_region"]},
                "allowed_account_ids": {"references": ["var.bo_allowed_account_ids"]}},
        "google": {"region": {"constant_value": "us-central1"}},
        "azurerm": {"features": [{"key_vault": [{"purge_soft_delete_on_destroy": {"constant_value": True}}]}]},
        "oci": {"region": {"constant_value": "sa-saopaulo-1"}}}[provider]
    return {"format_version": "1.2", "terraform_version": "1.9.8", "resource_changes": list(changes),
            "configuration": {"provider_config": {provider: {"name": provider, "full_name": provider,
                                                             "expressions": expr}}}}


def ctx(provider="aws", **kw):
    region = {"aws": "us-east-1", "google": "us-central1", "azurerm": "eastus", "oci": "sa-saopaulo-1"}[provider]
    base = {"module": "SMOKE-AWS", "provider": provider, "batch_id": "B-AWS-01", "ttl_hours": 2, "window_hours": 1,
            "region": region}
    base.update(kw)
    return base


def dumps(o):
    return json.dumps(o, sort_keys=True)
