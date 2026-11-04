"""Oráculo offline do piloto STO (armazenamento de objeto), escrito por quem não implementa o pipeline.

Lê uma fixture sintética de UM provedor (configuração Terraform em sintaxe JSON + contexto + linha do tempo
sintética de objetos) e devolve o ESTADO EFETIVO pela semântica documentada daquele provedor:

  versioning(fx, c)        ENABLED | SUSPENDED | DISABLED | INVALID_TRANSITION | UNKNOWN
  public_access(fx, c)     {anonymous_read, anonymous_list, authenticated_read}, cada eixo bool ou UNKNOWN,
                           mais as recusas de API previstas (apply_rejections)
  simulate(fx)             estado de cada versão sintética no dia de avaliação (CURRENT | NONCURRENT | DELETED,
                           marcador de exclusão à parte), dia a dia, com os eventos e as regras de ciclo de vida
  decompose(fx)            unidades neutras (contêiner, namespace, configuração) com dono, alcance efetivo,
                           controlador de ciclo de vida e evidência que falta
  judge(src, tgt, losses)  julga uma configuração-alvo contra a de origem: ACCEPT | ACCEPT_WITH_DECLARED_LOSS |
                           REJECT | UNKNOWN; divergência não declarada é perda silenciosa (REJECT)
  judge_claim(fx, claim)   julga uma alegação (contraexemplo) sobre o estado efetivo ou a decomposição

Independência: só biblioteca padrão; nenhuma importação do pipeline (glossário, mapeamento, grão, tradutor).
Cada regra aplicada é citada por id em RULES (evidência publicada nos docs fixados do provider, derivada ou
interpretada, com a base). Onde a evidência fixada não decide, a resposta é UNKNOWN com código, nunca um
padrão inventado. Unidade de tempo: dia inteiro; o arredondamento para a meia-noite UTC não é modelado (a
idade de uma versão no dia d é d - dia_de_criação).
"""
from __future__ import annotations

import copy
import fnmatch
import json
import math
import re

ORACLE_VERSION = "1.1.0"
PROVIDERS = ("aws", "google", "azurerm", "oci")
PINS = {"aws": "6.71.0", "google": "8.9.0", "azurerm": "5.12.0", "oci": "9.11.0"}

# ----------------------------------------------------------------------------------------------------------
# Regras e evidência. level: published (frase do doc fixado, conferida pelos testes), derived (consequência
# direta de frases publicadas), interpreted (leitura com base declarada; o PILOT-EXIT pode estratificar).
# ----------------------------------------------------------------------------------------------------------
D_AWS = "docs-aws/v6.71.0/website/docs/r/"
D_GCP = "docs-google/website/docs/r/"
D_AZ = "docs-azurerm/v5.12.0/website/docs/r/"
D_OCI = "docs-oci/website/docs/r/"


def _ev(file, line, needle):
    return {"file": file, "line": line, "needle": needle}


