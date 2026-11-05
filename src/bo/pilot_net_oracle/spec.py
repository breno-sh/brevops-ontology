"""Casos obrigatórios, catálogo de perdas e as 12 direções da fatia NET (escritos à mão, sem mapeador)."""
from __future__ import annotations

PROVIDERS = ("aws", "google", "azurerm", "oci")
DIRECTIONS = [f"{a}->{b}" for a in PROVIDERS for b in PROVIDERS if a != b]

# capacidades lidas do semantics_profile.json (leitura default)
CAPS = {
    "aws": {"deny": False, "priority": False, "state": "stateful", "no_match": "deny", "selector": "attachment", "src_ports": False},
    "google": {"deny": True, "priority": True, "state": "stateful", "no_match": "implied_deny_in_allow_out", "selector": "tags", "src_ports": False},
    "azurerm": {"deny": True, "priority": True, "state": "unevidenced", "no_match": "unevidenced", "selector": "attachment", "src_ports": True},
    "oci": {"deny": False, "priority": False, "state": "per_rule", "no_match": "deny", "selector": "attachment", "src_ports": True},
}

CASES = {
    "NET-C01": {"name": "embalagem: regra embutida x recurso separado", "commitments": ["CMT-FW-P01"], "requirements": ["REQ-NET-01", "REQ-ENT-01"], "layer": "decomposition"},
    "NET-C02": {"name": "estado de conexão do conjunto e tráfego de retorno", "commitments": ["CMT-FW-P02", "CMT-FW-U03"], "requirements": ["REQ-NET-01", "REQ-NET-02", "REQ-CFG-02"], "layer": "evaluation"},
    "NET-C03": {"name": "estado de conexão por regra (security list e NSG OCI)", "commitments": ["CMT-FW-P03", "CMT-FW-N02", "CMT-TAX-N03"], "requirements": ["REQ-NET-01"], "layer": "evaluation"},
    "NET-C04": {"name": "precedência numérica e efeito permitir/negar; ordem textual irrelevante", "commitments": ["CMT-FW-P04", "CMT-FW-P06"], "requirements": ["REQ-NET-01", "REQ-NET-02", "REQ-ID-01"], "layer": "evaluation"},
    "NET-C05": {"name": "desempate e prioridade repetida", "commitments": ["CMT-FW-U02"], "requirements": ["REQ-NET-01", "REQ-ABS-01"], "layer": "evaluation"},
    "NET-C06": {"name": "direção: regra de saída não autoriza entrada", "commitments": ["CMT-FW-N03"], "requirements": ["REQ-NET-01", "REQ-NET-02"], "layer": "evaluation"},
    "NET-C07": {"name": "leitura parcial do conjunto", "commitments": ["CMT-FW-U01"], "requirements": ["REQ-ABS-01", "REQ-NET-02"], "layer": "evaluation"},
    "NET-C08": {"name": "alvo por anexação ou seleção; vários conjuntos no mesmo alvo", "commitments": ["CMT-FW-P05"], "requirements": ["REQ-NET-01"], "layer": "domain"},
    "NET-C09": {"name": "fluxo que nenhuma regra casa (padrão do provedor)", "commitments": ["CMT-FW-N03", "CMT-FW-U01"], "requirements": ["REQ-ABS-01", "REQ-LOSS-01"], "layer": "evaluation"},
    "NET-C10": {"name": "tradução entre provedores: negação não vira permissão; perda declarada", "commitments": ["CMT-FW-N01"], "requirements": ["REQ-NET-01", "REQ-LOSS-01", "REQ-METH-02"], "layer": "translation"},
}

LOSS_CATALOG = {
    "LOSS-NET-EFFECT-DENY": {
        "code": "DECLARED_LOSS", "when": {"source": ["google", "azurerm"], "target": ["aws", "oci"]},
        "covers": ["ALLOW->DENY"],
        "text": "o destino só exprime permissão: regra de negação e precedência não viram regra; o alvo aceitável permite só o conjunto efetivo (negação compilada fora) ou bloqueia; nunca permite o que a origem nega"},
    "LOSS-NET-STATE": {
        "code": "MISSING_EVIDENCE", "when": {"source": list(PROVIDERS), "target": ["azurerm"]},
        "covers": ["ALLOW->UNKNOWN", "DENY->UNKNOWN"],
        "text": "o estado de conexão do NSG Azure não tem evidência no SERVICE-EVIDENCE: a decisão do tráfego de retorno no destino é UNKNOWN (SG AWS, firewall GCP e OCI: com estado, publicado desde o CC-14)"},
    "LOSS-NET-DEFAULT": {
        "code": "MISSING_EVIDENCE", "when": {"source": list(PROVIDERS), "target": ["azurerm"]},
        "covers": ["ALLOW->UNKNOWN", "DENY->UNKNOWN"],
        "text": "o padrão do NSG Azure para fluxo sem regra não tem evidência publicada (regras padrão ausentes); evitável com negação explícita de menor precedência. No GCP as regras implícitas são publicadas (entrada nega, saída permite): sem negação explícita de saída, a saída fica PERMITIDA, o que é transporte em caso negativo, não perda"},
    "LOSS-NET-SRCPORT": {
        "code": "DECLARED_LOSS", "when": {"source": ["azurerm", "oci"], "target": ["aws", "google"]},
        "covers": ["ALLOW->DENY"],
        "text": "o destino não filtra porta de origem: a regra que depende dela só pode ser omitida (bloqueio conservador), nunca alargada"},
    "LOSS-NET-SELECTOR": {
        "code": "DECLARED_LOSS", "when": {"source": ["google"], "target": ["aws", "azurerm", "oci"]},
        "covers": ["ALLOW->UNKNOWN", "DENY->UNKNOWN", "ALLOW->DENY"],
        "text": "seleção por rótulo vira anexação: sem a lista de instâncias, a aplicação no destino é desconhecida ou fica fechada"},
    "LOSS-NET-UNKNOWN-INPUT": {
        "code": "UNKNOWN_INPUT", "when": {"source": list(PROVIDERS), "target": list(PROVIDERS)},
        "covers": ["UNKNOWN->ALLOW", "UNKNOWN->DENY"],
        "text": "a decisão de origem é UNKNOWN (semântica sem evidência ou entrada simbólica): o destino escolhe e declara; nunca conta como transporte correto"},
}

