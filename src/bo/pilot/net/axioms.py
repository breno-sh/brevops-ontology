"""Catálogo de axiomas da fatia NET (o que separa c3_full de c2_taxonomy), cada um com evidência e nível.

Regra de entrada: só entram no TBox do c3 axiomas cujo nível é published ou derived (SERVICE-EVIDENCE C25, docs C03,
compromissos C24); 'derived' aqui é derivação deste módulo a partir de linhas publicadas, com a base escrita. Nível
interpreted fica FORA (listado em EXCLUDED, com o motivo): o c3 não o usa. Nada aqui lê o oráculo.

Forma: cada axioma é TTL (OWL 2 DL) sobre o vocabulário neutro bo: e diz que consequência nomeada produz
(entails), para o traço C23 citar justifying_axioms. As realizações (que construção tem que tipo) são do c2;
os axiomas abaixo são restrições, valores e formas, e só o c3 os carrega.
"""

from __future__ import annotations

# classes de realização: a construção do provedor é instância delas (c2 já sabe disso; é taxonomia)
REALIZATION_CLASSES = {
    "aws_security_group": ["bo:FilterRuleSet", "bo:PermissionListRuleSet", "bo:NoMatchDenyRuleSet"],
    "oci_core_security_list": ["bo:FilterRuleSet", "bo:PermissionListRuleSet"],
    "oci_core_network_security_group": ["bo:FilterRuleSet", "bo:PermissionListRuleSet"],
    "google_compute_network": ["bo:FilterRuleSet", "bo:PrecedenceRuleSet", "bo:DenyTieRuleSet"],
    "azurerm_network_security_group": ["bo:FilterRuleSet", "bo:PrecedenceRuleSet", "bo:UniquePriorityRuleSet"],
}
RULE_REALIZATION_CLASSES = {
    ("aws_security_group", "ingress"): ["bo:FilterRule"],
    ("aws_security_group", "egress"): ["bo:FilterRule"],
    "aws_vpc_security_group_ingress_rule": ["bo:FilterRule"],
    "aws_vpc_security_group_egress_rule": ["bo:FilterRule"],
    "aws_security_group_rule": ["bo:FilterRule"],
    "google_compute_firewall": ["bo:FilterRule"],
    ("azurerm_network_security_group", "security_rule"): ["bo:FilterRule"],
    "azurerm_network_security_rule": ["bo:FilterRule"],
    ("oci_core_security_list", "ingress_security_rules"): ["bo:FilterRule", "bo:DeclaredDefaultStateRule"],
    ("oci_core_security_list", "egress_security_rules"): ["bo:FilterRule", "bo:DeclaredDefaultStateRule"],
    "oci_core_network_security_group_security_rule": ["bo:FilterRule"],
}

# taxonomia (c2 e c3): só rdfs:subClassOf entre classes nomeadas e disjunções não entram aqui
TAXONOMY = [
    ("bo:PermissionListRuleSet", "bo:FilterRuleSet"),
    ("bo:PrecedenceRuleSet", "bo:FilterRuleSet"),
    ("bo:DenyTieRuleSet", "bo:PrecedenceRuleSet"),
    ("bo:UniquePriorityRuleSet", "bo:PrecedenceRuleSet"),
    ("bo:IngressRule", "bo:FilterRule"),
    ("bo:EgressRule", "bo:FilterRule"),
    ("bo:AllowingRule", "bo:FilterRule"),
    ("bo:DenyingRule", "bo:FilterRule"),
    ("bo:DeclaredDefaultStateRule", "bo:FilterRule"),
    ("bo:NoMatchDenyRuleSet", "bo:FilterRuleSet"),
]

