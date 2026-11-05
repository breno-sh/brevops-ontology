"""Realizações da fatia NET por provedor (padrão de descritor do ONTPAT, C14 realizations).

Uma realização diz como uma classe ou propriedade NEUTRA aparece no Terraform de um provedor: que tipo de recurso
ou bloco a realiza, em que campo mora o valor e como o valor do provedor se escreve no vocabulário neutro (codec).
Não é correspondência entre provedores: o valor lido de um átomo só atravessa para outro provedor por uma alegação
OK do C09 (claims.py); o codec só serve para (1) raciocinar sobre o valor no vocabulário neutro e (2) descer um valor
que a ontologia ENTAILOU (realização estrutural no c2, axioma no c3), e que portanto não tem átomo de origem.

Cada realização cita a evidência que a sustenta (SERVICE-EVIDENCE C25 ou docs_facts C03 do pin). Nada aqui é
default de provedor inventado: campo que o plano precisa e cujo valor ninguém sabe vira UNKNOWN_INPUT no translate.

Vocabulário neutro (C24, REQ-NET-01): rule_set, filter_rule, attachment, selection; propriedades da regra:
direction {ingress, egress}, effect {allow, deny}, protocol {tcp, udp, icmp, all}, dst_ports [(lo, hi)] | None
(qualquer), src_ports idem, remote [CIDR], local [CIDR] | None, priority int | None, stateless bool | None, name.
"""

from __future__ import annotations

NEUTRAL_UNITS = ("rule_set", "filter_rule", "attachment", "selection")

# conceitos do glossário (C20 do PILOT-NET-GLOSS) -> propriedade neutra. Lido das alegações (subject_concept /
# object_concept); conceito fora desta lista não é usado pela tradução (fica no OWL como propriedade sem uso).
CONCEPT_PROPERTY = {
    "concept:rule_direction": "direction",
    "concept:rule_effect": "effect",
    "concept:rule_protocol": "protocol",
    "concept:rule_port_range_start": "port_from",
    "concept:rule_port_range_end": "port_to",
    "concept:rule_destination_port_list": "dst_ports",
    "concept:rule_source_address_range": "src_range",
    "concept:rule_destination_address_range": "dst_range",
    "concept:rule_priority": "priority",
    "concept:rule_stateless": "stateless",
    "concept:rule_parent_set_reference": "in_set",
    "concept:rule_set_network": "set_network",
    "concept:rule_target": "target_labels",
    "concept:attachment_rule_set_reference": "attached_set",
    "concept:attachment_interface_reference": "attached_interface",
    "concept:attachment_subnet_reference": "attached_subnet",
    "concept:filter_rule_set": "RuleSet",
    "concept:filter_rule": "FilterRule",
    "concept:rule_set_attachment": "Attachment",
    "concept:rule_name": "name",
}

# propriedade neutra -> IRI no espaço único de termos do ONTPAT (naming_rules.yaml: lowerCamelCase, sem provedor)
PROPERTY_IRI = {
    "direction": "bo:ruleDirection", "effect": "bo:ruleEffect", "protocol": "bo:ruleProtocol",
    "port_from": "bo:rulePortRangeStart", "port_to": "bo:rulePortRangeEnd", "dst_ports": "bo:ruleDestinationPorts",
    "src_ports": "bo:ruleSourcePorts", "src_range": "bo:ruleSourceAddressRange",
    "dst_range": "bo:ruleDestinationAddressRange", "priority": "bo:rulePriority", "stateless": "bo:ruleStateless",
    "in_set": "bo:ruleInSet", "set_network": "bo:ruleSetNetwork", "target_labels": "bo:ruleTargetLabel",
    "attached_set": "bo:attachesRuleSet", "attached_interface": "bo:attachesInterface",
    "attached_subnet": "bo:attachesSubnet", "name": "bo:ruleName", "remote": "bo:ruleRemoteRange",
    "local": "bo:ruleLocalRange",
}

CLASS_IRI = {"rule_set": "bo:FilterRuleSet", "filter_rule": "bo:FilterRule", "attachment": "bo:RuleSetAttachment",
             "selection": "bo:RuleTargetSelection", "endpoint": "bo:NetworkEndpoint"}

# --------------------------------------------------------------------------------------------- codecs neutros

