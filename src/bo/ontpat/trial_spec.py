"""Especificação do teste de ontologia de topo (S2): regra de decisão, alinhamentos mínimos e casos.

A REGRA DE DECISÃO abaixo foi escrita e versionada ANTES da primeira execução do teste (o commit que a
introduz não contém results/ONTPAT/upper_trial.json). Mudá-la depois de ver resultado é ajuste e tem de
ser declarado como emenda adaptativa (PLANO §9.5).

As respostas esperadas NÃO estão aqui: são lidas de requirements/commitments.jsonl (REQUIREMENTS, congelado).
Aqui está só a operacionalização de cada compromisso em OWL: a fixture levantada nos padrões do bo e as
consultas (axiomas cuja consequência o HermiT decide).
"""

from __future__ import annotations

DECISION_RULE_VERSION = "1"
DECISION_RULE_WRITTEN_AT = "2026-11-02T23:05:00-03:00"
DECISION_RULE = [
    ("D1", "Elegível só a candidata que, com o seu alinhamento mínimo de melhor esforço, reproduz a resposta "
           "esperada de TODOS os compromissos com eixo identidade, tempo ou papel do REQUIREMENTS (16), e do caso "
           "extra CMT-CFG-N01, com os axiomas do bo completos."),
    ("D2", "Elegível só se o fecho bo-patterns + candidata + alinhamento for OWL 2 DL (ROBOT validate-profile), "
           "for consistente com o ABox de exemplo e se o alinhamento não exigir punning nem metamodelagem "
           "(bo.ontpat.no_punning)."),
    ("D3", "Entre as elegíveis, ganha a que tem mais PROTEÇÕES PRÓPRIAS: casos cuja resposta esperada continua "
           "sendo obtida com os axiomas de exclusão do bo retirados (disjunção de classes e de propriedades, "
           "diferença de indivíduos, irreflexividade, assimetria), descontados os que 'nenhuma' também obtém sem "
           "eles. Mede o que a ontologia de topo protege sozinha contra um reparo que apague axiomas do bo (F9). "
           "Não conta inferências no tradutor."),
    ("D4", "Empate em D3 (inclusive zero a zero): ganha a de menor custo, nesta ordem: (a) desajustes "
           "categoriais declarados no alinhamento; (b) axiomas lógicos no fecho de um caso típico; (c) tempo "
           "total do HermiT no teste. 'Nenhuma' disputa como as outras; não é escolhida por não gerar inferência, "
           "só se perder em D3 ninguém e custar menos em D4."),
]

ABLATED_PREDICATES = ("owl:disjointWith", "owl:propertyDisjointWith", "owl:differentFrom")
ABLATED_TYPES = ("owl:AllDisjointClasses", "owl:AllDifferent", "owl:AllDisjointProperties",
                 "owl:IrreflexiveProperty", "owl:AsymmetricProperty")
ABLATED_OTHER = ("owl:disjointUnionOf (substituído por nada: as subclasses já estão declaradas)",)

CANDIDATE_FILES = {
    "bfo": ("bfo2020/bfo-core.ttl", "BFO 2020 (ISO/IEC 21838-2), release-2024-01-29"),
    "dul": ("dul/DUL.ttl", "DOLCE+DnS Ultralite 4.2"),
    "gufo": ("gufo/gufo.ttl", "gUFO 1.0.0"),
    "none": (None, "nenhuma ontologia de topo"),
}

PREFIXES = """@prefix rdf:  <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix owl:  <http://www.w3.org/2002/07/owl#> .
@prefix xsd:  <http://www.w3.org/2001/XMLSchema#> .
@prefix prov: <http://www.w3.org/ns/prov#> .
@prefix bo:   <https://w3id.org/brevops/ontology#> .
@prefix tv:   <https://example.org/bo-trial/vocab#> .
@prefix obo:  <http://purl.obolibrary.org/obo/> .
@prefix dul:  <http://www.ontologydesignpatterns.org/ont/dul/DUL.owl#> .
@prefix gufo: <http://purl.org/nemo/gufo#> .
"""

