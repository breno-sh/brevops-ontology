"""Dados da fatia net: tipos, conceitos, âncoras e decisões do glossarista (PILOT-NET-GLOSS).

Tudo aqui é decisão do glossarista, escrita uma vez e gravada pelo build com carimbo fixo (regeneração idêntica).
Separação pedida pelo achado F1 da revisão GPT-6: conjunto de regras, regra, alvo, anexação, estado de conexão,
precedência e efeito são conceitos distintos; os critérios de casamento (sentido, protocolo, portas, prefixo do
par) também. Âncora só com sentença de documentação do próprio átomo, citada pelo SERVICE-EVIDENCE (C25), na tag
fixada; sem sentença nas entradas, o conceito fica sem âncora (UNRESOLVED), nunca com âncora inventada.
"""

from __future__ import annotations

MODULE = "PILOT-NET-GLOSS"
DOMAIN = "NET"
SLICE = "net"
MODEL_ID = "claude-opus-5-5"
# carimbo das decisões do glossarista (fixo para a regeneração sair idêntica)
RECORDED_AT = "2026-11-04T02:30:00-03:00"
DECIDED_ON = "2026-11-04"

# Tipos Terraform da fatia (security group inline e standalone, firewall, NSG, security list e NSG da OCI, mais os
# recursos de anexação que existem como tipo). Ordem estável por provedor.
SLICE_TYPES = {
    "aws": ["aws_network_interface_sg_attachment", "aws_security_group", "aws_security_group_rule",
            "aws_vpc_security_group_egress_rule", "aws_vpc_security_group_ingress_rule"],
    "google": ["google_compute_firewall"],
    "azurerm": ["azurerm_network_interface_security_group_association", "azurerm_network_security_group",
                "azurerm_network_security_rule", "azurerm_subnet_network_security_group_association"],
    "oci": ["oci_core_network_security_group", "oci_core_network_security_group_security_rule",
            "oci_core_security_list"],
}
PROVIDERS = ("aws", "google", "azurerm", "oci")
# pares embutido × separado da mesma regra (critério E2: a decomposição tem de sair igual nas duas embalagens)
E2_PAIRS = [("aws", "aws_security_group.ingress", "aws_vpc_security_group_ingress_rule"),
            ("aws", "aws_security_group.egress", "aws_vpc_security_group_egress_rule"),
            ("azurerm", "azurerm_network_security_group.security_rule", "azurerm_network_security_rule")]
PAIR_CODE = {"aws": "AWS", "google": "GCP", "azurerm": "AZ", "oci": "OCI"}
PAIRS = (("aws", "google"), ("aws", "azurerm"), ("aws", "oci"), ("google", "azurerm"), ("google", "oci"),
         ("azurerm", "oci"))


def all_types() -> list[str]:
    return [t for p in PROVIDERS for t in SLICE_TYPES[p]]


NA = "NOT_APPLICABLE"


def _c(cid, label, definition, qk=NA, unit=NA):
    d = {"concept_id": cid, "label": label, "definition": definition, "domain": DOMAIN, "quantity_kind": qk,
         "status": "active"}
    if qk != "UNKNOWN":
        d["unit"] = unit
    return d


