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
       "condição sobre fluxos de rede (sentido, protocolo, portas e endereço do par) ligada a um efeito, que "
       "decide se o fluxo que casa com ela passa"),
    _c("concept:rule_target", "alvo da regra",
       "seletor declarado na própria regra que restringe a quais membros da rede (por etiqueta, identidade de "
       "serviço ou grupo de aplicação) a regra se aplica, independentemente de onde o conjunto está anexado"),
    _c("concept:rule_set_attachment", "anexação do conjunto de regras",
       "vínculo entre um conjunto de regras de filtragem e um recurso de rede (interface ou sub-rede) que faz o "
       "tráfego desse recurso passar pela avaliação do conjunto"),
    _c("concept:rule_set_network", "rede do conjunto de regras",
       "referência de um conjunto de regras de filtragem à rede virtual que o contém e fora da qual ele não "
       "pode ser anexado"),
    _c("concept:rule_stateless", "regra sem estado",
       "indicador booleano de uma regra de filtragem que, verdadeiro, faz a regra valer só no sentido declarado "
       "sem rastrear a conexão, de modo que o tráfego de resposta precisa de regra própria no sentido oposto"),
    _c("concept:rule_priority", "prioridade da regra",
       "número ordinal de uma regra de filtragem que decide qual regra prevalece quando mais de uma casa o mesmo "
       "fluxo, prevalecendo o menor número"),
    _c("concept:rule_effect", "efeito da regra",
       "decisão, permitir ou negar, que uma regra de filtragem aplica ao fluxo que casa com ela"),
    _c("concept:rule_direction", "sentido da regra",
       "sentido do fluxo, entrada ou saída em relação ao recurso protegido, a que uma regra de filtragem se "
       "aplica"),
    _c("concept:rule_protocol", "protocolo da regra",
       "protocolo de rede ou de transporte (por exemplo TCP, UDP, ICMP ou todos) que um fluxo precisa usar "
       "para casar com a regra de filtragem"),
    _c("concept:rule_destination_port_range", "faixa de portas de destino da regra",
       "intervalo de portas de destino da camada de transporte que um fluxo precisa usar para casar com a regra "
       "de filtragem"),
    _c("concept:rule_peer_address_prefix", "prefixo de endereço do par da regra",
       "bloco de endereços IP em notação CIDR do lado remoto do fluxo (origem na entrada, destino na saída) que "
       "um fluxo precisa ter para casar com a regra de filtragem"),
]