# Alinhamento mínimo de melhor esforço por candidata: só as categorias que os eixos identidade, tempo e papel
# exercitam (unidade e seus tipos, descrição, estado observado, observação, eventos, parte-todo, ciclo de vida).
# Cada desajuste é declarado: categoria que contradiz a definição da candidata ou que impede usar uma categoria
# dela num eixo.
ALIGNMENTS = {
    "bfo": {
        "ttl": """
bo:Unit rdfs:subClassOf obo:BFO_0000031 .                 # generically dependent continuant
bo:ConfigurationDescription rdfs:subClassOf obo:BFO_0000031 .
bo:ObservedState rdfs:subClassOf obo:BFO_0000031 .
bo:Observation rdfs:subClassOf obo:BFO_0000015 .          # process
bo:LifecycleEvent rdfs:subClassOf obo:BFO_0000015 .
bo:MappingActivity rdfs:subClassOf obo:BFO_0000015 .
bo:componentOf rdfs:subPropertyOf obo:BFO_0000176 .       # continuant part of
""",
        "misfits": [
            "recurso de nuvem não é entidade material: alinhado a generically dependent continuant (GDC), "
            "concretizado no hardware do provedor",
            "papel do BFO (BFO_0000023) inere só em continuante independente; recurso alinhado a GDC não porta "
            "papel, logo 'membro de pool' fica sem categoria do BFO (eixo papel sem apoio)",
            "faceta não pode ser qualidade (BFO_0000019), que também exige portador independente: fica GDC, "
            "sem distinção categorial de recurso",
            "vínculo não pode ser qualidade relacional (BFO_0000145) pelo mesmo motivo: fica GDC",
            "estado observado e descrição viram GDC: o BFO não separa descrição, estado e recurso entre si",
        ],
        "role_probe": {
            "label": "papel do BFO portado pelo recurso (vm1 bearer of r1, r1 a role)",
            "ttl": "K:r1 a owl:NamedIndividual , obo:BFO_0000023 .\nK:vm1 obo:BFO_0000196 K:r1 .\n"
                   "obo:BFO_0000196 a owl:ObjectProperty .\n",
            "expect": "consistency",
        },
    },
    "dul": {
        "ttl": """
bo:Resource rdfs:subClassOf dul:Object .
bo:Facet rdfs:subClassOf dul:Quality .
bo:facetOf rdfs:subPropertyOf dul:isQualityOf .
bo:Binding rdfs:subClassOf dul:Situation .
bo:relates rdfs:subPropertyOf dul:isSettingFor .
bo:ConfigurationDescription rdfs:subClassOf dul:Description .
bo:describes rdfs:subPropertyOf dul:describes .
bo:ObservedState rdfs:subClassOf dul:Situation .
bo:stateOf rdfs:subPropertyOf dul:isSettingFor .
bo:Observation rdfs:subClassOf dul:Action .
bo:LifecycleEvent rdfs:subClassOf dul:Event .
bo:MappingActivity rdfs:subClassOf dul:Action .
bo:componentOf rdfs:subPropertyOf dul:isComponentOf .
""",
        "misfits": [
            "papel do DUL é indivíduo (dul:Role, um Concept que classifica): a classe antirrígida 'membro de "
            "pool' do bo não tem contraparte de classe sem punning; o papel do DUL fica num indivíduo à parte",
            "vínculo e estado observado caem os dois em dul:Situation: o DUL não os separa",
            "descrição (dul:Description) é dul:Object, como o recurso: o DUL não separa descrição de recurso",
        ],
        "role_probe": {
            "label": "papel do DUL como Concept que classifica o recurso (vm1 hasRole r1)",
            "ttl": "K:r1 a owl:NamedIndividual , dul:Role .\nK:vm1 dul:hasRole K:r1 .\n"
                   "dul:hasRole a owl:ObjectProperty .\n",
            "expect": "consistency",
        },
    },
    "gufo": {
        "ttl": """
bo:Resource rdfs:subClassOf gufo:FunctionalComplex .
bo:Facet rdfs:subClassOf gufo:IntrinsicMode .
bo:facetOf rdfs:subPropertyOf gufo:inheresIn .
bo:Binding rdfs:subClassOf gufo:Relator .
bo:relates rdfs:subPropertyOf gufo:mediates .
bo:ConfigurationDescription rdfs:subClassOf gufo:Object .
bo:ObservedState rdfs:subClassOf gufo:Situation .
bo:Observation rdfs:subClassOf gufo:Event .
bo:LifecycleEvent rdfs:subClassOf gufo:Event .
bo:MappingActivity rdfs:subClassOf gufo:Event .
bo:createdBy rdfs:subPropertyOf gufo:wasCreatedIn .
bo:endedBy rdfs:subPropertyOf gufo:wasTerminatedIn .
bo:componentOf rdfs:subPropertyOf gufo:isComponentOf .
""",
        "misfits": [
            "o gUFO não tem objeto de informação: a descrição de configuração fica em gufo:Object genérico, sem "
            "disjunção com o recurso",
            "a checagem de rigidez do gUFO é de nível de tipo (tv:BackendMember a gufo:Role): exige punning, que "
            "a regra do projeto proíbe; a rigidez fica na anotação bo:rigidity",
        ],
        "role_probe": {
            "label": "tipo de nível de classe do gUFO (tv:BackendMember a gufo:Role)",
            "ttl": "tv:BackendMember a gufo:Role .\n",
            "expect": "punning",
        },
    },
    "none": {"ttl": "", "misfits": [], "role_probe": None},
}

