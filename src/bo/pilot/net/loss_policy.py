"""Política de perda ÚNICA dos três controles: código de perda do plano (C26 losses.code) -> perda do catálogo da
direção (pilot/net/oracle/directions.json, do PILOT-NET-ORACLE) e o recorte de fluxos que ela declara.

O recorte é por forma do fluxo, nunca pelo resultado do oráculo: 'all' = todo fluxo da fixture; 'return' = só
tráfego de retorno (estado de conexão). O juiz do oráculo ainda restringe o TIPO de divergência que cada perda
cobre (covers) e nunca aceita DENY -> ALLOW. Código sem perda no catálogo da direção fica listado como perda não
declarável (o juiz devolve em undeclarable_losses) — é achado, não é escondido.
"""

from __future__ import annotations

POLICY = {
    "UNKNOWN_INPUT": ("LOSS-NET-UNKNOWN-INPUT", "all"),
    "DEFAULT_NO_EVIDENCE": ("LOSS-NET-DEFAULT", "all"),
    "STATE_NOT_EXPRESSIBLE": ("LOSS-NET-STATE", "return"),
    "DENY_COMPILED": ("LOSS-NET-EFFECT-DENY", "all"),
    "SRC_PORT_DROPPED": ("LOSS-NET-SRCPORT", "all"),
    "SELECTOR_AS_ATTACHMENT": ("LOSS-NET-SELECTOR", "all"),
}


def declared(plan_losses: list, flows: list) -> list:
    """[{code, field, detail}] do caso -> [{loss_id, flows, from_codes}] para o juiz."""
    out = {}
    for l in plan_losses:
        if l["code"] not in POLICY:
            raise ValueError(f"código de perda fora da política: {l['code']}")
        lid, scope = POLICY[l["code"]]
        fl = [f["flow_id"] for f in flows if scope == "all" or (scope == "return" and f.get("state") == "return")]
        d = out.setdefault(lid, {"loss_id": lid, "flows": set(), "from_codes": set()})
        d["flows"].update(fl)
        d["from_codes"].add(l["code"])
    return [{"loss_id": k, "flows": sorted(v["flows"]), "from_codes": sorted(v["from_codes"])}
            for k, v in sorted(out.items())]


def document() -> dict:
    return {code: {"loss_id": lid, "flows": scope} for code, (lid, scope) in sorted(POLICY.items())}
