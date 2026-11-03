"""Os compromissos do REQUIREMENTS que listam o ONTPAT como consumidor, como casos de teste dos padrões.

  python -I -m bo.ontpat.suite --run     grava results/ONTPAT/commitment_suite.json
  python -I -m bo.ontpat.suite --check   re-executa e compara; falha se algum compromisso testado diverge

Os 17 casos do teste de topo vêm de results/ONTPAT/upper_trial.json (candidata 'nenhuma', modo completo); os
três da contagem de interfaces, do selftest; os demais são operacionalizados aqui, sobre bo-patterns.ttl + o
vocabulário de teste (HermiT do ROBOT fixado, SHACL, avaliador de ausência). O que não se decide no nível dos
padrões fica 'fora do alcance', com o módulo que decide e o motivo; nada é pulado em silêncio. Cada caso
testado aqui traz uma mutação que tem de virar a resposta. A resposta esperada vem sempre do REQUIREMENTS.
"""

from __future__ import annotations

import sys
from itertools import combinations

import rdflib

from . import common as c
from . import robot, selftest
from . import trial_spec as S
from . import upper_trial as U

TBOX = """
tv:NicAttachment a owl:Class ; rdfs:subClassOf bo:Binding ; bo:rigidity bo:Rigid .
tv:attachesInterface a owl:ObjectProperty , owl:FunctionalProperty ; rdfs:subPropertyOf bo:relates ; rdfs:domain tv:NicAttachment ; rdfs:range tv:NetworkInterface .
tv:attachesTo a owl:ObjectProperty , owl:FunctionalProperty ; rdfs:subPropertyOf bo:relates ; rdfs:domain tv:NicAttachment ; rdfs:range tv:ComputeInstance .
tv:NicAttachment owl:hasKey ( tv:attachesInterface tv:attachesTo ) .
tv:deviceIndex a owl:DatatypeProperty , owl:FunctionalProperty .
tv:inSubnet a owl:ObjectProperty ; rdfs:subPropertyOf bo:references ; rdfs:range tv:Subnet .
tv:Subnet a owl:Class ; rdfs:subClassOf bo:IndependentResource ; bo:rigidity bo:Rigid .
tv:DnsZone a owl:Class ; rdfs:subClassOf bo:IndependentResource ; bo:rigidity bo:Rigid .
tv:DnsRecord a owl:Class ; rdfs:subClassOf bo:Resource ; bo:rigidity bo:Rigid .
tv:recordIn a owl:ObjectProperty ; rdfs:subPropertyOf bo:references ; rdfs:domain tv:DnsRecord ; rdfs:range tv:DnsZone .
tv:PlacementPolicy a owl:Class ; rdfs:subClassOf bo:IndependentResource ; bo:rigidity bo:Rigid .
tv:DedicatedHost a owl:Class ; rdfs:subClassOf bo:IndependentResource ; bo:rigidity bo:Rigid .
tv:VirtualMachine a owl:Class ; rdfs:subClassOf tv:ComputeInstance ; bo:rigidity bo:Rigid .
tv:placedBy a owl:ObjectProperty ; rdfs:subPropertyOf bo:references .
tv:runsOn a owl:ObjectProperty ; rdfs:subPropertyOf bo:references .
tv:FilterRule a owl:Class ; rdfs:subClassOf bo:Resource ; bo:rigidity bo:Rigid .
tv:StatefulRule a owl:Class ; rdfs:subClassOf tv:FilterRule ; bo:rigidity bo:Rigid .
tv:StatelessRule a owl:Class ; rdfs:subClassOf tv:FilterRule ; bo:rigidity bo:Rigid .
tv:RuleSet a owl:Class ; rdfs:subClassOf bo:IndependentResource ; bo:rigidity bo:Rigid .
tv:SecretHolder a owl:Class ; rdfs:subClassOf bo:IndependentResource ; bo:rigidity bo:Rigid .
tv:secretOf a owl:ObjectProperty ; rdfs:subPropertyOf bo:references ; rdfs:domain tv:SecretHolder .
tv:LbListener a owl:Class ; rdfs:subClassOf bo:Resource ; bo:rigidity bo:Rigid .
tv:LbFrontend a owl:Class ; rdfs:subClassOf bo:Resource ; bo:rigidity bo:Rigid .
tv:RoutingRule a owl:Class ; rdfs:subClassOf bo:Resource ; bo:rigidity bo:Rigid .
tv:HealthProbe a owl:Class ; rdfs:subClassOf bo:Resource ; bo:rigidity bo:Rigid .
tv:TlsCertificate a owl:Class ; rdfs:subClassOf bo:IndependentResource ; bo:rigidity bo:Rigid .
tv:LoadBalancer a owl:Class ; rdfs:subClassOf bo:IndependentResource ; bo:rigidity bo:Rigid .
tv:TlsSetting a owl:Class ; rdfs:subClassOf bo:Facet ; bo:rigidity bo:Rigid .
tv:probes a owl:ObjectProperty ; rdfs:subPropertyOf bo:references ; rdfs:domain tv:HealthProbe ; rdfs:range tv:BackendPool .
tv:IpAddress a owl:Class ; rdfs:subClassOf bo:NaryRelation ; bo:rigidity bo:Rigid .
tv:memberAddress a owl:ObjectProperty ; rdfs:range tv:IpAddress .
tv:hasAddress a owl:ObjectProperty .
[] a owl:AllDisjointClasses ; owl:members ( tv:ComputeInstance tv:NetworkInterface tv:Subnet tv:DnsZone tv:DnsRecord tv:PlacementPolicy
    tv:DedicatedHost tv:FilterRule tv:RuleSet tv:SecretHolder tv:LbListener tv:LbFrontend tv:RoutingRule tv:HealthProbe tv:TlsCertificate
    tv:LoadBalancer tv:BackendPool tv:DbInstance tv:ScopeNode tv:Alarm ) .
tv:StatefulRule owl:disjointWith tv:StatelessRule .
tv:desc_attachesInterface a owl:NamedIndividual , bo:PropertyDescriptor ; bo:descriptorKey "attachesInterface" ; bo:describesProperty tv:attachesInterface .
tv:desc_privateAddress a owl:NamedIndividual , bo:PropertyDescriptor ; bo:descriptorKey "privateAddress" ; bo:describesProperty tv:hasAddress .
tv:desc_probes a owl:NamedIndividual , bo:PropertyDescriptor ; bo:descriptorKey "probes" ; bo:describesProperty tv:probes .
tv:desc_secret a owl:NamedIndividual , bo:PropertyDescriptor ; bo:descriptorKey "secretValue" ; bo:describesProperty tv:secretOf .
tv:desc_memberOfPool a owl:NamedIndividual , bo:PropertyDescriptor ; bo:descriptorKey "memberOfPool" ; bo:describesProperty tv:memberOfPool .
tv:desc_Alarm a owl:NamedIndividual , bo:ClassDescriptor ; bo:descriptorKey "Alarm" ; bo:describesClass tv:Alarm .
"""