RULES = {
    # versionamento
    "AWS-VER-NO-RETURN": {"level": "published", "evidence": [
        _ev(D_AWS + "s3_bucket_versioning.html.markdown", 104, "does not support returning buckets to an unversioned state"),
        _ev(D_AWS + "s3_bucket.html.markdown", 289, "it can never return to an unversioned state")]},
    "AWS-VER-STATUS": {"level": "published", "evidence": [
        _ev(D_AWS + "s3_bucket_versioning.html.markdown", 109, "Valid values: `Enabled`, `Suspended`, or `Disabled`")]},
    "AWS-VER-INLINE-SUSPEND": {"level": "derived", "basis": "enabled=false depois de habilitado = suspenso, pela frase que proíbe voltar a não versionado e permite suspender", "evidence": [
        _ev(D_AWS + "s3_bucket.html.markdown", 289, "You can, however, suspend versioning on that bucket")]},
    "AWS-VER-INLINE-VS-SEPARATE": {"level": "published", "evidence": [
        _ev(D_AWS + "s3_bucket.html.markdown", 285, "To manage changes of versioning state to an S3 bucket, use the `aws_s3_bucket_versioning` resource instead")]},
    "AWS-VER-DEFAULT": {"level": "derived", "basis": "sem configuração o contêiner nunca foi versionado (a doc fala em 'version-enable a bucket' como ato)", "evidence": [
        _ev(D_AWS + "s3_bucket.html.markdown", 289, "Once you version-enable a bucket")]},
    "AWS-OBJLOCK-VERSIONING": {"level": "published", "evidence": [
        _ev(D_AWS + "s3_bucket.html.markdown", 154, "Amazon S3 automatically enables versioning for the bucket"),
        _ev(D_AWS + "s3_bucket.html.markdown", 155, "you can't disable Object Lock or suspend versioning")]},
    "GCP-VER-ENABLED": {"level": "published", "evidence": [
        _ev(D_GCP + "storage_bucket.html.markdown", 333, "While set to `true`, versioning is fully enabled for this bucket")]},
    "GCP-VER-SUSPEND": {"level": "interpreted", "basis": "enabled=false depois de true = suspenso (versões não correntes guardadas, novas gravações sem versão); a doc fixada só diz o que true faz e aponta para a página de versionamento", "evidence": [
        _ev(D_GCP + "storage_bucket.html.markdown", 231, "The bucket's [Versioning](https://cloud.google.com/storage/docs/object-versioning) configuration")]},
    "GCP-VER-DEFAULT": {"level": "interpreted", "basis": "bloco versioning ausente = nunca versionado; marcado como padrão, não configurado", "evidence": [
        _ev(D_GCP + "storage_bucket.html.markdown", 231, "(Optional) The bucket's [Versioning]")]},
    "AZ-VER-ACCOUNT": {"level": "published", "evidence": [
        _ev(D_AZ + "storage_account.html.markdown", 209, "`versioning_enabled` - (Optional) Is versioning enabled? Default to `false`.")]},
    "AZ-VER-SCOPE": {"level": "interpreted", "basis": "o versionamento de blob_properties da conta vale para todo contêiner da conta (compromisso CMT-BKT-P02, nota azurerm; a doc fixada não diz o alcance)", "evidence": [
        _ev(D_AZ + "storage_account.html.markdown", 151, "`blob_properties` - (Optional) A `blob_properties` block")]},
    "AZ-VER-SUSPEND": {"level": "interpreted", "basis": "versioning_enabled=false depois de true = suspenso (versões anteriores ficam)", "evidence": [
        _ev(D_AZ + "storage_account.html.markdown", 209, "Is versioning enabled?")]},
    "OCI-VER-VALUES": {"level": "published", "evidence": [
        _ev(D_OCI + "objectstorage_bucket.html.markdown", 76, "Allowed Create values: Enabled, Disabled. Allowed Update values: Enabled, Suspended.")]},
    "OCI-VER-DEFAULT": {"level": "published", "evidence": [
        _ev(D_OCI + "objectstorage_bucket.html.markdown", 76, "By default, a bucket is created with versioning `Disabled`")]},
    # gravação e exclusão de objetos sob cada estado de versionamento
    "WRITE-VERSIONED": {"level": "published", "evidence": [
        _ev(D_OCI + "objectstorage_bucket.html.markdown", 76, "Previous versions of the same object will be available in the bucket")]},
    "WRITE-UNVERSIONED": {"level": "derived", "basis": "sem versionamento, regravar substitui o objeto (oposto da frase de proteção contra sobrescrita)", "evidence": [
        _ev(D_OCI + "objectstorage_bucket.html.markdown", 76, "Objects in a version enabled bucket are protected from overwrites and deletions")]},
    "AWS-SUSPENDED-NULL": {"level": "interpreted", "basis": "no S3 suspenso a gravação cria a versão nula e substitui a versão nula anterior; versões com id ficam (guia de versionamento do S3 ligado pela doc)", "evidence": [
        _ev(D_AWS + "s3_bucket_versioning.html.markdown", 15, "How S3 versioning works")]},
    "DELETE-MARKER-AWS": {"level": "derived", "basis": "a doc fala de marcadores de exclusão expirados em contêiner versionado ou suspenso: excluir ali cria marcador", "evidence": [
        _ev(D_AWS + "s3_bucket.html.markdown", 120, "On a versioned bucket (versioning-enabled or versioning-suspended bucket)")]},
    "DELETE-NOMARKER": {"level": "interpreted", "basis": "GCS e Azure não têm marcador: excluir a versão corrente a torna não corrente; OCI cria marcador (docs de versionamento dos provedores, fora do pin)", "evidence": []},
    # ciclo de vida AWS
    "AWS-LC-DAYS": {"level": "published", "evidence": [
        _ev(D_AWS + "s3_bucket.html.markdown", 119, "Number of days after object creation when the specific rule action takes effect")]},
    "AWS-LC-EXPIRE-VERSIONED": {"level": "derived", "basis": "expirar a versão corrente em contêiner versionado cria marcador (é o marcador 'expirado' de que fala a doc); em não versionado apaga", "evidence": [
        _ev(D_AWS + "s3_bucket.html.markdown", 120, "direct Amazon S3 to delete expired object delete markers")]},
    "AWS-LC-EODM": {"level": "published", "evidence": [
        _ev(D_AWS + "s3_bucket_lifecycle_configuration.html.markdown", 404, "Whether Amazon S3 will remove a delete marker with no noncurrent versions")]},
    "AWS-LC-NONCURRENT": {"level": "published", "evidence": [
        _ev(D_AWS + "s3_bucket_lifecycle_configuration.html.markdown", 423, "Number of days an object is noncurrent before Amazon S3 can perform the associated action"),
        _ev(D_AWS + "s3_bucket_lifecycle_configuration.html.markdown", 422, "Number of noncurrent versions Amazon S3 will retain")]},
    "AWS-LC-STATUS": {"level": "published", "evidence": [
        _ev(D_AWS + "s3_bucket_lifecycle_configuration.html.markdown", 389, "Whether the rule is currently being applied. Valid values: `Enabled` or `Disabled`")]},
    "AWS-LC-FILTER": {"level": "published", "evidence": [
        _ev(D_AWS + "s3_bucket_lifecycle_configuration.html.markdown", 415, "Prefix identifying one or more objects to which the rule applies"),
        _ev(D_AWS + "s3_bucket_lifecycle_configuration.html.markdown", 412, "The Lifecycle Rule will apply to any object matching all the predicates")]},
    "AWS-LC-NOMIX": {"level": "published", "evidence": [
        _ev(D_AWS + "s3_bucket.html.markdown", 98, "`lifecycle_rule` cannot be mixed with the external `aws_s3_bucket_lifecycle_configuration` resource")]},
    "AWS-LC-SINGLE": {"level": "published", "evidence": [
        _ev(D_AWS + "s3_bucket_lifecycle_configuration.html.markdown", 21, "S3 Buckets only support a single lifecycle configuration")]},
    "AWS-LC-TRANSITION": {"level": "published", "evidence": [
        _ev(D_AWS + "s3_bucket_lifecycle_configuration.html.markdown", 440, "Number of days after creation when objects are transitioned")]},
    # ciclo de vida Google
    "GCP-LC-ALL": {"level": "published", "evidence": [
        _ev(D_GCP + "storage_bucket.html.markdown", 289, "an object has to match all of the conditions for the action to be taken")]},
    "GCP-LC-AGE": {"level": "published", "evidence": [
        _ev(D_GCP + "storage_bucket.html.markdown", 291, "Minimum age of an object in days to satisfy this condition")]},
    "GCP-LC-AGE0": {"level": "published", "evidence": [
        _ev(D_GCP + "storage_bucket.html.markdown", 93, "a default `age` of 0 will be set")]},
    "GCP-LC-STATE": {"level": "published", "evidence": [
        _ev(D_GCP + "storage_bucket.html.markdown", 295, "Match to live and/or archived objects. Unversioned buckets have only live objects")]},
    "GCP-LC-NEWER": {"level": "published", "evidence": [
        _ev(D_GCP + "storage_bucket.html.markdown", 303, "The number of newer versions of an object to satisfy this condition")]},
    "GCP-LC-NONCURRENT": {"level": "published", "evidence": [
        _ev(D_GCP + "storage_bucket.html.markdown", 315, "Number of days elapsed since the noncurrent timestamp of an object")]},
    "GCP-LC-PREFIX": {"level": "published", "evidence": [
        _ev(D_GCP + "storage_bucket.html.markdown", 299, "One or more matching name prefixes to satisfy this condition")]},
    "GCP-LC-DELETE-LIVE": {"level": "interpreted", "basis": "Delete na versão viva de contêiner versionado a torna não corrente (arquivada); em não versionado apaga", "evidence": [
        _ev(D_GCP + "storage_bucket.html.markdown", 285, "Supported values include: `Delete`, `SetStorageClass`")]},
    # ciclo de vida Azure
    "AZ-LC-GT": {"level": "published", "evidence": [
        _ev(D_AZ + "storage_management_policy.html.markdown", 148, "The age in days after last modification to delete the blob"),
        _ev(D_AZ + "storage_management_policy.html.markdown", 148, "Defaults to `-1`")]},
    "AZ-LC-VERSION": {"level": "interpreted", "basis": "version.delete_after_days_since_creation conta da criação da versão (gravação do conteúdo dela), com 'maior que' como os demais limites da política", "evidence": [
        _ev(D_AZ + "storage_management_policy.html.markdown", 174, "The age in days after creation to delete the blob version")]},
    "AZ-LC-PREFIX": {"level": "interpreted", "basis": "prefix_match começa pelo nome do contêiner ('container1/prefix1' no exemplo publicado)", "evidence": [
        _ev(D_AZ + "storage_management_policy.html.markdown", 38, "prefix_match = [\"container1/prefix1\"]")]},
    "AZ-LC-ACCOUNT": {"level": "published", "evidence": [
        _ev(D_AZ + "storage_management_policy.html.markdown", 89, "Specifies the id of the storage account to apply the management policy to")]},
    "AZ-LC-DELETE-VERSIONED": {"level": "interpreted", "basis": "excluir o blob base com versionamento ligado deixa a versão anterior (não corrente)", "evidence": []},
    "AZ-LC-ENABLED": {"level": "published", "evidence": [
        _ev(D_AZ + "storage_management_policy.html.markdown", 98, "Boolean to specify whether the rule is enabled")]},
    # ciclo de vida OCI
    "OCI-LC-LASTMOD": {"level": "published", "evidence": [
        _ev(D_OCI + "objectstorage_object_lifecycle_policy.html.markdown", 74, "is calculated in relation to each object's Last-Modified time")]},
    "OCI-LC-UNIT": {"level": "published", "evidence": [
        _ev(D_OCI + "objectstorage_object_lifecycle_policy.html.markdown", 75, "Years are defined as 365.2425 days long and likewise round up to the next midnight UTC")]},
    "OCI-LC-DELETE": {"level": "published", "evidence": [
        _ev(D_OCI + "objectstorage_object_lifecycle_policy.html.markdown", 56, "Rules using the action 'DELETE' permanently delete objects from buckets")]},
    "OCI-LC-TARGET": {"level": "published", "evidence": [
        _ev(D_OCI + "objectstorage_object_lifecycle_policy.html.markdown", 73, "\"previous-object-versions\" is used to specify ARCHIVE, INFREQUENT_ACCESS or DELETE rule for previous versions")]},
    "OCI-LC-EXCLUDE": {"level": "published", "evidence": [
        _ev(D_OCI + "objectstorage_object_lifecycle_policy.html.markdown", 60, "Exclusion patterns take precedence over inclusion patterns"),
        _ev(D_OCI + "objectstorage_object_lifecycle_policy.html.markdown", 72, "An empty array means to include all objects")]},
    "OCI-LC-ENABLED": {"level": "published", "evidence": [
        _ev(D_OCI + "objectstorage_object_lifecycle_policy.html.markdown", 57, "A Boolean that determines whether this rule is currently enabled")]},
    "OCI-LC-VERSIONED-CONFLICT": {"level": "published", "basis": "a frase fixada diz que DELETE apaga permanentemente; para a versão corrente num contêiner versionado a doc fixada não diz se vira versão anterior: UNKNOWN", "evidence": [
        _ev(D_OCI + "objectstorage_object_lifecycle_policy.html.markdown", 56, "permanently delete objects from buckets")]},
    # acesso público AWS
    "AWS-PAB-ACLS": {"level": "published", "evidence": [
        _ev(D_AWS + "s3_bucket_public_access_block.html.markdown", 38, "PUT Bucket ACL and PUT Object ACL calls fail if the specified ACL allows public access"),
        _ev(D_AWS + "s3_account_public_access_block.html.markdown", 31, "Whether Amazon S3 should block public ACLs for buckets in this account")]},
    "AWS-PAB-POLICY": {"level": "published", "evidence": [
        _ev(D_AWS + "s3_bucket_public_access_block.html.markdown", 39, "Amazon S3 rejects calls to PUT Bucket policy if the specified bucket policy allows public access"),
        _ev(D_AWS + "s3_bucket_public_access_block.html.markdown", 39, "Enabling this setting does not affect the existing bucket policy")]},
    "AWS-PAB-IGNORE": {"level": "published", "evidence": [
        _ev(D_AWS + "s3_bucket_public_access_block.html.markdown", 41, "Amazon S3 ignores public ACLs on this bucket and any objects that it contains"),
        _ev(D_AWS + "s3_account_public_access_block.html.markdown", 33, "Amazon S3 ignores all public ACLs on buckets in this account")]},
    "AWS-PAB-RESTRICT": {"level": "published", "evidence": [
        _ev(D_AWS + "s3_bucket_public_access_block.html.markdown", 43, "only the bucket owner and AWS services can access this bucket if it has a public policy"),
        _ev(D_AWS + "s3_account_public_access_block.html.markdown", 34, "only the bucket owner and AWS Services can access buckets with public policies")]},
    "AWS-PAB-DEFAULTS": {"level": "published", "evidence": [
        _ev(D_AWS + "s3_bucket_public_access_block.html.markdown", 38, "Defaults to `false`")]},
    "AWS-PAB-ACCOUNT-SCOPE": {"level": "published", "evidence": [
        _ev(D_AWS + "s3_account_public_access_block.html.markdown", 13, "Each AWS account may only have one S3 Public Access Block configuration")]},
    "AWS-OWNERSHIP-ENFORCED": {"level": "published", "evidence": [
        _ev(D_AWS + "s3_bucket_ownership_controls.html.markdown", 43, "ACLs no longer affect permissions to data in the S3 bucket")]},
    "AWS-ACL-PUBLIC-READ": {"level": "published", "evidence": [
        _ev(D_AWS + "s3_bucket_acl.html.markdown", 44, "all bucket objects become publicly exposed")]},
    "AWS-DEFAULT-SECURITY": {"level": "published", "basis": "a doc fixada fala das configurações de segurança padrão do contêiner sem enumerá-las: sem o bloqueio ou o controle de propriedade declarados, o efeito é UNKNOWN", "evidence": [
        _ev(D_AWS + "s3_bucket_acl.html.markdown", 43, "This example explicitly disables the default S3 bucket security settings")]},
    "AWS-POLICY-PUBLIC": {"level": "interpreted", "basis": "declaração Allow com Principal '*' e sem Condition é política pública; com Condition, UNKNOWN (CONDITION_INDETERMINATE); Deny equivalente anula", "evidence": [
        _ev(D_AWS + "s3_bucket_public_access_block.html.markdown", 39, "if the specified bucket policy allows public access")]},
    # acesso público Google
    "GCP-PAP": {"level": "published", "evidence": [
        _ev(D_GCP + "storage_bucket.html.markdown", 256, "only if the bucket is subject to the public access prevention organization policy constraint")]},
    "GCP-PAP-INHERITED": {"level": "interpreted", "basis": "SE-google-2lbhng4aavw3ulnv: inherited só impede se a política da organização impõe; política não lida = UNKNOWN", "evidence": [
        _ev(D_GCP + "storage_bucket.html.markdown", 256, "Defaults to \"inherited\"")]},
    "GCP-ALLUSERS": {"level": "published", "evidence": [
        _ev(D_GCP + "storage_bucket_iam.html.markdown", 161, "A special identifier that represents anyone who is on the internet"),
        _ev(D_GCP + "storage_bucket_iam.html.markdown", 162, "anyone who is authenticated with a Google account or a service account")]},
    "GCP-ROLE-PERMS": {"level": "interpreted", "basis": "objectViewer lê e lista; legacyObjectReader só lê; legacyBucketReader só lista (tabela de papéis do IAM do Cloud Storage, fora do pin)", "evidence": []},
    "GCP-UBLA": {"level": "interpreted", "basis": "com acesso uniforme no nível do contêiner as ACLs deixam de valer; só o IAM concede (SE-google-wpq2kb4u5hopohcz cita a coexistência de ACL e IAM)", "evidence": [
        _ev(D_GCP + "storage_bucket.html.markdown", 254, "Enables [Uniform bucket-level access]")]},
    "GCP-IAM-CONDITION": {"level": "interpreted", "basis": "concessão com condição: a decisão depende do contexto do pedido (CMT-IAM-U03)", "evidence": []},
    # acesso público Azure
    "AZ-NESTED": {"level": "published", "evidence": [
        _ev(D_AZ + "storage_account.html.markdown", 123, "Allow or disallow nested items within this Account to opt into being public. Defaults to `false`")]},
    "AZ-CONTAINER-ACCESS": {"level": "published", "evidence": [
        _ev(D_AZ + "storage_container.html.markdown", 48, "Possible values are `blob`, `container` or `private`. Defaults to `private`")]},
    "AZ-ACCESS-LEVELS": {"level": "interpreted", "basis": "blob = leitura anônima de blobs sem listar; container = leitura e listagem (SE-azurerm-jsrgfyqpyvcurgpn liga o efeito ao nível da conta)", "evidence": []},
    # acesso público OCI
    "OCI-ACCESS-TYPE": {"level": "published", "evidence": [
        _ev(D_OCI + "objectstorage_bucket.html.markdown", 57, "When `ObjectRead` is enabled on the bucket, public access is allowed for the `GetObject`, `HeadObject`, and `ListObjects` operations"),
        _ev(D_OCI + "objectstorage_bucket.html.markdown", 57, "When `ObjectReadWithoutList` is enabled on the bucket, public access is allowed for the `GetObject` and `HeadObject` operations")]},
    "OCI-ACCESS-DEFAULT": {"level": "published", "evidence": [
        _ev(D_OCI + "objectstorage_bucket.html.markdown", 57, "A bucket is set to `NoPublicAccess` by default")]},
    # leitura e referências
    "READ-INCOMPLETE": {"level": "derived", "basis": "CMT-BKT-U01 e REQ-ABS-01: nível que pode mudar a resposta e não foi lido dá UNKNOWN", "evidence": []},
    "REF-UNRESOLVED": {"level": "derived", "basis": "CMT-BKT-U02: referência não resolvida ao contêiner dá UNKNOWN com a evidência que falta", "evidence": []},
    "UNSUPPORTED": {"level": "derived", "basis": "recurso da configuração fora do que o oráculo modela: UNKNOWN, nunca valor inventado", "evidence": []},
    # decomposição
    "DEC-OWN-ID": {"level": "derived", "basis": "recurso de topo com identidade própria na API e sem pai na evidência = entidade (compromisso CMT-BKT-P03, nota aws/google; google: SE-google-ax5cm4zf5mcm6pzq dono self na API)", "evidence": []},
    "DEC-FACET-REF": {"level": "derived", "basis": "recurso separado identificado pelo contêiner (identity schema: bucket obrigatório) é faceta do contêiner (CMT-BKT-P01)", "evidence": []},
    "DEC-AZ-CONTAINER": {"level": "derived", "basis": "SE-azurerm-qvoe5bsgpg3atfy2 (controlador de ciclo de vida self na camada de API, R-LIFE-API) e SE-azurerm-si55lp2kgnkl4qun (dono self na API); a identidade fica dentro da conta (SE-azurerm-n2yvw45ffqgp2565, SE-azurerm-xxozs3v2tmjpca2z). Componente exige controlador = pai (CMT-BKT-P03, CMT-LC-P01): com controlador self o contêiner é entidade no namespace da conta. Se a conta apaga o contêiner junto continua sem evidência", "evidence": []},
    "DEC-OCI-NAMESPACE": {"level": "derived", "basis": "oci_objectstorage_namespace_metadata: dono não documentado (SE-oci-esq4tizacudkvhhx); ciclo de vida e alcance só na camada Terraform (SE-oci-2jyxv2tqy5eg2i2g, SE-oci-r34zohdkd44rvbid), que pela nota da própria regra não diz quem cria ou apaga o objeto na API: na unidade de domínio continuam UNKNOWN", "evidence": []},
    "DEC-OCI-BUCKET": {"level": "derived", "basis": "o namespace é escopo de unicidade do nome (bucket_scope NAMESPACE), não pai com ciclo de vida: contêiner é entidade com chave composta (SE-oci-bqtq3hd3wukbga5o dono self e SE-oci-bjc4cjf3tka6ongc ciclo de vida self na API)", "evidence": [
        _ev(D_OCI + "objectstorage_bucket.html.markdown", 66, "Bucket names must be unique within an Object Storage namespace")]},
}

