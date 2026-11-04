"""Decisões do mapeador PILOT-NET-MAP (fatia net), registradas como dado.

Leitura: uma REGRA de filtragem aparece em formas diferentes por provedor (recurso separado, bloco embutido no
conjunto, regra que é o próprio firewall). Cada FORMA declara como sentido e efeito são realizados:
  dir   in | out (fixo pelo tipo ou pelo bloco) | attr (atributo dir_term, valores documentados em dir_vals)
  eff   allow | deny (fixo) | attr (atributo eff_term) | struct (bloco usado: eff_present)
Uma FAIXA (slot) junta os átomos que realizam a mesma decisão. O gerador emparelha os membros de uma faixa em
cada par, com a guarda que o contexto exige (sentido e efeito); quando o lado que precisaria da guarda não
documenta o valor no pacote, o emparelhamento não sai (nunca valor inventado) e o átomo vai para ausência.

Fontes das decisões: só o pacote (tipos, enum e faixa do C01/C05; sentenças publicadas das âncoras e do C25;
notas do glossarista slice_notes, citadas onde usadas). Nenhum valor de enum fora do pacote; testes de identidade
usam um valor neutro ("exemplo") porque o pacote não traz o vocabulário de valores desses atributos de texto.
"""

from __future__ import annotations

MAPPING_DATE = "2026-11-04"

# ------------------------------------------------------------------------------------------------- formas
G_DIR = {"in": "INGRESS", "out": "EGRESS"}
Z_DIR = {"in": "Inbound", "out": "Outbound"}
Z_EFF = {"allow": "Allow", "deny": "Deny"}

SHAPES: dict[str, dict] = {
    # aws: regra separada (tipo com atributo type), regras separadas por sentido, blocos embutidos no grupo
    "a_sgr": {"prov": "aws", "rtype": "aws_security_group_rule", "prefix": "", "dir": "attr", "dir_term": "type",
              "dir_vals": {"in": "ingress"}, "eff": "allow"},
    "a_vin": {"prov": "aws", "rtype": "aws_vpc_security_group_ingress_rule", "prefix": "", "dir": "in", "eff": "allow"},
    "a_veg": {"prov": "aws", "rtype": "aws_vpc_security_group_egress_rule", "prefix": "", "dir": "out", "eff": "allow"},
    "a_sgi": {"prov": "aws", "rtype": "aws_security_group", "prefix": "ingress.", "dir": "in", "eff": "allow",
              "block": True},
    "a_sge": {"prov": "aws", "rtype": "aws_security_group", "prefix": "egress.", "dir": "out", "eff": "allow",
              "block": True},
    "a_set": {"prov": "aws", "rtype": "aws_security_group", "prefix": "", "dir": None, "eff": None},
    "a_att": {"prov": "aws", "rtype": "aws_network_interface_sg_attachment", "prefix": "", "dir": None, "eff": None},
    # google: o firewall é a própria regra; efeito pelo bloco allow{} ou deny{}
    "g_fw": {"prov": "google", "rtype": "google_compute_firewall", "prefix": "", "dir": "attr",
             "dir_term": "direction", "dir_vals": G_DIR, "eff": "struct", "eff_present": {"allow": "allow", "deny": "deny"}},
    "g_allow": {"prov": "google", "rtype": "google_compute_firewall", "prefix": "allow.", "dir": "attr",
                "dir_term": "direction", "dir_vals": G_DIR, "eff": "allow", "block": True},
    "g_deny": {"prov": "google", "rtype": "google_compute_firewall", "prefix": "deny.", "dir": "attr",
               "dir_term": "direction", "dir_vals": G_DIR, "eff": "deny", "block": True},
    # azurerm: regra separada e bloco security_rule embutido; sentido e efeito por atributo
    "z_rule": {"prov": "azurerm", "rtype": "azurerm_network_security_rule", "prefix": "", "dir": "attr",
               "dir_term": "direction", "dir_vals": Z_DIR, "eff": "attr", "eff_term": "access", "eff_vals": Z_EFF},
    # no bloco embutido o pacote não tipa os campos: a guarda usa o caminho do bloco, sem valor documentado
    "z_emb": {"prov": "azurerm", "rtype": "azurerm_network_security_group", "prefix": "security_rule.",
              "dir": "attr", "dir_term": "security_rule.direction", "dir_vals": None, "eff": "attr",
              "eff_term": "security_rule.access", "eff_vals": None, "block": True},
    "z_set": {"prov": "azurerm", "rtype": "azurerm_network_security_group", "prefix": "", "dir": None, "eff": None},
    "z_nic": {"prov": "azurerm", "rtype": "azurerm_network_interface_security_group_association", "prefix": "",
              "dir": None, "eff": None},
    "z_sub": {"prov": "azurerm", "rtype": "azurerm_subnet_network_security_group_association", "prefix": "",
              "dir": None, "eff": None},
    # oci: regra de NSG separada (sentido em texto sem valores no pacote) e blocos da security list
    "o_nsg": {"prov": "oci", "rtype": "oci_core_network_security_group_security_rule", "prefix": "", "dir": "attr",
              "dir_term": "direction", "dir_vals": None, "eff": "allow"},
    "o_sli": {"prov": "oci", "rtype": "oci_core_security_list", "prefix": "ingress_security_rules.", "dir": "in",
              "eff": "allow", "block": True},
    "o_sle": {"prov": "oci", "rtype": "oci_core_security_list", "prefix": "egress_security_rules.", "dir": "out",
              "eff": "allow", "block": True},
    "o_nset": {"prov": "oci", "rtype": "oci_core_network_security_group", "prefix": "", "dir": None, "eff": None},
    "o_sl": {"prov": "oci", "rtype": "oci_core_security_list", "prefix": "", "dir": None, "eff": None},
}
# efeito fixo (allow) em aws e oci: notas do glossarista SN-NET-0001 (aws: regras só permitem) e SN-NET-0002
# (oci: CQFIX, sem negação). O C25 diz effect unknown nesses tipos: por isso nenhuma alegação de efeito fixo
# (fixed_default) chega a DOC_SUPPORTED; o efeito fixo só restringe emparelhamentos (aws/oci × deny não sai).
EFFECT_NOTES = {"aws": "SN-NET-0001", "oci": "SN-NET-0002"}