R = lambda **k: S.ident(ptype="tv:pt_instance", **k)  # noqa: E731

VM_NICS = f"""
K:vm1 a owl:NamedIndividual , tv:ComputeInstance ; {R(key='vm_a', inc='inc-vm1')} .
K:sa a owl:NamedIndividual , tv:Subnet ; {R(key='sub_a', inc='inc-sa')} .
K:nic1 a owl:NamedIndividual , tv:NetworkInterface , bo:IndependentResource ; {R(key='if_a', inc='inc-n1')} ; tv:inSubnet K:sa .
K:att1 a owl:NamedIndividual , tv:NicAttachment ; tv:attachesInterface K:nic1 ; tv:attachesTo K:vm1 ; tv:deviceIndex 0 .
"""

# tipos de consulta: os de upper_trial (ent, not_ent, unknown com triplas) e mais:
#   ent_raw / unknown_raw   α (e ¬α) em Turtle livre
#   inconsistent            o caso inteiro é inconsistente
#   absence                 avaliador de ausência (vocabulário de ausência): (indivíduo, descritor de classe) -> valor, código
#   value_state             (valor reificado) -> estado e motivo lidos do ABox
#   shacl_violates          a fixture viola as formas (pyshacl, regime declarado)
CASES = {
    "CMT-NIC-P04": {"how": "leitura embutida e leitura separada levantadas nos padrões têm a mesma assinatura de relações e a mesma contagem",
                    "fixture": VM_NICS.replace("K:", "K:A_") + VM_NICS.replace("K:", "K:B_").replace("tv:inSubnet K:B_sa .", "tv:inSubnet K:B_sa ; bo:textPosition 2 ."),
                    "checks": [("ent", "mesma interface nas duas leituras", [("K:A_nic1", "owl:sameAs", "K:B_nic1")]),
                               ("ent", "mesma anexação nas duas leituras", [("K:A_att1", "owl:sameAs", "K:B_att1")])],
                    "mutation": {"label": "posição textual na chave local da leitura embutida",
                                 "replace_all": [("tv:inSubnet K:B_sa ; bo:textPosition 2 .", "tv:inSubnet K:B_sa .")],
                                 "extra": "", "rekey": ('bo:localKey "if_a" ; bo:incarnationKey "inc-n1" ; tv:inSubnet K:B_sa', 'bo:localKey "if_a@2" ; bo:incarnationKey "inc-n1" ; tv:inSubnet K:B_sa'),
                                 "flips": 0}},
    "CMT-NIC-N01": {"how": "disjunção entre instância e interface (tipos rígidos)",
                    "fixture": f"K:x1 a owl:NamedIndividual , tv:ComputeInstance , tv:NetworkInterface ; {R(key='vm_a', inc='inc-x1')} .\n",
                    "checks": [("inconsistent", "x1 instância e interface", None)],
                    "mutation": {"label": "x1 só instância", "replace_all": [("tv:ComputeInstance , tv:NetworkInterface", "tv:ComputeInstance")], "flips": 0}},
    "CMT-NIC-N02": {"how": "sub-rede é da interface (não funcional na instância): sem igualdade espúria",
                    "fixture": f"""
K:vm1 a owl:NamedIndividual , tv:ComputeInstance ; {R(key='vm_a', inc='inc-vm1')} .
K:sa a owl:NamedIndividual , tv:Subnet ; {R(key='sub_a')} .
K:sb a owl:NamedIndividual , tv:Subnet ; {R(key='sub_b')} .
K:nic1 a owl:NamedIndividual , tv:NetworkInterface , bo:IndependentResource ; {R(key='if_a')} ; tv:inSubnet K:sa .
K:nic2 a owl:NamedIndividual , tv:NetworkInterface , bo:IndependentResource ; {R(key='if_b')} ; tv:inSubnet K:sb .
K:att1 a owl:NamedIndividual , tv:NicAttachment ; tv:attachesInterface K:nic1 ; tv:attachesTo K:vm1 ; tv:deviceIndex 0 .
K:att2 a owl:NamedIndividual , tv:NicAttachment ; tv:attachesInterface K:nic2 ; tv:attachesTo K:vm1 ; tv:deviceIndex 1 .
""",
                    "checks": [("not_ent", "sa = sb não é consequência", [("K:sa", "owl:sameAs", "K:sb")]),
                               ("not_ent", "nic1 = nic2 não é consequência", [("K:nic1", "owl:sameAs", "K:nic2")])],
                    "mutation": {"label": "'sub-rede da instância' funcional", "extra": "tv:instanceSubnet a owl:ObjectProperty , owl:FunctionalProperty .\nK:vm1 tv:instanceSubnet K:sa , K:sb .\n", "flips": 0}},
    "CMT-NIC-N03": {"how": "interface não é instância",
                    "fixture": VM_NICS,
                    "checks": [("not_ent", "nic1 não é instância", [("K:nic1", "a", "tv:ComputeInstance")])],
                    "mutation": {"label": "interface ⊑ instância", "extra": "tv:NetworkInterface rdfs:subClassOf tv:ComputeInstance .\n", "flips": 0}},
    "CMT-NIC-U01": {"how": "anexação de nic2 não lida: 'vm1 tem só uma interface' nem segue nem é refutado; motivo na marca",
                    "fixture": VM_NICS + f"""K:nic2 a owl:NamedIndividual , tv:NetworkInterface , bo:IndependentResource ; {R(key='if_b', inc='inc-n2')} ; tv:inSubnet K:sa .
K:m1 a owl:NamedIndividual , bo:UnknownMarker ; bo:markerOf K:nic2 ; bo:of tv:desc_attachesInterface ; bo:valueState bo:NotRead ; bo:unknownReason bo:IncompleteRead .
""",
                    "checks": [("unknown_raw", "número de interfaces de vm1 = 1",
                                ("K:vm1 a [ a owl:Restriction ; owl:onProperty [ owl:inverseOf tv:attachesTo ] ; owl:maxQualifiedCardinality \"1\"^^xsd:nonNegativeInteger ; owl:onClass tv:NicAttachment ] .",
                                 "K:vm1 a [ a owl:Restriction ; owl:onProperty [ owl:inverseOf tv:attachesTo ] ; owl:minQualifiedCardinality \"2\"^^xsd:nonNegativeInteger ; owl:onClass tv:NicAttachment ] .")),
                               ("marker_code", "motivo", ("K:nic2", "tv:desc_attachesInterface"))],
                    "mutation": {"label": "anexação de nic2 lida", "extra": "K:att2 a owl:NamedIndividual , tv:NicAttachment ; tv:attachesInterface K:nic2 ; tv:attachesTo K:vm1 ; tv:deviceIndex 1 .\n", "flips": 0}},
    "CMT-NIC-U02": {"how": "referência de anexação simbólica: a instância de nic3 nem segue nem é refutada",
                    "fixture": f"""K:vm1 a owl:NamedIndividual , tv:ComputeInstance ; {R(key='vm_a', inc='inc-vm1')} .
K:nic3 a owl:NamedIndividual , tv:NetworkInterface , bo:IndependentResource ; {R(key='if_c', inc='inc-n3')} .
K:m1 a owl:NamedIndividual , bo:UnknownMarker ; bo:markerOf K:nic3 ; bo:of tv:desc_attachesInterface ; bo:valueState bo:Unknown ; bo:unknownReason bo:UnknownSymbolicInput .
""",
                    "checks": [("unknown_raw", "nic3 anexada a vm1",
                                ("K:nic3 a [ a owl:Restriction ; owl:onProperty [ owl:inverseOf tv:attachesInterface ] ; owl:someValuesFrom [ a owl:Restriction ; owl:onProperty tv:attachesTo ; owl:hasValue K:vm1 ] ] .",
                                 "K:nic3 a [ a owl:Class ; owl:complementOf [ a owl:Restriction ; owl:onProperty [ owl:inverseOf tv:attachesInterface ] ; owl:someValuesFrom [ a owl:Restriction ; owl:onProperty tv:attachesTo ; owl:hasValue K:vm1 ] ] ] .")),
                               ("marker_code", "motivo", ("K:nic3", "tv:desc_attachesInterface"))],
                    "mutation": {"label": "referência resolvida", "extra": "K:att3 a owl:NamedIndividual , tv:NicAttachment ; tv:attachesInterface K:nic3 ; tv:attachesTo K:vm1 .\n", "flips": 0}},
    "CMT-LB-P02": {"how": "nove unidades distintas com grãos misturados (componente, entidade); membros fora da contagem",
                   "fixture": f"""K:lb1 a owl:NamedIndividual , tv:LoadBalancer ; {R(key='lb_a', inc='inc-lb1')} .
K:fe1 a owl:NamedIndividual , tv:LbFrontend , bo:Component ; bo:componentOf K:lb1 ; bo:occurrenceKey "frontend=fe" .
K:li1 a owl:NamedIndividual , tv:LbListener , bo:Component ; bo:componentOf K:fe1 ; bo:occurrenceKey "port=443" .
K:li2 a owl:NamedIndividual , tv:LbListener , bo:Component ; bo:componentOf K:fe1 ; bo:occurrenceKey "port=80" .
K:ru1 a owl:NamedIndividual , tv:RoutingRule , bo:Component ; bo:componentOf K:li1 ; bo:occurrenceKey "match=path" .
K:ru2 a owl:NamedIndividual , tv:RoutingRule , bo:Component ; bo:componentOf K:li1 ; bo:occurrenceKey "match=any" .
K:pool1 a owl:NamedIndividual , tv:BackendPool ; {R(key='pool_1', inc='inc-p1')} .
K:pool2 a owl:NamedIndividual , tv:BackendPool ; {R(key='pool_2', inc='inc-p2')} .
K:hp1 a owl:NamedIndividual , tv:HealthProbe , bo:IndependentResource ; {R(key='probe_1', inc='inc-hp1')} ; tv:probes K:pool1 .
K:cert1 a owl:NamedIndividual , tv:TlsCertificate ; {R(key='cert_1', inc='inc-c1')} .
K:vm1 a owl:NamedIndividual , tv:ComputeInstance ; {R(key='vm_1', inc='inc-v1')} ; tv:memberOfPool K:pool1 .
""",
                   "checks": [("count", "COUNT unidades abaixo do todo", (["tv:LbFrontend", "tv:LbListener", "tv:RoutingRule", "tv:BackendPool", "tv:HealthProbe", "tv:TlsCertificate"], None))],
                   "mutation": {"label": "as duas regras com a mesma chave de ocorrência", "replace_all": [('"match=any"', '"match=path"')], "flips": 0}},
    "CMT-LB-N03": {"how": "faceta TLS é do listener (dono), não se propaga ao irmão",
                   "fixture": f"""K:lb1 a owl:NamedIndividual , tv:LoadBalancer ; {R(key='lb_a', inc='inc-lb1')} .
K:li1 a owl:NamedIndividual , tv:LbListener , bo:Component ; bo:componentOf K:lb1 ; bo:occurrenceKey "port=443" .
K:li2 a owl:NamedIndividual , tv:LbListener , bo:Component ; bo:componentOf K:lb1 ; bo:occurrenceKey "port=80" .
K:tls1 a owl:NamedIndividual , tv:TlsSetting ; bo:facetOf K:li1 ; bo:appliesTo K:li1 .
""",
                   "checks": [("not_ent_raw", "li2 termina TLS", "K:li2 a [ a owl:Restriction ; owl:onProperty [ owl:inverseOf bo:facetOf ] ; owl:someValuesFrom tv:TlsSetting ] .")],
                   "mutation": {"label": "faceta TLS copiada no listener irmão (cópia por dono)",
                                "extra": "K:tls2 a owl:NamedIndividual , tv:TlsSetting ; bo:facetOf K:li2 ; bo:appliesTo K:li2 .\n", "flips": 0}},
    "CMT-LB-U01": {"how": "membro só por endereço: qual instância é o membro nem segue nem é refutado",
                   "fixture": f"""K:pool1 a owl:NamedIndividual , tv:BackendPool ; {R(key='pool_1', inc='inc-p1')} .
K:vm1 a owl:NamedIndividual , tv:ComputeInstance ; {R(key='vm_1', inc='inc-v1')} .
K:mem1 a owl:NamedIndividual , bo:UnknownMarker ; bo:markerOf K:pool1 ; bo:of tv:desc_memberOfPool ; bo:valueState bo:Unknown ; bo:unknownReason bo:UnknownSymbolicInput .
""",
                   "checks": [("unknown", "vm1 é o membro", [("K:vm1", "tv:memberOfPool", "K:pool1")]),
                              ("marker_code", "motivo", ("K:pool1", "tv:desc_memberOfPool"))],
                   "mutation": {"label": "endereço resolvido para vm1", "extra": "K:vm1 tv:memberOfPool K:pool1 .\n", "flips": 0}},
    "CMT-LB-U02": {"how": "pool sem sonda declarada e sem evidência de padrão: 'sem sonda' nem segue nem é refutado",
                   "fixture": f"""K:pool1 a owl:NamedIndividual , tv:BackendPool ; {R(key='pool_1', inc='inc-p1')} .
K:mp a owl:NamedIndividual , bo:UnknownMarker ; bo:markerOf K:pool1 ; bo:of tv:desc_probes ; bo:valueState bo:Unknown ; bo:unknownReason bo:MissingEvidence .
""",
                   "checks": [("unknown_raw", "pool1 sem sonda",
                               ("K:pool1 a [ a owl:Class ; owl:complementOf [ a owl:Restriction ; owl:onProperty [ owl:inverseOf tv:probes ] ; owl:someValuesFrom tv:HealthProbe ] ] .",
                                "K:pool1 a [ a owl:Restriction ; owl:onProperty [ owl:inverseOf tv:probes ] ; owl:someValuesFrom tv:HealthProbe ] .")),
                              ("marker_code", "motivo", ("K:pool1", "tv:desc_probes"))],
                   "mutation": {"label": "sonda padrão inventada", "extra": f"K:hp9 a owl:NamedIndividual , tv:HealthProbe , bo:IndependentResource ; tv:probes K:pool1 .\n", "flips": 0}},
    "CMT-TAX-N01": {"how": "registro e zona disjuntos; pertencer à zona não é ser zona",
                    "fixture": f"""K:z1 a owl:NamedIndividual , tv:DnsZone ; {R(key='zone_a', inc='inc-z1')} .
K:r1 a owl:NamedIndividual , tv:DnsRecord , bo:IndependentResource ; {R(key='www', inc='inc-r1')} ; tv:recordIn K:z1 .
""",
                    "checks": [("not_ent", "r1 não é zona", [("K:r1", "a", "tv:DnsZone")])],
                    "mutation": {"label": "registro ⊑ zona (erro do esqueleto)", "extra": "tv:DnsRecord rdfs:subClassOf tv:DnsZone .\n", "flips": 0}},
    "CMT-TAX-N02": {"how": "política e host disjuntos de instância; host dedicado não é máquina virtual",
                    "fixture": f"""K:vm1 a owl:NamedIndividual , tv:ComputeInstance ; {R(key='vm_a', inc='inc-vm1')} ; tv:placedBy K:pp1 ; tv:runsOn K:h1 .
K:pp1 a owl:NamedIndividual , tv:PlacementPolicy ; {R(key='pp_a', inc='inc-pp1')} .
K:h1 a owl:NamedIndividual , tv:DedicatedHost ; {R(key='h_a', inc='inc-h1')} .
""",
                    "checks": [("not_ent", "pp1 não é instância", [("K:pp1", "a", "tv:ComputeInstance")]),
                               ("not_ent", "h1 não é máquina virtual", [("K:h1", "a", "tv:VirtualMachine")])],
                    "mutation": {"label": "política ⊑ instância (erro do esqueleto)", "extra": "tv:PlacementPolicy rdfs:subClassOf tv:ComputeInstance .\n", "flips": 0}},
    "CMT-TAX-N03": {"how": "com e sem estado disjuntos: a subsunção torna a regra sem estado insatisfatível",
                    "fixture": f"""K:rs1 a owl:NamedIndividual , tv:RuleSet ; {R(key='rs_a', inc='inc-rs1')} .
K:r1 a owl:NamedIndividual , tv:StatelessRule , bo:Component ; bo:componentOf K:rs1 ; bo:occurrenceKey "dir=ingress;proto=tcp;port=443" .
tv:StatelessRule rdfs:subClassOf tv:StatefulRule .
""",
                    "checks": [("inconsistent", "sem estado ⊑ com estado é rejeitada", None)],
                    "mutation": {"label": "sem a subsunção errada", "replace_all": [("tv:StatelessRule rdfs:subClassOf tv:StatefulRule .\n", "")], "flips": 0}},
    "CMT-CFG-P02": {"how": "origem do valor é padrão do provedor e, por consequência, não é 'configurado'",
                    "fixture": f"""K:c1 a owl:NamedIndividual , tv:ObjectContainer , bo:IndependentResource ; {S.ident(inc='inc-c1')} .
K:ob1 a owl:NamedIndividual , bo:Observation ; prov:startedAtTime "2026-11-02T10:00:00-03:00"^^xsd:dateTime ; bo:readCompleteness bo:CompleteRead ; bo:coversScope tv:acct_a .
K:o1 a owl:NamedIndividual , bo:ObservedState ; bo:stateOf K:c1 ; prov:wasGeneratedBy K:ob1 ; bo:hasSettingValue K:v1 .
K:v1 a owl:NamedIndividual , bo:SettingValue ; bo:of tv:desc_versioning ; bo:iriValue tv:Disabled ; bo:valueOrigin bo:ProviderDefault ; bo:valueState bo:Known .
""",
                    "checks": [("ent", "origem = padrão", [("K:v1", "bo:valueOrigin", "bo:ProviderDefault")]),
                               ("ent_raw", "NOT configurado", "K:v1 a [ a owl:Class ; owl:complementOf [ a owl:Restriction ; owl:onProperty bo:valueOrigin ; owl:hasValue bo:Configured ] ] .")],
                    "mutation": {"label": "valor também marcado configurado", "extra": "K:v1 bo:valueOrigin bo:Configured .\n", "flips": 1}},
    "CMT-CFG-U01": {"how": "endereço computado na criação: estado desconhecido com motivo, nunca ausente",
                    "fixture": f"""K:nic1 a owl:NamedIndividual , tv:NetworkInterface , bo:IndependentResource ; {R(key='if_a', inc='inc-n1')} .
K:d1 a owl:NamedIndividual , bo:ConfigurationDescription ; bo:describes K:nic1 ; bo:descriptionSource bo:SourceCode ; bo:hasSettingValue K:v1 .
K:v1 a owl:NamedIndividual , bo:SettingValue ; bo:of tv:desc_privateAddress ; bo:valueOrigin bo:Configured ; bo:valueState bo:Unknown ; bo:unknownReason bo:UnknownSymbolicInput .
""",
                    "checks": [("not_ent", "não é ausente", [("K:v1", "bo:valueState", "bo:Absent")]),
                               ("value_code", "estado e motivo", "K:v1")],
                    "mutation": {"label": "endereço gravado como ausente", "extra": "K:v1 bo:valueState bo:Absent .\n", "flips": 0}},
    "CMT-ABS-P01": {"how": "avaliador de ausência: leitura completa do tipo no escopo",
                    "fixture": f"""K:i1 a owl:NamedIndividual , tv:DbInstance ; {R(key='db_1', inc='inc-i1')} .
K:s1 a owl:NamedIndividual , tv:ScopeNode ; {R(key='scope_1', inc='inc-s1')} .
K:ob1 a owl:NamedIndividual , bo:Observation ; prov:startedAtTime "2026-11-02T10:00:00-03:00"^^xsd:dateTime ; bo:readCompleteness bo:CompleteRead ; bo:coversScope K:s1 ; bo:coversKind tv:desc_Alarm .
K:i1 bo:references K:s1 .
""",
                    "checks": [("absence", "i1 sem alarme", ("K:i1", "K:s1", "ENTAILED", None))],
                    "mutation": {"label": "leitura parcial", "replace_all": [("bo:readCompleteness bo:CompleteRead ; bo:coversScope K:s1", "bo:readCompleteness bo:PartialRead ; bo:coversScope K:s1")], "flips": 0}},
    "CMT-ABS-U01": {"how": "avaliador de ausência: leitura parcial dá UNKNOWN com motivo",
                    "fixture": f"""K:i1 a owl:NamedIndividual , tv:DbInstance ; {R(key='db_1', inc='inc-i1')} .
K:s1 a owl:NamedIndividual , tv:ScopeNode ; {R(key='scope_1', inc='inc-s1')} .
K:ob1 a owl:NamedIndividual , bo:Observation ; prov:startedAtTime "2026-11-02T10:00:00-03:00"^^xsd:dateTime ; bo:readCompleteness bo:PartialRead ; bo:coversScope K:s1 ; bo:coversKind tv:desc_Alarm .
K:i1 bo:references K:s1 .
""",
                    "checks": [("absence", "i1 tem alarme?", ("K:i1", "K:s1", "UNKNOWN", "INCOMPLETE_READ"))],
                    "mutation": {"label": "leitura completa", "replace_all": [("bo:PartialRead", "bo:CompleteRead")], "flips": 0}},
    "CMT-ABS-N01": {"how": "segredo retido: presença conhecida, valor não gravado, 'não tem segredo' não segue",
                    "fixture": f"""K:i1 a owl:NamedIndividual , tv:DbInstance ; {R(key='db_1', inc='inc-i1')} .
K:k1 a owl:NamedIndividual , tv:SecretHolder ; {R(key='secret_1', inc='inc-k1')} ; tv:secretOf K:i1 .
K:ob1 a owl:NamedIndividual , bo:Observation ; prov:startedAtTime "2026-11-02T10:00:00-03:00"^^xsd:dateTime ; bo:readCompleteness bo:CompleteRead ; bo:coversScope tv:acct_a .
K:o1 a owl:NamedIndividual , bo:ObservedState ; bo:stateOf K:k1 ; prov:wasGeneratedBy K:ob1 ; bo:hasSettingValue K:v1 .
K:v1 a owl:NamedIndividual , bo:SettingValue ; bo:of tv:desc_secret ; bo:valueOrigin bo:Observed ; bo:valueState bo:Withheld .
""",
                    "checks": [("not_ent_raw", "i1 não tem segredo", "K:i1 a [ a owl:Class ; owl:complementOf [ a owl:Restriction ; owl:onProperty [ owl:inverseOf tv:secretOf ] ; owl:someValuesFrom tv:SecretHolder ] ] ."),
                               ("value_code", "estado do valor", "K:v1"),
                               ("shacl_conforms", "forma: nenhum valor nem hash gravado", None)],
                    "mutation": {"label": "hash do segredo gravado", "extra": "K:v1 bo:literalValue \"9f86d081884c7d65\" .\n", "flips": 2}},
    "CMT-LC-U01": {"how": "sem controlador declarado: o fim da configuração com o contêiner nem segue nem é refutado",
                   "fixture": f"""K:c1 a owl:NamedIndividual , tv:ObjectContainer , bo:IndependentResource ; {S.ident(inc='inc-c1')} ; bo:endedBy K:del .
K:del a owl:NamedIndividual , bo:Deletion .
K:s1 a owl:NamedIndividual , bo:Facet ; bo:declaredOn K:c1 ; bo:appliesTo K:c1 .
K:m1 a owl:NamedIndividual , bo:UnknownMarker ; bo:markerOf K:s1 ; bo:of bo:desc_lifecycleControlledBy ; bo:valueState bo:Unknown ; bo:unknownReason bo:MissingEvidence .
""",
                   "checks": [("unknown", "s1 encerrada", [("K:s1", "a", "bo:EndedUnit")]),
                              ("marker_code", "motivo", ("K:s1", "bo:desc_lifecycleControlledBy"))],
                   "mutation": {"label": "dono declarado (o contêiner)", "extra": "K:s1 bo:facetOf K:c1 .\n", "flips": 0}},
}