CONCEPTS = [
    _c("concept:filter_rule_set", "conjunto de regras de filtragem",
       "coleção de regras de filtragem de tráfego de rede que é avaliada como um todo e anexada por inteiro aos "
       "recursos cujo tráfego ela controla"),
    _c("concept:filter_rule", "regra de filtragem de tráfego",
       "condição sobre fluxos de rede (sentido, protocolo, portas e endereços) ligada a um efeito, que decide se o "
       "fluxo que casa com ela passa"),
    _c("concept:rule_target", "alvo da regra",
       "seletor declarado na própria regra que restringe a quais membros da rede (por etiqueta ou identidade de "
       "serviço) a regra se aplica, independentemente de onde o conjunto está anexado"),
    _c("concept:rule_set_attachment", "anexação do conjunto de regras",
       "vínculo entre um conjunto de regras de filtragem e um recurso de rede (interface ou sub-rede) que faz o "
       "tráfego desse recurso passar pela avaliação do conjunto"),
    _c("concept:attachment_rule_set_reference", "conjunto anexado",
       "referência, dentro de uma anexação, ao conjunto de regras de filtragem que passa a valer para o recurso de "
       "rede anexado"),
    _c("concept:attachment_interface_reference", "interface anexada",
       "referência, dentro de uma anexação, à interface de rede cujo tráfego passa a ser avaliado pelo conjunto de "
       "regras"),
    _c("concept:attachment_subnet_reference", "sub-rede anexada",
       "referência, dentro de uma anexação, à sub-rede cujo tráfego passa a ser avaliado pelo conjunto de regras"),
    _c("concept:rule_parent_set_reference", "conjunto da regra",
       "referência de uma regra de filtragem declarada como recurso separado ao conjunto de regras a que ela "
       "pertence"),
    _c("concept:rule_set_network", "rede do conjunto de regras",
       "referência de um conjunto de regras de filtragem à rede virtual que o contém e fora da qual ele não pode ser "
       "anexado"),
    _c("concept:rule_stateless", "regra sem estado",
       "indicador booleano de uma regra de filtragem que, verdadeiro, faz a regra valer só no sentido declarado sem "
       "rastrear a conexão, de modo que o tráfego de resposta precisa de regra própria no sentido oposto"),
    _c("concept:rule_priority", "prioridade da regra",
       "número ordinal de uma regra de filtragem que decide qual regra prevalece quando mais de uma casa o mesmo "
       "fluxo, prevalecendo o menor número"),
    _c("concept:rule_effect", "efeito da regra",
       "decisão, permitir ou negar, que uma regra de filtragem aplica ao fluxo que casa com ela"),
    _c("concept:rule_direction", "sentido da regra",
       "sentido do fluxo, entrada ou saída em relação ao recurso protegido, a que uma regra de filtragem se aplica"),
    _c("concept:rule_protocol", "protocolo da regra",
       "protocolo de rede ou de transporte (por exemplo TCP, UDP, ICMP ou todos) que um fluxo precisa usar para "
       "casar com a regra de filtragem"),
    _c("concept:rule_destination_port_list", "portas de destino da regra",
       "conjunto de portas ou faixas de portas de destino, escritas como texto, que um fluxo precisa usar para casar "
       "com a regra de filtragem"),
    _c("concept:rule_port_range_start", "porta inicial da regra",
       "limite inferior numérico da faixa de portas de destino que um fluxo de transporte precisa usar para casar "
       "com a regra de filtragem"),
    _c("concept:rule_port_range_end", "porta final da regra",
       "limite superior numérico da faixa de portas de destino que um fluxo de transporte precisa usar para casar "
       "com a regra de filtragem"),
    _c("concept:rule_source_address_range", "faixa de origem da regra",
       "bloco de endereços IP de onde o fluxo precisa vir para casar com a regra de filtragem"),
    _c("concept:rule_destination_address_range", "faixa de destino da regra",
       "bloco de endereços IP para onde o fluxo precisa ir para casar com a regra de filtragem"),
]

# Âncoras. kind: atom (ref = atom_id), block (ref = block_id) ou type (ref = type_id), C20 3.2.0. src: "C03" =
# fato description publicado do próprio átomo (docs_facts; a menor linha, que é a da seção de argumentos), ou um
# evidence_id do SERVICE-EVIDENCE do tipo. query: regex procurada nas sentenças do provedor (C25 e C03); found e note
# são o julgamento do glossarista sobre o que a busca achou.
CC_MAP_NET_5_AT = "2026-11-04T23:20:00-03:00"   # âncoras do efeito fixo (pedido CC-MAP-NET-5)
_N = "nenhum uso com outro significado nos tipos da fatia"


def _a(cid, ref, concept, src, context, query, found=False, note=_N, kind="atom", implication=None, at=None):
    d = {"claim_id": cid, "ref": ref, "kind": kind, "concept_id": concept, "src": src, "context": context,
         "query": query, "found": found, "note": note}
    if at:
        d["recorded_at"] = at
    if implication:
        d["implication"] = implication
    return d


def _imp(realization, value, rule, alts):
    return {"realization": realization, "value": value, "rule": rule,
            "alternatives": [{"ref": r, "value": v} for r, v in alts]}


G, Z, A, O = "google:google_compute_firewall", "azurerm:azurerm_network_security_rule", "aws", "oci"
AI, AE = "aws:aws_vpc_security_group_ingress_rule", "aws:aws_vpc_security_group_egress_rule"
SLI, SLE = "oci:oci_core_security_list:ingress_security_rules", "oci:oci_core_security_list:egress_security_rules"
_PRIO = r"\bpriority\b"
_PROTO = r"\bprotocol\b"
_ICMP = ("o mesmo atributo carrega o tipo ou o código ICMP quando o protocolo é ICMP: o significado de porta vale "
         "sob a guarda protocolo ∈ {tcp, udp}")
