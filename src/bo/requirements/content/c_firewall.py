"""Caso adversarial FIREWALL: conjunto de regras, regra, alvo, anexação, estado de conexão, precedência e efeito."""

from ..model import cm, fx, ground

CONS = ["PILOT-NET-ORACLE", "GRAIN", "GRAIN-REPRO", "DOMAIN-CONTRACTS", "AXIOMS", "SEMANTIC-REGRESSION", "CQFIX"]

G_INLINE = [
    ground("aws", "aws_security_group com ingress{}/egress{} embutidos x aws_vpc_security_group_ingress_rule (ou aws_security_group_rule) separados"),
    ground("azurerm", "azurerm_network_security_group com security_rule{} embutidos x azurerm_network_security_rule separado"),
    ground("oci", "oci_core_security_list com ingress_security_rules{} embutidos x oci_core_network_security_group_security_rule separado (este para NSG)"),
    ground("google", "google_compute_firewall é uma regra por recurso, com allow{}/deny{} embutidos; não há conjunto explícito: o conjunto é a rede, e o alvo vem de rótulo ou identidade de serviço"),
]
G_STATE = [
    ground("aws", "grupo de segurança: com estado, só allow; lista de controle de rede (aws_network_acl): sem estado, numerada, allow/deny"),
    ground("oci", "security list e NSG: estado POR REGRA (atributo stateless, padrão false = com estado); não são intrinsecamente sem estado"),
    ground("azurerm", "NSG: com estado, prioridade 100-4096, allow/deny; prioridade única por direção"),
    ground("google", "firewall de VPC: com estado, prioridade 0-65535 (menor avaliada antes), allow/deny"),
]
G_PREC = [
    ground("google", "em prioridade igual, deny prevalece sobre allow: confirmar na documentação fixada antes de usar"),
    ground("azurerm", "não aceita duas regras com a mesma prioridade na mesma direção"),
    ground("aws", "grupo de segurança não tem precedência (só allow, união); a lista de controle de rede avalia por número crescente, primeira que casa"),
    ground("oci", "só allow; sem precedência entre regras"),
]
G_TARGET = [
    ground("google", "alvo por target_tags ou target_service_accounts: seleção por rótulo"),
    ground("aws", "o conjunto é anexado à interface (vpc_security_group_ids da instância ou da interface)"),
    ground("azurerm", "o NSG é associado à interface ou à sub-rede (recursos de associação separados)"),
    ground("oci", "security list associada à sub-rede; NSG associado à VNIC"),
]


def _rule(i, direction, port, effect, cidr="203.0.113.0/24", prio=None, state=None, inline=None, pos=None):
    a = [f"r{i}.direction={direction}", "r%d.protocol=tcp" % i, f"r{i}.port={port}", f"r{i}.effect={effect}"]
    a.append(f"r{i}.{'source_cidr' if direction == 'ingress' else 'dest_cidr'}={cidr}")
    if prio is not None:
        a.append(f"r{i}.priority={prio}")
    if state is not None:
        a.append(f"r{i}.state_tracking={state}")
    if inline is not None:
        a.append(f"r{i}.declared_inline={'true' if inline else 'false'}")
    if pos is not None:
        a.append(f"r{i}.text_position={pos}")
    return a


def _flow(fid, direction, port, src):
    return [f"{fid}.direction={direction}", f"{fid}.protocol=tcp", f"{fid}.port={port}", f"{fid}.source_cidr={src}"]