OUT_OF_SCOPE = {
    "CMT-LB-P01": ("DOMAIN-CONTRACTS, AXIOMS", "cadeia tipada frontend→listener→regra→pool→membro e terminação TLS são vocabulário do domínio LB"),
    "CMT-LB-P03": ("GRAIN, DOMAIN-CONTRACTS", "invariância entre embalagens depende do procedimento de grão sobre os schemas"),
    "CMT-LB-N02": ("DOMAIN-CONTRACTS, SHACL", "roteamento por caminho só na camada 7 é forma de domínio"),
    "CMT-NEW-P01": ("CLASS, GLOSSARY, HOLDOUT", "acomodar provedor retirado sem classe nova é propriedade do processo de indução"),
    "CMT-NEW-N01": ("CLASS, OWL", "conceito exclusivo fora do núcleo é regra de módulo (bo-ext) do gerador"),
    "CMT-NEW-U01": ("GLOSSARY, CLASS", "UNGLOSSED é decisão do glossário; o vocabulário de ausência tem o motivo bo:Unglossed (conferido abaixo)"),
}

FROM_TRIAL = sorted(S.CASES)
FROM_SELFTEST = {"CMT-NIC-P01": ("n2", "resources", 3), "CMT-NIC-P02": ("n1", "resources", 2), "CMT-NIC-P03": ("structure", None, "INVARIANT")}