# Vocabulário de teste (rótulos de trabalho do REQUIREMENTS levados aos padrões do bo) e contexto comum.
TRIAL_TBOX = """
tv:StorageNamespace a owl:Class ; rdfs:subClassOf bo:Resource ; bo:rigidity bo:Rigid .
tv:ObjectContainer a owl:Class ; rdfs:subClassOf bo:Resource ; bo:rigidity bo:Rigid .
tv:AddressableResource a owl:Class ; rdfs:subClassOf bo:IndependentResource ; bo:rigidity bo:Rigid .
tv:ComputeInstance a owl:Class ; rdfs:subClassOf tv:AddressableResource ; bo:rigidity bo:Rigid .
tv:NetworkInterface a owl:Class ; rdfs:subClassOf bo:Resource ; bo:rigidity bo:Rigid .
tv:BackendPool a owl:Class ; rdfs:subClassOf bo:IndependentResource ; bo:rigidity bo:Rigid .
tv:DbInstance a owl:Class ; rdfs:subClassOf bo:IndependentResource ; bo:rigidity bo:Rigid .
tv:Principal a owl:Class ; rdfs:subClassOf bo:IndependentResource ; bo:rigidity bo:Rigid .
tv:PermissionSet a owl:Class ; rdfs:subClassOf bo:IndependentResource ; bo:rigidity bo:Rigid .
tv:ScopeNode a owl:Class ; rdfs:subClassOf bo:IndependentResource ; bo:rigidity bo:Rigid .
tv:NotificationTopic a owl:Class ; rdfs:subClassOf bo:IndependentResource ; bo:rigidity bo:Rigid .
tv:Alarm a owl:Class ; rdfs:subClassOf bo:IndependentResource ; bo:rigidity bo:Rigid .
[] a owl:AllDisjointClasses ; owl:members ( tv:StorageNamespace tv:ObjectContainer tv:ComputeInstance tv:NetworkInterface
    tv:BackendPool tv:DbInstance tv:Principal tv:PermissionSet tv:ScopeNode tv:NotificationTopic tv:Alarm ) .

tv:memberOfPool a owl:ObjectProperty ; rdfs:subPropertyOf bo:references ; rdfs:domain bo:IndependentResource ; rdfs:range tv:BackendPool .
tv:BackendMember a owl:Class ; bo:rigidity bo:AntiRigid ;
    owl:equivalentClass [ a owl:Class ; owl:intersectionOf ( tv:AddressableResource [ a owl:Restriction ; owl:onProperty tv:memberOfPool ; owl:someValuesFrom tv:BackendPool ] ) ] .
tv:replicaOf a owl:ObjectProperty , owl:IrreflexiveProperty , owl:AsymmetricProperty ; rdfs:subPropertyOf bo:references ;
    rdfs:domain tv:DbInstance ; rdfs:range tv:DbInstance .
tv:Replica a owl:Class ; bo:rigidity bo:AntiRigid ;
    owl:equivalentClass [ a owl:Class ; owl:intersectionOf ( tv:DbInstance [ a owl:Restriction ; owl:onProperty tv:replicaOf ; owl:someValuesFrom tv:DbInstance ] ) ] .
tv:notifies a owl:ObjectProperty ; rdfs:subPropertyOf bo:references ; rdfs:domain tv:Alarm ; rdfs:range bo:Unit .
tv:NotificationDestination a owl:Class ; bo:rigidity bo:AntiRigid ;
    owl:equivalentClass [ a owl:Class ; owl:intersectionOf ( bo:Unit [ a owl:Restriction ; owl:onProperty [ owl:inverseOf tv:notifies ] ; owl:someValuesFrom tv:Alarm ] ) ] .

tv:Assignment a owl:Class ; rdfs:subClassOf bo:Binding ; bo:rigidity bo:Rigid .
tv:assignsPrincipal a owl:ObjectProperty , owl:FunctionalProperty ; rdfs:subPropertyOf bo:relates ; rdfs:domain tv:Assignment ; rdfs:range tv:Principal .
tv:assignsSet a owl:ObjectProperty , owl:FunctionalProperty ; rdfs:subPropertyOf bo:relates ; rdfs:domain tv:Assignment ; rdfs:range tv:PermissionSet .
tv:atScope a owl:ObjectProperty , owl:FunctionalProperty ; rdfs:subPropertyOf bo:relates ; rdfs:domain tv:Assignment ; rdfs:range tv:ScopeNode .
tv:Assignment owl:hasKey ( tv:assignsPrincipal tv:assignsSet tv:atScope ) .

tv:versioningStatus a owl:ObjectProperty , owl:FunctionalProperty ; rdfs:range tv:VersioningStatus .
tv:VersioningStatus a owl:Class ; bo:rigidity bo:Rigid ; owl:equivalentClass [ a owl:Class ; owl:oneOf ( tv:Enabled tv:Disabled ) ] .
tv:Enabled a owl:NamedIndividual , tv:VersioningStatus .
tv:Disabled a owl:NamedIndividual , tv:VersioningStatus .
[] a owl:AllDifferent ; owl:distinctMembers ( tv:Enabled tv:Disabled ) .
tv:desc_versioning a owl:NamedIndividual , bo:PropertyDescriptor ; bo:descriptorKey "versioningStatus" ; bo:describesProperty tv:versioningStatus .

tv:prov_a a owl:NamedIndividual , bo:Provider .
tv:acct_a a owl:NamedIndividual , bo:SyntheticAccount ; bo:ofProvider tv:prov_a .
tv:loc_r1 a owl:NamedIndividual , bo:Location ; bo:ofProvider tv:prov_a ; bo:locationScope bo:RegionalScope ; bo:locationCode "r1" .
tv:loc_r2 a owl:NamedIndividual , bo:Location ; bo:ofProvider tv:prov_a ; bo:locationScope bo:RegionalScope ; bo:locationCode "r2" .
tv:pt_container a owl:NamedIndividual , bo:ProviderType ; bo:ofProvider tv:prov_a ; bo:artifactName "type_container" .
tv:pt_namespace a owl:NamedIndividual , bo:ProviderType ; bo:ofProvider tv:prov_a ; bo:artifactName "type_namespace" .
tv:pt_instance a owl:NamedIndividual , bo:ProviderType ; bo:ofProvider tv:prov_a ; bo:artifactName "type_instance" .
"""