TARGET_REQUIREMENTS = {
    "REQ-T-DECISIONS": "decisão igual à da origem em todo fluxo da fixture, salvo divergência coberta por perda declarada do catálogo da direção",
    "REQ-T-NO-DENY-TO-ALLOW": "nenhum fluxo negado na origem é permitido no destino (perda declarada não cobre)",
    "REQ-T-CATCHALL": "negação explícita de entrada e de saída na menor precedência: no Azure, para não depender do padrão sem evidência; no GCP, porque a regra implícita de saída PERMITE",
    "REQ-T-AZ-PRIORITY": "prioridades entre 100 e 4096, distintas entre si (também entre direções, para a validade não ficar UNKNOWN)",
    "REQ-T-GCP-TIE": "nenhuma permissão na mesma prioridade da negação que deveria perder para ela (empate: deny vence)",
    "REQ-T-EFFECTIVE-SET": "destino só-permissão: permitir só o conjunto efetivo da origem (permissões menos negações de precedência maior)",
    "REQ-T-ATTACH": "o conjunto do destino aplica-se aos mesmos alvos (anexação ou rótulo equivalente)",
}

NEGATIVE_INVARIANTS = [
    "DENY na origem nunca vira ALLOW no destino (CMT-FW-N01)",
    "regra de saída não autoriza entrada nova no destino (CMT-FW-N03)",
    "regra sem estado não ganha retorno automático no destino (CMT-FW-P03)",
    "egress do grupo de segurança AWS sem bloco egress não é permissão total (SE-aws-jcsq5zrpnuvxzaxv)",
]


def direction_entry(d: str) -> dict:
    a, b = d.split("->")
    losses = [lid for lid, l in LOSS_CATALOG.items() if a in l["when"]["source"] and b in l["when"]["target"]]
    req = ["REQ-T-DECISIONS", "REQ-T-NO-DENY-TO-ALLOW", "REQ-T-ATTACH"]
    if b in ("google", "azurerm"):
        req.append("REQ-T-CATCHALL")
    if b == "azurerm":
        req.append("REQ-T-AZ-PRIORITY")
    if b == "google":
        req.append("REQ-T-GCP-TIE")
    if CAPS[a]["deny"] and not CAPS[b]["deny"]:
        req.append("REQ-T-EFFECTIVE-SET")
    unknowns = []
    if CAPS[b]["state"] == "unevidenced":
        unknowns.append("retorno de conexão no destino: UNKNOWN (estado sem evidência)")
    if CAPS[a]["state"] == "unevidenced":
        unknowns.append("retorno de conexão na origem (NSG Azure): UNKNOWN; destino com estado definido não prova transporte (UNDETERMINED sem LOSS-NET-UNKNOWN-INPUT)")
    if CAPS[b]["no_match"] == "unevidenced":
        unknowns.append("fluxo sem regra no destino: UNKNOWN sem negação explícita")
    if CAPS[a]["no_match"] == "unevidenced":
        unknowns.append("fluxo sem regra na origem: UNKNOWN")
    if b == "google" and a != "google":
        unknowns.append("saída sem regra no GCP: a regra implícita permite; sem negação explícita é contraexemplo (não UNKNOWN)")
    if b == "oci":
        unknowns.append("security list e NSG no mesmo alvo com decisões diferentes: UNKNOWN (combinação sem evidência)")
    if b == "azurerm":
        unknowns.append("NSG na NIC e na sub-rede com decisões diferentes: UNKNOWN (combinação sem evidência)")
    return {"source": a, "target": b, "expected_losses": losses, "acceptable_target": req,
            "negatives": NEGATIVE_INVARIANTS, "unknowns": unknowns}
