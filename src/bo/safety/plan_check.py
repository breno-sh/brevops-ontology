"""Checador de plano (plan_guard): roda sobre `terraform show -json <plano>` em memória, antes do apply.

Recusa (cada achado tem código; um achado basta para recusar o lote):
  PG-TYPE        tipo fora da allowlist do provedor
  PG-CLASSC      tipo da Classe C do §10.1 sem OK do Breno para este lote (approved_class_c)
  PG-SKU         atributo de SKU fora da lista/limite (SKU caro) ou desconhecido no plano
  PG-RULE        regra de resíduo/custo do tipo (force_destroy, snapshot final, proteção contra remoção...)
  PG-TAG         tipo com tag sem a tag da execução (bo-run = run_tag) ou com valor diferente
  PG-NAME        tipo sem tag sem nome sintético rastreável da execução (bo-<lote>-NNNN) ou nome desconhecido
  PG-INTENT      recurso a criar sem intenção gravada antes (intents = vínculos endereço -> intenção do manifesto)
  PG-TTL         TTL do runner ausente, acima da janela do tipo, ou janela longa sem supervisor vivo (D16)
  PG-COST        custo estimado (horas + armazenamento + tráfego + requisições + resíduo) acima do teto do lote,
                 do provedor ou do total (D3); preço vivo acima do teto da tabela (PG-PRICE)
  PG-DELETE      plano de apply que apaga ou substitui recurso (só o teardown apaga, e só o que é da execução)
  PG-PROVIDER    bloco provider com credencial, perfil, assume_role, conta/projeto/subscription literal, ou sem
                 allowed_account_ids (aws), ou sem purge do Key Vault no destroy (azurerm com cofre)
  PG-REGION      região fora das permitidas
  PG-BACKEND     backend/cloud na configuração (o state só vive no canal efêmero)
  PG-PROVISIONER provisioner local-exec/remote-exec/file
O relatório não leva valor de atributo, só endereço, tipo, código e o nome da regra.
"""

from __future__ import annotations

import re
from datetime import timedelta
from pathlib import Path

from . import skus
from .common import PROVIDERS, SafetyError, parse_iso, now_dt, slug, tag_value

PROVIDER_PREFIX = {"aws": "aws_", "google": "google_", "azurerm": "azurerm_", "oci": "oci_"}
CRED_KEYS = {
    "aws": {"access_key", "secret_key", "token", "profile", "shared_credentials_files", "shared_config_files",
            "assume_role", "assume_role_with_web_identity", "sts_region", "custom_ca_bundle"},
    "google": {"credentials", "access_token", "impersonate_service_account", "impersonate_service_account_delegates",
               "project", "billing_project", "user_project_override"},
    "azurerm": {"client_id", "client_secret", "client_certificate", "client_certificate_path",
                "client_certificate_password", "use_msi", "use_oidc", "oidc_token", "tenant_id",
                "subscription_id", "auxiliary_tenant_ids"},
    "oci": {"private_key", "private_key_path", "private_key_password", "fingerprint", "user_ocid", "tenancy_ocid",
            "auth", "config_file_profile"},
}
NAME_ATTR = {"aws_kms_alias": "name"}


class PlanRefused(SafetyError):
    def __init__(self, msg, findings=None):
        super().__init__(msg, "PLAN")
        self.findings = findings or []


def _get(obj, dotted: str):
    cur = obj
    for part in dotted.split("."):
        if isinstance(cur, list):
            if not part.isdigit() or int(part) >= len(cur):
                return None, False
            cur = cur[int(part)]
        elif isinstance(cur, dict):
            if part not in cur:
                return None, False
            cur = cur[part]
        else:
            return None, False
    return cur, True


def _unknown(after_unknown, dotted: str) -> bool:
    cur = after_unknown
    for part in dotted.split("."):
        if cur is True:
            return True
        if isinstance(cur, list) and part.isdigit() and int(part) < len(cur):
            cur = cur[int(part)]
        elif isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return False
    return cur is True