_TAGS = "o atributo também aceita etiquetas de serviço e '*': o domínio é mais largo que bloco CIDR"
ANCHORS = [
    # ---- firewall do provedor google
    _a("ANC-google-0001", f"{G}:priority", "concept:rule_priority", "C03", "argumento priority do firewall", _PRIO,
       note=("nos tipos de política de firewall o termo tem o mesmo sentido de ordem de avaliação; no empate de "
             "prioridade a negação prevalece (avaliação do conjunto, não significado do atributo)")),
    _a("ANC-google-0002", f"{G}:allow", "concept:rule_effect", "SE-google-iasfqf3ocxmoevym",
       "bloco allow do firewall; fato effect (effect_block) do SERVICE-EVIDENCE", r"(ALLOW|DENY) rules", kind="block",
       implication=_imp("block_choice", "allow", "o bloco allow{} usado no firewall implica efeito = permitir",
                        [(f"{G}:deny", "deny")])),
    _a("ANC-google-0003", f"{G}:deny", "concept:rule_effect", "SE-google-xdqcqcyrrh2jrehq",
       "bloco deny do firewall; fato effect (effect_block) do SERVICE-EVIDENCE", r"(ALLOW|DENY) rules", kind="block",
       implication=_imp("block_choice", "deny", "o bloco deny{} usado no firewall implica efeito = negar",
                        [(f"{G}:allow", "allow")])),
    _a("ANC-google-0004", f"{G}:direction", "concept:rule_direction", "C03", "argumento direction do firewall",
       r"\bdirection\b"),
    _a("ANC-google-0005", f"{G}:allow.protocol", "concept:rule_protocol", "C03", "argumento protocol do bloco allow",
       _PROTO),
    _a("ANC-google-0006", f"{G}:deny.protocol", "concept:rule_protocol", "C03", "argumento protocol do bloco deny",
       _PROTO),
    _a("ANC-google-0007", f"{G}:allow.ports", "concept:rule_destination_port_list", "C03",
       "argumento ports do bloco allow", r"list of ports",
       note="a lista aceita porta única ou faixa 'a-b' como texto; a multiplicidade é do atributo"),
    _a("ANC-google-0008", f"{G}:deny.ports", "concept:rule_destination_port_list", "C03",
       "argumento ports do bloco deny", r"list of ports",
       note="a lista aceita porta única ou faixa 'a-b' como texto; a multiplicidade é do atributo"),
    _a("ANC-google-0009", f"{G}:source_ranges", "concept:rule_source_address_range", "C03",
       "argumento source_ranges do firewall", r"source (IP address|ranges)",
       note="lista de blocos; a multiplicidade é do atributo"),
    _a("ANC-google-0010", f"{G}:destination_ranges", "concept:rule_destination_address_range", "C03",
       "argumento destination_ranges do firewall", r"destination (IP address|ranges)",
       note="lista de blocos; a multiplicidade é do atributo"),
    _a("ANC-google-0011", f"{G}:target_tags", "concept:rule_target", "C03", "argumento target_tags do firewall",
       r"\btarget", note="etiquetas de origem (source_tags) são seletor do par remoto, não alvo: conceito à parte"),
    _a("ANC-google-0012", f"{G}:target_service_accounts", "concept:rule_target", "C03",
       "argumento target_service_accounts do firewall", r"\btarget",
       note="contas de serviço de origem são seletor do par remoto, não alvo; alvo por etiqueta e por conta se excluem"),
    _a("ANC-google-0013", f"{G}:network", "concept:rule_set_network", "C03", "argumento network do firewall",
       r"network to attach", found=True,
       note=("a frase diz 'attach': aqui a rede é ao mesmo tempo o contêiner e a anexação (o firewall vale para a "
             "rede inteira, filtrado pelo alvo); a anexação a interface ou sub-rede não existe neste provedor")),
    # ---- regra separada e anexações do provedor azurerm
    _a("ANC-azurerm-0001", f"{Z}:priority", "concept:rule_priority", "C03", "argumento priority da regra", _PRIO,
       note="em restrições de aplicação web o termo é a mesma ordem; aqui o número é único no conjunto (sem empate)"),
    _a("ANC-azurerm-0002", f"{Z}:access", "concept:rule_effect", "C03", "argumento access da regra",
       r"allowed or denied|Allow`? (and|or) `?Deny"),
    _a("ANC-azurerm-0003", f"{Z}:direction", "concept:rule_direction", "C03", "argumento direction da regra",
       r"\bdirection\b"),
    _a("ANC-azurerm-0004", f"{Z}:protocol", "concept:rule_protocol", "C03", "argumento protocol da regra", _PROTO),
    _a("ANC-azurerm-0005", f"{Z}:destination_port_ranges", "concept:rule_destination_port_list", "C03",
       "argumento destination_port_ranges da regra", r"destination port",
       note="há também destination_port_range (um só valor), exclusivo com este; porta ou faixa como texto"),
    _a("ANC-azurerm-0006", f"{Z}:source_address_prefix", "concept:rule_source_address_range", "C03",
       "argumento source_address_prefix da regra", r"source IP range|address prefix", found=True, note=_TAGS),
    _a("ANC-azurerm-0007", f"{Z}:destination_address_prefix", "concept:rule_destination_address_range", "C03",
       "argumento destination_address_prefix da regra", r"destination IP range|address prefix", found=True,
       note=_TAGS),
    _a("ANC-azurerm-0008", f"{Z}:network_security_group_name", "concept:rule_parent_set_reference", "C03",
       "argumento network_security_group_name da regra", r"attach the rule to",
       note="referência por nome (não por identificador), no mesmo grupo de recursos"),
    _a("ANC-azurerm-0009", "azurerm:azurerm_network_interface_security_group_association:network_security_group_id",
       "concept:attachment_rule_set_reference", "C03", "argumento network_security_group_id da anexação à interface",
       r"should be (attached|associated)"),
    _a("ANC-azurerm-0010", "azurerm:azurerm_subnet_network_security_group_association:network_security_group_id",
       "concept:attachment_rule_set_reference", "C03", "argumento network_security_group_id da anexação à sub-rede",
       r"should be (attached|associated)"),
    _a("ANC-azurerm-0011", "azurerm:azurerm_network_interface_security_group_association:network_interface_id",
       "concept:attachment_interface_reference", "C03", "argumento network_interface_id da anexação à interface",
       r"ID of the Network Interface"),
    _a("ANC-azurerm-0012", "azurerm:azurerm_subnet_network_security_group_association:subnet_id",
       "concept:attachment_subnet_reference", "C03", "argumento subnet_id da anexação à sub-rede",
       r"ID of the Subnet"),
    # ---- security group, regras separadas e anexação do provedor aws
    _a("ANC-aws-0001", AI, "concept:rule_direction", "SE-aws-ikvsebbkuhrdk7i5",
       "tipo de regra de entrada; fato import_key do SERVICE-EVIDENCE", r"(ingress|egress) rules", kind="type",
       implication=_imp("type_choice", "ingress", "o tipo de regra de entrada implica sentido = entrada", [(AE, "egress")])),
    _a("ANC-aws-0002", AE, "concept:rule_direction", "SE-aws-as6ufq3egpm6jfqy",
       "tipo de regra de saída; fato import_key do SERVICE-EVIDENCE", r"(ingress|egress) rules", kind="type",
       implication=_imp("type_choice", "egress", "o tipo de regra de saída implica sentido = saída", [(AI, "ingress")])),
    _a("ANC-aws-0003", "aws:aws_security_group:ingress", "concept:rule_direction", "C03",
       "bloco ingress do conjunto (regras embutidas)", r"(ingress|egress) rules", kind="block",
       implication=_imp("block_choice", "ingress", "o bloco ingress{} implica sentido = entrada",
                        [("aws:aws_security_group:egress", "egress")])),
    _a("ANC-aws-0004", "aws:aws_security_group:egress", "concept:rule_direction", "C03",
       "bloco egress do conjunto (regras embutidas)", r"(ingress|egress) rules", kind="block",
       implication=_imp("block_choice", "egress", "o bloco egress{} implica sentido = saída",
                        [("aws:aws_security_group:ingress", "ingress")])),
    _a("ANC-aws-0005", f"{AI}:ip_protocol", "concept:rule_protocol", "C03", "argumento ip_protocol da regra de entrada",
       r"IP protocol"),
    _a("ANC-aws-0006", f"{AE}:ip_protocol", "concept:rule_protocol", "C03", "argumento ip_protocol da regra de saída",
       r"IP protocol"),
    _a("ANC-aws-0007", f"{AI}:from_port", "concept:rule_port_range_start", "C03",
       "argumento from_port da regra de entrada", r"port range", found=True, note=_ICMP),
    _a("ANC-aws-0008", f"{AE}:from_port", "concept:rule_port_range_start", "C03",
       "argumento from_port da regra de saída", r"port range", found=True, note=_ICMP),
    _a("ANC-aws-0009", f"{AI}:to_port", "concept:rule_port_range_end", "C03", "argumento to_port da regra de entrada",
       r"port range", found=True, note=_ICMP),
    _a("ANC-aws-0010", f"{AE}:to_port", "concept:rule_port_range_end", "C03", "argumento to_port da regra de saída",
       r"port range", found=True, note=_ICMP),
    _a("ANC-aws-0011", f"{AI}:cidr_ipv4", "concept:rule_source_address_range", "C03",
       "argumento cidr_ipv4 da regra de entrada", r"CIDR range",
       note="só IPv4; o bloco IPv6 é outro átomo (cidr_ipv6), não ancorado neste piloto"),
    _a("ANC-aws-0012", f"{AE}:cidr_ipv4", "concept:rule_destination_address_range", "C03",
       "argumento cidr_ipv4 da regra de saída", r"CIDR range",
       note="só IPv4; o bloco IPv6 é outro átomo (cidr_ipv6), não ancorado neste piloto"),
    _a("ANC-aws-0013", "aws:aws_security_group_rule:security_group_id", "concept:rule_parent_set_reference", "C03",
       "argumento security_group_id da regra genérica", r"apply this rule to"),
    _a("ANC-aws-0014", f"{AI}:security_group_id", "concept:rule_parent_set_reference", "C03",
       "argumento security_group_id da regra de entrada", r"ID of the security group",
       note="a mesma frase descreve o grupo na anexação a interface: lá é o conjunto anexado, conceito à parte"),
    _a("ANC-aws-0015", f"{AE}:security_group_id", "concept:rule_parent_set_reference", "C03",
       "argumento security_group_id da regra de saída", r"ID of the security group",
       note="a mesma frase descreve o grupo na anexação a interface: lá é o conjunto anexado, conceito à parte"),
    _a("ANC-aws-0016", "aws:aws_network_interface_sg_attachment:security_group_id",
       "concept:attachment_rule_set_reference", "C03", "argumento security_group_id da anexação à interface",
       r"ID of the security group", found=True,
       note="frase idêntica à das regras separadas (lá o grupo é o dono da regra); o sentido aqui vem do tipo anexação"),
    _a("ANC-aws-0017", "aws:aws_network_interface_sg_attachment:network_interface_id",
       "concept:attachment_interface_reference", "C03", "argumento network_interface_id da anexação",
       r"network interface to attach"),
    # ---- security list e NSG do provedor oci
    _a("ANC-oci-0001", f"{SLI}.stateless", "concept:rule_stateless", "C03", "argumento stateless das regras de entrada",
       r"\bstateless\b", note="o termo só aparece nas regras de filtragem do provedor, sempre como regra sem estado"),
    _a("ANC-oci-0002", f"{SLE}.stateless", "concept:rule_stateless", "C03", "argumento stateless das regras de saída",
       r"\bstateless\b", note="o termo só aparece nas regras de filtragem do provedor, sempre como regra sem estado"),
    _a("ANC-oci-0003", "oci:oci_core_network_security_group_security_rule:stateless", "concept:rule_stateless",
       "SE-oci-cxwuvxzhyrwz3j6f", "argumento stateless da regra separada; fato connection_state interpretado",
       r"\bstateless\b", note="o docs_facts não tem description publicada deste átomo; a frase vem do C25"),
    _a("ANC-oci-0004", "oci:oci_core_security_list:vcn_id", "concept:rule_set_network", "C03",
       "argumento vcn_id do conjunto", r"of the VCN",
       note="a mesma frase serve a outros objetos da rede (tabela de rotas, gateways), sempre como rede que contém"),
    _a("ANC-oci-0005", "oci:oci_core_network_security_group:vcn_id", "concept:rule_set_network", "C03",
       "argumento vcn_id do grupo", r"of the VCN",
       note="a mesma frase serve a outros objetos da rede (tabela de rotas, gateways), sempre como rede que contém"),
    _a("ANC-oci-0006", f"{SLI}.protocol", "concept:rule_protocol", "C03", "argumento protocol das regras de entrada",
       r"transport protocol"),
    _a("ANC-oci-0007", f"{SLE}.protocol", "concept:rule_protocol", "C03", "argumento protocol das regras de saída",
       r"transport protocol"),
    _a("ANC-oci-0008", f"{SLI}.source", "concept:rule_source_address_range", "C03",
       "argumento source das regras de entrada", r"range of IP addresses", found=True,
       note="com source_type de serviço o valor é um rótulo de serviço, não bloco CIDR: domínio mais largo"),
    _a("ANC-oci-0009", f"{SLE}.destination", "concept:rule_destination_address_range", "C03",
       "argumento destination das regras de saída", r"range of IP addresses", found=True,
       note="com destination_type de serviço o valor é um rótulo de serviço, não bloco CIDR: domínio mais largo"),
    _a("ANC-oci-0010", "oci:oci_core_network_security_group_security_rule:network_security_group_id",
       "concept:rule_parent_set_reference", "C03", "argumento network_security_group_id da regra separada",
       r"of the network security group"),
    # ---- efeito fixo "só permitem" (CC-MAP-NET-5): frase oficial publicada pelo SERVICE-EVIDENCE (fatos effect)
    _a("ANC-aws-0018", "aws:aws_security_group:ingress", "concept:rule_effect", "SE-aws-6gqdywgpolbhwsgh",
       "regras embutidas de entrada do conjunto; fato effect allow_only do SERVICE-EVIDENCE (guia de regras)",
       r"allow rules|deny rules", kind="block",
       implication=_imp("block_choice", "allow", "toda regra do bloco ingress{} permite: não há regra de negação", []), at=CC_MAP_NET_5_AT),
    _a("ANC-aws-0019", "aws:aws_security_group:egress", "concept:rule_effect", "SE-aws-6gqdywgpolbhwsgh",
       "regras embutidas de saída do conjunto; fato effect allow_only do SERVICE-EVIDENCE (guia de regras)",
       r"allow rules|deny rules", kind="block",
       implication=_imp("block_choice", "allow", "toda regra do bloco egress{} permite: não há regra de negação", []), at=CC_MAP_NET_5_AT),
    _a("ANC-aws-0020", "aws:aws_security_group_rule", "concept:rule_effect", "SE-aws-dhmyfhb32dip3gm3",
       "tipo de regra genérica; fato effect allow_only do SERVICE-EVIDENCE (guia de regras)",
       r"allow rules|deny rules", kind="type",
       implication=_imp("type_choice", "allow", "toda instância do tipo de regra genérica permite", []), at=CC_MAP_NET_5_AT),
    _a("ANC-aws-0021", AI, "concept:rule_effect", "SE-aws-uprjohepvlbrisrj",
       "tipo de regra de entrada; fato effect allow_only do SERVICE-EVIDENCE (guia de regras)",
       r"allow rules|deny rules", kind="type",
       implication=_imp("type_choice", "allow", "toda instância do tipo de regra de entrada permite", []), at=CC_MAP_NET_5_AT),
    _a("ANC-aws-0022", AE, "concept:rule_effect", "SE-aws-27fce6orje6kwxl7",
       "tipo de regra de saída; fato effect allow_only do SERVICE-EVIDENCE (guia de regras)",
       r"allow rules|deny rules", kind="type",
       implication=_imp("type_choice", "allow", "toda instância do tipo de regra de saída permite", []), at=CC_MAP_NET_5_AT),
    _a("ANC-oci-0011", "oci:oci_core_network_security_group_security_rule", "concept:rule_effect",
       "SE-oci-c5zpsmypese5ipku", "tipo de regra separada; fato effect rule_allows do SERVICE-EVIDENCE (guia de regras)",
       r"rule allows|no traffic is allowed", kind="type",
       implication=_imp("type_choice", "allow_capable", "a regra pode permitir um tipo de tráfego (literal do guia); que só permite não está publicado", []), at=CC_MAP_NET_5_AT),
    _a("ANC-oci-0012", SLI, "concept:rule_effect", "SE-oci-i4qhfl5ma4mlbegd",
       "bloco de regras de entrada do conjunto; fato effect rule_allows do SERVICE-EVIDENCE (guia de regras)",
       r"rule allows|no traffic is allowed", kind="block",
       implication=_imp("block_choice", "allow_capable", "a regra do bloco pode permitir um tipo de tráfego (literal do guia); que só permite não está publicado", []), at=CC_MAP_NET_5_AT),
    _a("ANC-oci-0013", SLE, "concept:rule_effect", "SE-oci-i4qhfl5ma4mlbegd",
       "bloco de regras de saída do conjunto; fato effect rule_allows do SERVICE-EVIDENCE (guia de regras)",
       r"rule allows|no traffic is allowed", kind="block",
       implication=_imp("block_choice", "allow_capable", "a regra do bloco pode permitir um tipo de tráfego (literal do guia); que só permite não está publicado", []), at=CC_MAP_NET_5_AT),
]


