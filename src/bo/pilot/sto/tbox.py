"""TBox da fatia sto e as tabelas de realização (o modelo do PILOT-STO-E2E; semente do OWL de escala).

O que está aqui é modelagem, com a base declarada ao lado de cada linha; não é resposta do oráculo:
  - classes neutras da fatia sobre os padrões do ONTPAT (bo:IndependentResource, bo:Facet, bo:Component);
  - o domínio de cada conceito do glossário (a qual classe de configuração ele pertence);
  - a realização por tipo Terraform (qual classe o recurso realiza quando não é contêiner);
  - o descritor de lowering por provedor: tipo do contêiner e do namespace, campo de referência ao dono e os
    valores de contexto de implantação DECLARADOS (sintetizados e marcados no plano, nunca inseridos em silêncio).

Três níveis de axiomatização, um por controle (mesmas classes, mesmas propriedades, mesma entrada):
  c1_table     nenhum axioma: só a tabela das correspondências (o TTL do controle tem só as linhas SSSOM em RDF);
  c2_taxonomy  taxonomia (rdfs:subClassOf) e realizações (descritores, facetOf lido das referências);
  c3_full      c2 + disjunções, propriedades funcionais, domínios por união, cadeias de alcance efetivo
               (scopeAnchor ∘ hasContainer ⊑ appliesTo; hasRule ∘ selectsContainer ⊑ appliesTo;
               facetOfContainer ⊑ appliesTo) e a regra de seleção por prefixo do ciclo de vida do Azure.
"""

from __future__ import annotations

STO = "https://w3id.org/brevops/ontology/sto#"
BO = "https://w3id.org/brevops/ontology#"
CONCEPT = "https://w3id.org/brevops/glossary#"

# ----------------------------------------------------------------------------------------------------------
# Classes
# ----------------------------------------------------------------------------------------------------------
CLASSES = {
    "StorageNamespace": {"parent": "bo:IndependentResource", "kind": "ENTITY", "token": "namespace",
                         "label": "espaço de nomes de armazenamento",
                         "definition": "unidade com identidade própria que contém contêineres de objetos e pode ser dona de configuração que vale para todos eles"},
    "ObjectContainer": {"parent": "bo:IndependentResource", "kind": "ENTITY", "token": "container",
                        "label": "contêiner de objetos",
                        "definition": "unidade com identidade própria que guarda objetos e suas versões e recebe as configurações da fatia"},
    "StorageSetting": {"parent": "bo:Facet", "kind": "FACET", "token": "setting", "label": "configuração de armazenamento",
                       "definition": "faceta de configuração de um contêiner ou de um espaço de nomes, sem identidade própria na API"},
    "VersioningSetting": {"parent": "sto:StorageSetting", "kind": "FACET", "token": "versioning",
                          "label": "configuração de versionamento",
                          "definition": "faceta que decide se versões anteriores dos objetos são guardadas ao sobrescrever ou apagar"},
    "LifecycleSetting": {"parent": "sto:StorageSetting", "kind": "FACET", "token": "lifecycle",
                         "label": "configuração de ciclo de vida",
                         "definition": "faceta com as regras que expiram, apagam ou movem objetos e versões pela idade"},
    "PublicAccessBlockSetting": {"parent": "sto:StorageSetting", "kind": "FACET", "token": "public_access_block",
                                 "label": "bloqueio de acesso público",
                                 "definition": "faceta que impede ou limita que concessões públicas tenham efeito"},
    "AccessGrantSetting": {"parent": "sto:StorageSetting", "kind": "FACET", "token": "access_grant",
                           "label": "concessão de acesso",
                           "definition": "faceta que concede acesso ao contêiner ou aos objetos (ACL, política, nível anônimo)"},
    "AclModeSetting": {"parent": "sto:StorageSetting", "kind": "FACET", "token": "acl_mode",
                       "label": "modo das ACLs",
                       "definition": "faceta que decide se as ACLs por objeto têm efeito e quem é dono dos objetos"},
    "EncryptionSetting": {"parent": "sto:StorageSetting", "kind": "FACET", "token": "encryption",
                          "label": "criptografia padrão",
                          "definition": "faceta que escolhe a criptografia aplicada por padrão aos objetos novos"},
    "NamespaceDefaultsSetting": {"parent": "sto:StorageSetting", "kind": "FACET", "token": "namespace_defaults",
                                 "label": "padrões do espaço de nomes",
                                 "definition": "faceta de padrões do espaço de nomes inteiro (compartimentos padrão de APIs compatíveis)"},
    "LifecycleRule": {"parent": "bo:Component", "kind": "COMPONENT", "token": "lifecycle_rule",
                      "label": "regra de ciclo de vida",
                      "definition": "componente de uma configuração de ciclo de vida: condição, filtro e ação de uma regra"},
}
SETTING_CLASSES = [k for k, v in CLASSES.items() if v["parent"] == "sto:StorageSetting"]
TOKEN_CLASS = {v["token"]: k for k, v in CLASSES.items()}