# --------------------------------------------------------------------------------------------- faixas
# membro = (forma, caminho dentro da forma[, sentido fixado pelo próprio membro])
# política: value (escalar ou lista), ref (referência), priority, address, direction, related
SLOTS: list[dict] = [
    {"slot": "protocol", "policy": "value", "members": [
        ("a_sgr", "protocol"), ("a_vin", "ip_protocol"), ("a_veg", "ip_protocol"), ("a_sgi", "protocol"),
        ("a_sge", "protocol"), ("g_allow", "protocol"), ("g_deny", "protocol"), ("z_rule", "protocol"),
        ("z_emb", "protocol"), ("o_nsg", "protocol"), ("o_sli", "protocol"), ("o_sle", "protocol")]},
    {"slot": "rule_description", "policy": "value", "members": [
        ("a_sgr", "description"), ("a_vin", "description"), ("a_veg", "description"), ("a_sgi", "description"),
        ("a_sge", "description"), ("g_fw", "description"), ("z_rule", "description"), ("z_emb", "description"),
        ("o_nsg", "description"), ("o_sli", "description"), ("o_sle", "description")]},
    {"slot": "rule_name", "policy": "value", "members": [
        ("g_fw", "name"), ("z_rule", "name"), ("z_emb", "name")]},
    {"slot": "priority", "policy": "priority", "members": [
        ("g_fw", "priority"), ("z_rule", "priority"), ("z_emb", "priority")]},
    {"slot": "direction", "policy": "direction", "members": [
        ("a_sgr", "type"), ("g_fw", "direction"), ("z_rule", "direction"), ("z_emb", "direction"),
        ("o_nsg", "direction")]},
    {"slot": "dst_port_from", "policy": "value", "members": [
        ("a_sgr", "from_port"), ("a_vin", "from_port"), ("a_veg", "from_port"), ("a_sgi", "from_port"),
        ("a_sge", "from_port"), ("o_nsg", "tcp_options.destination_port_range.min"),
        ("o_nsg", "udp_options.destination_port_range.min"), ("o_sli", "tcp_options.min"), ("o_sli", "udp_options.min"),
        ("o_sle", "tcp_options.min"), ("o_sle", "udp_options.min")]},
    {"slot": "dst_port_to", "policy": "value", "members": [
        ("a_sgr", "to_port"), ("a_vin", "to_port"), ("a_veg", "to_port"), ("a_sgi", "to_port"),
        ("a_sge", "to_port"), ("o_nsg", "tcp_options.destination_port_range.max"),
        ("o_nsg", "udp_options.destination_port_range.max"), ("o_sli", "tcp_options.max"), ("o_sli", "udp_options.max"),
        ("o_sle", "tcp_options.max"), ("o_sle", "udp_options.max")]},
    {"slot": "dst_port_text", "policy": "value", "members": [
        ("g_allow", "ports"), ("g_deny", "ports"), ("z_rule", "destination_port_range"),
        ("z_rule", "destination_port_ranges"), ("z_emb", "destination_port_range"), ("z_emb", "destination_port_ranges")]},
    {"slot": "src_port_text", "policy": "value", "members": [
        ("z_rule", "source_port_range"), ("z_rule", "source_port_ranges"), ("z_emb", "source_port_range"),
        ("z_emb", "source_port_ranges")]},
    {"slot": "src_addr", "policy": "address", "members": [
        ("a_sgr", "cidr_blocks", "in"), ("a_sgr", "ipv6_cidr_blocks", "in"), ("a_vin", "cidr_ipv4"),
        ("a_vin", "cidr_ipv6"), ("a_sgi", "cidr_blocks"), ("a_sgi", "ipv6_cidr_blocks"), ("g_fw", "source_ranges", "in"),
        ("z_rule", "source_address_prefix"), ("z_rule", "source_address_prefixes"), ("z_emb", "source_address_prefix"),
        ("z_emb", "source_address_prefixes"), ("o_nsg", "source"), ("o_sli", "source")]},
    {"slot": "dst_addr", "policy": "address", "members": [
        ("a_veg", "cidr_ipv4"), ("a_veg", "cidr_ipv6"), ("a_sge", "cidr_blocks"), ("a_sge", "ipv6_cidr_blocks"),
        ("g_fw", "destination_ranges"), ("z_rule", "destination_address_prefix"),
        ("z_rule", "destination_address_prefixes"), ("z_emb", "destination_address_prefix"),
        ("z_emb", "destination_address_prefixes"), ("o_nsg", "destination"), ("o_sle", "destination")]},
    {"slot": "stateless", "policy": "value", "members": [
        ("o_nsg", "stateless"), ("o_sli", "stateless"), ("o_sle", "stateless")]},
    # seletores de par por grupo, etiqueta ou identidade: mecanismos diferentes -> related (não transporta)
    {"slot": "peer_selector_src", "policy": "related", "members": [
        ("a_sgr", "source_security_group_id", "in"), ("a_vin", "referenced_security_group_id"),
        ("a_sgi", "security_groups"), ("g_fw", "source_tags", "in"), ("g_fw", "source_service_accounts", "in"),
        ("z_rule", "source_application_security_group_ids"), ("z_emb", "source_application_security_group_ids")]},
    {"slot": "peer_selector_dst", "policy": "related", "members": [
        ("a_veg", "referenced_security_group_id"), ("a_sge", "security_groups"),
        ("z_rule", "destination_application_security_group_ids"),
        ("z_emb", "destination_application_security_group_ids")]},
    {"slot": "target_selector", "policy": "related", "members": [
        ("g_fw", "target_tags"), ("g_fw", "target_service_accounts"),
        ("z_rule", "destination_application_security_group_ids", "in")]},
    # conjunto de regras
    {"slot": "set_name", "policy": "value", "members": [
        ("a_set", "name"), ("z_set", "name"), ("o_nset", "display_name"), ("o_sl", "display_name")]},
    {"slot": "set_tags", "policy": "value", "members": [
        ("a_set", "tags"), ("z_set", "tags"), ("o_nset", "freeform_tags"), ("o_sl", "freeform_tags")]},
    {"slot": "set_network", "policy": "ref", "members": [
        ("a_set", "vpc_id"), ("g_fw", "network"), ("o_nset", "vcn_id"), ("o_sl", "vcn_id")]},
    {"slot": "rule_parent_set", "policy": "ref", "members": [
        ("a_sgr", "security_group_id"), ("a_vin", "security_group_id"), ("a_veg", "security_group_id"),
        ("z_rule", "network_security_group_name"), ("o_nsg", "network_security_group_id")]},
    {"slot": "attach_set", "policy": "ref", "members": [
        ("a_att", "security_group_id"), ("z_nic", "network_security_group_id"), ("z_sub", "network_security_group_id")]},
    {"slot": "attach_nic", "policy": "ref", "members": [
        ("a_att", "network_interface_id"), ("z_nic", "network_interface_id")]},
]

