"""Caso adversarial BUCKET: contêiner x dono da configuração x alcance efetivo; conta x contêiner."""

from ..model import cm, fx, ground

CONS = ["GRAIN", "GRAIN-REPRO", "PILOT-STO-ORACLE", "DOMAIN-CONTRACTS", "AXIOMS", "SEMANTIC-REGRESSION"]

G_FACET = [
    ground("aws", "contêiner = aws_s3_bucket; versionamento como recurso separado aws_s3_bucket_versioning, que referencia o contêiner: faceta do contêiner apesar de ser recurso Terraform próprio"),
    ground("google", "contêiner = google_storage_bucket; versionamento é bloco versioning{} embutido: mesma faceta, outra embalagem"),
    ground("oci", "contêiner = oci_objectstorage_bucket; versionamento é atributo do próprio recurso"),
]
G_OWNER = [
    ground("azurerm", "o versionamento é declarado na conta (azurerm_storage_account, blob_properties.versioning_enabled) e vale para todos os contêineres (azurerm_storage_container) dela: dono = conta, alcance = cada contêiner"),
    ground("aws", "bloqueio de acesso público de nível de conta (aws_s3_account_public_access_block) vale para todos os contêineres da conta; o de contêiner (aws_s3_bucket_public_access_block) só para um"),
]
G_ACCOUNT = [
    ground("azurerm", "azurerm_storage_container vive dentro de azurerm_storage_account e é apagado com ela: componente; a conta tem configuração própria (replicação, rede, versionamento)"),
    ground("aws", "não há recurso de namespace configurável acima do contêiner: o contêiner é entidade (a conta é só contexto de identidade)"),
    ground("google", "não há namespace de armazenamento configurável no provider; o projeto é escopo, não dono das configurações do contêiner"),
    ground("oci", "o namespace de armazenamento existe na API, com metadados próprios (oci_objectstorage_namespace_metadata), mas o contêiner não é apagado com ele: verificar se é escopo ou pai"),
]
G_EFFECT = [
    ground("aws", "com o bloqueio de nível de conta ligado, a política pública do contêiner não tem efeito"),
    ground("azurerm", "allow_nested_items_to_be_public=false na conta impede que container_access_type público tenha efeito"),
    ground("google", "public_access_prevention=enforced no contêiner, ou a restrição de organização equivalente, impede concessão pública"),
]


def _ns_two_containers(fid, summary, setting_kind="versioning", extra_attrs=()):
    return fx(fid, summary,
              "ns1:storage_namespace c1:object_container c2:object_container s1:storage_setting",
              ["c1 container_in ns1", "c2 container_in ns1", "s1 setting_declared_on ns1", "s1 setting_owned_by ns1"],
              [f"s1.setting_kind={setting_kind}", "s1.versioning=enabled"] + list(extra_attrs))