# Domínio de cada conceito do glossário (rótulo e definição do glossário da fatia). Conceito fora desta tabela não
# tem classe: o átomo vira valor sem unidade de configuração (NO_REALIZATION, achado do piloto).
CONCEPT_CLASS = {
    "object_container_name": "ObjectContainer",
    "object_container_location": "ObjectContainer",
    "default_storage_class": "ObjectContainer",
    "object_versioning_state": "VersioningSetting",
    "versioning_mfa_delete": "VersioningSetting",
    "lifecycle_rule_enabled": "LifecycleRule",
    "lifecycle_rule_name": "LifecycleRule",
    "lifecycle_filter_name_prefix": "LifecycleRule",
    "lifecycle_condition_age": "LifecycleRule",
    "object_expiration_age": "LifecycleRule",
    "object_transition_age": "LifecycleRule",
    "transition_target_storage_class": "LifecycleRule",
    "lifecycle_action_kind": "LifecycleRule",
    "noncurrent_version_expiration_age": "LifecycleRule",
    "version_deletion_age_since_creation": "LifecycleRule",
    "noncurrent_versions_retained": "LifecycleRule",
    "abort_incomplete_upload_age": "LifecycleRule",
    "lifecycle_filter_min_object_size": "LifecycleRule",
    "lifecycle_filter_max_object_size": "LifecycleRule",
    "expired_delete_marker_removal": "LifecycleRule",
    "default_encryption_algorithm": "EncryptionSetting",
    "default_encryption_key": "EncryptionSetting",
    "bucket_key_enabled": "EncryptionSetting",
    "encryption_type_restriction": "EncryptionSetting",
    "infrastructure_double_encryption": "EncryptionSetting",
    "container_default_encryption_scope": "EncryptionSetting",
    "block_public_acls": "PublicAccessBlockSetting",
    "ignore_public_acls": "PublicAccessBlockSetting",
    "block_public_policy": "PublicAccessBlockSetting",
    "restrict_public_policy_access": "PublicAccessBlockSetting",
    "public_access_prevention": "PublicAccessBlockSetting",
    "nested_public_opt_in_allowed": "PublicAccessBlockSetting",
    "container_anonymous_access_level": "AccessGrantSetting",
    "canned_acl": "AccessGrantSetting",
    "acl_grant_permission": "AccessGrantSetting",
    "acl_grantee": "AccessGrantSetting",
    "access_policy_document": "AccessGrantSetting",
    "policy_grant_role": "AccessGrantSetting",
    "policy_grant_principals": "AccessGrantSetting",
    "uniform_container_access": "AclModeSetting",
    "object_ownership_mode": "AclModeSetting",
}
# Classe de configuração que um componente compõe.
COMPONENT_OF = {"LifecycleRule": "LifecycleSetting"}
# Conceitos de contexto de implantação (posicionamento): não transportados viram contexto simbólico DECLARADO no
# plano (C26 contexts), não bloqueio da unidade.
CONTEXT_CONCEPTS = {"object_container_location"}
# Conceitos de identidade (nome): sem eles o recurso de destino não tem nome derivado.
NAME_CONCEPTS = {"object_container_name"}