# grupos (regra sobre subgrafo): início e fim numéricos <-> faixa em texto, pelo combinador do registro
PORT_PAIRS = [  # (forma, campo início, campo fim)
    ("a_sgr", "from_port", "to_port"), ("a_vin", "from_port", "to_port"), ("a_veg", "from_port", "to_port"),
    ("a_sgi", "from_port", "to_port"), ("a_sge", "from_port", "to_port"),
    ("o_nsg", "tcp_options.destination_port_range.min", "tcp_options.destination_port_range.max"),
    ("o_nsg", "udp_options.destination_port_range.min", "udp_options.destination_port_range.max"),
    ("o_sli", "tcp_options.min", "tcp_options.max"), ("o_sli", "udp_options.min", "udp_options.max"),
    ("o_sle", "tcp_options.min", "tcp_options.max"), ("o_sle", "udp_options.min", "udp_options.max"),
]
SRC_PORT_PAIRS = [
    ("o_nsg", "tcp_options.source_port_range.min", "tcp_options.source_port_range.max"),
    ("o_nsg", "udp_options.source_port_range.min", "udp_options.source_port_range.max"),
    ("o_sli", "tcp_options.source_port_range.min", "tcp_options.source_port_range.max"),
    ("o_sli", "udp_options.source_port_range.min", "udp_options.source_port_range.max"),
    ("o_sle", "tcp_options.source_port_range.min", "tcp_options.source_port_range.max"),
    ("o_sle", "udp_options.source_port_range.min", "udp_options.source_port_range.max"),
]
PORT_TEXT = {"dst": [("z_rule", "destination_port_range"), ("z_emb", "destination_port_range"),
                     ("g_allow", "ports"), ("g_deny", "ports"), ("z_rule", "destination_port_ranges"),
                     ("z_emb", "destination_port_ranges")],
             "src": [("z_rule", "source_port_range"), ("z_emb", "source_port_range"),
                     ("z_rule", "source_port_ranges"), ("z_emb", "source_port_ranges")]}