CODES = ("INCOMPLETE_READ", "MISSING_EVIDENCE", "UNRESOLVED", "CONDITION_INDETERMINATE", "UNKNOWN_SYMBOLIC_INPUT",
         "UNSUPPORTED_BY_ORACLE", "ORDER_DEPENDENT", "INVALID_FIXTURE")


class Unk:
    """Valor desconhecido com código e regras; nunca vira padrão."""

    __slots__ = ("code", "why", "rules")

    def __init__(self, code, why, rules=()):
        assert code in CODES, code
        self.code, self.why, self.rules = code, why, list(rules)

    def __eq__(self, other):
        return isinstance(other, Unk) and other.code == self.code

    def __hash__(self):
        return hash(("Unk", self.code))

    def __repr__(self):
        return f"Unk({self.code})"

    def to_json(self):
        return {"value": "UNKNOWN", "code": self.code, "why": self.why, "rules": self.rules}


class FixtureError(ValueError):
    pass


def is_unk(v):
    return isinstance(v, Unk)


# ----------------------------------------------------------------------------------------------------------
# Leitura da configuração (sintaxe JSON do Terraform)
# ----------------------------------------------------------------------------------------------------------
REF_RE = re.compile(r"^\$\{([a-z][a-z0-9_]*)\.([A-Za-z0-9_-]+)\.([a-z_]+)\}$")


def resources(fx):
    for rtype, insts in sorted((fx.get("terraform", {}).get("resource") or {}).items()):
        for name, body in sorted(insts.items()):
            yield rtype, name, body


def res(fx, addr):
    rtype, name = addr.split(".", 1)
    return ((fx.get("terraform", {}).get("resource") or {}).get(rtype) or {}).get(name)


def blk(body, name):
    v = (body or {}).get(name)
    if v is None:
        return []
    return v if isinstance(v, list) else [v]


def ref(fx, value):
    """'${tipo.nome.attr}' → 'tipo.nome' se o recurso está na configuração; None se não resolve."""
    if not isinstance(value, str):
        return None
    m = REF_RE.match(value)
    if not m:
        return None
    addr = f"{m.group(1)}.{m.group(2)}"
    return addr if res(fx, addr) is not None else None


def not_read(fx, of, what):
    for x in (fx.get("read") or {}).get("not_read", []):
        if x.get("of") == of and x.get("what") in (what, "*"):
            return True
    return False


CONTAINER_TYPES = {"aws": "aws_s3_bucket", "google": "google_storage_bucket", "azurerm": "azurerm_storage_container",
                   "oci": "oci_objectstorage_bucket"}


def containers(fx):
    t = CONTAINER_TYPES[fx["provider"]]
    return [f"{rt}.{n}" for rt, n, _ in resources(fx) if rt == t]


def azure_account(fx, c):
    body = res(fx, c)
    return ref(fx, body.get("storage_account_id"))


def attached(fx, rtype, c, key="bucket"):
    """Recursos de tipo rtype cujo atributo key referencia o contêiner c; e os que não resolvem."""
    hit, unresolved = [], []
    for rt, n, body in resources(fx):
        if rt != rtype:
            continue
        r = ref(fx, body.get(key))
        if r == c:
            hit.append((f"{rt}.{n}", body))
        elif r is None:
            unresolved.append(f"{rt}.{n}")
    return hit, unresolved


# ----------------------------------------------------------------------------------------------------------
# Versionamento
# ----------------------------------------------------------------------------------------------------------
def _ver_step(provider, form, value, ever, first, objlock, rules):
    """Um passo da sequência de valores nativos. Devolve o novo estado ou 'INVALID_TRANSITION'."""
    if provider == "aws" and form == "separate":
        rules.append("AWS-VER-STATUS")
        if value == "Enabled":
            return "ENABLED"
        if value == "Suspended":
            if objlock:
                rules.append("AWS-OBJLOCK-VERSIONING")
                return "INVALID_TRANSITION"
            return "SUSPENDED"
        if value == "Disabled":
            if ever:
                rules.append("AWS-VER-NO-RETURN")
                return "INVALID_TRANSITION"
            return "DISABLED"
        raise FixtureError(f"status de versionamento desconhecido: {value!r}")
    if provider == "oci":
        rules.append("OCI-VER-VALUES")
        allowed = ("Enabled", "Disabled") if first else ("Enabled", "Suspended")
        if value not in allowed:
            return "INVALID_TRANSITION"
        return {"Enabled": "ENABLED", "Disabled": "DISABLED", "Suspended": "SUSPENDED"}[value]
    if not isinstance(value, bool):
        raise FixtureError(f"valor booleano esperado para {provider}/{form}: {value!r}")
    if value:
        rules.append({"aws": "AWS-VER-INLINE-SUSPEND", "google": "GCP-VER-ENABLED", "azurerm": "AZ-VER-ACCOUNT"}[provider])
        return "ENABLED"
    if ever:
        if provider == "aws" and objlock:
            rules.append("AWS-OBJLOCK-VERSIONING")
            return "INVALID_TRANSITION"
        rules.append({"aws": "AWS-VER-INLINE-SUSPEND", "google": "GCP-VER-SUSPEND", "azurerm": "AZ-VER-SUSPEND"}[provider])
        return "SUSPENDED"
    return "DISABLED"


def versioning_config(fx, c):
    """Valor nativo configurado (final) para o contêiner c, a forma e a origem; ou Unk."""
    p = fx["provider"]
    body = res(fx, c)
    if not_read(fx, c, "versioning"):
        return Unk("INCOMPLETE_READ", "versionamento do contêiner não lido", ["READ-INCOMPLETE"])
    if p == "aws":
        inline = blk(body, "versioning")
        sep, unresolved = attached(fx, "aws_s3_bucket_versioning", c)
        if inline and sep:
            return Unk("UNRESOLVED", "versionamento embutido e recurso separado no mesmo contêiner", ["AWS-VER-INLINE-VS-SEPARATE"])
        if len(sep) > 1:
            return Unk("UNRESOLVED", "dois recursos de versionamento para o mesmo contêiner", ["AWS-VER-INLINE-VS-SEPARATE"])
        if sep:
            st = blk(sep[0][1], "versioning_configuration")
            return {"value": st[0]["status"], "form": "separate", "origin": "configured", "by": [sep[0][0]]}
        if unresolved:
            return Unk("MISSING_EVIDENCE", "recurso de versionamento com referência ao contêiner não resolvida", ["REF-UNRESOLVED"])
        if inline:
            return {"value": bool(inline[0].get("enabled", False)), "form": "inline", "origin": "configured", "by": [c + "/versioning"]}
        if body.get("object_lock_enabled") is True:
            return {"value": True, "form": "inline", "origin": "object_lock", "by": [c + "/object_lock_enabled"]}
        return {"value": False, "form": "inline", "origin": "default", "by": [], "rule": "AWS-VER-DEFAULT"}
    if p == "google":
        v = blk(body, "versioning")
        if v:
            return {"value": bool(v[0].get("enabled")), "form": "inline", "origin": "configured", "by": [c + "/versioning"]}
        return {"value": False, "form": "inline", "origin": "default", "by": [], "rule": "GCP-VER-DEFAULT"}
    if p == "azurerm":
        acct = azure_account(fx, c)
        if acct is None:
            return Unk("INCOMPLETE_READ", "conta do contêiner não lida (referência não resolvida)", ["READ-INCOMPLETE", "AZ-VER-SCOPE"])
        if not_read(fx, acct, "blob_properties"):
            return Unk("INCOMPLETE_READ", "blob_properties da conta não lido", ["READ-INCOMPLETE"])
        bp = blk(res(fx, acct), "blob_properties")
        if bp and "versioning_enabled" in bp[0]:
            return {"value": bool(bp[0]["versioning_enabled"]), "form": "inline", "origin": "configured",
                    "by": [acct + "/blob_properties.versioning_enabled"], "scope_rule": "AZ-VER-SCOPE"}
        return {"value": False, "form": "inline", "origin": "default", "by": [], "rule": "AZ-VER-ACCOUNT", "scope_rule": "AZ-VER-SCOPE"}
    if p == "oci":
        if "versioning" in body:
            return {"value": body["versioning"], "form": "attr", "origin": "configured", "by": [c + "/versioning"]}
        return {"value": "Disabled", "form": "attr", "origin": "default", "by": [], "rule": "OCI-VER-DEFAULT"}
    raise FixtureError(p)


