"""Caso adversarial LB: balanceador como grafo de frontend, listener, roteamento, backend, sonda e TLS."""

from ..model import cm, fx, ground

CONS = ["DOMAIN-CONTRACTS", "GRAIN", "GRAIN-REPRO", "AXIOMS", "ONTPAT", "SEMANTIC-REGRESSION", "CQFIX"]

G_GRAPH = [
    ground("aws", "aws_lb (load_balancer_type application ou network) + aws_lb_listener + aws_lb_listener_rule + aws_lb_target_group (sonda embutida em health_check{}) + aws_lb_target_group_attachment: tudo standalone"),
    ground("google", "não há recurso \"balanceador\": o todo é implícito no grafo forwarding_rule (frontend) -> target_https_proxy (listener e TLS) -> url_map (roteamento) -> backend_service (pool) -> grupo de instâncias, com health_check separado"),
    ground("azurerm", "azurerm_lb (camada 4: frontend embutido; pool, sonda e regra standalone) é tipo distinto de azurerm_application_gateway (camada 7: tudo embutido em blocos)"),
    ground("oci", "oci_load_balancer_load_balancer + _listener + _backend_set (health_checker{} embutido) + _backend + _certificate (camada 7); oci_network_load_balancer_* para camada 4"),
]


def _l7(fid, summary, inline=None):
    attrs = ["lb1.layer=7", "li1.port=443", "li1.tls=true", "li2.port=80", "li2.tls=false",
             "ru1.match=path", "ru2.match=any"]
    if inline is not None:
        attrs += [f"{u}.declared_inline={'true' if inline else 'false'}" for u in ("li1", "li2", "ru1", "ru2", "pool1", "hp1")]
    return fx(fid, summary,
              "lb1:load_balancer fe1:lb_frontend li1:lb_listener li2:lb_listener ru1:routing_rule ru2:routing_rule "
              "pool1:backend_pool pool2:backend_pool hp1:health_probe cert1:tls_certificate "
              "vm1:compute_instance vm2:compute_instance vm3:compute_instance",
              ["fe1 frontend_of lb1", "li1 listener_on fe1", "li2 listener_on fe1", "li1 uses_certificate cert1",
               "ru1 rule_of_listener li1", "ru2 rule_of_listener li1", "ru1 forwards_to pool1", "ru2 forwards_to pool2",
               "vm1 member_of_pool pool1", "vm2 member_of_pool pool1", "vm3 member_of_pool pool2", "hp1 probes pool1"],
              attrs)