PROTO_IN = {
    "aws": {"tcp": "tcp", "udp": "udp", "icmp": "icmp", "-1": "all", "all": "all", "6": "tcp", "17": "udp", "1": "icmp"},
    "google": {"tcp": "tcp", "udp": "udp", "icmp": "icmp", "all": "all"},
    "azurerm": {"Tcp": "tcp", "Udp": "udp", "Icmp": "icmp", "*": "all", "tcp": "tcp", "udp": "udp", "icmp": "icmp"},
    "oci": {"6": "tcp", "17": "udp", "1": "icmp", "all": "all"},
}
PROTO_OUT = {"aws": {"tcp": "tcp", "udp": "udp", "icmp": "icmp", "all": "-1"},
             "google": {"tcp": "tcp", "udp": "udp", "icmp": "icmp", "all": "all"},
             "azurerm": {"tcp": "Tcp", "udp": "Udp", "icmp": "Icmp", "all": "*"},
             "oci": {"tcp": "6", "udp": "17", "icmp": "1", "all": "all"}}
PROTO_EVIDENCE = {"aws": "C03:aws_vpc_security_group_ingress_rule.ip_protocol",
                  "google": "C03:google_compute_firewall.allow.protocol",
                  "azurerm": "C03:azurerm_network_security_rule.protocol",
                  "oci": "C03:oci_core_security_list.ingress_security_rules.protocol"}

DIRECTION_OUT = {"google": {"ingress": "INGRESS", "egress": "EGRESS"},
                 "azurerm": {"ingress": "Inbound", "egress": "Outbound"},
                 "oci": {"ingress": "INGRESS", "egress": "EGRESS"}}
DIRECTION_IN = {p: {v: k for k, v in m.items()} for p, m in DIRECTION_OUT.items()}
DIRECTION_IN["aws"] = {"ingress": "ingress", "egress": "egress"}

EFFECT_OUT = {"azurerm": {"allow": "Allow", "deny": "Deny"}}
EFFECT_IN = {"azurerm": {"Allow": "allow", "Deny": "deny"}}

# Evidência das realizações estruturais (c2): o valor neutro sai da construção usada, não de um átomo.
STRUCTURAL_EVIDENCE = {
    ("aws", "aws_security_group", "ingress", "direction"): ["SE-aws-ikvsebbkuhrdk7i5", "C03:aws_security_group.ingress"],
    ("aws", "aws_security_group", "egress", "direction"): ["SE-aws-as6ufq3egpm6jfqy", "C03:aws_security_group.egress"],
    ("aws", "aws_vpc_security_group_ingress_rule", None, "direction"): ["SE-aws-ikvsebbkuhrdk7i5"],
    ("aws", "aws_vpc_security_group_egress_rule", None, "direction"): ["SE-aws-as6ufq3egpm6jfqy"],
    ("google", "google_compute_firewall", "allow", "effect"): ["SE-google-iasfqf3ocxmoevym"],
    ("google", "google_compute_firewall", "deny", "effect"): ["SE-google-xdqcqcyrrh2jrehq"],
    ("oci", "oci_core_security_list", "ingress_security_rules", "direction"): ["SE-oci-bp7mulbmn76camow"],
    ("oci", "oci_core_security_list", "egress_security_rules", "direction"): ["SE-oci-3ihxku562hxrgq4b"],
}
EFFECT_EVIDENCE = {"azurerm": ["SE-azurerm-x42gvfavlctlsm6r"], "google": ["SE-google-iasfqf3ocxmoevym",
                                                                         "SE-google-xdqcqcyrrh2jrehq"]}
PRIORITY_RANGE = {"google": (0, 65535), "azurerm": (100, 4096)}
PRIORITY_EVIDENCE = {"google": ["SE-google-n2ccqgtmt4jm72sp", "SE-google-dcmc4qigsgr3wxue"],
                     "azurerm": ["SE-azurerm-hfppj5whireqkdcl"]}

# --------------------------------------------------------------------------------------------- construções

# conjuntos de regras: tipo -> (campo de nome, campo de rede/contêiner)
RULE_SETS = {
    "aws": {"aws_security_group": {"name": "name"}},
    "google": {"google_compute_network": {"name": "name"}},
    "azurerm": {"azurerm_network_security_group": {"name": "name"}},
    "oci": {"oci_core_security_list": {"name": "display_name"},
            "oci_core_network_security_group": {"name": "display_name"}},
}