# identidade comum de um recurso de teste: <conta, provedor, localização, tipo, chave local>
def ident(loc="tv:loc_r1", ptype="tv:pt_container", key="data_a", inc=None):
    s = f"bo:inAccount tv:acct_a ; bo:ofProvider tv:prov_a ; bo:inLocation {loc} ; bo:hasProviderType {ptype} ; bo:localKey \"{key}\""
    if inc:
        s += f" ; bo:incarnationKey \"{inc}\""
    return s


# Consultas. Cada item: (tipo, rótulo, triplas). Tipos:
#   ent      as triplas são consequência            not_ent  não são consequência
#   unknown  nem as triplas nem a negação delas são consequência
#   consistent / inconsistent   (o caso inteiro)
#   oc_reject / oc_accept       OntoClean (regra corrigida) sobre a hierarquia inferida, com a mutação de TBox dada
#   count    (classe, n): indivíduos nomeados da fixture na classe, todos distintos por consequência
#   ask      consulta SPARQL ASK sobre o grafo asserido + tipos inferidos (regime declarado), valor esperado
#   code     motivo (bo:UnknownReason) que acompanha o desconhecido, lido da marca
# A primeira consulta de cada variante é a principal (dá o rótulo observado); as outras são condições.
DRIFT_ASK = """ASK {
  ?d a bo:ConfigurationDescription ; bo:describes ?u ; bo:hasSettingValue ?a .
  ?o a bo:ObservedState ; bo:stateOf ?u ; bo:hasSettingValue ?b .
  ?a bo:of ?desc ; bo:valueState bo:Known ; bo:iriValue ?x .
  ?b bo:of ?desc ; bo:valueState bo:Known ; bo:iriValue ?y .
  FILTER (?x != ?y) }"""

