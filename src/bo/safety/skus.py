"""Tabela de tipos e SKUs (deploy/safety/allowlist_skus.yaml): política curada (sku_policy.yaml) + suporte a tag
e a TTL por tipo lido do SERVICE-EVIDENCE ($BO_DATA/SERVICE-EVIDENCE/service_evidence.jsonl, C25).

Regras de junção (mecânicas, sem ajuste à mão):
  tag.supported   = algum fato tag_support "stated" com value.supported=true para o tipo; sem fato = false
                    (no_evidence). Tipo sem tag NUNCA é filtrado por tag: recebe nome sintético rastreável
                    (common.synthetic_name) e entra no manifesto; trace "tag" da política vira "name" (ou fica "ref"
                    para vínculo sem nome próprio), com o motivo gravado.
  ttl.supported   = algum fato ttl_support "stated" (atributo de expiração do tipo: retenção de mensagem, TTL de
                    item, retenção de backup...). Isso NÃO é destruição nativa do recurso: native_resource_destruction
                    é sempre false, e o prazo do runner (ttl_hours) é cumprido pelo supervisor e pelo teardown.
Os ids de evidência (evidence_id) vão junto, para auditoria.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

from .common import PROVIDERS, SafetyError, bo_data, deploy_dir, sha256_file

POLICY = Path(__file__).with_name("sku_policy.yaml")
SE_PATH = "$BO_DATA/SERVICE-EVIDENCE/service_evidence.jsonl"
SCHEMA = "bo.safety.allowlist_skus/1"
REMOVAL_DEFAULT = {"mode": "sync", "pending_hours": 0, "purge_days": 0, "residual_state": "absent",
                   "max_residual_usd": 0.0}
COST_KEYS = ("hourly", "storage_gb_month", "egress_gb", "per_million_requests", "one_time")
RULE_KEYS = {"in", "max", "eq", "absent", "sku", "why"}
REMOVAL_MODES = {"sync", "async", "scheduled", "soft_delete", "retained"}


def se_path() -> Path:
    return bo_data() / "SERVICE-EVIDENCE" / "service_evidence.jsonl"


def _yaml():
    import yaml  # PyYAML: no Mac (requirements.lock); a VM do supervisor lê o JSON do pacote (bundle.sh)
    return yaml


def load_policy() -> dict:
    return _yaml().safe_load(POLICY.read_text(encoding="utf-8"))


def evidence_index(types: set[tuple[str, str]], path: Path | None = None) -> dict:
    """{(provider, tipo): {"tag": [fatos], "ttl": [fatos]}} só para os tipos da política."""
    idx: dict = {}
    with open(path or se_path(), encoding="utf-8") as f:
        for ln in f:
            if '"tag_support"' not in ln and '"ttl_support"' not in ln:
                continue
            r = json.loads(ln)
            key = (r["provider"], r["terraform_resource_type"])
            if key not in types or r["fact_kind"] not in ("tag_support", "ttl_support"):
                continue
            idx.setdefault(key, {"tag": [], "ttl": []})[r["fact_kind"][:3]].append(r)
    return idx


def _tag_block(facts: list[dict]) -> dict:
    stated = [r for r in facts if r.get("status") == "stated"]
    yes = [r for r in stated if (r.get("value") or {}).get("supported") is True]
    if yes:
        attrs = sorted({r["value"].get("attribute") for r in yes if r["value"].get("attribute")})
        return {"supported": True, "status": "stated", "attributes": attrs,
                "evidence_ids": sorted(r["evidence_id"] for r in yes), "level": sorted({r["level"] for r in yes})}
    if stated:
        return {"supported": False, "status": "stated", "attributes": [],
                "evidence_ids": sorted(r["evidence_id"] for r in stated), "level": sorted({r["level"] for r in stated})}
    return {"supported": False, "status": "no_evidence", "attributes": [], "evidence_ids": [], "level": []}


def _ttl_block(facts: list[dict]) -> dict:
    stated = [r for r in facts if r.get("status") == "stated"]
    base = {"native_resource_destruction": False,
            "note": "atributo de expiração do tipo (dado, item, mensagem, backup); não destrói o recurso. "
                    "O prazo do runner é cumprido pelo supervisor e pelo teardown."}
    if stated:
        return {"supported": True, "status": "stated",
                "attributes": sorted({(r.get("value") or {}).get("attribute") for r in stated} - {None}),
                "evidence_ids": sorted(r["evidence_id"] for r in stated), **base}
    unk = [r for r in facts if r.get("status") == "unknown"]
    return {"supported": False, "status": "unknown" if unk else "no_evidence", "attributes": [],
            "evidence_ids": sorted(r["evidence_id"] for r in unk), **base}


def validate_policy(pol: dict) -> list[str]:
    errs = []
    if pol.get("schema") != "bo.safety.sku_policy/1":
        errs.append("schema da política")
    b = pol.get("budget", {})
    if sum(b.get("providers", {}).values()) < 0 or b.get("total_cap", 0) <= 0:
        errs.append("orçamento")
    for p in PROVIDERS:
        pv = pol["providers"].get(p)
        if not pv:
            errs.append(f"{p}: provedor ausente")
            continue
        if not pv.get("regions_allowed"):
            errs.append(f"{p}: sem regiões permitidas")
        cc = [re.compile(x) for x in pv.get("class_c", [])]
        for t, e in pv["types"].items():
            if not t.startswith({"aws": "aws_", "google": "google_", "azurerm": "azurerm_", "oci": "oci_"}[p]):
                errs.append(f"{t}: prefixo de provedor")
            if any(x.search(t) for x in cc):
                errs.append(f"{t}: tipo da Classe C na lista de permitidos")
            if set(e.get("cost", {})) - set(COST_KEYS) or not e.get("cost"):
                errs.append(f"{t}: custo sem as chaves conhecidas")
            for a, r in (e.get("rules") or {}).items():
                if set(r) - RULE_KEYS or not (set(r) & {"in", "max", "eq", "absent"}):
                    errs.append(f"{t}.{a}: regra inválida")
            rm = e.get("removal", {})
            if rm and rm.get("mode") not in REMOVAL_MODES:
                errs.append(f"{t}: modo de remoção")
            if e.get("trace") not in ("tag", "name", "ref"):
                errs.append(f"{t}: trace")
            if e.get("trace") == "ref" and any(float(v) for v in e.get("cost", {}).values()):
                errs.append(f"{t}: vínculo rastreado só por referência tem de ter custo zero (some com o pai)")
            if not isinstance(e.get("delete_order"), int):
                errs.append(f"{t}: delete_order")
    return errs


def build_table(se: Path | None = None) -> dict:
    pol = load_policy()
    errs = validate_policy(pol)
    if errs:
        raise SafetyError("política de SKU inválida: " + "; ".join(errs), "SKU")
    keys = {(p, t) for p in PROVIDERS for t in pol["providers"][p]["types"]}
    idx = evidence_index(keys, se)
    out = {"schema": SCHEMA, "generated_from": {"policy": "src/bo/safety/sku_policy.yaml",
                                                "policy_sha256": sha256_file(POLICY),
                                                "service_evidence": SE_PATH,
                                                "service_evidence_sha256": sha256_file(se or se_path())},
           "budget": pol["budget"], "providers": {}}
    for p in PROVIDERS:
        pv = pol["providers"][p]
        types = {}
        for t in sorted(pv["types"]):
            e = dict(pv["types"][t])
            facts = idx.get((p, t), {"tag": [], "ttl": []})
            tag = _tag_block(facts["tag"])
            ttl = _ttl_block(facts["ttl"])
            trace = e.get("trace")
            reason = "política"
            if trace == "tag" and not tag["supported"]:
                trace, reason = "name", f"tag {tag['status']} no SERVICE-EVIDENCE: nome sintético + manifesto"
            ent = {
                "cost": {k: float(e["cost"].get(k, 0.0)) for k in COST_KEYS},
                "rules": e.get("rules") or {},
                "removal": {**REMOVAL_DEFAULT, **(e.get("removal") or {})},
                "max_window_hours": int(e.get("max_window_hours", pol["budget"]["max_window_hours"])),
                "trace": trace, "trace_reason": reason,
                "delete_order": e["delete_order"],
                "tag": tag, "ttl": ttl,
            }
            types[t] = ent
        out["providers"][p] = {"regions_allowed": pv["regions_allowed"], "tag_attribute": pv["tag_attribute"],
                               "class_c": pv.get("class_c", []), "types": types}
    return out


HEADER = ("# GERADO por python -I -m bo.safety.build (não editar à mão): política curada src/bo/safety/sku_policy.yaml\n"
          "# + suporte a tag e a TTL por tipo do SERVICE-EVIDENCE (C25). Lido pelo plan_guard, pelo manifesto de\n"
          "# intenção (tag_supported, ttl_supported), pela varredura e pelo DEPSAMPLE (tipo fora daqui não é sorteado).\n")


def render(table: dict) -> str:
    return HEADER + _yaml().safe_dump(table, sort_keys=True, allow_unicode=True, width=110, default_flow_style=False)


def table_path() -> Path:
    import os
    if os.environ.get("BO_SAFETY_TABLE"):
        return Path(os.environ["BO_SAFETY_TABLE"])
    p = deploy_dir() / "allowlist_skus.yaml"
    return p if p.exists() or not (deploy_dir() / "allowlist_skus.json").exists() else deploy_dir() / "allowlist_skus.json"


@lru_cache(maxsize=4)
def _load(path: str, mtime: float) -> dict:
    txt = Path(path).read_text(encoding="utf-8")
    d = json.loads(txt) if path.endswith(".json") else _yaml().safe_load(txt)
    if d.get("schema") != SCHEMA:
        raise SafetyError("allowlist_skus.yaml sem schema bo.safety.allowlist_skus/1", "SKU")
    return d


def load_table(path: Path | None = None) -> dict:
    p = Path(path or table_path())
    return _load(str(p), p.stat().st_mtime)


def entry(table: dict, provider: str, rtype: str) -> dict | None:
    return table["providers"].get(provider, {}).get("types", {}).get(rtype)


def is_class_c(table: dict, provider: str, rtype: str) -> bool:
    return any(re.search(x, rtype) for x in table["providers"][provider].get("class_c", []))


def intent_fields(table: dict, provider: str, rtype: str) -> dict:
    """Campos do C16 que vêm da tabela (tag_supported, ttl_supported, prazo e custo residual)."""
    e = entry(table, provider, rtype)
    if e is None:
        raise SafetyError(f"{provider}:{rtype} fora da allowlist de tipos", "SKU")
    return {"tag_supported": bool(e["tag"]["supported"]) and e["trace"] == "tag",
            "ttl_supported": bool(e["ttl"]["supported"]),
            "purge_days": e["removal"]["purge_days"], "pending_hours": e["removal"]["pending_hours"],
            "max_residual_usd": float(e["removal"]["max_residual_usd"]), "trace": e["trace"]}