P = "bo:"
AXIOMS = [
    {
        "axiom_id": "AX-NET-01",
        "text": "conjunto lista-de-permissão: toda regra dele permite (efeito = permitir)",
        "ttl": "bo:PermissionListRuleSet rdfs:subClassOf [ a owl:Restriction ; owl:onProperty bo:hasRule ; "
               "owl:allValuesFrom [ a owl:Restriction ; owl:onProperty bo:hasEffect ; owl:hasValue bo:Allow ] ] .",
        "entails": ["effect"],
        "level": "derived",
        "evidence": ["SE-aws-jcsq5zrpnuvxzaxv", "SE-oci-bp7mulbmn76camow", "C24:REQ-NET-01",
                     "C01:sem-atomo-de-efeito"],
        "basis": "o schema fixado (C01) não tem átomo de efeito nesses tipos de regra; a frase publicada da AWS diz "
                 "que sem regra o tráfego é bloqueado e a da OCI que a regra 'allows traffic'; num conjunto em que "
                 "a regra só pode permitir, o efeito de toda regra é permitir (definição de lista de permissão, "
                 "REQ-NET-01)",
    },
    {
        "axiom_id": "AX-NET-02",
        "text": "lista-de-permissão é independente de ordem: a decisão é a união do que as regras permitem",
        "ttl": "bo:PermissionListRuleSet rdfs:subClassOf [ a owl:Restriction ; owl:onProperty bo:hasPrecedenceOrder ; "
               "owl:hasValue bo:OrderIndependent ] .",
        "entails": ["precedence"],
        "level": "derived",
        "evidence": ["C24:REQ-NET-01", "AX-NET-01"],
        "basis": "com todas as regras permitindo, nenhuma pode anular outra: a ordem não muda a decisão",
    },
    {
        "axiom_id": "AX-NET-03",
        "text": "grupo de segurança sem regra que case nega",
        "ttl": "bo:NoMatchDenyRuleSet rdfs:subClassOf [ a owl:Restriction ; owl:onProperty bo:hasNoMatchDecision ; "
               "owl:hasValue bo:Deny ] .",
        "entails": ["no_match"],
        "level": "published",
        "evidence": ["SE-aws-jcsq5zrpnuvxzaxv"],
        "basis": "'If nothing is specified, traffic will be blocked'; e o Terraform remove a regra padrão de saída",
        "applies_to_types": ["aws_security_group"],
    },
    {
        "axiom_id": "AX-NET-04",
        "text": "precedência numérica: menor valor primeiro",
        "ttl": "bo:PrecedenceRuleSet rdfs:subClassOf [ a owl:Restriction ; owl:onProperty bo:hasPrecedenceOrder ; "
               "owl:hasValue bo:LowerValueFirst ] .",
        "entails": ["precedence"],
        "level": "published",
        "evidence": ["SE-google-n2ccqgtmt4jm72sp", "SE-azurerm-hfppj5whireqkdcl"],
        "basis": "'Lower value of priority implies higher precedence' / 'The lower the priority number, the higher "
                 "the priority of the rule'",
    },
    {
        "axiom_id": "AX-NET-05",
        "text": "empate de prioridade: negar vence permitir",
        "ttl": "bo:DenyTieRuleSet rdfs:subClassOf [ a owl:Restriction ; owl:onProperty bo:hasTieBreak ; "
               "owl:hasValue bo:DenyOverAllow ] .",
        "entails": ["tie_break"],
        "level": "published",
        "evidence": ["SE-google-t45d32hahm5ikdc3"],
        "basis": "'DENY rules take precedence over ALLOW rules having equal priority'",
    },
    {
        "axiom_id": "AX-NET-06",
        "text": "prioridade única por coleção: duas regras do mesmo conjunto e do mesmo sentido com a mesma "
                "prioridade tornam a configuração inválida (forma SHACL)",
        "ttl": "bo:UniquePriorityRuleSet rdfs:subClassOf [ a owl:Restriction ; owl:onProperty bo:hasPriorityRule ; "
               "owl:hasValue bo:UniquePerCollection ] .",
        "entails": ["validity"],
        "level": "published",
        "evidence": ["SE-azurerm-hfppj5whireqkdcl"],
        "basis": "'The priority number must be unique for each rule in the collection'",
        "shape": "SH-NET-PRIO-UNIQ",
    },
    {
        "axiom_id": "AX-NET-07",
        "text": "regra da security list sem 'stateless' declarado tem estado (rastreia conexão)",
        "ttl": "bo:DeclaredDefaultStateRule rdfs:subClassOf [ a owl:Class ; owl:unionOf ( bo:StateDeclaredRule "
               "[ a owl:Restriction ; owl:onProperty bo:hasConnectionTracking ; owl:hasValue bo:Stateful ] ) ] . "
               "bo:StateNotDeclaredRule owl:disjointWith bo:StateDeclaredRule .",
        "entails": ["state"],
        "level": "published",
        "evidence": ["SE-oci-bp7mulbmn76camow", "SE-oci-3ihxku562hxrgq4b"],
        "basis": "'stateless - (Optional) ... default false' no atributo da regra da security list (por regra)",
    },
    {
        "axiom_id": "AX-NET-08",
        "text": "regra com 'stateless' declarado: o valor declarado é o estado",
        "ttl": "bo:StatelessTrueRule owl:equivalentClass [ a owl:Restriction ; owl:onProperty bo:hasConnectionTracking ; "
               "owl:hasValue bo:Stateless ] . bo:StatelessFalseRule owl:equivalentClass [ a owl:Restriction ; "
               "owl:onProperty bo:hasConnectionTracking ; owl:hasValue bo:Stateful ] . "
               "bo:hasConnectionTracking a owl:FunctionalProperty . bo:Stateful owl:differentFrom bo:Stateless .",
        "entails": ["state"],
        "level": "published",
        "evidence": ["SE-oci-bp7mulbmn76camow", "SE-oci-3ihxku562hxrgq4b", "C24:CMT-FW-P03"],
        "basis": "o atributo stateless é por regra; uma regra não pode ter os dois estados (CMT-FW-P03)",
    },
    {
        "axiom_id": "AX-NET-09",
        "text": "sentido e efeito são funcionais e disjuntos; conjunto, regra e anexação são disjuntos",
        "ttl": "bo:hasEffect a owl:FunctionalProperty . bo:Allow owl:differentFrom bo:Deny . "
               "bo:IngressRule owl:disjointWith bo:EgressRule . "
               "[] a owl:AllDisjointClasses ; owl:members ( bo:FilterRuleSet bo:FilterRule bo:RuleSetAttachment "
               "bo:NetworkEndpoint ) .",
        "entails": ["consistency"],
        "level": "published",
        "evidence": ["C24:CMT-TAX-N03", "C24:CMT-FW-N01", "C24:REQ-NET-01"],
        "basis": "compromissos negativos do REQUIREMENTS: indivíduo não é regra e conjunto ao mesmo tempo; regra tem "
                 "um efeito e um sentido",
    },
    {
        "axiom_id": "AX-NET-10",
        "text": "efeito lido do átomo ou da construção vira o valor neutro (AllowingRule/DenyingRule)",
        "ttl": "bo:AllowingRule owl:equivalentClass [ a owl:Restriction ; owl:onProperty bo:hasEffect ; "
               "owl:hasValue bo:Allow ] . bo:DenyingRule owl:equivalentClass [ a owl:Restriction ; "
               "owl:onProperty bo:hasEffect ; owl:hasValue bo:Deny ] .",
        "entails": ["effect"],
        "level": "published",
        "evidence": ["SE-azurerm-x42gvfavlctlsm6r", "SE-google-iasfqf3ocxmoevym", "SE-google-xdqcqcyrrh2jrehq"],
        "basis": "valores publicados do efeito (access Allow/Deny; blocos allow{}/deny{})",
    },
]