# regras embutidas: (tipo do conjunto, bloco) -> direção estrutural (ou None = campo) e campos por propriedade
INLINE_RULES = {
    "aws": {("aws_security_group", "ingress"): {"direction": "ingress",
                                                "fields": {"protocol": "protocol", "port_from": "from_port",
                                                           "port_to": "to_port", "remote": "cidr_blocks"}},
            ("aws_security_group", "egress"): {"direction": "egress",
                                               "fields": {"protocol": "protocol", "port_from": "from_port",
                                                          "port_to": "to_port", "remote": "cidr_blocks"}}},
    "azurerm": {("azurerm_network_security_group", "security_rule"): {
        "direction": None,
        "fields": {"name": "name", "priority": "priority", "direction": "direction", "effect": "access",
                   "protocol": "protocol", "dst_ports": "destination_port_range",
                   "dst_ports_multi": "destination_port_ranges", "src_ports": "source_port_range",
                   "src_ports_multi": "source_port_ranges", "src_range": "source_address_prefix",
                   "src_range_multi": "source_address_prefixes", "dst_range": "destination_address_prefix",
                   "dst_range_multi": "destination_address_prefixes"}}},
    "oci": {("oci_core_security_list", "ingress_security_rules"): {
        "direction": "ingress", "fields": {"protocol": "protocol", "remote": "source", "stateless": "stateless"}},
        ("oci_core_security_list", "egress_security_rules"): {
            "direction": "egress", "fields": {"protocol": "protocol", "remote": "destination", "stateless": "stateless"}}},
}

# regras em recurso separado: tipo -> campo do pai, direção estrutural (tipo) ou campo, campos
STANDALONE_RULES = {
    "aws": {"aws_vpc_security_group_ingress_rule": {"parent": "security_group_id", "direction": "ingress",
                                                    "fields": {"protocol": "ip_protocol", "port_from": "from_port",
                                                               "port_to": "to_port", "remote": "cidr_ipv4"}},
            "aws_vpc_security_group_egress_rule": {"parent": "security_group_id", "direction": "egress",
                                                   "fields": {"protocol": "ip_protocol", "port_from": "from_port",
                                                              "port_to": "to_port", "remote": "cidr_ipv4"}},
            "aws_security_group_rule": {"parent": "security_group_id", "direction": None,
                                        "fields": {"direction": "type", "protocol": "protocol",
                                                   "port_from": "from_port", "port_to": "to_port",
                                                   "remote": "cidr_blocks"}}},
    # parent_by: "name" = o pai é dado pelo NOME do conjunto (azurerm network_security_group_name; google network,
    # "name or self_link"); sem a chave, o pai vem por id. Valor simbólico num atributo de nome é o próprio pai.
    "google": {"google_compute_firewall": {"parent": "network", "parent_by": "name", "direction": None,
                                           "fields": {"name": "name", "direction": "direction", "priority": "priority",
                                                      "src_range": "source_ranges", "dst_range": "destination_ranges",
                                                      "target_labels": "target_tags"},
                                           "match_blocks": {"allow": "allow", "deny": "deny"}}},
    "azurerm": {"azurerm_network_security_rule": {"parent": "network_security_group_name", "parent_by": "name",
                                                  "direction": None,
                                                  "fields": INLINE_RULES["azurerm"][("azurerm_network_security_group",
                                                                                    "security_rule")]["fields"]}},
    "oci": {"oci_core_network_security_group_security_rule": {"parent": "network_security_group_id", "direction": None,
                                                              "fields": {"direction": "direction",
                                                                         "protocol": "protocol", "remote_in": "source",
                                                                         "remote_out": "destination",
                                                                         "stateless": "stateless"}}},
}

# anexações: tipo -> (campo do conjunto, campo do ponto de anexação) ou atributo-lista no ponto de anexação
ATTACH_FIELDS = {
    "aws": [("aws_instance", "vpc_security_group_ids"), ("aws_network_interface", "security_groups")],
    "azurerm": [],
    "oci": [("oci_core_subnet", "security_list_ids"), ("oci_core_instance", "create_vnic_details.nsg_ids")],
    "google": [],
}
ATTACH_RESOURCES = {
    "azurerm": {"azurerm_network_interface_security_group_association": ("network_security_group_id",
                                                                         "network_interface_id"),
                "azurerm_subnet_network_security_group_association": ("network_security_group_id", "subnet_id")},
}

# pontos de anexação (fora da fatia: contexto do caso) e como o alvo do fluxo chega até eles
ENDPOINT_TYPES = {"aws": ("aws_instance",), "google": ("google_compute_instance",),
                  "azurerm": ("azurerm_linux_virtual_machine",), "oci": ("oci_core_instance",)}


def proto_in(provider: str, raw):
    if raw is None:
        return None
    return PROTO_IN[provider].get(str(raw), PROTO_IN[provider].get(str(raw).lower()))


def proto_out(provider: str, neutral: str):
    return PROTO_OUT[provider].get(neutral)