def _dec(n, kind, concept, reason, related=None, value=None, evidence=None):
    d = {"schema": "bo.glossary_decision/1", "decision_id": f"GD-NET-{n:04d}", "kind": kind,
         "concept_id": concept, "reason": reason, "evidence": evidence or [], "author": MODULE,
         "recorded_at": RECORDED_AT}
    if related:
        d["related_concept"] = related
    if value:
        d["value"] = value
    return d


def _vt(datatype, sem):
    return {"datatype": datatype, "enum_semantics": sem}


# (n, kind, concept, related, value, reason, evidências: evidence_id do C25 ou fact_id do C03)
DECISION_SPECS = [
    (1, "value_type", "concept:rule_priority", None, _vt("integer", "ordinal: menor número prevalece"),
     "inteiro ordinal, o menor prevalece; a faixa admitida é do átomo, não do conceito",
     ["SE-google-n2ccqgtmt4jm72sp", "SE-azurerm-hfppj5whireqkdcl"]),
    (2, "value_type", "concept:rule_effect", None, _vt("enum", "nominal: permitir | negar"),
     ("enum nominal de dois valores; num provedor vem do bloco usado, não de atributo. Provedor aws: efeito fixo = "
      "permitir (literal publicado no guia: só regras de permissão). Provedor oci: a regra permite (allow_capable), "
      "mas a exclusividade (só permite) não está publicada: nenhuma guarda de 'só permite' sai daqui"),
     ["SE-azurerm-x42gvfavlctlsm6r", "SE-aws-6gqdywgpolbhwsgh", "SE-oci-i4qhfl5ma4mlbegd"]),
    (3, "value_type", "concept:rule_stateless", None,
     _vt("boolean", "verdadeiro = sem estado (a resposta precisa de regra própria); falso = com estado"),
     "booleano com polaridade sem estado = verdadeiro", ["SE-oci-bp7mulbmn76camow", "SE-oci-3ihxku562hxrgq4b"]),
    (4, "exclusive", "concept:rule_stateless", None, None,
     ("estado de conexão declarável por regra só existe num provedor da fatia; nos outros três o fato "
      "connection_state do SERVICE-EVIDENCE é unknown e a constatação do CQFIX citada no brief de lançamento é que "
      "o estado não é declarável por regra; não se força âncora nos outros três"), ["SE-oci-cxwuvxzhyrwz3j6f"]),
    (5, "same_kind_distinct", "concept:rule_target", "concept:rule_set_attachment", None,
     ("alvo e anexação decidem a quem as regras se aplicam, mas são distintos: o alvo é um seletor dentro da regra; "
      "a anexação é um vínculo do conjunto inteiro com um recurso de rede (achado F1)"), []),
    (6, "same_kind_distinct", "concept:rule_set_network", "concept:rule_set_attachment", None,
     ("pertencer a uma rede virtual não é estar anexado: a rede limita onde o conjunto pode ser anexado; num provedor "
      "a rede é também a anexação (o firewall vale para a rede inteira, filtrado pelo alvo)"),
     ["SE-oci-pshq6e42psyl6dzo"]),
    (7, "same_kind_distinct", "concept:rule_priority", "concept:rule_effect", None,
     ("precedência e efeito são eixos separados (achado F1): a prioridade escolhe a regra que vale; o efeito diz o "
      "que ela faz; no empate de prioridade a negação prevalecer é regra de avaliação do conjunto"),
     ["SE-google-t45d32hahm5ikdc3"]),
    (8, "same_kind_distinct", "concept:filter_rule_set", "concept:filter_rule", None,
     ("conjunto e regra são unidades distintas: a regra é avaliada dentro de um conjunto; a mesma regra aparece "
      "embutida no conjunto ou como recurso separado, e isso é embalagem, não outro conceito"), []),
    (9, "value_type", "concept:rule_set_network", None,
     _vt("string", "referência opaca: identificador ou nome da rede que contém o conjunto"),
     "referência por identificador ou nome, sem grandeza", ["SE-oci-pshq6e42psyl6dzo"]),
    (10, "value_type", "concept:rule_direction", None, _vt("enum", "nominal: entrada | saída"),
     "enum nominal; em dois provedores o sentido vem do bloco ou do tipo, não de um atributo", []),
    (11, "value_type", "concept:rule_protocol", None,
     _vt("string", "nome ou número do protocolo IP; o curinga 'todos' tem grafia própria em cada provedor"),
     "texto: nome ou número; os valores admitidos e o curinga são do átomo", []),
    (12, "value_type", "concept:rule_destination_port_list", None,
     _vt("string", "cada elemento é uma porta ou uma faixa 'a-b' como texto; a multiplicidade é do atributo"),
     "elemento textual; lista ou valor único é cardinalidade do atributo, não do conceito", []),
    (13, "value_type", "concept:rule_port_range_start", None, _vt("integer", "porta 0..65535, limite inferior"),
     "inteiro; o atributo pode carregar outro significado sob outro protocolo (guarda do mapeador)", []),
    (14, "value_type", "concept:rule_port_range_end", None, _vt("integer", "porta 0..65535, limite superior"),
     "inteiro; o atributo pode carregar outro significado sob outro protocolo (guarda do mapeador)", []),
    (15, "value_type", "concept:rule_source_address_range", None,
     _vt("string", "bloco CIDR (IPv4 ou IPv6); alguns átomos aceitam também rótulos de serviço"),
     "texto CIDR; o domínio de cada átomo pode ser mais largo", []),
    (16, "value_type", "concept:rule_destination_address_range", None,
     _vt("string", "bloco CIDR (IPv4 ou IPv6); alguns átomos aceitam também rótulos de serviço"),
     "texto CIDR; o domínio de cada átomo pode ser mais largo", []),
    (17, "same_kind_distinct", "concept:rule_source_address_range", "concept:rule_destination_address_range", None,
     ("mesmo tipo de valor (bloco de endereços), papéis opostos no fluxo; o 'par remoto' de uma regra é a origem na "
      "entrada e o destino na saída, por isso não há conceito de par: num provedor a regra tem os dois sempre"), []),
    (18, "same_kind_distinct", "concept:rule_port_range_start", "concept:rule_port_range_end", None,
     "mesmo tipo (porta), limites opostos da mesma faixa", []),
    (19, "same_kind_distinct", "concept:rule_destination_port_list", "concept:rule_port_range_start", None,
     ("portas como texto (porta ou faixa) e limite numérico da faixa descrevem a mesma restrição por estruturas "
      "diferentes: juntar ou separar é tradução do mapeador, não sinônimo"), []),
    (20, "same_kind_distinct", "concept:attachment_interface_reference", "concept:attachment_subnet_reference", None,
     "a anexação vale para uma interface ou para uma sub-rede inteira: alcances diferentes", []),
    (21, "same_kind_distinct", "concept:rule_parent_set_reference", "concept:attachment_rule_set_reference", None,
     ("as duas apontam para um conjunto de regras: a da regra diz a que conjunto ela pertence; a da anexação diz que "
      "conjunto passa a valer para o recurso (a frase de documentação pode ser idêntica)"), []),
    (22, "value_type", "concept:rule_target", None,
     _vt("string", "cada elemento é uma etiqueta de instância ou uma conta de serviço; multiplicidade do atributo"),
     "seletor textual", []),
    (23, "value_type", "concept:rule_parent_set_reference", None,
     _vt("string", "referência opaca ao conjunto (identificador ou nome)"), "referência", []),
    (24, "value_type", "concept:attachment_rule_set_reference", None,
     _vt("string", "referência opaca ao conjunto anexado"), "referência", []),
    (25, "value_type", "concept:attachment_interface_reference", None,
     _vt("string", "referência opaca à interface de rede"), "referência", []),
    (26, "value_type", "concept:attachment_subnet_reference", None,
     _vt("string", "referência opaca à sub-rede"), "referência", []),
]