def _ver_events(fx, c):
    tl = fx.get("timeline") or {}
    if tl.get("container") != c:
        return []
    return [e for e in tl.get("events", []) if e["op"] == "set_versioning"]


def versioning_series(fx, c):
    """Lista [(dia, estado)] da história de versionamento do contêiner c, e as regras usadas; ou Unk."""
    cfg = versioning_config(fx, c)
    if is_unk(cfg):
        return cfg, []
    p = fx["provider"]
    rules = [cfg["rule"]] if cfg.get("rule") else []
    if cfg.get("scope_rule"):
        rules.append(cfg["scope_rule"])
    evs = _ver_events(fx, c)
    seq = [(e["day"], e["value"]) for e in evs]
    if seq:
        if seq[-1][1] != cfg["value"]:
            raise FixtureError(f"último set_versioning ({seq[-1][1]!r}) diverge da configuração final ({cfg['value']!r})")
    else:
        seq = [(0, cfg["value"])]
    objlock = p == "aws" and res(fx, c).get("object_lock_enabled") is True
    if objlock:
        rules.append("AWS-OBJLOCK-VERSIONING")
    out, ever, prev_val = [], False, None
    for i, (day, val) in enumerate(seq):
        if p == "oci" and i > 0 and val == prev_val:
            st = out[-1][1]
        else:
            st = _ver_step(p, cfg["form"], val, ever, i == 0, objlock, rules)
        if objlock and st in ("DISABLED",):
            st = "ENABLED"
        if st == "INVALID_TRANSITION":
            out.append((day, st))
            return out, sorted(set(rules))
        ever = ever or st in ("ENABLED", "SUSPENDED")
        out.append((day, st))
        prev_val = val
    return out, sorted(set(rules))


def versioning(fx, c):
    """Estado efetivo final do versionamento do contêiner c."""
    s, rules = versioning_series(fx, c)
    if is_unk(s):
        return s
    cfg = versioning_config(fx, c)
    return {"value": s[-1][1], "origin": cfg["origin"], "rules": rules}


def versioning_at(series, day):
    st = "DISABLED"
    for d, s in series:
        if d <= day:
            st = s
    return st


# ----------------------------------------------------------------------------------------------------------
# Acesso público efetivo
# ----------------------------------------------------------------------------------------------------------
AXES = ("anonymous_read", "anonymous_list", "authenticated_read")
_NONE = {a: False for a in AXES}


def _or(a, b):
    """OU de três valores: True vence Unk; Unk vence False."""
    if a is True or b is True:
        return True
    if is_unk(a):
        return a
    if is_unk(b):
        return b
    return False


def _and_not(grant, block):
    """grant E NÃO block, em três valores."""
    if block is True or grant is False:
        return False
    if is_unk(grant):
        return grant
    if is_unk(block):
        return block
    return grant


def _pab(fx, scope, c=None):
    """Bloqueio de acesso público AWS: dict de 4 flags ou Unk. scope = 'account' | 'bucket'."""
    keys = ("block_public_acls", "block_public_policy", "ignore_public_acls", "restrict_public_buckets")
    if scope == "account":
        decl = [(f"{rt}.{n}", b) for rt, n, b in resources(fx) if rt == "aws_s3_account_public_access_block"]
        if decl:
            return {k: bool(decl[0][1].get(k, False)) for k in keys}
        ctx = (fx.get("context") or {}).get("account_public_access_block") or {"status": "not_read"}
        if ctx["status"] == "not_read" or not_read(fx, "account", "public_access_block"):
            return Unk("INCOMPLETE_READ", "bloqueio de acesso público da conta não lido", ["READ-INCOMPLETE", "AWS-PAB-ACCOUNT-SCOPE"])
        if ctx["status"] == "none_configured":
            return {k: False for k in keys}
        return {k: bool(ctx.get(k, False)) for k in keys}
    hit, unresolved = attached(fx, "aws_s3_bucket_public_access_block", c)
    if hit:
        return {k: bool(hit[0][1].get(k, False)) for k in keys}
    if unresolved:
        return Unk("MISSING_EVIDENCE", "bloqueio de contêiner com referência não resolvida", ["REF-UNRESOLVED"])
    if not_read(fx, c, "public_access_block"):
        return Unk("INCOMPLETE_READ", "bloqueio do contêiner não lido", ["READ-INCOMPLETE"])
    return Unk("MISSING_EVIDENCE", "bloqueio do contêiner não declarado; o padrão do serviço não está na evidência fixada",
               ["AWS-DEFAULT-SECURITY"])


def _flag(pab_a, pab_b, key):
    va = pab_a if is_unk(pab_a) else pab_a[key]
    vb = pab_b if is_unk(pab_b) else pab_b[key]
    return _or(va, vb)


def _aws_policy_public(doc, rules):
    """{eixo: bool|Unk} concedido pela política (só a parte pública)."""
    rules.append("AWS-POLICY-PUBLIC")
    if not isinstance(doc, str):
        u = Unk("UNKNOWN_SYMBOLIC_INPUT", "documento de política simbólico", ["AWS-POLICY-PUBLIC"])
        return {a: u for a in AXES}
    try:
        pol = json.loads(re.sub(r"\$\{[^}]*\}", "__SYM__", doc))
    except ValueError:
        u = Unk("UNKNOWN_SYMBOLIC_INPUT", "política não é JSON", ["AWS-POLICY-PUBLIC"])
        return {a: u for a in AXES}
    stmts = pol.get("Statement", [])
    stmts = stmts if isinstance(stmts, list) else [stmts]

    def public_principal(s):
        pr = s.get("Principal")
        if pr == "*":
            return True
        if isinstance(pr, dict):
            v = pr.get("AWS")
            return v == "*" or (isinstance(v, list) and "*" in v)
        return False

    def covers(s, action):
        acts = s.get("Action", [])
        acts = acts if isinstance(acts, list) else [acts]
        return any(fnmatch.fnmatchcase(action, a) for a in acts)

    for s in stmts:
        if any("__SYM__" in json.dumps(s.get(k)) for k in ("Effect", "Principal", "Action", "Condition", "NotPrincipal", "NotAction")):
            u = Unk("UNKNOWN_SYMBOLIC_INPUT", "efeito, principal, ação ou condição simbólicos na política", ["AWS-POLICY-PUBLIC"])
            return {a: u for a in AXES}
        if "NotPrincipal" in s or "NotAction" in s:
            u = Unk("UNSUPPORTED_BY_ORACLE", "NotPrincipal/NotAction fora do modelo", ["UNSUPPORTED"])
            return {a: u for a in AXES}
    out = {}
    for axis, action in (("anonymous_read", "s3:GetObject"), ("anonymous_list", "s3:ListBucket")):
        allow = False
        for s in stmts:
            if s.get("Effect") == "Allow" and public_principal(s) and covers(s, action):
                if s.get("Condition"):
                    allow = _or(allow, Unk("CONDITION_INDETERMINATE", "concessão pública condicionada", ["AWS-POLICY-PUBLIC"]))
                else:
                    allow = True
        deny = any(s.get("Effect") == "Deny" and public_principal(s) and covers(s, action) and not s.get("Condition")
                   for s in stmts)
        out[axis] = False if deny else allow
    out["authenticated_read"] = False
    return out


def _aws_acl_public(fx, c, rules):
    body = res(fx, c)
    canned = None
    hit, unresolved = attached(fx, "aws_s3_bucket_acl", c)
    if hit:
        canned = hit[0][1].get("acl")
        grants = []
        for acp in blk(hit[0][1], "access_control_policy"):
            for g in blk(acp, "grant"):
                for ge in blk(g, "grantee"):
                    grants.append((ge.get("type"), ge.get("uri"), g.get("permission")))
    else:
        canned = body.get("acl")
        grants = [(g.get("type"), g.get("uri"), p) for g in blk(body, "grant") for p in g.get("permissions", [])]
    if unresolved and not hit:
        u = Unk("MISSING_EVIDENCE", "ACL com referência não resolvida", ["REF-UNRESOLVED"])
        return {a: u for a in AXES}
    out = dict(_NONE)
    if canned in ("public-read", "public-read-write"):
        rules.append("AWS-ACL-PUBLIC-READ")
        out["anonymous_read"] = out["anonymous_list"] = True
    if canned == "authenticated-read":
        rules.append("AWS-ACL-PUBLIC-READ")
        out["authenticated_read"] = True
    for typ, uri, perm in grants:
        if typ == "Group" and perm in ("READ", "FULL_CONTROL") and isinstance(uri, str):
            if uri.endswith("/global/AllUsers"):
                rules.append("AWS-ACL-PUBLIC-READ")
                out["anonymous_read"] = out["anonymous_list"] = True
            elif uri.endswith("/global/AuthenticatedUsers"):
                out["authenticated_read"] = True
    return out