C = [
    cm("CMT-LB-P01", "LB", "positive", "entails",
       "No balanceador de camada 7, o caminho frontend -> listener -> regra de roteamento -> pool -> membro é "
       "uma cadeia de relações tipadas entre unidades distintas; a sonda verifica o pool, o certificado serve o "
       "listener que termina TLS.",
       "path(fe1 -> li1 -> ru1 -> pool1 -> vm1) AND probes(hp1, pool1) AND uses_certificate(li1, cert1)",
       _l7("FX-LB-P01", "balanceador de camada 7 com dois listeners, duas regras e dois pools"),
       "ENTAILED", "grafo de balanceador (F1)", ["REQ-LB-01"], ["F1"], "grafo tipado do balanceador",
       grounding=G_GRAPH, consumers=CONS),
    cm("CMT-LB-P02", "LB", "positive", "count",
       "Abaixo do todo, o grafo do balanceador da fixture tem nove unidades (frontend, 2 listeners, 2 regras, 2 "
       "pools, sonda, certificado), cada uma um indivíduo, qualquer que seja o grão (componente, entidade ou "
       "vínculo) que a evidência lhe der; as instâncias membros não são unidades do balanceador. Se o todo é "
       "indivíduo onde o provedor não tem recurso para ele é decisão do GRAIN, fora desta contagem.",
       "COUNT unidades do grafo abaixo de lb1 = 9 AND vm1, vm2, vm3 fora da contagem",
       _l7("FX-LB-P02", "mesma fixture, contagem de unidades"),
       9, "membro é papel de recurso externo; a contagem não depende do grão de cada unidade", ["REQ-LB-01", "REQ-TAX-02"], ["F1"],
       "contagem de componentes do grafo", consumers=CONS),
    cm("CMT-LB-P03", "LB", "positive", "invariant",
       "Realização com listener, regra, pool e sonda como recursos separados e realização com tudo embutido em "
       "blocos do balanceador produzem o mesmo grafo.",
       "grafo(embutido) == grafo(separado) a menos da camada Terraform",
       [_l7("FX-LB-P03-INLINE", "tudo embutido", inline=True), _l7("FX-LB-P03-SEPARATE", "tudo separado", inline=False)],
       "INVARIANT", "o grafo não depende da embalagem", ["REQ-LB-01", "REQ-ENT-01"], ["F1"],
       "invariância de realização do balanceador", layer="terraform", grounding=G_GRAPH, consumers=CONS),
    cm("CMT-LB-P04", "LB", "positive", "entails",
       "Ser membro de pool é papel: a instância membro continua instância de computação, e deixar o pool não a "
       "faz deixar de existir nem de ser instância.",
       "type(vm1) = compute_instance com e sem member_of_pool(vm1, pool1); member é antirrígido",
       fx("FX-LB-P04", "instância membro de um pool",
          "vm1:compute_instance pool1:backend_pool", ["vm1 member_of_pool pool1"], ["vm1.local_key=vm_a"]),
       "ENTAILED", "papel antirrígido sobre tipo rígido (OntoClean correto)", ["REQ-TAX-02"], ["R1-M3", "S2"],
       "papel x tipo", axes=["role", "time"], consumers=CONS),
    cm("CMT-LB-N01", "LB", "negative", "rejects",
       "A subsunção \"instância de computação ⊑ membro de pool\" é erro OntoClean (classe rígida sob papel "
       "antirrígido): uma instância que não está em nenhum pool continua instância.",
       "TBox com compute_instance ⊑ backend_member reprova no OntoClean; vm9 sem pool não é inferida membro",
       fx("FX-LB-N01", "instância fora de qualquer pool", "vm9:compute_instance", [], ["vm9.local_key=vm_z"]),
       "REJECTED", "Instância ⊑ MembroDePool reprovado (ONTPAT ontoclean_selftest)", ["REQ-TAX-02"],
       ["R1-M3", "F9"], "regra OntoClean na direção correta", code="INCONSISTENT", axes=["role"], consumers=CONS),
    cm("CMT-LB-N02", "LB", "negative", "rejects",
       "Regra de roteamento por caminho em balanceador de camada 4 é rejeitada: roteamento por caminho só existe "
       "na camada 7.",
       "SHACL: routing_rule com match=path ligada a load_balancer com layer=4 viola a forma",
       fx("FX-LB-N02", "regra por caminho em camada 4",
          "lb1:load_balancer fe1:lb_frontend li1:lb_listener ru1:routing_rule pool1:backend_pool",
          ["fe1 frontend_of lb1", "li1 listener_on fe1", "ru1 rule_of_listener li1", "ru1 forwards_to pool1"],
          ["lb1.layer=4", "li1.port=443", "ru1.match=path"]),
       "REJECTED", "camada 4 e camada 7 são tipos distintos", ["REQ-LB-01"], ["F1"], "distinção L4 x L7",
       code="SHACL_VIOLATION", grounding=G_GRAPH[2:3], consumers=CONS),
    cm("CMT-LB-N03", "LB", "negative", "not_entails",
       "Listener sem TLS não é inferido como terminando TLS porque outro listener do mesmo balanceador usa "
       "certificado.",
       "NOT tls(li2) = true AND NOT uses_certificate(li2, cert1)",
       _l7("FX-LB-N03", "dois listeners, só um com certificado"),
       "NOT_ENTAILED", "TLS é do listener, não do balanceador", ["REQ-LB-01"], ["F1"], "TLS no nível certo",
       consumers=CONS),
    cm("CMT-LB-U01", "LB", "unknown", "unknown",
       "Membro de pool referenciado só por endereço, sem recurso resolvido: qual instância é o membro é UNKNOWN.",
       "member_instance(ip1) = UNKNOWN",
       fx("FX-LB-U01", "membro por endereço sem recurso resolvido",
          "pool1:backend_pool ip1:ip_address vm1:compute_instance", ["ip1 member_of_pool pool1"],
          ["ip1.public=false"], complete=False, not_read=["ip1.reference"]),
       "UNKNOWN", "endereço não identifica instância sem resolução", ["REQ-LB-01", "REQ-ABS-01"], ["F1"],
       "membro não inventado", code="UNKNOWN_SYMBOLIC_INPUT", consumers=CONS),
    cm("CMT-LB-U02", "LB", "unknown", "unknown",
       "Pool sem sonda declarada, quando não há evidência de sonda padrão do provedor: a verificação de saúde do "
       "pool é UNKNOWN, não \"sem sonda\".",
       "health_check(pool1) = UNKNOWN",
       fx("FX-LB-U02", "pool sem sonda declarada",
          "lb1:load_balancer fe1:lb_frontend li1:lb_listener ru1:routing_rule pool1:backend_pool vm1:compute_instance",
          ["fe1 frontend_of lb1", "li1 listener_on fe1", "ru1 rule_of_listener li1", "ru1 forwards_to pool1",
           "vm1 member_of_pool pool1"],
          ["lb1.layer=7", "li1.port=443"], complete=False, not_read=["pool1.default"]),
       "UNKNOWN", "padrão do provedor não inventado", ["REQ-LB-01", "REQ-CFG-02"], ["F1"], "default não assumido",
       code="MISSING_EVIDENCE", consumers=CONS),
]