# fatos tipados da fatia para o pacote do mapeador (onde o conceito mora por estrutura, ausências): só leitura das
# entradas; nada aqui é correspondência
SLICE_NOTES = [
    {"concept_id": "concept:rule_effect", "provider": "aws",
     "note": ("regras só permitem (guia: 'You can specify allow rules, but not deny rules'): âncoras ANC-aws-0018..0022 "
              "com efeito = permitir; à parte, o provedor cria uma regra padrão de saída que o Terraform remove"),
     "evidence": ["SE-aws-6gqdywgpolbhwsgh", "SE-aws-jcsq5zrpnuvxzaxv"]},
    {"concept_id": "concept:rule_effect", "provider": "oci",
     "note": ("só o literal do guia: a regra permite um tipo de tráfego (âncoras ANC-oci-0011..0013, efeito "
              "allow_capable) e, sem regras, nenhum tráfego passa; que a regra só permite não está publicado: nenhuma "
              "exclusividade"),
     "evidence": ["SE-oci-i4qhfl5ma4mlbegd", "SE-oci-7fsekbectwthhskg"]},
    {"concept_id": "concept:rule_priority", "provider": "aws",
     "note": "fato precedence unknown no SERVICE-EVIDENCE; regras só permitem, sem atributo de prioridade",
     "evidence": [{"provider": "aws", "fact_kind": "precedence", "status": "unknown"}]},
    {"concept_id": "concept:rule_priority", "provider": "oci",
     "note": "fato precedence unknown no SERVICE-EVIDENCE; CQFIX (via brief): sem negação, logo sem precedência entre efeitos",
     "evidence": [{"provider": "oci", "fact_kind": "precedence", "status": "unknown"}]},
    {"concept_id": "concept:rule_stateless", "provider": "aws,google,azurerm",
     "note": "fato connection_state unknown no SERVICE-EVIDENCE; CQFIX (via brief): estado de conexão não declarável por regra",
     "evidence": [{"provider": "aws", "fact_kind": "connection_state", "status": "unknown"},
                  {"provider": "google", "fact_kind": "connection_state", "status": "unknown"},
                  {"provider": "azurerm", "fact_kind": "connection_state", "status": "unknown"}]},
    {"concept_id": "concept:rule_set_attachment", "provider": "google",
     "note": "não há anexação a interface ou sub-rede: o firewall vale para a rede (network) e o alvo filtra os membros",
     "evidence": []},
    {"concept_id": "concept:rule_set_attachment", "provider": "oci",
     "note": "a anexação mora em atributos de outros tipos (sub-rede e interface virtual), fora dos tipos da fatia",
     "evidence": []},
    {"concept_id": "concept:rule_direction", "provider": "oci",
     "note": "nas regras embutidas o sentido vem do bloco (ingress_security_rules / egress_security_rules), sem frase do bloco no docs_facts; na regra separada o atributo direction não tem description publicada",
     "evidence": []},
    {"concept_id": "concept:rule_port_range_start", "provider": "oci",
     "note": "tcp_options/udp_options min e max têm a mesma frase para destino e origem ('The minimum port number'): não ancorados (ambíguos)",
     "evidence": []},
    {"concept_id": "concept:filter_rule", "provider": "aws,azurerm",
     "note": "as regras embutidas (ingress/egress e security_rule) são lista de objetos sem description por campo no docs_facts: só as regras separadas têm átomos ancorados",
     "evidence": []},
]