def check_rule(attr: str, rule: dict, after: dict, after_unknown) -> str | None:
    """None se a regra passa; senão o motivo (sem o valor)."""
    if _unknown(after_unknown, attr):
        return "valor desconhecido no plano" if (rule.get("sku") or "eq" in rule or "in" in rule) else None
    val, present = _get(after, attr)
    if val is None:
        present = False
    if "absent" in rule:
        bad = rule["absent"]
        if present and (not bad or val in bad):
            return "valor proibido" if bad else "atributo proibido"
        if not present:
            return None
    if "eq" in rule:
        if not present or val != rule["eq"]:
            return "diferente do exigido"
    if "in" in rule:
        if not present or val not in rule["in"]:
            return "fora da lista permitida"
    if "max" in rule and present:
        try:
            if float(val) > float(rule["max"]):
                return "acima do limite"
        except (TypeError, ValueError):
            return "não numérico"
    return None


def _provider_of(rc: dict) -> str | None:
    pn = rc.get("provider_name", "")
    for p in PROVIDERS:
        if pn.endswith("/" + p) or pn == p:
            return p
    t = rc.get("type", "")
    for p, pre in PROVIDER_PREFIX.items():
        if t.startswith(pre):
            return p
    return None


def _norm_region(r: str) -> str:
    return re.sub(r"[\s_]+", "", r.strip().lower())


def _cost(entry: dict, hours: float, usage: dict, default_usage: dict) -> dict:
    c = entry["cost"]
    u = {**default_usage, **(usage or {})}
    parts = {
        "compute": c["hourly"] * hours,
        "storage": c["storage_gb_month"] * float(u.get("storage_gb", 0)) * hours / 730.0,
        "traffic": c["egress_gb"] * float(u.get("egress_gb", 0)),
        "requests": c["per_million_requests"] * float(u.get("requests_millions", 0)),
        "one_time": c["one_time"],
        "residual": float(entry["removal"]["max_residual_usd"]),
    }
    return {k: round(v, 6) for k, v in parts.items()}


def _provider_findings(plan: dict, provider: str, ctx: dict, table: dict, types_present: set) -> list[dict]:
    out = []
    pc = (plan.get("configuration") or {}).get("provider_config") or {}
    blocks = [v for v in pc.values() if v.get("name") == provider]
    if not blocks:
        out.append({"code": "PG-PROVIDER", "address": f"provider.{provider}", "detail": "bloco provider ausente"})
        return out
    allowed_regions = set(table["providers"][provider]["regions_allowed"])
    for b in blocks:
        ex = b.get("expressions") or {}
        addr = f"provider.{b.get('full_name', provider)}" + (f".{b['alias']}" if b.get("alias") else "")
        for k in sorted(set(ex) & CRED_KEYS[provider]):
            if provider == "google" and k == "project" and "constant_value" not in (ex[k] or {}):
                continue  # projeto por variável vem do runner (GOOGLE_PROJECT conferido)
            out.append({"code": "PG-PROVIDER", "address": addr, "detail": f"{k} no bloco provider"})
        reg_key = {"aws": "region", "google": "region", "azurerm": None, "oci": "region"}[provider]
        if reg_key and reg_key in ex and "constant_value" in ex[reg_key]:
            if ex[reg_key]["constant_value"] not in allowed_regions:
                out.append({"code": "PG-REGION", "address": addr, "detail": "região literal fora das permitidas"})
        if provider == "aws" and "allowed_account_ids" not in ex:
            out.append({"code": "PG-PROVIDER", "address": addr, "detail": "sem allowed_account_ids"})
        if provider == "azurerm" and "azurerm_key_vault" in types_present:
            feats = ex.get("features") or [{}]
            kv = (feats[0] or {}).get("key_vault") or [{}]
            v = ((kv[0] or {}).get("purge_soft_delete_on_destroy") or {}).get("constant_value")
            if v is not True:
                out.append({"code": "PG-PROVIDER", "address": addr,
                            "detail": "features.key_vault.purge_soft_delete_on_destroy != true"})
    if ctx.get("region") and ctx["region"] not in allowed_regions:
        out.append({"code": "PG-REGION", "address": f"provider.{provider}", "detail": "região do contexto fora das permitidas"})
    return out