def _mut(fx: str, mut: dict) -> str:
    out = fx
    for a, b in mut.get("replace_all", []):
        if a not in out:
            raise ValueError(f"mutação não se aplica: {a!r}")
        out = out.replace(a, b)
    if "rekey" in mut:
        a, b = mut["rekey"]
        if a not in out:
            raise ValueError(f"mutação não se aplica: {a!r}")
        out = out.replace(a, b)
    return out + mut.get("extra", "")


def raw_query(cid: str, ttl: str) -> str:
    return U.render(cid, S.PREFIXES + U.case_header(cid) + ttl + "\n")


def absence(g: rdflib.Graph, unit, scope, kind_desc) -> tuple[str, str | None]:
    """Avaliador de ausência (P6): 'unit tem instância de kind?' sob o escopo.
    TRUE se há; ENTAILED (ausência) só se há observação COMPLETA que cobre kind no escopo; senão UNKNOWN."""
    B = c.BO
    kind = next(g.objects(kind_desc, B.describesClass), None)
    if kind is not None:
        for x in g.subjects(rdflib.RDF.type, kind):
            if (x, B.references, unit) in g or (unit, B.references, x) in g:
                return "HAS", None
    for ob in g.subjects(B.coversKind, kind_desc):
        if (ob, B.coversScope, scope) in g:
            if (ob, B.readCompleteness, B.CompleteRead) in g:
                return "ENTAILED", None
    return "UNKNOWN", "INCOMPLETE_READ"