C = [
    cm("CMT-FW-P01", "FIREWALL", "positive", "invariant",
       "Regra declarada embutida no conjunto e regra declarada como recurso separado ligado ao conjunto produzem "
       "a mesma decomposição: o conjunto é entidade, a regra é componente dele com identidade de ocorrência, e "
       "direção, protocolo, porta, origem e efeito são os mesmos.",
       "unidades(embutida) == unidades(separada): rs1 ENTITY; r1 COMPONENT de rs1",
       [fx("FX-FW-P01-INLINE", "regra de entrada embutida no conjunto",
           "rs1:rule_set r1:filter_rule", ["r1 rule_in rs1"],
           ["rs1.evaluation=allow_only", "rs1.default_state_tracking=stateful"] + _rule(1, "ingress", 443, "allow", inline=True)),
        fx("FX-FW-P01-SEPARATE", "a mesma regra como recurso separado",
           "rs1:rule_set r1:filter_rule", ["r1 rule_in rs1"],
           ["rs1.evaluation=allow_only", "rs1.default_state_tracking=stateful"] + _rule(1, "ingress", 443, "allow", inline=False))],
       "INVARIANT", "o grão de regra não depende da embalagem (F1)", ["REQ-NET-01", "REQ-ENT-01"], ["F1"],
       "decomposição inline x standalone de regras", layer="terraform", grounding=G_INLINE, consumers=CONS),
    cm("CMT-FW-P02", "FIREWALL", "positive", "entails",
       "Num conjunto com estado de conexão, a regra de entrada que permite um fluxo permite também o tráfego de "
       "retorno desse fluxo sem regra de saída.",
       "decision(retorno de f1) = allow",
       fx("FX-FW-P02", "conjunto com estado, só regra de entrada",
          "rs1:rule_set r1:filter_rule nic1:network_interface f1:flow",
          ["r1 rule_in rs1", "rs1 attached_to nic1"],
          ["rs1.evaluation=allow_only", "rs1.default_state_tracking=stateful"] + _rule(1, "ingress", 443, "allow")
          + _flow("f1", "ingress", 443, "203.0.113.10/32")),
       "ENTAILED", "estado de conexão muda a decisão do retorno", ["REQ-NET-01", "REQ-NET-02"], ["F1"],
       "semântica do estado de conexão", layer="evaluation", grounding=G_STATE, consumers=CONS),
    cm("CMT-FW-P03", "FIREWALL", "positive", "entails",
       "Quando o estado de conexão é atributo de cada regra, um conjunto pode misturar regra com estado e regra "
       "sem estado: o retorno do fluxo da regra com estado é permitido; o da regra sem estado só com regra de "
       "saída explícita.",
       "decision(retorno de f1) = allow AND decision(retorno de f2) = deny AND state_tracking é atributo de r1 e r2, não de rs1",
       fx("FX-FW-P03", "conjunto com uma regra com estado e uma sem estado",
          "rs1:rule_set r1:filter_rule r2:filter_rule nic1:network_interface f1:flow f2:flow",
          ["r1 rule_in rs1", "r2 rule_in rs1", "rs1 attached_to nic1"],
          ["rs1.evaluation=allow_only"] + _rule(1, "ingress", 443, "allow", state="stateful")
          + _rule(2, "ingress", 8080, "allow", state="stateless")
          + _flow("f1", "ingress", 443, "203.0.113.10/32") + _flow("f2", "ingress", 8080, "203.0.113.10/32")),
       "ENTAILED", "estado por regra (F1: o conjunto de regras de um provedor não é intrinsecamente sem estado)", ["REQ-NET-01"],
       ["F1"], "estado de conexão no nível certo", layer="evaluation", grounding=G_STATE[1:2], consumers=CONS),
    cm("CMT-FW-P04", "FIREWALL", "positive", "entails",
       "Num conjunto com precedência numérica e efeitos permitir/negar, a regra de negação de maior precedência "
       "vence a regra de permissão de menor precedência para o fluxo que as duas cobrem.",
       "decision(f1) = deny",
       fx("FX-FW-P04", "deny de precedência maior sobre allow",
          "rs1:rule_set r1:filter_rule r2:filter_rule nic1:network_interface f1:flow",
          ["r1 rule_in rs1", "r2 rule_in rs1", "rs1 attached_to nic1"],
          ["rs1.evaluation=priority_allow_deny", "rs1.default_state_tracking=stateful"]
          + _rule(1, "ingress", 22, "deny", cidr="0.0.0.0/0", prio=100)
          + _rule(2, "ingress", 22, "allow", prio=200) + _flow("f1", "ingress", 22, "203.0.113.5/32")),
       "ENTAILED", "precedência explícita decide o conflito", ["REQ-NET-01", "REQ-NET-02"], ["F1"],
       "precedência e efeito", layer="evaluation", grounding=G_PREC, consumers=CONS),
    cm("CMT-FW-P05", "FIREWALL", "positive", "entails",
       "Conjunto que seleciona alvos por rótulo aplica-se exatamente às instâncias com o rótulo, sob leitura "
       "completa; a aplicação vem da seleção ou da anexação, não de a regra ser parte do alvo.",
       "applies(rs1) = {vm1}",
       fx("FX-FW-P05", "seleção de alvo por rótulo",
          "rs1:rule_set r1:filter_rule vm1:compute_instance vm2:compute_instance l1:label",
          ["r1 rule_in rs1", "rs1 targets_label l1", "vm1 has_label l1"],
          ["l1.value=web"] + _rule(1, "ingress", 443, "allow")),
       "ENTAILED", "alvo e anexação são relações próprias", ["REQ-NET-01"], ["F1"],
       "alvo por seleção x anexação", grounding=G_TARGET, consumers=CONS),
    cm("CMT-FW-P06", "FIREWALL", "positive", "invariant",
       "Com precedência numérica, a ordem textual das regras não muda a decisão.",
       "decision(f1, base) == decision(f1, variante) == deny",
       [fx("FX-FW-P06-A", "deny antes no texto",
           "rs1:rule_set r1:filter_rule r2:filter_rule f1:flow", ["r1 rule_in rs1", "r2 rule_in rs1"],
           ["rs1.evaluation=priority_allow_deny"] + _rule(1, "ingress", 22, "deny", cidr="0.0.0.0/0", prio=100, pos=1)
           + _rule(2, "ingress", 22, "allow", prio=200, pos=2) + _flow("f1", "ingress", 22, "203.0.113.5/32")),
        fx("FX-FW-P06-B", "deny depois no texto",
           "rs1:rule_set r1:filter_rule r2:filter_rule f1:flow", ["r1 rule_in rs1", "r2 rule_in rs1"],
           ["rs1.evaluation=priority_allow_deny"] + _rule(1, "ingress", 22, "deny", cidr="0.0.0.0/0", prio=100, pos=2)
           + _rule(2, "ingress", 22, "allow", prio=200, pos=1) + _flow("f1", "ingress", 22, "203.0.113.5/32"))],
       "INVARIANT", "posição textual não é precedência quando há número", ["REQ-NET-01", "REQ-ID-01"], ["F1"],
       "precedência independente da posição", layer="evaluation", consumers=CONS),
    cm("CMT-FW-N01", "FIREWALL", "negative", "rejects",
       "Regra de negação não vira permissão. Traduzir um conjunto com negação para um destino que só exprime "
       "permissão: a tradução é bloqueada ou declara perda preservando a decisão; nunca emite permissão que "
       "cubra o tráfego negado, nunca omite a negação em silêncio.",
       "toda tradução T com decision_T(f1) = allow é rejeitada",
       fx("FX-FW-N01", "origem com deny, destino só-allow",
          "rs1:rule_set r1:filter_rule r2:filter_rule tgt:target_setting f1:flow",
          ["r1 rule_in rs1", "r2 rule_in rs1", "rs1 translates_to tgt"],
          ["rs1.evaluation=priority_allow_deny"] + _rule(1, "ingress", 22, "deny", cidr="0.0.0.0/0", prio=100)
          + _rule(2, "ingress", 22, "allow", prio=200) + ["tgt.supports_deny=false"]
          + _flow("f1", "ingress", 22, "203.0.113.5/32")),
       "REJECTED", "o exemplo do brief: regra deny não vira allow", ["REQ-NET-01", "REQ-LOSS-01"], ["F9", "F1"],
       "preservação do efeito na tradução", layer="translation", grounding=G_STATE[:1],
       consumers=CONS + ["TRANSLATOR", "PILOT-NET-E2E"]),
    cm("CMT-FW-N02", "FIREWALL", "negative", "rejects",
       "Uma regra não tem ao mesmo tempo estado de conexão e ausência de estado; e a classe das regras sem estado "
       "não é subclasse da das regras com estado.",
       "x1 com state_tracking=stateful e state_tracking=stateless é inconsistente",
       fx("FX-FW-N02", "regra com dois estados de conexão",
          "x1:filter_rule", [], ["x1.state_tracking=stateful", "x1.state_tracking=stateless"]),
       "REJECTED", "R1-M3: regra de ACL sem estado sob regra com estado", ["REQ-TAX-01", "REQ-NET-01"],
       ["R1-M3", "F9"], "estado de conexão funcional e disjunto", code="INCONSISTENT", consumers=CONS),
    cm("CMT-FW-N03", "FIREWALL", "negative", "not_entails",
       "Regra de saída não autoriza conexão nova de entrada.",
       "NOT decision(f1) = allow",
       fx("FX-FW-N03", "só regra de saída; fluxo de entrada novo",
          "rs1:rule_set r1:filter_rule nic1:network_interface f1:flow",
          ["r1 rule_in rs1", "rs1 attached_to nic1"],
          ["rs1.evaluation=allow_only", "rs1.default_state_tracking=stateful"]
          + _rule(1, "egress", 443, "allow", cidr="0.0.0.0/0") + _flow("f1", "ingress", 443, "203.0.113.5/32")),
       "NOT_ENTAILED", "direção faz parte da regra", ["REQ-NET-01", "REQ-NET-02"], ["F1"],
       "direção respeitada", layer="evaluation", consumers=CONS),
    cm("CMT-FW-U01", "FIREWALL", "unknown", "unknown",
       "Se parte das regras do conjunto não foi lida, a decisão sobre um fluxo que nenhuma regra lida permite "
       "é UNKNOWN, não negado.",
       "decision(f1) = UNKNOWN",
       fx("FX-FW-U01", "conjunto lido pela metade",
          "rs1:rule_set r1:filter_rule f1:flow", ["r1 rule_in rs1"],
          ["rs1.evaluation=allow_only"] + _rule(1, "ingress", 443, "allow") + _flow("f1", "ingress", 22, "203.0.113.5/32"),
          complete=False, not_read=["rs1.rules"]),
       "UNKNOWN", "negação implícita só vale sob leitura completa", ["REQ-ABS-01", "REQ-NET-02"], ["F1", "S1"],
       "UNKNOWN sob leitura parcial", code="INCOMPLETE_READ", layer="evaluation", consumers=CONS),
    cm("CMT-FW-U02", "FIREWALL", "unknown", "unknown",
       "Duas regras de mesma precedência, uma permite e outra nega o mesmo fluxo: sem evidência da regra de "
       "desempate do provedor, a decisão é UNKNOWN.",
       "decision(f1) = UNKNOWN",
       fx("FX-FW-U02", "permitir e negar com a mesma precedência",
          "rs1:rule_set r1:filter_rule r2:filter_rule f1:flow", ["r1 rule_in rs1", "r2 rule_in rs1"],
          ["rs1.evaluation=priority_allow_deny"] + _rule(1, "ingress", 22, "allow", prio=100)
          + _rule(2, "ingress", 22, "deny", prio=100) + _flow("f1", "ingress", 22, "203.0.113.5/32"),
          complete=False, not_read=["rs1.tie_break"]),
       "UNKNOWN", "desempate é semântica do provedor e precisa de evidência", ["REQ-NET-01", "REQ-ABS-01"],
       ["F1"], "desempate não inventado", code="MISSING_EVIDENCE", layer="evaluation", grounding=G_PREC[:2],
       consumers=CONS),
    cm("CMT-FW-U03", "FIREWALL", "unknown", "unknown",
       "Se o estado de conexão não foi declarado e o padrão do provedor não tem evidência, a decisão sobre o "
       "tráfego de retorno é UNKNOWN; não se assume \"com estado\".",
       "decision(retorno de f1) = UNKNOWN",
       fx("FX-FW-U03", "regra sem estado declarado e sem padrão evidenciado",
          "rs1:rule_set r1:filter_rule f1:flow", ["r1 rule_in rs1"],
          ["rs1.evaluation=allow_only"] + _rule(1, "ingress", 443, "allow") + _flow("f1", "ingress", 443, "203.0.113.5/32"),
          complete=False, not_read=["r1.state_tracking"]),
       "UNKNOWN", "default não inventado", ["REQ-NET-01", "REQ-CFG-02"], ["F1"], "estado de conexão não assumido",
       code="MISSING_EVIDENCE", layer="evaluation", consumers=CONS),
]