# Âncoras: átomo → conceito, cada uma citando um fato do SERVICE-EVIDENCE (evidence_id) cuja sentença de
# documentação é do PRÓPRIO átomo. counterexample: regex procurada nas sentenças do SERVICE-EVIDENCE do mesmo
# provedor (a contagem sai do build) e o julgamento do glossarista sobre o que achou.
ANCHORS = [
    {"claim_id": "ANC-google-0001", "atom_id": "google:google_compute_firewall:priority",
     "concept_id": "concept:rule_priority", "evidence_id": "SE-google-n2ccqgtmt4jm72sp",
     "context": "argumento priority do tipo de firewall; fato precedence (order_attribute) do SERVICE-EVIDENCE",
     "query": r"\bpriority\b", "found": False,
     "note": ("nos tipos de política de firewall e de segurança o termo tem o mesmo sentido de ordem de avaliação; "
              "nenhum uso com outro significado; diferença registrada: no empate de prioridade a regra de negação "
              "prevalece (avaliação do conjunto, não significado do atributo)")},
    {"claim_id": "ANC-azurerm-0001", "atom_id": "azurerm:azurerm_network_security_rule:priority",
     "concept_id": "concept:rule_priority", "evidence_id": "SE-azurerm-hfppj5whireqkdcl",
     "context": "argumento priority do tipo de regra separada; fato precedence (order_attribute) do SERVICE-EVIDENCE",
     "query": r"\bpriority\b", "found": False,
     "note": ("em tipos de aplicação web e de política o termo é ordem de avaliação de restrição; nenhum uso com "
              "outro significado; diferença registrada: aqui o número é único no conjunto (sem empate)")},
    {"claim_id": "ANC-azurerm-0002", "atom_id": "azurerm:azurerm_network_security_rule:access",
     "concept_id": "concept:rule_effect", "evidence_id": "SE-azurerm-x42gvfavlctlsm6r",
     "context": "argumento access do tipo de regra separada; fato effect (effect_attribute) do SERVICE-EVIDENCE",
     "query": r"Allow`? (and|or) `?Deny", "found": False,
     "note": "os mesmos valores aparecem em restrições de acesso de aplicação web, com o mesmo sentido de efeito"},
    {"claim_id": "ANC-oci-0001", "atom_id": "oci:oci_core_security_list:ingress_security_rules.stateless",
     "concept_id": "concept:rule_stateless", "evidence_id": "SE-oci-bp7mulbmn76camow",
     "context": "argumento stateless do bloco de regras de entrada; fato connection_state do SERVICE-EVIDENCE",
     "query": r"\bstateless\b", "found": False,
     "note": "o termo só aparece nas regras de filtragem do provedor, sempre com o sentido de regra sem estado"},
    {"claim_id": "ANC-oci-0002", "atom_id": "oci:oci_core_security_list:egress_security_rules.stateless",
     "concept_id": "concept:rule_stateless", "evidence_id": "SE-oci-3ihxku562hxrgq4b",
     "context": "argumento stateless do bloco de regras de saída; fato connection_state do SERVICE-EVIDENCE",
     "query": r"\bstateless\b", "found": False,
     "note": "o termo só aparece nas regras de filtragem do provedor, sempre com o sentido de regra sem estado"},
    {"claim_id": "ANC-oci-0003", "atom_id": "oci:oci_core_network_security_group_security_rule:stateless",
     "concept_id": "concept:rule_stateless", "evidence_id": "SE-oci-cxwuvxzhyrwz3j6f",
     "context": "argumento stateless do tipo de regra separada; fato connection_state interpretado do SERVICE-EVIDENCE",
     "query": r"\bstateless\b", "found": False,
     "note": "o termo só aparece nas regras de filtragem do provedor, sempre com o sentido de regra sem estado"},
    {"claim_id": "ANC-oci-0004", "atom_id": "oci:oci_core_security_list:vcn_id",
     "concept_id": "concept:rule_set_network", "evidence_id": "SE-oci-pshq6e42psyl6dzo",
     "context": "argumento vcn_id do tipo de conjunto de regras; fato owner (parent_attribute) do SERVICE-EVIDENCE",
     "query": r"of the VCN the .* belongs to", "found": False,
     "note": ("a mesma frase serve a outros objetos da rede (tabela de rotas, gateways, opções de DHCP), sempre como "
              "rede que contém o objeto; nenhum uso com outro significado")},
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


# evidência das decisões: {source, sentence, date}; source = evidence_id do SERVICE-EVIDENCE (a sentença é a do fato)
DECISION_SPECS = [
    (1, "value_type", "concept:rule_priority", None, {"datatype": "integer",
                                                       "enum_semantics": "ordinal: menor número prevalece"},
     "tipo de valor da prioridade: inteiro ordinal, o menor prevalece; a faixa admitida é do átomo, não do conceito",
     ["SE-google-n2ccqgtmt4jm72sp", "SE-azurerm-hfppj5whireqkdcl"]),
    (2, "value_type", "concept:rule_effect", None, {"datatype": "enum",
                                                     "enum_semantics": "nominal: permitir | negar"},
     "tipo de valor do efeito: enum nominal de dois valores", ["SE-azurerm-x42gvfavlctlsm6r"]),
    (3, "value_type", "concept:rule_stateless", None, {"datatype": "boolean",
                                                        "enum_semantics": "verdadeiro = sem estado (a resposta precisa de regra própria); falso = com estado"},
     "tipo de valor do estado de conexão por regra: booleano com polaridade sem estado = verdadeiro",
     ["SE-oci-bp7mulbmn76camow", "SE-oci-3ihxku562hxrgq4b"]),
    (4, "exclusive", "concept:rule_stateless", None, None,
     ("estado de conexão declarável por regra só existe num provedor da fatia; nos outros três o fato "
      "connection_state do SERVICE-EVIDENCE é unknown (não documentado) e a constatação do CQFIX citada no brief "
      "de lançamento é que o estado não é declarável por regra; não se força âncora nos outros três"),
     ["SE-oci-cxwuvxzhyrwz3j6f"]),
    (5, "same_kind_distinct", "concept:rule_target", "concept:rule_set_attachment", None,
     ("alvo e anexação decidem a quem as regras se aplicam, mas são distintos: o alvo é um seletor dentro da "
      "regra; a anexação é um vínculo do conjunto inteiro com um recurso de rede (achado F1)"), []),
    (6, "same_kind_distinct", "concept:rule_set_network", "concept:rule_set_attachment", None,
     ("pertencer a uma rede virtual não é estar anexado: a rede do conjunto limita onde ele pode ser anexado, a "
      "anexação é que faz o tráfego passar por ele"), ["SE-oci-pshq6e42psyl6dzo"]),
    (7, "same_kind_distinct", "concept:rule_priority", "concept:rule_effect", None,
     ("precedência e efeito são eixos separados (achado F1): a prioridade escolhe a regra que vale; o efeito diz "
      "o que a regra escolhida faz; no empate de prioridade a negação prevalecer é regra de avaliação do conjunto"),
     ["SE-google-t45d32hahm5ikdc3"]),
    (8, "same_kind_distinct", "concept:filter_rule_set", "concept:filter_rule", None,
     ("conjunto de regras e regra são unidades distintas: a regra é avaliada dentro de um conjunto; a mesma regra "
      "aparece embutida no conjunto ou como recurso separado, e isso é embalagem, não outro conceito"), []),
    (9, "value_type", "concept:rule_set_network", None, {"datatype": "string",
                                                           "enum_semantics": "referência opaca: identificador da rede que contém o conjunto"},
     "tipo de valor da rede do conjunto: referência por identificador, sem grandeza", ["SE-oci-pshq6e42psyl6dzo"]),
    (10, "value_type", "concept:rule_direction", None, {"datatype": "enum",
                                                        "enum_semantics": "nominal: entrada | saída"},
     "tipo de valor do sentido: enum nominal; em alguns provedores o sentido vem do bloco ou do tipo, não de um atributo",
     []),
]

# fatos tipados da fatia, para o pacote do mapeador (ausência e onde o conceito mora por estrutura): só leitura do
# SERVICE-EVIDENCE e do brief de lançamento; nada aqui é correspondência
SLICE_NOTES = [
    {"concept_id": "concept:rule_effect", "provider": "google",
     "note": "o efeito vem do bloco usado (allow ou deny), não de um atributo; não há átomo a ancorar",
     "evidence": ["SE-google-iasfqf3ocxmoevym", "SE-google-xdqcqcyrrh2jrehq"]},
    {"concept_id": "concept:rule_effect", "provider": "aws",
     "note": "regras só permitem; o fato effect do tipo de conjunto descreve a regra padrão de saída que o provedor cria",
     "evidence": ["SE-aws-jcsq5zrpnuvxzaxv"]},
    {"concept_id": "concept:rule_effect", "provider": "oci",
     "note": "fato effect unknown (não documentado) no SERVICE-EVIDENCE; o brief de lançamento registra a constatação do CQFIX: sem negação com precedência",
     "evidence": [{"provider": "oci", "fact_kind": "effect", "status": "unknown"}]},
    {"concept_id": "concept:rule_priority", "provider": "aws",
     "note": "fato precedence unknown (não documentado) no SERVICE-EVIDENCE; regras só permitem e não há atributo de prioridade",
     "evidence": [{"provider": "aws", "fact_kind": "precedence", "status": "unknown"}]},
    {"concept_id": "concept:rule_priority", "provider": "oci",
     "note": "fato precedence unknown no SERVICE-EVIDENCE; CQFIX (via brief): sem negação, logo sem precedência entre efeitos",
     "evidence": [{"provider": "oci", "fact_kind": "precedence", "status": "unknown"}]},
    {"concept_id": "concept:rule_stateless", "provider": "aws,google,azurerm",
     "note": "fato connection_state unknown no SERVICE-EVIDENCE; CQFIX (via brief): estado de conexão não declarável por regra",
     "evidence": [{"provider": "aws", "fact_kind": "connection_state", "status": "unknown"},
                  {"provider": "google", "fact_kind": "connection_state", "status": "unknown"},
                  {"provider": "azurerm", "fact_kind": "connection_state", "status": "unknown"}]},
    {"concept_id": "concept:rule_priority", "provider": "azurerm",
     "note": "regras embutidas no conjunto são um atributo de lista de objetos: o schema não expõe átomos por campo da regra embutida",
     "evidence": []},
]