def run() -> dict:
    cm = U.commitments()
    work = c.tmp_dir() / "suite"
    work.mkdir(parents=True, exist_ok=True)
    for p in work.iterdir():
        p.unlink()
    inputs = U.write_inputs(work)
    tvg = U._ttl_graph(S.PREFIXES + S.TRIAL_TBOX + TBOX)
    base = U._nt(inputs["full"][0]) + U._nt(tvg)
    pl = U.Plan(work)
    jobs = {}
    for cid, spec in CASES.items():
        for run_name in ("base", "mutation"):
            fx = spec["fixture"] if run_name == "base" else _mut(spec["fixture"], spec["mutation"])
            jid = f"suite__{cid}__{run_name}"
            fx_ttl = U.render(cid, S.PREFIXES + U.case_header(cid) + fx)
            pl.job(jid, [pl.file(f"job_{jid}.nt", base + U._nt(U._ttl_graph(fx_ttl)))], {"kind": "suite", "fx_ttl": fx_ttl})
            jobs[(cid, run_name)] = jid
            for ci, chk in enumerate(spec["checks"]):
                k = chk[0]
                if k in ("ent", "not_ent"):
                    pl.ent(jid, str(ci), U.query_ttl(cid, chk[2]))
                elif k == "unknown":
                    pl.ent(jid, str(ci), U.query_ttl(cid, chk[2]))
                    pl.ent(jid, f"{ci}neg", U.query_ttl(cid, chk[2], negate=True))
                elif k in ("ent_raw", "not_ent_raw"):
                    pl.ent(jid, str(ci), raw_query(cid, chk[2]))
                elif k == "unknown_raw":
                    pl.ent(jid, str(ci), raw_query(cid, chk[2][0]))
                    pl.ent(jid, f"{ci}neg", raw_query(cid, chk[2][1]))
                elif k == "count":
                    inds = sorted(set(__import__("re").findall(r"(?m)^K:([A-Za-z0-9_]+) a ", fx)))
                    for a, b in combinations(inds, 2):
                        pl.ent(jid, f"{ci}diff:{a}:{b}", U.query_ttl(cid, [(f"K:{a}", "owl:differentFrom", f"K:{b}")]))
            if any(chk[0] == "count" for chk in spec["checks"]):
                pl.dump(jid)
    (work / "jobs.tsv").write_text("\n".join(pl.lines) + "\n", encoding="utf-8")
    U.parse_output(pl, robot.harness(work / "jobs.tsv", work / "out.tsv"))

    cases = {}
    for cid, spec in CASES.items():
        exp = cm[cid]["expected_answer"]
        res = {}
        for run_name in ("base", "mutation"):
            J = pl.jobs[jobs[(cid, run_name)]]
            g = None
            out = []
            for ci, chk in enumerate(spec["checks"]):
                k = chk[0]
                r = {"check": chk[1], "kind": k}
                e = J["ents"]
                if k in ("ent", "ent_raw"):
                    r["observed"], r["pass"] = e.get(str(ci)), e.get(str(ci)) == "true"
                elif k in ("not_ent", "not_ent_raw"):
                    r["observed"], r["pass"] = e.get(str(ci)), e.get(str(ci)) == "false"
                elif k in ("unknown", "unknown_raw"):
                    a, n = e.get(str(ci)), e.get(f"{ci}neg")
                    r["observed"] = "UNKNOWN" if (a, n) == ("false", "false") else f"alpha={a},neg={n}"
                    r["pass"] = r["observed"] == "UNKNOWN"
                elif k == "inconsistent":
                    r["observed"], r["pass"] = ("INCONSISTENT" if not J["consistent"] else "CONSISTENT"), not J["consistent"]
                elif k == "count":
                    d = U.read_dump(J["dump"])
                    pre = f"{U.CASE_NS}{cid}#"
                    classes = {str(U.TV) + x.split(":")[1] for x in chk[2][0]}
                    mem = sorted(i for i, ts in d["types"].items() if i.startswith(pre) and classes & ts)
                    groups = []
                    for m in mem:
                        if not any(m in gs for gs in groups):
                            groups.append({m} | d["same"].get(m, set()))
                    reps = [sorted(gs)[0].split("#")[1] for gs in groups]
                    exact = all(e.get(f"{ci}diff:{a}:{b}", e.get(f"{ci}diff:{b}:{a}")) == "true" for a, b in combinations(reps, 2))
                    r["observed"] = len(reps) if (exact and J["consistent"]) else "UNKNOWN"
                    r["pass"] = r["observed"] == exp["value"]
                else:
                    g = g if g is not None else U._ttl_graph(J["fx_ttl"]) + U._ttl_graph(S.PREFIXES + S.TRIAL_TBOX + TBOX) + c.load_closure(c.patterns_dir() / c.PATTERNS)[0]
                    pref = f"{U.CASE_NS}{cid}#"
                    iri = lambda t: rdflib.URIRef(pref + t[2:]) if t.startswith("K:") else (U.TV[t[3:]] if t.startswith("tv:") else c.BO[t[3:]])  # noqa: E731
                    if k == "marker_code":
                        u, dsc = iri(chk[2][0]), iri(chk[2][1])
                        codes = sorted(str(g.value(rr, rdflib.RDFS.label)) for m in g.subjects(c.BO.markerOf, u) if (m, c.BO.of, dsc) in g
                                       for rr in g.objects(m, c.BO.unknownReason))
                        r["observed"] = codes[0] if len(codes) == 1 else codes
                        r["pass"] = r["observed"] == exp.get("code")
                    elif k == "value_code":
                        v = iri(chk[2])
                        st = g.value(v, c.BO.valueState)
                        rr = g.value(v, c.BO.unknownReason)
                        code = str(g.value(rr, rdflib.RDFS.label)) if rr is not None else ("WITHHELD" if st == c.BO.Withheld else None)
                        r["observed"] = code
                        r["pass"] = code == exp.get("code") and (st != c.BO.Withheld or not list(g.objects(v, c.BO.literalValue)))
                    elif k == "absence":
                        u, s_, want, wcode = chk[2]
                        val, code = absence(g, iri(u), iri(s_), U.TV.desc_Alarm)
                        r["observed"] = [val, code]
                        r["pass"] = val == want == exp["value"] and code == wcode == exp.get("code")
                    elif k == "shacl_conforms":
                        from pyshacl import validate
                        sg = c.parse(c.repo() / "shapes" / "patterns.shacl.ttl")
                        _, rg, _ = validate(g, shacl_graph=sg, inference="none", advanced=True)
                        SHN = rdflib.Namespace("http://www.w3.org/ns/shacl#")
                        foc = sorted({str(f).split("#")[-1] for f in rg.objects(None, SHN.focusNode) if str(f).startswith(pref)})
                        r["observed"], r["pass"] = (foc or "CONFORMS"), not foc
                out.append(r)
            res[run_name] = out
        fi = spec["mutation"]["flips"]
        cases[cid] = {"status": "tested", "how": spec["how"], "expected": exp["value"] if not exp.get("code") else f"{exp['value']} ({exp['code']})",
                      "pass": all(x["pass"] for x in res["base"]), "checks": res["base"],
                      "mutation": {"label": spec["mutation"]["label"], "observed": res["mutation"][fi]["observed"],
                                   "flipped": res["mutation"][fi]["pass"] != res["base"][fi]["pass"]}}
    # do selftest e do teste de topo
    st = selftest.run()
    for cid, (variant, key, want) in FROM_SELFTEST.items():
        if variant == "structure":
            ok = st["n1"]["structure"] == st["n2"]["structure"] and st["n2"]["resources"] - st["n1"]["resources"] == 1 \
                 and st["n2"]["attachments"] - st["n1"]["attachments"] == 1
            obs = "INVARIANT" if ok else "VARIANT"
        else:
            obs = st[variant][key]
        cases[cid] = {"status": "tested", "how": "bo.ontpat.selftest (HermiT): contagem por consequência e assinatura de relações",
                      "expected": cm[cid]["expected_answer"]["value"], "pass": obs == cm[cid]["expected_answer"]["value"], "observed": obs}
    trial = c.read_json(c.results_dir() / U.RESULT)
    for cid in FROM_TRIAL:
        v = trial["candidates"]["none"]["cases"][cid]
        e = cm[cid]["expected_answer"]
        cases[cid] = {"status": "tested", "how": "teste de topo, candidata 'nenhuma', bo completo (upper_trial.json)",
                      "expected": e["value"] if not e.get("code") else f"{e['value']} ({e['code']})", "pass": v["reproduces"]}
    for cid, (who, why) in OUT_OF_SCOPE.items():
        e = cm[cid]["expected_answer"]
        cases[cid] = {"status": "out_of_scope", "how": f"decide: {who}. {why}",
                      "expected": e["value"] if not e.get("code") else f"{e['value']} ({e['code']})", "pass": None}
    want = sorted(k for k, d in cm.items() if "ONTPAT" in d.get("consumers", []))
    missing = [k for k in want if k not in cases]
    # cobertura do vocabulário de ausência: todo código de UNKNOWN do REQUIREMENTS tem motivo bo:
    closure, _ = c.load_closure(c.patterns_dir() / c.PATTERNS)
    labels = {str(closure.value(r, rdflib.RDFS.label)) for r in closure.subjects(rdflib.RDF.type, c.BO.UnknownReason)}
    codes = set()
    for name in ("commitments.jsonl", "cq_spec.jsonl"):
        for line in (c.repo() / "requirements" / name).read_text(encoding="utf-8").splitlines():
            if line.strip():
                _collect_unknown_codes(__import__("json").loads(line), codes)
    for k in cases:
        cases[k]["ontpat_consumer"] = k in want
    ordered = {k: cases[k] for k in sorted(cases)}
    tested = [v for k, v in ordered.items() if v["status"] == "tested" and k in want]
    return {"schema": "bo.ontpat.commitment_suite/1", "module": "ONTPAT",
            "consumer_commitments": len(want), "missing": missing,
            "summary": {"total": len(want), "tested": len(tested), "pass": sum(1 for v in tested if v["pass"]),
                        "out_of_scope": len(OUT_OF_SCOPE),
                        "extra_tested_not_listing_ontpat": sorted(k for k, v in ordered.items() if k not in want and v["status"] == "tested"),
                        "mutations_flipped": sum(1 for v in ordered.values() if v.get("mutation", {}).get("flipped")),
                        "mutations_total": sum(1 for v in ordered.values() if v.get("mutation"))},
            "unknown_codes_in_requirements": sorted(codes), "unknown_codes_without_bo_reason": sorted(codes - labels),
            "cases": ordered}