CASES = {
    "CMT-BKT-P03": [{
        "variant": "FX-BKT-P03",
        "fixture": f"""
K:ns1 a owl:NamedIndividual , tv:StorageNamespace , bo:IndependentResource ; {ident(ptype='tv:pt_namespace', key='acct_a', inc='inc-ns1')} .
K:c1 a owl:NamedIndividual , tv:ObjectContainer ; bo:componentOf K:ns1 ; bo:occurrenceKey "name=data_a" .
""",
        "checks": [("ent", "kind(c1)=COMPONENT", [("K:c1", "a", "bo:Component")]),
                   ("ent", "lifecycle_controller(c1)=parent", [("K:c1", "bo:lifecycleControlledBy", "K:ns1")]),
                   ("ent", "ns1 != c1", [("K:c1", "owl:differentFrom", "K:ns1")])],
        "mutation": {"label": "contêiner só referencia o namespace (sem parte-todo)",
                     "replace": ("bo:componentOf K:ns1 ; bo:occurrenceKey \"name=data_a\"", "bo:references K:ns1"),
                     "flips": 0},
    }],
    "CMT-NIC-P05": [{
        "variant": "FX-NIC-P05-ORDER-A+B",
        "fixture": f"""
K:vm1 a owl:NamedIndividual , tv:ComputeInstance ; {ident(ptype='tv:pt_instance', key='vm_a', inc='inc-vm1')} .
K:nic1a a owl:NamedIndividual , tv:NetworkInterface , bo:Component ; bo:componentOf K:vm1 ; bo:occurrenceKey "device_index=0" ; bo:textPosition 1 .
K:nic2a a owl:NamedIndividual , tv:NetworkInterface , bo:Component ; bo:componentOf K:vm1 ; bo:occurrenceKey "device_index=1" ; bo:textPosition 2 .
K:nic1b a owl:NamedIndividual , tv:NetworkInterface , bo:Component ; bo:componentOf K:vm1 ; bo:occurrenceKey "device_index=0" ; bo:textPosition 2 .
K:nic2b a owl:NamedIndividual , tv:NetworkInterface , bo:Component ; bo:componentOf K:vm1 ; bo:occurrenceKey "device_index=1" ; bo:textPosition 1 .
""",
        "checks": [("ent", "occ(nic1) igual em A e B", [("K:nic1a", "owl:sameAs", "K:nic1b")]),
                   ("ent", "occ(nic2) igual em A e B", [("K:nic2a", "owl:sameAs", "K:nic2b")]),
                   ("ent", "nic1 != nic2", [("K:nic1a", "owl:differentFrom", "K:nic2b")])],
        "mutation": {"label": "chave de ocorrência com a posição textual",
                     "replace_all": [('"device_index=0" ; bo:textPosition 1', '"device_index=0;pos=1" ; bo:textPosition 1'),
                                     ('"device_index=0" ; bo:textPosition 2', '"device_index=0;pos=2" ; bo:textPosition 2')],
                     "flips": 0},
    }],
    "CMT-LB-P04": [
        {"variant": "FX-LB-P04 (membro)",
         "fixture": f"""
K:vm1 a owl:NamedIndividual , tv:ComputeInstance ; {ident(ptype='tv:pt_instance', key='vm_a', inc='inc-vm1')} ; tv:memberOfPool K:pool1 .
K:pool1 a owl:NamedIndividual , tv:BackendPool ; {ident(ptype='tv:pt_instance', key='pool_a', inc='inc-pool1')} .
""",
         "checks": [("ent", "type(vm1)=compute_instance com membro", [("K:vm1", "a", "tv:ComputeInstance")]),
                    ("ent", "vm1 desempenha o papel", [("K:vm1", "a", "tv:BackendMember")])]},
        {"variant": "FX-LB-P04 (depois de sair do pool)",
         "fixture": f"""
K:vm1 a owl:NamedIndividual , tv:ComputeInstance ; {ident(ptype='tv:pt_instance', key='vm_a', inc='inc-vm1')} .
K:pool1 a owl:NamedIndividual , tv:BackendPool ; {ident(ptype='tv:pt_instance', key='pool_a', inc='inc-pool1')} .
""",
         "checks": [("ent", "type(vm1)=compute_instance sem membro", [("K:vm1", "a", "tv:ComputeInstance")]),
                    ("not_ent", "vm1 não é inferida membro", [("K:vm1", "a", "tv:BackendMember")])],
         "mutation": {"label": "instância ⊑ membro de pool (erro OntoClean)", "tbox": "tv:ComputeInstance rdfs:subClassOf tv:BackendMember .\n",
                      "flips": 1}},
    ],
    "CMT-LB-N01": [{
        "variant": "FX-LB-N01",
        "fixture": f"""
K:vm9 a owl:NamedIndividual , tv:ComputeInstance ; {ident(ptype='tv:pt_instance', key='vm_z', inc='inc-vm9')} .
""",
        "checks": [("oc_reject", "OntoClean reprova instância ⊑ membro de pool", "tv:ComputeInstance rdfs:subClassOf tv:BackendMember .\n"),
                   ("not_ent", "vm9 sem pool não é inferida membro", [("K:vm9", "a", "tv:BackendMember")])],
    }],
    "CMT-DB-P02": [{
        "variant": "FX-DB-P02",
        "fixture": f"""
K:i1 a owl:NamedIndividual , tv:DbInstance ; {ident(ptype='tv:pt_instance', key='db_1', inc='inc-i1')} .
K:i2 a owl:NamedIndividual , tv:DbInstance ; {ident(ptype='tv:pt_instance', key='db_2', inc='inc-i2')} ; tv:replicaOf K:i1 .
""",
        "checks": [("count", "COUNT db_instance", ("tv:DbInstance", None)),
                   ("ent", "replica_of(i2,i1) e type(i2)=db_instance", [("K:i2", "tv:replicaOf", "K:i1"), ("K:i2", "a", "tv:DbInstance")]),
                   ("ent", "i2 desempenha o papel réplica", [("K:i2", "a", "tv:Replica")])],
        "mutation": {"label": "réplica contada como instância à parte com a mesma chave (mesma encarnação)",
                     "replace_all": [('"db_2" ; bo:incarnationKey "inc-i2"', '"db_1" ; bo:incarnationKey "inc-i1"')],
                     "flips": 0},
    }],
    "CMT-TAX-P01": [{
        "variant": "FX-TAX-P01",
        "fixture": f"""
K:vm1 a owl:NamedIndividual , tv:ComputeInstance ; {ident(ptype='tv:pt_instance', key='vm_a', inc='inc-vm1')} ; tv:memberOfPool K:pool1 .
K:pool1 a owl:NamedIndividual , tv:BackendPool ; {ident(ptype='tv:pt_instance', key='pool_a', inc='inc-pool1')} .
""",
        "checks": [("oc_accept", "OntoClean aceita membro de pool ⊑ recurso endereçável", ""),
                   ("ent", "vm1 membro é recurso endereçável", [("K:vm1", "a", "tv:AddressableResource"), ("K:vm1", "a", "tv:BackendMember")])],
    }],
    "CMT-TAX-N04": [{
        "variant": "FX-TAX-N04",
        "fixture": f"""
K:t1 a owl:NamedIndividual , tv:NotificationTopic ; {ident(ptype='tv:pt_instance', key='topic_1', inc='inc-t1')} .
K:t2 a owl:NamedIndividual , tv:NotificationTopic ; {ident(ptype='tv:pt_instance', key='topic_2', inc='inc-t2')} .
K:al1 a owl:NamedIndividual , tv:Alarm ; {ident(ptype='tv:pt_instance', key='alarm_1', inc='inc-al1')} ; tv:notifies K:t1 .
""",
        "checks": [("oc_reject", "OntoClean reprova tópico ⊑ destino de notificação", "tv:NotificationTopic rdfs:subClassOf tv:NotificationDestination .\n"),
                   ("ent", "t1 notificado é destino", [("K:t1", "a", "tv:NotificationDestination")]),
                   ("not_ent", "t2 não notificado não é destino", [("K:t2", "a", "tv:NotificationDestination")])],
    }],
    "CMT-CFG-P01": [{
        "variant": "FX-CFG-P01",
        "fixture": f"""
K:c1 a owl:NamedIndividual , tv:ObjectContainer , bo:IndependentResource ; {ident(inc='inc-c1')} .
K:d1 a owl:NamedIndividual , bo:ConfigurationDescription ; bo:describes K:c1 ; bo:descriptionSource bo:SourceCode ; bo:hasSettingValue K:v1 .
K:v1 a owl:NamedIndividual , bo:SettingValue ; bo:of tv:desc_versioning ; bo:iriValue tv:Enabled ; bo:valueOrigin bo:Configured ; bo:valueState bo:Known .
K:ob1 a owl:NamedIndividual , bo:Observation ; prov:startedAtTime "2026-11-02T10:00:00-03:00"^^xsd:dateTime ; bo:readCompleteness bo:CompleteRead ; bo:coversScope tv:acct_a .
K:o1 a owl:NamedIndividual , bo:ObservedState ; bo:stateOf K:c1 ; prov:wasGeneratedBy K:ob1 ; bo:hasSettingValue K:v2 .
K:v2 a owl:NamedIndividual , bo:SettingValue ; bo:of tv:desc_versioning ; bo:iriValue tv:Disabled ; bo:valueOrigin bo:Observed ; bo:valueState bo:Known .
""",
        "checks": [("consistent", "desejado e observado divergentes coexistem", None),
                   ("ask", "drift(c1, versioning) = true", (DRIFT_ASK, True))],
        "mutation": {"label": "valores direto no recurso, com propriedade funcional (sem o modelo S1)",
                     "extra": "K:c1 tv:versioningStatus tv:Enabled , tv:Disabled .\n", "flips": 0},
    }],
    "CMT-CFG-N02": [{
        "variant": "FX-CFG-N02",
        "fixture": f"""
K:r1 a owl:NamedIndividual , tv:ObjectContainer , bo:IndependentResource ; {ident(inc='inc-c1')} .
K:r2 a owl:NamedIndividual , tv:ObjectContainer , bo:IndependentResource ; {ident(inc='inc-c1')} .
K:ob1 a owl:NamedIndividual , bo:Observation ; prov:startedAtTime "2026-11-01T10:00:00-03:00"^^xsd:dateTime ; bo:readCompleteness bo:CompleteRead ; bo:coversScope tv:acct_a .
K:ob2 a owl:NamedIndividual , bo:Observation ; prov:startedAtTime "2026-11-02T10:00:00-03:00"^^xsd:dateTime ; bo:readCompleteness bo:CompleteRead ; bo:coversScope tv:acct_a .
K:o1 a owl:NamedIndividual , bo:ObservedState ; bo:stateOf K:r1 ; prov:wasGeneratedBy K:ob1 ; bo:hasSettingValue K:v1 .
K:o2 a owl:NamedIndividual , bo:ObservedState ; bo:stateOf K:r2 ; prov:wasGeneratedBy K:ob2 ; bo:hasSettingValue K:v2 .
K:v1 a owl:NamedIndividual , bo:SettingValue ; bo:of tv:desc_versioning ; bo:iriValue tv:Enabled ; bo:valueOrigin bo:Observed ; bo:valueState bo:Known .
K:v2 a owl:NamedIndividual , bo:SettingValue ; bo:of tv:desc_versioning ; bo:iriValue tv:Disabled ; bo:valueOrigin bo:Observed ; bo:valueState bo:Known .
""",
        "checks": [("not_ent", "NOT c1 != c1' (dois estados, um recurso)", [("K:r1", "owl:differentFrom", "K:r2")]),
                   ("ent", "as duas leituras são o mesmo recurso", [("K:r1", "owl:sameAs", "K:r2")])],
        "mutation": {"label": "instante da leitura como atributo funcional do recurso",
                     "extra": "tv:observedAt a owl:DatatypeProperty , owl:FunctionalProperty .\n"
                              "K:r1 tv:observedAt \"2026-11-01T10:00:00-03:00\"^^xsd:dateTime .\n"
                              "K:r2 tv:observedAt \"2026-11-02T10:00:00-03:00\"^^xsd:dateTime .\n",
                     "flips": 0},
    }],
    "CMT-ID-P01": [{
        "variant": "FX-ID-P01",
        "fixture": f"""
K:c1 a owl:NamedIndividual , tv:ObjectContainer , bo:IndependentResource ; {ident(inc='inc-c1')} .
K:c1after a owl:NamedIndividual , tv:ObjectContainer , bo:IndependentResource ; {ident(inc='inc-c1')} .
K:upd a owl:NamedIndividual , bo:InPlaceUpdate .
K:d1 a owl:NamedIndividual , bo:ConfigurationDescription ; bo:describes K:c1 ; bo:descriptionSource bo:SourceCode .
K:d2 a owl:NamedIndividual , bo:ConfigurationDescription ; bo:describes K:c1after ; bo:descriptionSource bo:SourceCode ; bo:previousVersion K:d1 .
""",
        "checks": [("ent", "after(c1) = c1", [("K:c1", "owl:sameAs", "K:c1after")]),
                   ("ent", "COUNT config_versions(c1) = 2", [("K:d1", "bo:describes", "K:c1"), ("K:d2", "bo:describes", "K:c1"), ("K:d1", "owl:differentFrom", "K:d2")])],
        "mutation": {"label": "mudança no lugar registrada com encarnação nova",
                     "replace_all": [('bo:incarnationKey "inc-c1" .\nK:upd', 'bo:incarnationKey "inc-c1x" .\nK:upd')],
                     "flips": 0},
    }],
    "CMT-ID-P02": [{
        "variant": "FX-ID-P02",
        "fixture": f"""
K:c1 a owl:NamedIndividual , tv:ObjectContainer , bo:IndependentResource ; {ident(inc='inc-c1')} ; bo:replacedBy K:c2 ; bo:endedBy K:rep .
K:c2 a owl:NamedIndividual , tv:ObjectContainer , bo:IndependentResource ; {ident(inc='inc-c2')} .
K:rep a owl:NamedIndividual , bo:Replacement .
""",
        "checks": [("ent", "after(c1) = c2 AND c1 != c2 AND ended(c1)",
                    [("K:c1", "bo:replacedBy", "K:c2"), ("K:c1", "owl:differentFrom", "K:c2"), ("K:c1", "a", "bo:EndedUnit")])],
        "mutation": {"label": "chave só com os 5 componentes (sem encarnação)",
                     "tbox": "bo:IndependentResource owl:hasKey ( bo:inAccount bo:ofProvider bo:inLocation bo:hasProviderType bo:localKey ) .\n",
                     "flips": 0},
    }],
    "CMT-ID-N01": [{
        "variant": "FX-ID-N01",
        "fixture": f"""
K:c1 a owl:NamedIndividual , tv:ObjectContainer , bo:IndependentResource ; {ident(loc='tv:loc_r1', key='data')} .
K:c2 a owl:NamedIndividual , tv:ObjectContainer , bo:IndependentResource ; {ident(loc='tv:loc_r2', key='data')} .
""",
        "checks": [("not_ent", "NOT c1 = c2", [("K:c1", "owl:sameAs", "K:c2")])],
        "mutation": {"label": "chave sem localização (e sem encarnação)",
                     "tbox": "bo:IndependentResource owl:hasKey ( bo:inAccount bo:ofProvider bo:hasProviderType bo:localKey ) .\n",
                     "flips": 0},
    }],
    "CMT-ID-U01": [{
        "variant": "FX-ID-U01",
        "fixture": f"""
K:c1 a owl:NamedIndividual , tv:ObjectContainer , bo:IndependentResource ; {ident(inc='inc-c1')} .
K:c1after a owl:NamedIndividual , tv:ObjectContainer , bo:IndependentResource ; {ident()} .
K:m1 a owl:NamedIndividual , bo:UnknownMarker ; bo:markerOf K:c1after ; bo:of bo:desc_incarnationKey ; bo:valueState bo:Unknown ; bo:unknownReason bo:MissingEvidence .
""",
        "checks": [("unknown", "after(c1) = UNKNOWN", [("K:c1", "owl:sameAs", "K:c1after")]),
                   ("code", "código do desconhecido", ("K:c1after", "bo:desc_incarnationKey"))],
        "mutation": {"label": "evidência de mudança no lugar (mesma encarnação)",
                     "replace_all": [(f"{ident()} .\nK:m1", f"{ident(inc='inc-c1')} .\nK:m1")],
                     "flips": 0},
    }],
    "CMT-ID-U02": [{
        "variant": "FX-ID-U02",
        "fixture": f"""
K:c1 a owl:NamedIndividual , tv:ObjectContainer , bo:IndependentResource ; {ident(loc='tv:loc_r1', key='data', inc='inc-c1')} .
K:c2 a owl:NamedIndividual , tv:ObjectContainer , bo:IndependentResource ; bo:inAccount tv:acct_a ; bo:ofProvider tv:prov_a ; bo:hasProviderType tv:pt_container ; bo:localKey "data" ; bo:incarnationKey "inc-c1" .
K:m2 a owl:NamedIndividual , bo:UnknownMarker ; bo:markerOf K:c2 ; bo:of bo:desc_inLocation ; bo:valueState bo:NotRead ; bo:unknownReason bo:IncompleteRead .
""",
        "checks": [("unknown", "same(c1, c2) = UNKNOWN", [("K:c1", "owl:sameAs", "K:c2")]),
                   ("code", "código do desconhecido", ("K:c2", "bo:desc_inLocation"))],
        "mutation": {"label": "localização de c2 lida (igual à de c1)",
                     "replace_all": [('bo:ofProvider tv:prov_a ; bo:hasProviderType tv:pt_container ; bo:localKey "data" ; bo:incarnationKey "inc-c1" .',
                                      'bo:ofProvider tv:prov_a ; bo:inLocation tv:loc_r1 ; bo:hasProviderType tv:pt_container ; bo:localKey "data" ; bo:incarnationKey "inc-c1" .')],
                     "flips": 0},
    }],
    "CMT-LC-P01": [{
        "variant": "FX-LC-P01",
        "fixture": f"""
K:ns1 a owl:NamedIndividual , tv:StorageNamespace , bo:IndependentResource ; {ident(ptype='tv:pt_namespace', key='acct_a', inc='inc-ns1')} ; bo:endedBy K:del .
K:c1 a owl:NamedIndividual , tv:ObjectContainer ; bo:componentOf K:ns1 ; bo:occurrenceKey "name=data_a" .
K:del a owl:NamedIndividual , bo:Deletion .
""",
        "checks": [("ent", "delete(ns1) ⇒ ended(c1)", [("K:c1", "a", "bo:EndedUnit")])],
        "mutation": {"label": "contêiner só referencia o namespace",
                     "replace": ("bo:componentOf K:ns1 ; bo:occurrenceKey \"name=data_a\"", "bo:references K:ns1"),
                     "flips": 0},
    }],
    "CMT-LC-N01": [{
        "variant": "FX-LC-N01",
        "fixture": f"""
K:p1 a owl:NamedIndividual , tv:Principal ; {ident(ptype='tv:pt_instance', key='p1', inc='inc-p1')} .
K:ps1 a owl:NamedIndividual , tv:PermissionSet ; {ident(ptype='tv:pt_instance', key='ps1', inc='inc-ps1')} .
K:s1 a owl:NamedIndividual , tv:ScopeNode ; {ident(ptype='tv:pt_instance', key='s1', inc='inc-s1')} .
K:a1 a owl:NamedIndividual , tv:Assignment ; tv:assignsPrincipal K:p1 ; tv:assignsSet K:ps1 ; tv:atScope K:s1 ; bo:endedBy K:del .
K:del a owl:NamedIndividual , bo:Deletion .
""",
        "checks": [("not_ent", "delete(a1) ⇏ ended(p1)", [("K:p1", "a", "bo:EndedUnit")]),
                   ("not_ent", "delete(a1) ⇏ ended(ps1)", [("K:ps1", "a", "bo:EndedUnit")])],
        "mutation": {"label": "principal com ciclo de vida controlado pelo vínculo",
                     "extra": "K:p1 bo:lifecycleControlledBy K:a1 .\n", "flips": 0},
    }],
    # extra (não tem eixo de topo, mas é o caso de categoria S1 que uma ontologia de topo poderia proteger)
    "CMT-CFG-N01": [{
        "variant": "FX-CFG-N01",
        "fixture": """
K:x1 a owl:NamedIndividual , bo:ConfigurationDescription , tv:ObjectContainer .
""",
        "checks": [("inconsistent", "x1 descrição e contêiner é inconsistente", None)],
    }],
}

EXTRA_CASES = ("CMT-CFG-N01",)