EXCLUDED = [
    {"ref": "SE-google-yz5xmhx36uyxkd2x", "level": "interpreted",
     "why": "regras implícitas do firewall (deny de entrada, allow de saída) só interpretadas: fora do c3; "
            "o padrão sem regra que case no destino google fica desconhecido"},
    {"ref": "SE-oci-cxwuvxzhyrwz3j6f", "level": "interpreted",
     "why": "padrão de estado da regra de NSG da OCI só interpretado: fora do c3"},
    {"ref": "SE-oci-6gjp2guok3t6gzb7", "level": "interpreted",
     "why": "granularidade por regra lida por interpretação; o c3 usa só a frase publicada do atributo"},
]

# formas SHACL do c3 (validade da configuração de origem)
SHAPES_TTL = """
@prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix bo: <https://w3id.org/brevops/ontology#> .
bo:SH-NET-PRIO-UNIQ a sh:NodeShape ;
  sh:targetClass bo:UniquePriorityRuleSet ;
  sh:sparql [
    sh:message "duas regras do mesmo conjunto e sentido com a mesma prioridade (AX-NET-06)" ;
    sh:select \"\"\"
      PREFIX bo: <https://w3id.org/brevops/ontology#>
      SELECT $this ?r1 WHERE {
        $this bo:hasRule ?r1 , ?r2 .
        FILTER (STR(?r1) < STR(?r2))
        ?r1 bo:rulePriority ?p ; bo:hasDirection ?d .
        ?r2 bo:rulePriority ?p ; bo:hasDirection ?d .
      }\"\"\" ] .
"""

CONTROLLED_VALUES = ["bo:Allow", "bo:Deny", "bo:Ingress", "bo:Egress", "bo:Stateful", "bo:Stateless",
                     "bo:OrderIndependent", "bo:LowerValueFirst", "bo:DenyOverAllow", "bo:UniquePerCollection"]


def by_id() -> dict:
    return {a["axiom_id"]: a for a in AXIOMS}


def for_entailment(kind: str) -> list[str]:
    return [a["axiom_id"] for a in AXIOMS if kind in a["entails"]]