def _public_aws(fx, c, rules, rejections):
    acc = _pab(fx, "account")
    bkt = _pab(fx, "bucket", c)
    rules += ["AWS-PAB-DEFAULTS"]
    acl = _aws_acl_public(fx, c, rules)
    pols, unresolved = attached(fx, "aws_s3_bucket_policy", c)
    doc = pols[0][1].get("policy") if pols else res(fx, c).get("policy")
    pol = _aws_policy_public(doc, rules) if doc else dict(_NONE)
    if unresolved and not pols:
        u = Unk("MISSING_EVIDENCE", "política com referência não resolvida", ["REF-UNRESOLVED"])
        pol = {a: u for a in AXES}
    # dono do objeto: com BucketOwnerEnforced a ACL não afeta permissões
    oc, oc_unres = attached(fx, "aws_s3_bucket_ownership_controls", c)
    acl_public = any(v is True for v in acl.values())
    if acl_public:
        if oc:
            mode = blk(oc[0][1], "rule")[0].get("object_ownership")
            if mode == "BucketOwnerEnforced":
                rules.append("AWS-OWNERSHIP-ENFORCED")
                acl = dict(_NONE)
        else:
            u = Unk("MISSING_EVIDENCE", "controle de propriedade não declarado; o padrão do serviço não está na evidência fixada",
                    ["AWS-DEFAULT-SECURITY"])
            acl = {a: (u if v is True else v) for a, v in acl.items()}
    # bloqueios de PUT (block_public_*): conta é anterior à configuração; o do contêiner depende da ordem
    acc_bpa = acc if is_unk(acc) else acc["block_public_acls"]
    acc_bpp = acc if is_unk(acc) else acc["block_public_policy"]
    bkt_bpa = bkt if is_unk(bkt) else bkt["block_public_acls"]
    bkt_bpp = bkt if is_unk(bkt) else bkt["block_public_policy"]
    acl_pub = any(v is True for v in acl.values())
    pol_pub = any(v is True for v in pol.values())
    order_unk = Unk("ORDER_DEPENDENT", "bloqueio do contêiner e concessão pública na mesma configuração sem ordem declarada",
                    ["AWS-PAB-ACLS", "AWS-PAB-POLICY"])

    def put_gate(acc_flag, bkt_flag, kind, depends_ok):
        if acc_flag is True:
            rejections.append({"what": kind, "by": "account_public_access_block", "rules": ["AWS-PAB-ACLS" if kind == "acl" else "AWS-PAB-POLICY"]})
            return True
        if bkt_flag is True:
            if depends_ok:
                rejections.append({"what": kind, "by": "bucket_public_access_block", "rules": ["AWS-PAB-ACLS" if kind == "acl" else "AWS-PAB-POLICY"]})
                return True
            return order_unk
        if is_unk(acc_flag):
            return acc_flag
        if is_unk(bkt_flag):
            return bkt_flag
        return False

    pab_addr = [a for a, _ in attached(fx, "aws_s3_bucket_public_access_block", c)[0]]

    def after_pab(rtype):
        hit = attached(fx, rtype, c)[0]
        return bool(hit) and bool(pab_addr) and pab_addr[0] in hit[0][1].get("depends_on", [])

    if acl_pub:
        rules.append("AWS-PAB-ACLS")
        g = put_gate(acc_bpa, bkt_bpa, "acl", after_pab("aws_s3_bucket_acl"))
        acl = {a: _and_not(v, g) for a, v in acl.items()}
    if pol_pub:
        rules.append("AWS-PAB-POLICY")
        g = put_gate(acc_bpp, bkt_bpp, "policy", after_pab("aws_s3_bucket_policy"))
        pol = {a: _and_not(v, g) for a, v in pol.items()}
    # efeitos que valem sobre o que existe
    if any(v is True or is_unk(v) for v in acl.values()):
        rules.append("AWS-PAB-IGNORE")
        ign = _flag(acc, bkt, "ignore_public_acls")
        acl = {a: _and_not(v, ign) for a, v in acl.items()}
    if any(v is True or is_unk(v) for v in pol.values()):
        rules.append("AWS-PAB-RESTRICT")
        rst = _flag(acc, bkt, "restrict_public_buckets")
        pol = {a: _and_not(v, rst) for a, v in pol.items()}
    return {a: _or(acl[a], pol[a]) for a in AXES}


GCP_ROLES = {
    "roles/storage.objectViewer": {"read": True, "list": True},
    "roles/storage.objectAdmin": {"read": True, "list": True},
    "roles/storage.admin": {"read": True, "list": True},
    "roles/storage.legacyObjectReader": {"read": True, "list": False},
    "roles/storage.legacyBucketReader": {"read": False, "list": True},
    "roles/storage.objectCreator": {"read": False, "list": False},
}


def _public_google(fx, c, rules):
    body = res(fx, c)
    out = dict(_NONE)
    for rt in ("google_storage_bucket_iam_member", "google_storage_bucket_iam_binding"):
        hit, unresolved = attached(fx, rt, c)
        if unresolved:
            u = Unk("MISSING_EVIDENCE", "concessão IAM com referência não resolvida", ["REF-UNRESOLVED"])
            return {a: u for a in AXES}
        for _, b in hit:
            members = [b["member"]] if "member" in b else list(b.get("members", []))
            role = b.get("role")
            perms = GCP_ROLES.get(role)
            for m in members:
                if m not in ("allUsers", "allAuthenticatedUsers"):
                    continue
                rules += ["GCP-ALLUSERS", "GCP-ROLE-PERMS"]
                if perms is None:
                    u = Unk("MISSING_EVIDENCE", f"papel {role} fora da tabela de permissões", ["GCP-ROLE-PERMS"])
                    grant = {"read": u, "list": u}
                else:
                    grant = dict(perms)
                if blk(b, "condition"):
                    rules.append("GCP-IAM-CONDITION")
                    u = Unk("CONDITION_INDETERMINATE", "concessão pública condicionada", ["GCP-IAM-CONDITION"])
                    grant = {k: (u if v is True else v) for k, v in grant.items()}
                if m == "allUsers":
                    out["anonymous_read"] = _or(out["anonymous_read"], grant["read"])
                    out["anonymous_list"] = _or(out["anonymous_list"], grant["list"])
                else:
                    out["authenticated_read"] = _or(out["authenticated_read"], grant["read"])
    # ACL legada: só vale sem acesso uniforme
    acls, unres_acl = attached(fx, "google_storage_bucket_acl", c)
    ubla = bool(body.get("uniform_bucket_level_access", False))
    acl_out = dict(_NONE)
    for _, b in acls:
        for re_ in b.get("role_entity", []):
            role, _, ent = re_.partition(":")
            if ent == "allUsers" and role in ("READER", "OWNER", "WRITER"):
                acl_out["anonymous_list"] = True
            if ent == "allAuthenticatedUsers" and role in ("READER", "OWNER", "WRITER"):
                acl_out["authenticated_read"] = True
        if b.get("default_acl") == "publicRead":
            acl_out["anonymous_read"] = True
    if any(acl_out.values()):
        rules.append("GCP-UBLA")
        if not ubla:
            out = {a: _or(out[a], acl_out[a]) for a in AXES}
    # prevenção de acesso público
    pap = body.get("public_access_prevention", "inherited")
    rules.append("GCP-PAP")
    if pap == "enforced":
        block = True
    else:
        rules.append("GCP-PAP-INHERITED")
        org = (fx.get("context") or {}).get("org_policy_public_access_prevention", "not_read")
        if org == "not_read" or not_read(fx, "organization", "policy"):
            block = Unk("INCOMPLETE_READ", "política da organização (prevenção de acesso público) não lida", ["READ-INCOMPLETE", "GCP-PAP-INHERITED"])
        else:
            block = bool(org)
    return {a: _and_not(v, block) for a, v in out.items()}


def _public_azurerm(fx, c, rules):
    body = res(fx, c)
    acct = azure_account(fx, c)
    lvl = body.get("container_access_type", "private")
    rules += ["AZ-CONTAINER-ACCESS", "AZ-NESTED", "AZ-ACCESS-LEVELS"]
    grant = {"anonymous_read": lvl in ("blob", "container"), "anonymous_list": lvl == "container", "authenticated_read": False}
    if acct is None or not_read(fx, acct, "allow_nested_items_to_be_public"):
        gate = Unk("INCOMPLETE_READ", "configuração de acesso público da conta não lida", ["READ-INCOMPLETE", "AZ-NESTED"])
    else:
        gate = bool(res(fx, acct).get("allow_nested_items_to_be_public", False))
    return {a: _and_not(v, (not gate) if isinstance(gate, bool) else gate) for a, v in grant.items()}


def _public_oci(fx, c, rules):
    at = res(fx, c).get("access_type", "NoPublicAccess")
    rules += ["OCI-ACCESS-TYPE", "OCI-ACCESS-DEFAULT"]
    if at not in ("NoPublicAccess", "ObjectRead", "ObjectReadWithoutList"):
        raise FixtureError(f"access_type desconhecido: {at!r}")
    return {"anonymous_read": at != "NoPublicAccess", "anonymous_list": at == "ObjectRead", "authenticated_read": False}


def public_access(fx, c):
    p = fx["provider"]
    rules, rejections = [], []
    if not_read(fx, c, "public_access"):
        u = Unk("INCOMPLETE_READ", "concessões de acesso do contêiner não lidas", ["READ-INCOMPLETE"])
        return {"axes": {a: u for a in AXES}, "apply_rejections": [], "rules": ["READ-INCOMPLETE"]}
    if p == "aws":
        out = _public_aws(fx, c, rules, rejections)
    elif p == "google":
        out = _public_google(fx, c, rules)
    elif p == "azurerm":
        out = _public_azurerm(fx, c, rules)
    else:
        out = _public_oci(fx, c, rules)
    return {"axes": out, "apply_rejections": rejections, "rules": sorted(set(rules))}


# ----------------------------------------------------------------------------------------------------------
# Ciclo de vida: regras normalizadas por provedor (a semântica fica no provedor)
# ----------------------------------------------------------------------------------------------------------
def _int_or_none(v, sentinel=None):
    if v is None or v == sentinel:
        return None
    return int(v)