def scan_tf_dir(tf_dir: Path) -> list[dict]:
    """Backend/cloud e provisioners na configuração (texto dos .tf; o plano JSON não traz o backend)."""
    out = []
    for f in sorted(Path(tf_dir).rglob("*.tf")):
        if ".terraform" in f.parts:
            continue
        txt = re.sub(r"(?m)#.*$|//.*$", "", f.read_text(encoding="utf-8"))
        rel = f.name
        if re.search(r"\bbackend\s+\"", txt) or re.search(r"(?m)^\s*cloud\s*\{", txt):
            out.append({"code": "PG-BACKEND", "address": rel, "detail": "backend/cloud declarado"})
        if re.search(r"\bprovisioner\s+\"", txt):
            out.append({"code": "PG-PROVISIONER", "address": rel, "detail": "provisioner declarado"})
    return out


def check_plan(plan: dict, ctx: dict, table: dict | None = None, intents: list[dict] | None = None,
               tf_dir: Path | None = None, live_prices: dict | None = None, now=None) -> dict:
    """Relatório {ok, findings, cost}. ctx: module, provider, batch_id, run_tag (padrão: tag_value(batch_id)),
    ttl_hours, window_hours, region, usage{endereço: {storage_gb, egress_gb, requests_millions}},
    approved_class_c[], supervisor{last_ack_at, run_tag}, spent_usd{provider, total}, batch_cap_usd."""
    table = table or skus.load_table()
    provider = ctx.get("provider")
    if provider not in PROVIDERS:
        raise PlanRefused(f"provedor do contexto inválido: {provider}")
    budget = table["budget"]
    now = now or now_dt()
    findings: list[dict] = []
    run_tag = ctx.get("run_tag") or tag_value(ctx.get("batch_id", ""))
    batch_slug = slug(ctx.get("batch_id", "")).removeprefix("b-")
    name_rx = re.compile(rf"(?<![a-z0-9])bo-{re.escape(batch_slug[:30])}-\d{{4}}(?![0-9])")
    bindings = {b["address"]: b for b in (intents or []) if b.get("address")}

    # ---------------------------------------------------------------- TTL e janela (antes de olhar recurso)
    ttl = ctx.get("ttl_hours")
    window = float(ctx.get("window_hours") or 0)
    if not isinstance(ttl, (int, float)) or ttl <= 0:
        findings.append({"code": "PG-TTL", "address": "contexto", "detail": "TTL do runner ausente (ttl_hours)"})
        ttl = None
    elif ttl > budget["max_window_hours"]:
        findings.append({"code": "PG-TTL", "address": "contexto", "detail": "TTL acima da janela máxima (D12)"})
    eff_window = max(window, float(ttl or 0))
    if eff_window > budget["short_window_hours"]:
        sup = ctx.get("supervisor") or {}
        ok = False
        if sup.get("last_ack_at") and sup.get("run_tag") == run_tag:
            age = (now - parse_iso(sup["last_ack_at"])).total_seconds()
            ok = -5 <= age <= budget["heartbeat_grace_seconds"]
        if not ok:
            findings.append({"code": "PG-TTL", "address": "contexto",
                             "detail": "janela longa sem supervisor com heartbeat vivo (D16)"})

    # ---------------------------------------------------------------- recursos
    cost_items = []
    types_present = set()
    for rc in plan.get("resource_changes", []) or []:
        if rc.get("mode") == "data":
            continue
        addr, rtype = rc.get("address", "?"), rc.get("type", "")
        actions = (rc.get("change") or {}).get("actions") or []
        p = _provider_of(rc)
        if p != provider:
            findings.append({"code": "PG-TYPE", "address": addr, "detail": "recurso de outro provedor no lote"})
            continue
        types_present.add(rtype)
        if "delete" in actions:
            findings.append({"code": "PG-DELETE", "address": addr,
                             "detail": "apply com remoção/substituição (só o teardown apaga)"})
        if "create" not in actions and "update" not in actions:
            continue
        if skus.is_class_c(table, provider, rtype) and rtype not in (ctx.get("approved_class_c") or []):
            findings.append({"code": "PG-CLASSC", "address": addr, "detail": "tipo da Classe C sem OK"})
            continue
        ent = skus.entry(table, provider, rtype)
        if ent is None:
            findings.append({"code": "PG-TYPE", "address": addr, "detail": "tipo fora da allowlist"})
            continue
        ch = rc.get("change") or {}
        after, unk = ch.get("after") or {}, ch.get("after_unknown") or {}
        for attr, rule in sorted((ent.get("rules") or {}).items()):
            why = check_rule(attr, rule, after, unk)
            if why:
                findings.append({"code": "PG-SKU" if rule.get("sku") else "PG-RULE", "address": addr,
                                 "detail": f"{attr}: {why}"})
        for rk in ("region", "location"):
            rv = after.get(rk)
            if isinstance(rv, str) and rv and _norm_region(rv) not in {
                    _norm_region(x) for x in table["providers"][provider]["regions_allowed"]}:
                findings.append({"code": "PG-REGION", "address": addr, "detail": f"{rk} do recurso fora das permitidas"})
        if ttl and ttl > ent["max_window_hours"]:
            findings.append({"code": "PG-TTL", "address": addr, "detail": "TTL acima da janela do tipo"})
        # rastreio: tag da execução, ou nome sintético + manifesto, ou referência (vínculo)
        tattr = table["providers"][provider]["tag_attribute"]
        if ent["trace"] == "tag":
            tags = after.get(tattr + "_all") or after.get(tattr) or {}
            if _unknown(unk, tattr + "_all") and not after.get(tattr):
                tags = {}
            if not isinstance(tags, dict) or tags.get("bo-run") != run_tag:
                findings.append({"code": "PG-TAG", "address": addr, "detail": "sem a tag bo-run da execução"})
        elif ent["trace"] == "name":
            nattr = NAME_ATTR.get(rtype, "name")
            nm = after.get(nattr)
            if _unknown(unk, nattr) or not isinstance(nm, str):
                findings.append({"code": "PG-NAME", "address": addr, "detail": "nome desconhecido no plano"})
            elif not name_rx.search(nm):
                findings.append({"code": "PG-NAME", "address": addr,
                                 "detail": "tipo sem tag sem nome sintético da execução"})
        if intents is not None:
            b = bindings.get(addr)
            if b is None or b.get("resource_type") != rtype:
                findings.append({"code": "PG-INTENT", "address": addr, "detail": "sem intenção gravada antes"})
        # custo
        hours = float(ttl or 0)
        c = _cost(ent, hours, (ctx.get("usage") or {}).get(addr), budget["default_usage"])
        cost_items.append({"address": addr, "type": rtype, **c, "total": round(sum(c.values()), 6)})
        if live_prices:
            lp = (live_prices.get(provider) or {}).get(rtype) or {}
            for k, v in lp.items():
                if k in ent["cost"] and float(v) > float(ent["cost"][k]) + 1e-12:
                    findings.append({"code": "PG-PRICE", "address": addr,
                                     "detail": f"preço vivo de {k} acima do teto da tabela"})

    findings += _provider_findings(plan, provider, ctx, table, types_present)
    if tf_dir:
        findings += scan_tf_dir(Path(tf_dir))

    total = round(sum(i["total"] for i in cost_items), 6)
    spent = ctx.get("spent_usd") or {}
    caps = {"batch": ctx.get("batch_cap_usd"),
            "provider": budget["providers"][provider] - float(spent.get(provider, 0.0)),
            "total": budget["total_cap"] - float(spent.get("total", 0.0))}
    for k, cap in caps.items():
        if cap is not None and total > float(cap) + 1e-9:
            findings.append({"code": "PG-COST", "address": "lote", "detail": f"estimativa acima do teto ({k})"})
    cost = {"currency": "USD", "hours": float(ttl or 0), "items": cost_items, "total": total,
            "caps": {k: (round(v, 6) if v is not None else None) for k, v in caps.items()},
            "includes": ["compute", "storage", "traffic", "requests", "one_time", "residual"]}
    findings.sort(key=lambda f: (f["code"], f["address"], f["detail"]))
    return {"ok": not findings, "findings": findings, "cost": cost, "run_tag": run_tag,
            "checked_at": now.isoformat(timespec="seconds"), "provider": provider}


def enforce(plan: dict, ctx: dict, **kw) -> dict:
    rep = check_plan(plan, ctx, **kw)
    if not rep["ok"]:
        codes = sorted({f["code"] for f in rep["findings"]})
        raise PlanRefused(f"plano recusado ({len(rep['findings'])} achado(s): {', '.join(codes)})", rep["findings"])
    return rep


def ttl_deadline(ctx: dict, start=None) -> str:
    start = start or now_dt()
    return (start + timedelta(hours=float(ctx["ttl_hours"]))).isoformat(timespec="seconds")