# Propriedades funcionais (c3): um valor por indivíduo.
FUNCTIONAL = {c for c in CONCEPT_CLASS if c not in {"acl_grantee", "acl_grant_permission", "policy_grant_principals",
                                                     "lifecycle_filter_name_prefix", "encryption_type_restriction"}}

# ----------------------------------------------------------------------------------------------------------
# Realização por tipo Terraform (o que o recurso inteiro realiza). Contêiner e namespace por provedor; tipo de
# configuração separado com a classe e a base.
# ----------------------------------------------------------------------------------------------------------
CONTAINER_TYPE = {"aws": "aws_s3_bucket", "google": "google_storage_bucket", "azurerm": "azurerm_storage_container",
                  "oci": "oci_objectstorage_bucket"}
NAMESPACE_TYPE = {"azurerm": "azurerm_storage_account"}
TYPE_CLASS = {
    "aws_s3_bucket": ("ObjectContainer", "conceito object_container_name no atributo bucket"),
    "aws_s3_bucket_versioning": ("VersioningSetting", "conceitos object_versioning_state e versioning_mfa_delete"),
    "aws_s3_bucket_lifecycle_configuration": ("LifecycleSetting", "regras de ciclo de vida (rule.*)"),
    "aws_s3_bucket_server_side_encryption_configuration": ("EncryptionSetting", "conceitos de criptografia padrão"),
    "aws_s3_bucket_public_access_block": ("PublicAccessBlockSetting", "conceitos block_public_*/ignore/restrict"),
    "aws_s3_account_public_access_block": ("PublicAccessBlockSetting", "mesmos conceitos, alcance de conta (C25 type_scope)"),
    "aws_s3_bucket_acl": ("AccessGrantSetting", "canned_acl e concessões de ACL"),
    "aws_s3_bucket_policy": ("AccessGrantSetting", "access_policy_document"),
    "aws_s3_bucket_ownership_controls": ("AclModeSetting", "object_ownership_mode"),
    "google_storage_bucket": ("ObjectContainer", "conceito object_container_name no atributo name"),
    "google_storage_bucket_acl": ("AccessGrantSetting", "canned_acl"),
    "google_storage_bucket_access_control": ("AccessGrantSetting", "acl_grantee e acl_grant_permission"),
    "google_storage_bucket_iam_policy": ("AccessGrantSetting", "access_policy_document"),
    "google_storage_bucket_iam_binding": ("AccessGrantSetting", "policy_grant_role e policy_grant_principals"),
    "google_storage_bucket_iam_member": ("AccessGrantSetting", "policy_grant_role e policy_grant_principals"),
    "azurerm_storage_account": ("StorageNamespace", "alvo da referência de identidade do contêiner (C25 reference_target de storage_account_id)"),
    "azurerm_storage_container": ("ObjectContainer", "conceito object_container_name no atributo name"),
    "azurerm_storage_management_policy": ("LifecycleSetting", "regras de ciclo de vida (rule.*)"),
    "azurerm_storage_account_customer_managed_key": ("EncryptionSetting", "default_encryption_key"),
    "azurerm_storage_encryption_scope": ("EncryptionSetting", "infrastructure_double_encryption"),
    "oci_objectstorage_bucket": ("ObjectContainer", "conceito object_container_name no atributo name"),
    "oci_objectstorage_object_lifecycle_policy": ("LifecycleSetting", "regras de ciclo de vida (rules.*)"),
    "oci_objectstorage_namespace_metadata": ("NamespaceDefaultsSetting", "padrões do namespace (atributos sem conceito no glossário; tipo da embalagem da fatia)"),
}
# Configuração de nível de namespace cujo dono não é recurso da configuração (o namespace OCI é contexto).
CONTEXT_NAMESPACE_TYPES = {"oci_objectstorage_namespace_metadata"}
# Seleção de contêiner por prefixo no ciclo de vida de nível de namespace (Azure: o primeiro segmento do
# prefix_match é o nome do contêiner; regra de modelagem do c3, base na doc do recurso).
PREFIX_SELECTS_CONTAINER = {"azurerm_storage_management_policy": "rule.filters.prefix_match"}