def lifecycle_rules(fx, c):
    """Lista de regras do provedor aplicáveis ao contêiner c (forma nativa normalizada) ou Unk."""
    p = fx["provider"]
    body = res(fx, c)
    out = []
    if not_read(fx, c, "lifecycle"):
        return Unk("INCOMPLETE_READ", "ciclo de vida do contêiner não lido", ["READ-INCOMPLETE"])
    if p == "aws":
        sep, unresolved = attached(fx, "aws_s3_bucket_lifecycle_configuration", c)
        inline = blk(body, "lifecycle_rule")
        if sep and inline:
            return Unk("UNRESOLVED", "lifecycle_rule embutido misturado com o recurso separado", ["AWS-LC-NOMIX"])
        if len(sep) > 1:
            return Unk("UNRESOLVED", "duas configurações de ciclo de vida no mesmo contêiner", ["AWS-LC-SINGLE"])
        if unresolved and not sep:
            return Unk("MISSING_EVIDENCE", "ciclo de vida com referência não resolvida", ["REF-UNRESOLVED"])
        if sep:
            for r in blk(sep[0][1], "rule"):
                f = blk(r, "filter")
                prefix, tags = "", {}
                if f:
                    f0 = f[0]
                    if "object_size_greater_than" in f0 or "object_size_less_than" in f0:
                        return Unk("UNSUPPORTED_BY_ORACLE", "filtro por tamanho fora do modelo", ["UNSUPPORTED"])
                    prefix = f0.get("prefix", "")
                    for t in blk(f0, "tag"):
                        tags[t["key"]] = t["value"]
                    for a in blk(f0, "and"):
                        prefix = a.get("prefix", prefix)
                        tags.update(a.get("tags", {}))
                elif "prefix" in r:
                    prefix = r["prefix"]
                exp = blk(r, "expiration")
                if exp and exp[0].get("date"):
                    return Unk("UNSUPPORTED_BY_ORACLE", "expiração por data fora do modelo de dias", ["UNSUPPORTED"])
                nve = blk(r, "noncurrent_version_expiration")
                out.append({"id": r.get("id"), "enabled": r.get("status") == "Enabled", "prefix": prefix, "tags": tags,
                            "expiration_days": _int_or_none(exp[0].get("days")) if exp else None,
                            "eodm": bool(exp[0].get("expired_object_delete_marker", False)) if exp else False,
                            "noncurrent_days": _int_or_none(nve[0].get("noncurrent_days")) if nve else None,
                            "newer_noncurrent": _int_or_none(nve[0].get("newer_noncurrent_versions")) if nve else None,
                            "transition": [(int(t.get("days", 0)), t["storage_class"]) for t in blk(r, "transition")],
                            "rules": ["AWS-LC-STATUS", "AWS-LC-FILTER", "AWS-LC-DAYS", "AWS-LC-EXPIRE-VERSIONED",
                                      "AWS-LC-EODM", "AWS-LC-NONCURRENT"]})
        else:
            for r in inline:
                exp = blk(r, "expiration")
                nve = blk(r, "noncurrent_version_expiration")
                if exp and exp[0].get("date"):
                    return Unk("UNSUPPORTED_BY_ORACLE", "expiração por data fora do modelo de dias", ["UNSUPPORTED"])
                out.append({"id": r.get("id"), "enabled": bool(r.get("enabled")), "prefix": r.get("prefix", ""),
                            "tags": dict(r.get("tags", {})),
                            "expiration_days": _int_or_none(exp[0].get("days")) if exp else None,
                            "eodm": bool(exp[0].get("expired_object_delete_marker", False)) if exp else False,
                            "noncurrent_days": _int_or_none(nve[0].get("days")) if nve else None,
                            "newer_noncurrent": None,
                            "transition": [(int(t.get("days", 0)), t["storage_class"]) for t in blk(r, "transition")],
                            "rules": ["AWS-LC-DAYS", "AWS-LC-EXPIRE-VERSIONED", "AWS-LC-EODM", "AWS-LC-NONCURRENT"]})
        return out
    if p == "google":
        for r in blk(body, "lifecycle_rule"):
            a = blk(r, "action")[0]
            cnd = blk(r, "condition")[0]
            for unsup in ("created_before", "custom_time_before", "days_since_custom_time", "noncurrent_time_before",
                          "matches_suffix", "matches_storage_class"):
                if cnd.get(unsup) not in (None, "", [], 0):
                    return Unk("UNSUPPORTED_BY_ORACLE", f"condição {unsup} fora do modelo", ["UNSUPPORTED"])
            # sem age o provider manda age=0 (salvo send_age_if_zero=false); age>=0 vale sempre: sem efeito
            age = cnd.get("age") or None
            nnv = cnd.get("num_newer_versions") or None
            dsn = cnd.get("days_since_noncurrent_time") or None
            out.append({"action": a["type"], "storage_class": a.get("storage_class"), "age": age,
                        "with_state": cnd.get("with_state") or "ANY", "num_newer": nnv, "days_noncurrent": dsn,
                        "prefixes": list(cnd.get("matches_prefix", [])),
                        "rules": ["GCP-LC-ALL", "GCP-LC-AGE", "GCP-LC-AGE0", "GCP-LC-STATE", "GCP-LC-NEWER",
                                  "GCP-LC-NONCURRENT", "GCP-LC-PREFIX", "GCP-LC-DELETE-LIVE"]})
        return out
    if p == "azurerm":
        acct = azure_account(fx, c)
        if acct is None:
            return Unk("INCOMPLETE_READ", "conta do contêiner não lida", ["READ-INCOMPLETE"])
        pols, unresolved = attached(fx, "azurerm_storage_management_policy", acct, key="storage_account_id")
        if unresolved and not pols:
            return Unk("MISSING_EVIDENCE", "política de gestão com referência não resolvida", ["REF-UNRESOLVED"])
        if not_read(fx, acct, "management_policy"):
            return Unk("INCOMPLETE_READ", "política de gestão da conta não lida", ["READ-INCOMPLETE"])
        cname = body.get("name")
        for _, pol in pols:
            for r in blk(pol, "rule"):
                f = blk(r, "filters")[0]
                if "blockBlob" not in f.get("blob_types", []):
                    continue
                if blk(f, "match_blob_index_tag"):
                    return Unk("UNSUPPORTED_BY_ORACLE", "filtro por índice de tag fora do modelo", ["UNSUPPORTED"])
                acts = blk(r, "actions")[0]
                bb = (blk(acts, "base_blob") or [{}])[0]
                ve = (blk(acts, "version") or [{}])[0]
                for unsup in ("delete_after_days_since_last_access_time_greater_than", "delete_after_days_since_creation_greater_than"):
                    if _int_or_none(bb.get(unsup), -1) is not None:
                        return Unk("UNSUPPORTED_BY_ORACLE", f"{unsup} fora do modelo", ["UNSUPPORTED"])
                out.append({"name": r.get("name"), "enabled": bool(r.get("enabled")),
                            "prefixes": list(f.get("prefix_match", [])), "container_name": cname,
                            "base_delete_gt": _int_or_none(bb.get("delete_after_days_since_modification_greater_than"), -1),
                            "version_delete_gt": _int_or_none(ve.get("delete_after_days_since_creation"), -1),
                            "rules": ["AZ-LC-GT", "AZ-LC-VERSION", "AZ-LC-PREFIX", "AZ-LC-ACCOUNT", "AZ-LC-ENABLED",
                                      "AZ-LC-DELETE-VERSIONED"]})
        return out
    if p == "oci":
        pols, unresolved = attached(fx, "oci_objectstorage_object_lifecycle_policy", c)
        if unresolved and not pols:
            return Unk("MISSING_EVIDENCE", "política de ciclo de vida com referência não resolvida", ["REF-UNRESOLVED"])
        for _, pol in pols:
            for r in blk(pol, "rules"):
                unit = r.get("time_unit", "DAYS")
                amt = int(r["time_amount"])
                days = amt if unit == "DAYS" else math.ceil(amt * 365.2425)
                fl = (blk(r, "object_name_filter") or [{}])[0]
                if fl.get("inclusion_prefixes") and fl.get("inclusion_patterns"):
                    return Unk("MISSING_EVIDENCE", "prefixos e padrões de inclusão juntos: combinação não documentada", ["OCI-LC-EXCLUDE"])
                if "target" not in r:
                    return Unk("MISSING_EVIDENCE", "alvo da regra omitido: padrão não documentado na evidência fixada", ["OCI-LC-TARGET"])
                out.append({"name": r.get("name"), "enabled": bool(r.get("is_enabled")), "action": r["action"],
                            "target": r["target"], "days": days, "inc_prefixes": list(fl.get("inclusion_prefixes", [])),
                            "inc_patterns": list(fl.get("inclusion_patterns", [])),
                            "exc_patterns": list(fl.get("exclusion_patterns", [])),
                            "rules": ["OCI-LC-LASTMOD", "OCI-LC-UNIT", "OCI-LC-DELETE", "OCI-LC-TARGET", "OCI-LC-EXCLUDE",
                                      "OCI-LC-ENABLED"]})
        return out
    raise FixtureError(p)


def _oci_match(r, key):
    if any(fnmatch.fnmatchcase(key, pat) for pat in r["exc_patterns"]):
        return False
    if r["inc_prefixes"]:
        return any(key.startswith(x) for x in r["inc_prefixes"])
    if r["inc_patterns"]:
        return any(fnmatch.fnmatchcase(key, pat) for pat in r["inc_patterns"])
    return True


# ----------------------------------------------------------------------------------------------------------
# Simulação da linha do tempo
# ----------------------------------------------------------------------------------------------------------
class _V:
    __slots__ = ("vid", "key", "created", "marker", "null", "state", "noncurrent_since", "ended", "tier", "tags")

    def __init__(self, vid, key, created, marker=False, null=False, tags=None):
        self.vid, self.key, self.created, self.marker, self.null = vid, key, created, marker, null
        self.state, self.noncurrent_since, self.ended, self.tier, self.tags = "CURRENT", None, None, None, dict(tags or {})


def _write(p, vstate, versions, key, day, counter, tags, marker=False):
    """Gravação (marker=False) ou exclusão pedida pelo usuário (marker=True) sob o estado de versionamento."""
    live = [v for v in versions if v.state != "DELETED"]
    cur = next((v for v in live if v.state == "CURRENT"), None)
    if vstate == "DISABLED":
        if cur:
            cur.state, cur.ended = "DELETED", day
        if not marker:
            versions.append(_V(f"{key}#{counter}", key, day, tags=tags))
        return
    if vstate == "ENABLED":
        if marker:
            if p in ("aws", "oci"):
                if cur and not cur.marker:
                    cur.state, cur.noncurrent_since = "NONCURRENT", day
                    versions.append(_V(f"{key}#{counter}", key, day, marker=True))
            else:
                if cur:
                    cur.state, cur.noncurrent_since = "NONCURRENT", day
            return
        if cur:
            cur.state, cur.noncurrent_since = "NONCURRENT", day
        versions.append(_V(f"{key}#{counter}", key, day, tags=tags))
        return
    # SUSPENDED
    if p == "aws":
        for v in live:
            if v.null:
                v.state, v.ended = "DELETED", day
        if cur and not cur.null and cur.state == "CURRENT":
            cur.state, cur.noncurrent_since = "NONCURRENT", day
        versions.append(_V(f"{key}#{counter}", key, day, marker=marker, null=True, tags=tags))
        return
    if cur:
        cur.state, cur.ended = "DELETED", day
    if not marker:
        versions.append(_V(f"{key}#{counter}", key, day, tags=tags))


def _apply_lifecycle(p, rules, objs, day, vstate, container_name, unknown_keys):
    if is_unk(rules) or not rules:
        return
    for key, versions in objs.items():
        if key in unknown_keys:
            continue
        live = [v for v in versions if v.state != "DELETED"]
        if not live:
            continue
        cur = next((v for v in live if v.state == "CURRENT"), None)
        noncur = sorted((v for v in live if v.state == "NONCURRENT"), key=lambda v: (v.noncurrent_since, v.created), reverse=True)
        actions = []  # (versão, ação)
        if p == "aws":
            for r in rules:
                if not r["enabled"] or not key.startswith(r["prefix"]):
                    continue
                if r["tags"] and not all((cur.tags if cur else {}).get(k) == v for k, v in r["tags"].items()):
                    continue
                if r["expiration_days"] is not None and cur and not cur.marker and day - cur.created >= r["expiration_days"]:
                    actions.append((cur, "expire_current"))
                if r["eodm"] and cur and cur.marker and not noncur:
                    actions.append((cur, "delete"))
                if r["noncurrent_days"] is not None:
                    keep = r["newer_noncurrent"] or 0
                    for i, v in enumerate(noncur):
                        if i >= keep and day - v.noncurrent_since >= r["noncurrent_days"]:
                            actions.append((v, "delete"))
                for d, cls in r["transition"]:
                    if cur and not cur.marker and day - cur.created >= d:
                        actions.append((cur, ("tier", cls)))
        elif p == "google":
            newer = {}
            ordered = sorted(live, key=lambda v: v.created, reverse=True)
            for i, v in enumerate(ordered):
                newer[v.vid] = i
            for r in rules:
                for v in live:
                    if r["prefixes"] and not any(key.startswith(x) for x in r["prefixes"]):
                        continue
                    if r["with_state"] == "LIVE" and v.state != "CURRENT":
                        continue
                    if r["with_state"] == "ARCHIVED" and v.state != "NONCURRENT":
                        continue
                    if r["age"] is not None and day - v.created < r["age"]:
                        continue
                    if r["num_newer"] is not None and newer[v.vid] < r["num_newer"]:
                        continue
                    if r["days_noncurrent"] is not None and (v.state != "NONCURRENT" or day - v.noncurrent_since < r["days_noncurrent"]):
                        continue
                    if r["action"] == "Delete":
                        actions.append((v, "expire_current" if v.state == "CURRENT" else "delete"))
                    elif r["action"] == "SetStorageClass":
                        actions.append((v, ("tier", r["storage_class"])))
        elif p == "azurerm":
            path = f"{container_name}/{key}"
            for r in rules:
                if not r["enabled"]:
                    continue
                if r["prefixes"] and not any(path.startswith(x) for x in r["prefixes"]):
                    continue
                if r["base_delete_gt"] is not None and cur and day - cur.created > r["base_delete_gt"]:
                    actions.append((cur, "expire_current"))
                if r["version_delete_gt"] is not None:
                    for v in noncur:
                        if day - v.created > r["version_delete_gt"]:
                            actions.append((v, "delete"))
        elif p == "oci":
            for r in rules:
                if not r["enabled"] or not _oci_match(r, key):
                    continue
                if r["target"] == "objects" and cur and not cur.marker and day - cur.created >= r["days"]:
                    if r["action"] == "DELETE":
                        if vstate in ("ENABLED", "SUSPENDED"):
                            unknown_keys[key] = Unk("MISSING_EVIDENCE", "DELETE na versão corrente em contêiner versionado: a doc fixada diz 'apaga permanentemente' sem tratar versões",
                                                    ["OCI-LC-VERSIONED-CONFLICT"])
                            actions = []
                            break
                        actions.append((cur, "delete"))
                    else:
                        actions.append((cur, ("tier", r["action"])))
                if r["target"] == "previous-object-versions":
                    for v in noncur:
                        if day - v.created >= r["days"]:
                            actions.append((v, "delete") if r["action"] == "DELETE" else (v, ("tier", r["action"])))
        # aplica: exclusão vence transição; expirar a corrente depende do versionamento
        done = set()
        for v, act in sorted(actions, key=lambda x: 0 if x[1] in ("delete", "expire_current") else 1):
            if v.vid in done or v.state == "DELETED":
                continue
            if act == "delete":
                v.state, v.ended = "DELETED", day
                done.add(v.vid)
            elif act == "expire_current":
                if vstate == "DISABLED" or (vstate == "SUSPENDED" and (p != "aws" or v.null)):
                    v.state, v.ended = "DELETED", day
                    if p == "aws" and vstate == "SUSPENDED":
                        versions.append(_V(f"{key}#lc{day}", key, day, marker=True, null=True))
                else:
                    v.state, v.noncurrent_since = "NONCURRENT", day
                    if p in ("aws", "oci"):
                        versions.append(_V(f"{key}#lc{day}", key, day, marker=True, null=(vstate == "SUSPENDED")))
                done.add(v.vid)
            else:
                v.tier = act[1]