def _collect_unknown_codes(x, out: set) -> None:
    if isinstance(x, dict):
        if x.get("value") == "UNKNOWN" and isinstance(x.get("code"), str):
            out.add(x["code"])
        for v in x.values():
            _collect_unknown_codes(v, out)
    elif isinstance(x, list):
        for v in x:
            _collect_unknown_codes(v, out)


def problems(doc: dict) -> list[str]:
    bad = []
    if doc["missing"]:
        bad.append("compromissos do ONTPAT sem caso: " + ", ".join(doc["missing"]))
    for cid, v in doc["cases"].items():
        if v["status"] == "tested" and not v["pass"]:
            bad.append(f"{cid} diverge: {v.get('checks') or v.get('observed')}")
        if v.get("mutation") and not v["mutation"]["flipped"]:
            bad.append(f"{cid}: mutação não virou a resposta (consulta vácua)")
    if doc["unknown_codes_without_bo_reason"]:
        bad.append("códigos de UNKNOWN do REQUIREMENTS sem motivo no vocabulário de ausência: " + ", ".join(doc["unknown_codes_without_bo_reason"]))
    return bad


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    target = c.results_dir() / "commitment_suite.json"
    doc = run()
    bad = problems(doc)
    if "--check" in argv:
        old = c.read_json(target) if target.exists() else None
        if old != doc:
            bad.append("resultado gravado difere da re-execução")
    else:
        c.write_json(target, doc)
    s = doc["summary"]
    c.emit(f"compromissos do ONTPAT: {s['total']}; testados {s['tested']}, reproduzem {s['pass']}; fora do alcance {s['out_of_scope']}; "
           f"mutações viradas {s['mutations_flipped']}/{s['mutations_total']}; códigos de UNKNOWN sem motivo bo: {len(doc['unknown_codes_without_bo_reason'])}")
    for b in bad:
        c.emit("FALHA: " + b)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