# ----------------------------------------------------------------------------------------------------------
# Lowering: descritor por provedor
# ----------------------------------------------------------------------------------------------------------
# campo de referência ao dono: tipo -> (campo, atributo do alvo)
REF_FIELD = {
    "aws_s3_bucket_versioning": ("bucket", "id"),
    "aws_s3_bucket_lifecycle_configuration": ("bucket", "id"),
    "aws_s3_bucket_server_side_encryption_configuration": ("bucket", "id"),
    "aws_s3_bucket_public_access_block": ("bucket", "id"),
    "aws_s3_bucket_acl": ("bucket", "id"),
    "aws_s3_bucket_policy": ("bucket", "id"),
    "aws_s3_bucket_ownership_controls": ("bucket", "id"),
    "google_storage_bucket_acl": ("bucket", "name"),
    "google_storage_bucket_access_control": ("bucket", "name"),
    "google_storage_bucket_iam_policy": ("bucket", "name"),
    "google_storage_bucket_iam_binding": ("bucket", "name"),
    "google_storage_bucket_iam_member": ("bucket", "name"),
    "azurerm_storage_container": ("storage_account_id", "id"),
    "azurerm_storage_management_policy": ("storage_account_id", "id"),
    "oci_objectstorage_object_lifecycle_policy": ("bucket", "name"),
}
# Valores de contexto de implantação DECLARADOS para campos obrigatórios que a origem não traz. Cada um entra no
# plano como synthesized + marked (C26-SYNTH); símbolo = variável sem default ligada pelo executor.
DEPLOY_CONTEXT = {
    "google_storage_bucket": {"location": ("literal", "US")},
    "azurerm_resource_group": {"location": ("literal", "eastus")},
    "azurerm_storage_account": {"location": ("literal", "eastus"), "account_tier": ("literal", "Standard"),
                                "account_replication_type": ("literal", "LRS")},
    "oci_objectstorage_bucket": {"compartment_id": ("symbol", "compartment"), "namespace": ("symbol", "namespace")},
    "oci_objectstorage_object_lifecycle_policy": {"namespace": ("symbol", "namespace")},
}
# Dependência compartilhada criada pelo plano (fechamento de dependências): o namespace Azure precisa de grupo.
SHARED_PARENT = {"azurerm_storage_account": ("azurerm_resource_group", "resource_group_name", "name")}
# Nome derivado: tipo -> (campo do nome, modelo). Contêiner leva o nome transportado; o resto, nome sintetizado.
NAME_FIELD = {"aws_s3_bucket": "bucket", "google_storage_bucket": "name", "azurerm_storage_container": "name",
              "oci_objectstorage_bucket": "name", "azurerm_storage_account": "name", "azurerm_resource_group": "name",
              "azurerm_storage_management_policy": None}


def cls_iri(name: str) -> str:
    return "sto:" + name


def prop_local(concept_id: str) -> str:
    return concept_id.split(":", 1)[1] if ":" in concept_id else concept_id


def concept_class(concept_id: str) -> str | None:
    return CONCEPT_CLASS.get(prop_local(concept_id))


def setting_class_of(concept_id: str) -> str | None:
    c = concept_class(concept_id)
    if c is None:
        return None
    return COMPONENT_OF.get(c, c)