def simulate(fx):
    """Estado de cada versão no dia de avaliação. Devolve dict ou Unk (nunca valor inventado)."""
    tl = fx.get("timeline")
    if not tl:
        raise FixtureError("fixture sem linha do tempo")
    p, c, T = fx["provider"], tl["container"], int(tl["eval_day"])
    series, vrules = versioning_series(fx, c)
    if is_unk(series):
        return series
    if any(s == "INVALID_TRANSITION" for _, s in series):
        return Unk("INVALID_FIXTURE", "história de versionamento recusada pela API", vrules)
    rules = lifecycle_rules(fx, c)
    if is_unk(rules):
        return rules
    cname = res(fx, c).get("name") if p == "azurerm" else None
    objs, unknown_keys, counter = {}, {}, {}
    events = sorted((e for e in tl.get("events", []) if e["op"] in ("put", "delete")), key=lambda e: e["day"])
    for day in range(0, T + 1):
        vstate = versioning_at(series, day)
        for e in (e for e in events if e["day"] == day):
            k = e["key"]
            counter[k] = counter.get(k, 0) + 1
            _write(p, vstate, objs.setdefault(k, []), k, day, counter[k], e.get("tags"), marker=(e["op"] == "delete"))
        _apply_lifecycle(p, rules, objs, day, vstate, cname, unknown_keys)
    out = {"eval_day": T, "versions": {}, "markers": {}, "unknown_keys": {}, "rules": sorted(set(vrules + [x for r in rules for x in r["rules"]]))}
    for k, vs in sorted(objs.items()):
        if k in unknown_keys:
            out["unknown_keys"][k] = unknown_keys[k].to_json()
            continue
        for v in vs:
            rec = {"state": v.state, "since": v.ended if v.state == "DELETED" else (v.noncurrent_since if v.state == "NONCURRENT" else v.created)}
            if v.tier:
                rec["tier"] = v.tier
            (out["markers"] if v.marker else out["versions"])[v.vid] = rec
    return out


# ----------------------------------------------------------------------------------------------------------
# Decomposição esperada (unidades neutras)
# ----------------------------------------------------------------------------------------------------------
def _setting_units(fx):
    """(tipo de configuração, recurso que a realiza, contêiner-alvo ou None, dono) para cada configuração da fatia."""
    p = fx["provider"]
    out = []
    for rt, n, body in resources(fx):
        a = f"{rt}.{n}"
        if p == "aws":
            kinds = {"aws_s3_bucket_versioning": "versioning", "aws_s3_bucket_lifecycle_configuration": "lifecycle",
                     "aws_s3_bucket_public_access_block": "public_access_block", "aws_s3_bucket_policy": "access_grant",
                     "aws_s3_bucket_acl": "access_grant", "aws_s3_bucket_ownership_controls": "acl_mode"}
            if rt in kinds:
                out.append((kinds[rt], a, ref(fx, body.get("bucket")), "bucket"))
            if rt == "aws_s3_account_public_access_block":
                out.append(("public_access_block", a, None, "account"))
            if rt == "aws_s3_bucket":
                for blkname, kind in (("versioning", "versioning"), ("lifecycle_rule", "lifecycle"), ("grant", "access_grant")):
                    if blk(body, blkname):
                        out.append((kind, a + "/" + blkname, a, "bucket"))
                if body.get("acl"):
                    out.append(("access_grant", a + "/acl", a, "bucket"))
                if body.get("policy"):
                    out.append(("access_grant", a + "/policy", a, "bucket"))
        elif p == "google":
            if rt in ("google_storage_bucket_iam_member", "google_storage_bucket_iam_binding", "google_storage_bucket_acl"):
                out.append(("access_grant", a, ref(fx, body.get("bucket")), "bucket"))
            if rt == "google_storage_bucket":
                for blkname, kind in (("versioning", "versioning"), ("lifecycle_rule", "lifecycle")):
                    if blk(body, blkname):
                        out.append((kind, a + "/" + blkname, a, "bucket"))
                if "public_access_prevention" in body:
                    out.append(("public_access_block", a + "/public_access_prevention", a, "bucket"))
        elif p == "azurerm":
            if rt == "azurerm_storage_account":
                bp = blk(body, "blob_properties")
                if bp and "versioning_enabled" in bp[0]:
                    out.append(("versioning", a + "/blob_properties", a, "account"))
                if "allow_nested_items_to_be_public" in body:
                    out.append(("public_access_block", a + "/allow_nested_items_to_be_public", a, "account"))
            if rt == "azurerm_storage_management_policy":
                out.append(("lifecycle", a, ref(fx, body.get("storage_account_id")), "account"))
            if rt == "azurerm_storage_container" and "container_access_type" in body:
                out.append(("access_grant", a + "/container_access_type", a, "bucket"))
        elif p == "oci":
            if rt == "oci_objectstorage_object_lifecycle_policy":
                out.append(("lifecycle", a, ref(fx, body.get("bucket")), "bucket"))
            if rt == "oci_objectstorage_bucket":
                if "versioning" in body:
                    out.append(("versioning", a + "/versioning", a, "bucket"))
                if "access_type" in body:
                    out.append(("access_grant", a + "/access_type", a, "bucket"))
            if rt == "oci_objectstorage_namespace_metadata":
                out.append(("namespace_defaults", a, None, "namespace"))
    return out


def decompose(fx):
    """Unidades neutras da fixture. Ids: container:<addr>, namespace:<addr>, setting:<tipo>@<dono>."""
    p = fx["provider"]
    units = {}
    cs = containers(fx)
    if p == "azurerm":
        for rt, n, _ in resources(fx):
            if rt == "azurerm_storage_account":
                units[f"namespace:{rt}.{n}"] = {"kind": "ENTITY", "owner": "self", "lifecycle_controller": "self",
                                                "missing_evidence": [], "rules": ["DEC-OWN-ID"]}
        for c in cs:
            acct = azure_account(fx, c)
            units[f"container:{c}"] = {"kind": "ENTITY", "owner": "self", "lifecycle_controller": "self",
                                       "namespace": f"namespace:{acct}" if acct else "UNKNOWN",
                                       "missing_evidence": [] if acct else ["namespace"],
                                       "rules": ["DEC-AZ-CONTAINER"]}
    else:
        for c in cs:
            units[f"container:{c}"] = {"kind": "ENTITY", "owner": "self", "lifecycle_controller": "self",
                                       "missing_evidence": [], "rules": ["DEC-OCI-BUCKET" if p == "oci" else "DEC-OWN-ID"]}
    for kind, by, target, owner_level in _setting_units(fx):
        if owner_level == "namespace":
            units[f"setting:{kind}@namespace:context"] = {"kind": "UNKNOWN", "owner": "UNKNOWN", "effective_scope": "UNKNOWN",
                                                          "lifecycle_controller": "UNKNOWN", "realized_by": [by],
                                                          "missing_evidence": ["owner", "effective_scope", "lifecycle_controller"],
                                                          "rules": ["DEC-OCI-NAMESPACE"]}
            continue
        if owner_level == "account" and p == "aws":
            owner = "account:context"
            scope = {"all_in": "account:context", "known": sorted(f"container:{c}" for c in cs)}
            rules = ["AWS-PAB-ACCOUNT-SCOPE"]
        elif target is None:
            units[f"setting:{kind}@UNRESOLVED:{by}"] = {"kind": "UNKNOWN", "owner": "UNKNOWN", "effective_scope": "UNKNOWN",
                                                        "lifecycle_controller": "UNKNOWN", "realized_by": [by],
                                                        "missing_evidence": ["owner"], "rules": ["REF-UNRESOLVED"]}
            continue
        elif owner_level == "account":
            owner = f"namespace:{target}"
            members = [c for c in cs if azure_account(fx, c) == target]
            scope = sorted(f"container:{c}" for c in members)
            rules = ["AZ-VER-SCOPE" if kind == "versioning" else ("AZ-LC-ACCOUNT" if kind == "lifecycle" else "AZ-NESTED")]
            if kind == "lifecycle":
                prefixes = sorted({x for r in blk(res(fx, by), "rule") for f in blk(r, "filters")
                                   for x in f.get("prefix_match", [])})
                if prefixes:
                    def hit(name):
                        return any((name == x.split("/", 1)[0]) if "/" in x else name.startswith(x) for x in prefixes)
                    scope = sorted(f"container:{c}" for c in members if hit(res(fx, c).get("name") or ""))
                    rules.append("AZ-LC-PREFIX")
        else:
            owner = f"container:{target}"
            scope = [f"container:{target}"]
            rules = ["DEC-FACET-REF"]
        uid = f"setting:{kind}@{owner}"
        u = units.setdefault(uid, {"kind": "FACET", "owner": owner, "effective_scope": scope, "lifecycle_controller": "parent"
                                   if owner_level != "account" or p != "aws" else "external",
                                   "realized_by": [], "missing_evidence": [], "rules": rules})
        u["realized_by"] = sorted(set(u["realized_by"] + [by]))
    for u in units.values():
        u["rules"] = sorted(set(u["rules"]))
    return dict(sorted(units.items()))