# efeito por atributo (azurerm access) contra efeito fixo (oci: sem negação, SN-NET-0002): narrowMatch com valor
# fixo no destino e predicado de pertença finito. Só no AZOCI (orientação azurerm -> oci); nos pares em que o lado
# com efeito fixo é o sujeito, o fixed_default não se exprime na orientação canônica (vai como ausência anotada).
FIXED_EFFECT = [("z_rule", "access", "o_nsg"), ("z_rule", "access", "o_sli"), ("z_rule", "access", "o_sle")]

# átomos que o pacote declara mas que nenhuma correspondência que transporta alcança: tipo de ausência e porquê.
# Regra = (provedor do átomo | '*', padrão do átomo, provedor do outro lado | '*', tipo, motivo). Padrão:
# '<tipo>:<caminho>' exato, ou '*:<caminho>' (qualquer tipo; caminho terminado em '.' casa o prefixo). A primeira
# regra que casa vale. Sem regra: identificador, carimbo e saída calculada -> UNSUPPORTED_BY_TRANSLATOR quando o
# outro lado tem átomo do mesmo papel; o resto -> ABSENCE_DEMONSTRATED (procurado nos átomos canônicos do outro
# lado e nos vizinhos por referência).
ABSENCE_RULES: list[tuple[str, str, str, str, str]] = [
    ("azurerm", "azurerm_network_security_rule:access", "google", "UNSUPPORTED_BY_TRANSLATOR",
     "o efeito no firewall do outro lado é o bloco usado (allow{} ou deny{}); o registro não tem função que escolha bloco"),
    ("azurerm", "azurerm_network_security_rule:access", "aws", "UNRESOLVED",
     "o outro lado só tem regras que permitem (nota SN-NET-0001), sem atributo; o fixed_default não se exprime com o "
     "lado sem atributo como sujeito, e o C25 marca o efeito do tipo como unknown"),
    ("azurerm", "azurerm_network_security_group:security_rule.access", "*", "UNRESOLVED",
     "campo do bloco embutido sem tipo no pacote; o efeito do outro lado é bloco ou fixo"),
    ("oci", "oci_core_network_security_group_security_rule:direction", "*", "UNRESOLVED",
     "o pacote não documenta os valores do sentido da regra NSG (texto livre): tradução e guarda por sentido não se "
     "escrevem sem inventar valor"),
    ("aws", "aws_security_group:revoke_rules_on_delete", "*", "ABSENCE_DEMONSTRATED",
     "comportamento de remoção do provider aws sem atributo correspondente nos tipos do outro lado"),
    ("aws", "aws_security_group:name_prefix", "*", "UNSUPPORTED_BY_TRANSLATOR",
     "prefixo gerador de nome: o registro não tem função que gere nome a partir de prefixo"),
    ("aws", "*:region", "*", "UNSUPPORTED_BY_TRANSLATOR",
     "região: vocabulários de região distintos entre provedores e nenhuma função de tradução no registro"),
    ("azurerm", "azurerm_network_security_group:location", "*", "UNSUPPORTED_BY_TRANSLATOR",
     "local (região): vocabulários distintos, sem função de tradução no registro"),
    ("azurerm", "*:resource_group_name", "*", "UNSUPPORTED_BY_TRANSLATOR",
     "contêiner de recursos (grupo de recursos); o análogo do outro lado (projeto, compartimento) não se traduz por valor"),
    ("oci", "*:compartment_id", "*", "UNSUPPORTED_BY_TRANSLATOR",
     "compartimento: contêiner de recursos sem tradução por valor para o contêiner do outro lado"),
    ("google", "google_compute_firewall:project", "*", "UNSUPPORTED_BY_TRANSLATOR",
     "projeto: contêiner de recursos sem tradução por valor"),
    ("aws", "aws_security_group:owner_id", "*", "ABSENCE_DEMONSTRATED",
     "conta dona, atribuída pela API, sem atributo correspondente"),
    ("google", "google_compute_firewall:deletion_policy", "*", "ABSENCE_DEMONSTRATED",
     "política de remoção da camada Terraform do provider google (CC-NET-3c), sem análogo nos tipos do outro lado"),
    ("google", "google_compute_firewall:disabled", "*", "ABSENCE_DEMONSTRATED",
     "desligar a regra sem removê-la: nenhum átomo do outro lado"),
    ("google", "google_compute_firewall:enable_logging", "*", "ABSENCE_DEMONSTRATED",
     "registro de fluxo por regra: nenhum átomo do outro lado na fatia"),
    ("google", "google_compute_firewall:log_config.metadata", "*", "ABSENCE_DEMONSTRATED",
     "metadados do registro de fluxo: nenhum átomo do outro lado na fatia"),
    ("google", "google_compute_firewall:params.resource_manager_tags", "*", "ABSENCE_DEMONSTRATED",
     "etiquetas do resource manager presas ao firewall: o outro lado não tem esse mecanismo na fatia"),
    ("oci", "*:defined_tags", "*", "ABSENCE_DEMONSTRATED",
     "etiquetas com espaço de nomes definido: o outro lado só tem mapa livre de etiquetas"),
    ("oci", "*:icmp_options.", "*", "UNRESOLVED",
     "tipo e código ICMP: no aws vêm sobrecarregados em from_port/to_port conforme o protocolo, cujos valores o pacote "
     "não documenta; nos outros lados não há átomo"),
    ("oci", "*:source_type", "*", "UNRESOLVED",
     "discriminador do tipo de origem (CIDR ou serviço): o outro lado não tem discriminador; valores sem tradução"),
    ("oci", "*:destination_type", "*", "UNRESOLVED",
     "discriminador do tipo de destino (CIDR ou serviço): o outro lado não tem discriminador; valores sem tradução"),
    ("oci", "*:stateless", "*", "ABSENCE_DEMONSTRATED",
     "o outro lado não tem regra sem estado; o C25 marca o estado da conexão do outro lado como unknown, por isso nem o "
     "comportamento fixo se alega"),
    ("aws", "*:self", "*", "ABSENCE_DEMONSTRATED",
     "o próprio grupo como par: o outro lado não tem átomo equivalente na fatia"),
    ("aws", "*:prefix_list_id", "*", "ABSENCE_DEMONSTRATED",
     "lista de prefixos gerenciada como par: o outro lado não tem átomo na fatia"),
    ("aws", "*:prefix_list_ids", "*", "ABSENCE_DEMONSTRATED",
     "lista de prefixos gerenciada como par: o outro lado não tem átomo na fatia"),
    ("aws", "*:tags_all", "*", "UNSUPPORTED_BY_TRANSLATOR",
     "mapa calculado (etiquetas do recurso mais as padrão do provider): saída, não configuração"),
]
IDENTITY_ROLES = ("IDENTIFIER", "TIMESTAMP")
COMPUTED_PATHS = ("state", "is_valid", "arn", "self_link", "firewall_id", "security_group_rule_id",
                  "creation_timestamp", "time_created", "id")