C = [
    cm("CMT-BKT-P01", "BUCKET", "positive", "invariant",
       "Uma configuração cujo dono é o contêiner é faceta do contêiner, quer o código a escreva como bloco "
       "embutido, quer como recurso separado que referencia o contêiner; a decomposição das duas leituras é a mesma.",
       "unidades(base) == unidades(variante): c1 ENTITY; s1 FACET com owner=c1 e effective_scope={c1}",
       [fx("FX-BKT-P01-INLINE", "versionamento como bloco embutido no contêiner",
           "c1:object_container s1:storage_setting",
           ["s1 setting_declared_on c1", "s1 setting_owned_by c1", "s1 setting_applies_to c1"],
           ["c1.local_key=data_a", "s1.setting_kind=versioning", "s1.versioning=enabled", "s1.declared_inline=true"]),
        fx("FX-BKT-P01-SEPARATE", "versionamento como recurso separado que referencia o contêiner",
           "c1:object_container s1:storage_setting",
           ["s1 setting_declared_on c1", "s1 setting_owned_by c1", "s1 setting_applies_to c1"],
           ["c1.local_key=data_a", "s1.setting_kind=versioning", "s1.versioning=enabled", "s1.declared_inline=false"])],
       "INVARIANT", "ser faceta depende de identidade e dono, não da embalagem (F1)",
       ["REQ-ENT-01", "REQ-STO-01"], ["F1"], "regra de grão G3 independente da embalagem",
       layer="terraform", grounding=G_FACET, consumers=CONS),
    cm("CMT-BKT-P02", "BUCKET", "positive", "entails",
       "Configuração declarada no namespace, cujo dono é o namespace, vale para todos os contêineres dele: o "
       "alcance efetivo é o conjunto dos contêineres, e a configuração continua faceta do namespace, não de "
       "cada contêiner.",
       "effective_scope(s1) = {c1, c2} AND owner(s1) = ns1 AND NOT facet_of(s1, c1) AND NOT facet_of(s1, c2)",
       _ns_two_containers("FX-BKT-P02", "versionamento declarado no namespace com dois contêineres"),
       "ENTAILED", "dono e alcance são dados separados (REQ-REL-01); o alcance é derivado da pertença",
       ["REQ-REL-01", "REQ-STO-01"], ["F1"], "separação dono x alcance efetivo",
       grounding=G_OWNER, consumers=CONS),
    cm("CMT-BKT-P03", "BUCKET", "positive", "entails",
       "Onde o contêiner vive dentro de um namespace com ciclo de vida e configuração próprios, namespace e "
       "contêiner são dois indivíduos, e o contêiner é componente do namespace (identidade própria dentro do "
       "pai, ciclo de vida preso a ele).",
       "kind(c1) = COMPONENT AND parent(c1) = ns1 AND lifecycle_controller(c1) = parent AND ns1 != c1",
       fx("FX-BKT-P03", "namespace com um contêiner apagado junto com ele",
          "ns1:storage_namespace c1:object_container",
          ["c1 container_in ns1"],
          ["ns1.local_key=acct_a", "c1.local_key=data_a", "c1.lifecycle_controller=parent"]),
       "ENTAILED", "regra G2: componente por identidade e ciclo de vida, qualquer que seja a cardinalidade",
       ["REQ-STO-01", "REQ-ENT-01", "REQ-LC-01"], ["F1"], "nível de conta x nível de contêiner",
       axes=["identity"], grounding=G_ACCOUNT, consumers=CONS),
    cm("CMT-BKT-N01", "BUCKET", "negative", "rejects",
       "Nenhum indivíduo é ao mesmo tempo namespace de armazenamento e contêiner de objetos.",
       "fixture com x1 de tipo storage_namespace e object_container é inconsistente",
       fx("FX-BKT-N01", "indivíduo declarado namespace e contêiner",
          "x1:storage_namespace+object_container", [], ["x1.local_key=acct_a"]),
       "REJECTED", "disjunção entre tipos rígidos (REQ-ENT-02)", ["REQ-ENT-02", "REQ-STO-01"], ["F9", "F1"],
       "disjunção namespace x contêiner", code="INCONSISTENT", consumers=CONS),
    cm("CMT-BKT-N02", "BUCKET", "negative", "not_entails",
       "Bloqueio de acesso público no nível do namespace não vira acesso público efetivo porque o contêiner "
       "declara permissão pública: o efetivo é o mais restritivo dos níveis em que o provedor declara essa "
       "precedência.",
       "NOT effective_public_access(c1) = allowed (o efetivo é blocked)",
       fx("FX-BKT-N02", "namespace bloqueia, contêiner permite",
          "ns1:storage_namespace c1:object_container s1:storage_setting s2:storage_setting",
          ["c1 container_in ns1", "s1 setting_owned_by ns1", "s1 setting_applies_to c1",
           "s2 setting_owned_by c1", "s2 setting_applies_to c1"],
          ["s1.setting_kind=public_access", "s1.public_access=blocked",
           "s2.setting_kind=public_access", "s2.public_access=allowed"]),
       "NOT_ENTAILED", "bloqueio de nível superior não vira permissão (análogo a deny não virar allow)",
       ["REQ-REL-01", "REQ-STO-01"], ["F1"], "precedência entre níveis de configuração",
       layer="evaluation", grounding=G_EFFECT, consumers=CONS),
    cm("CMT-BKT-N03", "BUCKET", "negative", "rejects",
       "Configuração cujo dono é o namespace não pode ser registrada como faceta de um único contêiner: isso "
       "perde o efeito sobre os outros contêineres e contradiz a evidência de dono.",
       "unidade s1 com kind=FACET e owner=c1 é rejeitada (dono declarado diverge da evidência owner=ns1)",
       _ns_two_containers("FX-BKT-N03", "versionamento do namespace candidato a faceta de c1"),
       "REJECTED", "o dono vem da evidência, não de onde o código o escreve", ["REQ-REL-01", "REQ-ENT-01"],
       ["F1"], "dono da configuração conferido contra a evidência", code="SHACL_VIOLATION",
       grounding=G_OWNER[:1], consumers=CONS),
    cm("CMT-BKT-U01", "BUCKET", "unknown", "unknown",
       "Se a configuração de acesso público do namespace não foi lida, o acesso público efetivo do contêiner é "
       "UNKNOWN, mesmo que o contêiner declare permissão ou bloqueio próprio.",
       "effective_public_access(c1) = UNKNOWN (nem allowed nem blocked)",
       fx("FX-BKT-U01", "contêiner lido, configuração do namespace não lida",
          "ns1:storage_namespace c1:object_container s2:storage_setting",
          ["c1 container_in ns1", "s2 setting_owned_by c1", "s2 setting_applies_to c1"],
          ["s2.setting_kind=public_access", "s2.public_access=allowed"],
          complete=False, not_read=["ns1.setting"]),
       "UNKNOWN", "o nível superior pode bloquear; sem lê-lo não há decisão", ["REQ-ABS-01", "REQ-REL-01"],
       ["F1", "S1"], "UNKNOWN sob leitura parcial de nível superior", code="INCOMPLETE_READ",
       layer="evaluation", grounding=G_EFFECT, consumers=CONS),
    cm("CMT-BKT-U02", "BUCKET", "unknown", "unknown",
       "Configuração declarada como recurso separado cuja referência ao contêiner não foi resolvida tem grão "
       "UNKNOWN com a evidência que falta; nunca cai em entidade por exclusão.",
       "kind(s1) = UNKNOWN AND missing_evidence(s1) contém owner",
       fx("FX-BKT-U02", "versionamento separado com referência não resolvida",
          "c1:object_container s1:storage_setting", [],
          ["s1.setting_kind=versioning", "s1.versioning=enabled", "s1.declared_inline=false"],
          complete=False, not_read=["s1.reference"]),
       "UNKNOWN", "regra G0: evidência de dono ausente dá UNKNOWN", ["REQ-ENT-01", "REQ-ABS-01"], ["F1"],
       "saída UNKNOWN do grão", code="MISSING_EVIDENCE", consumers=CONS),
]