def neutral_decomposition(units):
    """Projeção sem 'realized_by' nem regras: o que tem de ser invariante à embalagem."""
    return {k: {kk: vv for kk, vv in v.items() if kk not in ("realized_by", "rules")} for k, v in units.items()}


# ----------------------------------------------------------------------------------------------------------
# Estado efetivo completo e julgamentos
# ----------------------------------------------------------------------------------------------------------
def _j(v):
    if is_unk(v):
        return v.to_json()
    if isinstance(v, dict):
        return {k: _j(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_j(x) for x in v]
    return v


def effective_state(fx):
    """Tudo o que o oráculo afirma sobre a fixture (serializável)."""
    out = {"provider": fx["provider"], "oracle_version": ORACLE_VERSION, "containers": {}}
    for c in containers(fx):
        out["containers"][c] = {"versioning": _j(versioning(fx, c)), "public_access": _j(public_access(fx, c))}
    if fx.get("timeline"):
        out["timeline"] = _j(simulate(fx))
    out["decomposition"] = decompose(fx)
    return out


LOSS_CODES = {
    # divergências cobríveis por perda declarada
    "RETAINED_LONGER": "versão mantida no alvo que a origem já apagou",
    "EXPIRED_LATER": "versão corrente no alvo que a origem já tornou não corrente",
    "ACCESS_NARROWED": "eixo de acesso público concedido na origem e negado no alvo",
    "SCOPE_WIDENED": "configuração do alvo alcança contêineres além dos traduzidos",
    "VERSIONING_STATE_DIFFERS": "estado de versionamento diferente sem perda de versão observável",
    # nunca cobríveis (o contraexemplo tem de continuar rejeitado)
    "EARLY_DELETION": "versão apagada no alvo que a origem mantém",
    "EARLY_EXPIRATION": "versão não corrente no alvo que a origem mantém corrente",
    "PUBLIC_WIDENED": "eixo de acesso público negado na origem e concedido no alvo",
}
NEVER_COVERABLE = {"EARLY_DELETION", "EARLY_EXPIRATION", "PUBLIC_WIDENED"}


def _cmp_timeline(src, tgt, mapping):
    div = []
    for vid, s in src["versions"].items():
        t = tgt["versions"].get(mapping.get(vid, vid))
        if t is None:
            div.append(("EARLY_DELETION", vid))
            continue
        if s["state"] != "DELETED" and t["state"] == "DELETED":
            div.append(("EARLY_DELETION", vid))
        elif s["state"] == "DELETED" and t["state"] != "DELETED":
            div.append(("RETAINED_LONGER", vid))
        elif s["state"] == "CURRENT" and t["state"] == "NONCURRENT":
            div.append(("EARLY_EXPIRATION", vid))
        elif s["state"] == "NONCURRENT" and t["state"] == "CURRENT":
            div.append(("EXPIRED_LATER", vid))
    return div


def judge(src, tgt, declared_losses=(), container_map=None):
    """Julga a configuração-alvo tgt (outro provedor) contra a de origem src.

    container_map: {contêiner da origem: contêiner do alvo}; os demais contêineres do alvo são vizinhos
    (bystanders) cujo estado não pode mudar sem perda declarada de alcance."""
    declared = set(declared_losses)
    unknown_codes, div = [], []
    cmap = container_map or {}
    for sc, tc in sorted(cmap.items()):
        sv, tv = versioning(src, sc), versioning(tgt, tc)
        if is_unk(sv) or is_unk(tv):
            unknown_codes.append((sv if is_unk(sv) else tv).code)
        elif sv["value"] != tv["value"]:
            # a diferença de estado só pesa como perda observável se a linha do tempo não a mostrar
            div.append(("VERSIONING_STATE_DIFFERS", sc))
        sp, tp = public_access(src, sc)["axes"], public_access(tgt, tc)["axes"]
        for a in AXES:
            if is_unk(sp[a]) or is_unk(tp[a]):
                unknown_codes.append((sp[a] if is_unk(sp[a]) else tp[a]).code)
            elif sp[a] and not tp[a]:
                div.append(("ACCESS_NARROWED", f"{sc}:{a}"))
            elif tp[a] and not sp[a]:
                div.append(("PUBLIC_WIDENED", f"{sc}:{a}"))
    if src.get("timeline") and tgt.get("timeline"):
        ss, ts = simulate(src), simulate(tgt)
        if is_unk(ss) or is_unk(ts):
            unknown_codes.append((ss if is_unk(ss) else ts).code)
        else:
            if ss["unknown_keys"] or ts["unknown_keys"]:
                unknown_codes.append("MISSING_EVIDENCE")
            div += _cmp_timeline(ss, ts, {})
    # alcance: configurações de nível de conta no alvo que alcançam vizinhos
    for b in (tgt.get("context") or {}).get("bystanders", []):
        before, after = b.get("before", {}), {}
        if "versioning" in before:
            v = versioning(tgt, b["container"])
            after["versioning"] = v.code if is_unk(v) else v["value"]
        if "lifecycle_rules" in before:
            r = lifecycle_rules(tgt, b["container"])
            after["lifecycle_rules"] = r.code if is_unk(r) else len([x for x in r if x.get("enabled", True)])
        if after != before:
            div.append(("SCOPE_WIDENED", b["container"]))
    codes = sorted({d[0] for d in div})
    detail = {"divergences": [list(d) for d in sorted(set(div))], "unknown_codes": sorted(set(unknown_codes)),
              "declared_losses": sorted(declared), "spurious_declared": sorted(declared - set(codes))}
    never = sorted(set(codes) & NEVER_COVERABLE)
    if never:
        return {"verdict": "REJECT", "code": never[0], **detail}
    if unknown_codes:
        return {"verdict": "UNKNOWN", "code": sorted(set(unknown_codes))[0], **detail}
    silent = sorted(set(codes) - declared)
    if silent:
        return {"verdict": "REJECT", "code": "SILENT_LOSS", "silent": silent, **detail}
    if codes:
        return {"verdict": "ACCEPT_WITH_DECLARED_LOSS", **detail}
    return {"verdict": "ACCEPT", **detail}


def judge_claim(fx, claim):
    """Alegação sobre a fixture: {'about': 'versioning'|'public_access'|'version_state'|'decomposition', ...}.
    ACCEPT só se a alegação coincide com o oráculo; alegação definida onde o oráculo diz UNKNOWN é REJECT."""
    about = claim["about"]
    if about == "versioning":
        v = versioning(fx, claim["container"])
        truth = "UNKNOWN" if is_unk(v) else v["value"]
        got = claim["value"]
    elif about == "public_access":
        ax = public_access(fx, claim["container"])["axes"][claim["axis"]]
        truth = "UNKNOWN" if is_unk(ax) else ax
        got = claim["value"]
    elif about == "version_state":
        s = simulate(fx)
        if is_unk(s):
            truth = "UNKNOWN"
        elif claim["key"] in s["unknown_keys"]:
            truth = "UNKNOWN"
        else:
            truth = s["versions"].get(claim["version"], {"state": "ABSENT"})["state"]
        got = claim["value"]
    elif about == "decomposition":
        units = decompose(fx)
        u = units.get(claim["unit"])
        truth = None if u is None else {k: u.get(k) for k in claim["value"]}
        got = claim["value"]
        if u is None and claim.get("value", {}).get("kind") is not None:
            return {"verdict": "REJECT", "code": "NO_SUCH_UNIT", "truth": None}
    elif about == "disjoint_kinds":
        kinds = set(claim["kinds"])
        both = {"storage_namespace", "object_container"} <= kinds
        return {"verdict": "REJECT" if both else "ACCEPT", "code": "INCONSISTENT" if both else None, "truth": not both}
    else:
        raise FixtureError(f"alegação desconhecida: {about}")
    if truth == got:
        return {"verdict": "ACCEPT", "truth": truth}
    code = "CLAIMS_CERTAINTY" if truth == "UNKNOWN" else "CONTRADICTS_ORACLE"
    return {"verdict": "REJECT", "code": code, "truth": truth}


def load(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def deep(fx):
    return copy.deepcopy(fx)


# ----------------------------------------------------------------------------------------------------------
# Conferência de uma resposta esperada (usada pelos testes, pelo build e pelo PILOT-EXIT nas retidas)
# ----------------------------------------------------------------------------------------------------------
def _as_expect(v):
    if is_unk(v):
        return {"unknown": v.code}
    return v


def evaluate_check(fx, chk):
    """Devolve (ok, obtido) para uma conferência {'kind': ..., 'expect': ...} de expected_answers.json."""
    k = chk["kind"]
    if k == "versioning":
        v = versioning(fx, chk["container"])
        got = _as_expect(v) if is_unk(v) else v["value"]
    elif k == "public":
        got = _as_expect(public_access(fx, chk["container"])["axes"][chk["axis"]])
    elif k == "apply_rejection":
        got = sorted(r["what"] for r in public_access(fx, chk["container"])["apply_rejections"])
    elif k in ("version_state", "timeline", "key_unknown"):
        s = simulate(fx)
        if k == "timeline":
            got = _as_expect(s) if is_unk(s) else "DEFINED"
        elif is_unk(s):
            got = _as_expect(s)
        elif k == "key_unknown":
            u = s["unknown_keys"].get(chk["key"])
            got = {"unknown": u["code"]} if u else "DEFINED"
        else:
            got = s["versions"].get(chk["version"], {"state": "ABSENT"})["state"]
    elif k == "decomposition":
        u = decompose(fx).get(chk["unit"])
        got = None if u is None else {kk: u.get(kk) for kk in chk["expect"]}
    elif k == "claim":
        j = judge_claim(fx, chk["claim"])
        got = {kk: j.get(kk) for kk in chk["expect"]}
    else:
        raise FixtureError(f"conferência desconhecida: {k}")
    return got == chk["expect"], got


def evaluate_entry(entry):
    """Julga uma entrada de direção; devolve (ok, veredito completo)."""
    j = judge(entry["source"], entry["target"], entry.get("declared_losses", ()), entry["container_map"])
    got = {kk: j.get(kk) for kk in entry["expect"]}
    return got == entry["expect"], j


def polarity_consistent(polarity, checks):
    """Positivo: só respostas definidas; negativo: ao menos um contraexemplo REJEITADO; desconhecido: ao menos
    uma resposta UNKNOWN (valor ou unidade de grão UNKNOWN)."""
    def is_unknown(c):
        e = c["expect"]
        return isinstance(e, dict) and ("unknown" in e or (c["kind"] == "decomposition" and e.get("kind") == "UNKNOWN"))
    if polarity == "negative":
        return any(c["kind"] == "claim" and c["expect"].get("verdict") == "REJECT" for c in checks)
    if polarity == "unknown":
        return any(is_unknown(c) for c in checks)
    return bool(checks) and not any(c["kind"] == "claim" for c in checks) and not any(
        isinstance(c["expect"], dict) and "unknown" in c["expect"] for c in checks)
