"""Decisões do mapeador PILOT-STO-MAP sobre o pacote do PILOT-STO-GLOSS (fatia sto, 6 pares).

Este arquivo é o juízo do mapeador (modelo claude-opus-5-5), escrito lendo SÓ o pacote (candidatos, átomos,
unidades, glossário, decisões e âncoras com as sentenças publicadas, value_space) e o MAPPER_BRIEF 1.2.0. O
build transforma cada decisão numa linha C09; tipos, conceitos, sentenças e estado de evidência saem do pacote
na hora do build (rerodar com um pacote novo refaz tudo, ver build.py). Nada aqui é veredito: o árbitro julga.

Formas:
  X(...)  alegação que transporta (exact | close | broad | narrow): função do registro, fidelidade, relação de
          domínio declarada (o árbitro recalcula), perdas, testes que rodam, e a intenção de evidência:
          'doc' = li as duas sentenças publicadas do pacote e elas sustentam a relação (o build rebaixa para
          STRUCTURALLY_VALID se alguma sentença falta ou se a âncora do átomo está UNRESOLVED no pacote);
          'structural' = não há sentença que sustente.
  R(...)  relação related (alinhamento sem transporte) + o tipo de ausência que o build grava para os átomos do
          par sem alegação que transporte, com o motivo (MAPPER_BRIEF M8).
Regras que segui (e que os testes conferem): só átomos do pacote; só funções do registro fechado; nenhum valor
de enum, faixa ou unidade inventado (quando o destino não tem enum no pacote, não há tabela: vira R); nenhuma
volta gravada como segunda linha; nenhum vencedor escolhido entre as realizações duplas do aws (bloco embutido
legado e recurso separado): as duas entram e o árbitro decide (ARB-REAL-MULTI).
"""

from __future__ import annotations

from dataclasses import dataclass, field

MAPPING_DATE = "2026-11-04"
DECIDED_AT = "2026-11-04T09:00:00-03:00"     # instante fixo do julgamento no pipeline (vereditos reprodutíveis)


@dataclass(frozen=True)
class Decision:
    claim_id: str
    pair: str
    subject: str
    object: str
    relation: str                     # exact | close | broad | narrow | related
    fn: object = None                 # {"name", "params"} do registro, ou None (related)
    fidelity: str = "none"
    vdr: str = "unknown"
    tests: tuple = ()
    evidence: str = "doc"             # doc | structural
    loss: tuple = ()
    note: str = ""
    absence_kind: str | None = None   # só em R
    absence_why: str = ""
    membership: dict | None = None
    guard: dict = field(default_factory=lambda: {"all": []})


def X(cid, pair, s, o, rel, fn, fid, vdr, tests, ev="doc", loss=(), note="", membership=None):
    return Decision(cid, pair, s, o, rel, fn, fid, vdr, tuple(tests), ev, tuple(loss), note, None, "", membership)


def R(cid, pair, s, o, kind, why, ev="doc", note=""):
    return Decision(cid, pair, s, o, "related", None, "none", "unknown", (), ev, (), note, kind, why)


ID = {"name": "identity", "params": {}}
STR = ({"input": "exemplo-01", "expected": "exemplo-01"},)
BOOL = ({"input": True, "expected": True}, {"input": False, "expected": False})
DAYS = ({"input": 30, "expected": 30}, {"input": 365, "expected": 365})
BYTES = ({"input": 1048576, "expected": 1048576},)
LIST = ({"input": ["logs/"], "expected": ["logs/"]},)
WRAP = {"name": "wrap_list", "params": {}}
WRAPPED = ({"input": "logs/", "expected": ["logs/"]},)
N_WRAP = ("prefixo único na origem -> lista de um prefixo no destino (wrap_list, C10 1.4.0): todo valor da origem "
          "cabe (subset), sem perda; a volta é unwrap_single, só para listas de um elemento")


def e2b(true, false):
    return {"name": "enum_to_bool", "params": {"true": list(true), "false": list(false)}}


def e2b_tests(true, false):
    return tuple({"input": v, "expected": True} for v in true) + tuple({"input": v, "expected": False} for v in false)


# --------------------------------------------------------------------------------------- motivos reutilizados
W_REGION = ("os códigos de região de cada provedor não estão no pacote (texto sem enum nem tabela); traduzir "
            "exigiria inventar a tabela de regiões")
W_REGION_AZ = ("no destino a localização é da conta de armazenamento (outra unidade, ligada ao contêiner por "
               "contenção) e os códigos de região não estão no pacote")
W_CLASS = ("os nomes de classe de armazenamento de cada lado não estão no pacote (texto sem enum) ou não se "
           "correspondem um a um; a tabela teria de ser inventada")
W_KEY = ("o valor é referência a uma chave no serviço de chaves de cada provedor; a chave do outro lado é outra "
         "unidade, e o registro não traduz referência entre provedores")
W_CTX_ACTION = ("na origem o número só vale para uma ação (expirar ou mudar de classe); no destino é condição de "
                "qualquer ação, e a guarda precisaria do valor de action.type, que o pacote não traz como enum")
W_CTX_ACTION_REV = ("na origem a idade é condição de qualquer ação; no destino cada campo fixa a ação (apagar ou "
                    "mudar de camada), e a guarda precisaria do valor de action.type, que o pacote não traz como enum")
W_OCI_TIME = ("time_amount é texto no C05 e a unidade vem de outro campo (rules.time_unit, texto sem enum); o "
              "registro não converte número em texto e a guarda precisaria de valores de time_unit")
W_OCI_VERS = "os valores de versioning do destino não estão no pacote (texto sem enum); não há tabela sem inventar"
W_TRANSITION_AZ = ("a classe-alvo vem de outro campo na origem (transition.storage_class) e escolhe o CAMPO de "
                   "saída no destino (cool, cold ou archive); o registro não tem passo que escolha o campo pelo valor")
W_ACL_NAMES = "os nomes das ACLs predefinidas do destino não estão no pacote (texto sem enum)"
W_IDENTITY = ("identidade de usuário, grupo ou domínio de um provedor não existe no outro; o registro não "
              "traduz identidades")
W_POLICY = "linguagens de política diferentes; o registro não traduz documento de política"
W_LIST_FIELDS = ("a origem é uma lista de tipos bloqueados e o destino tem um modo por tipo; não há combinador "
                 "lista -> campos no registro e os valores não estão no pacote")
W_LIST_ROLE = "lista de permissões na origem, um papel por entrada no destino; o registro não separa lista"
W_SCOPE_AZ = ("no destino o versionamento é da conta de armazenamento e vale para todos os contêineres dela; na "
              "origem é de um contêiner")
W_SUSP = "o destino é booleano: Suspended e Disabled viram false e não se distinguem na volta"
W_GT = ("o destino compara 'maior que' N dias (nome do campo); a origem fala em 'depois de N dias'; a fronteira "
        "de um dia não é provada pelas sentenças")

LOSS_SCOPE_AZ = {"kind": "semantic", "why": W_SCOPE_AZ}
LOSS_SUSP = {"kind": "not_expressible", "why": W_SUSP}
LOSS_AZ_DAYS = ({"kind": "semantic", "why": W_GT},
                {"kind": "saturation", "min": 0, "max": 99999, "why": "o destino aceita de 0 a 99999 dias"})

# ------------------------------------------------------------------------------------------------ átomos aws
A_BUCKET = "aws:aws_s3_bucket:bucket"
A_REGION = "aws:aws_s3_bucket:region"
A_VER_BOOL = "aws:aws_s3_bucket:versioning.enabled"
A_VER_STATUS = "aws:aws_s3_bucket_versioning:versioning_configuration.status"
A_PREFIXES = ("aws:aws_s3_bucket:lifecycle_rule.prefix",
              "aws:aws_s3_bucket_lifecycle_configuration:rule.filter.and.prefix",
              "aws:aws_s3_bucket_lifecycle_configuration:rule.filter.prefix",
              "aws:aws_s3_bucket_lifecycle_configuration:rule.prefix")
A_TRANS_CLASS = ("aws:aws_s3_bucket:lifecycle_rule.transition.storage_class",
                 "aws:aws_s3_bucket_lifecycle_configuration:rule.transition.storage_class")
A_NONCUR_DAYS = ("aws:aws_s3_bucket:lifecycle_rule.noncurrent_version_expiration.days",
                 "aws:aws_s3_bucket_lifecycle_configuration:rule.noncurrent_version_expiration.noncurrent_days")
A_NEWER = "aws:aws_s3_bucket_lifecycle_configuration:rule.noncurrent_version_expiration.newer_noncurrent_versions"
A_GT, A_AND_GT = ("aws:aws_s3_bucket_lifecycle_configuration:rule.filter.object_size_greater_than",
                  "aws:aws_s3_bucket_lifecycle_configuration:rule.filter.and.object_size_greater_than")
A_LT, A_AND_LT = ("aws:aws_s3_bucket_lifecycle_configuration:rule.filter.object_size_less_than",
                  "aws:aws_s3_bucket_lifecycle_configuration:rule.filter.and.object_size_less_than")
A_KMS = ("aws:aws_s3_bucket:server_side_encryption_configuration.rule.apply_server_side_encryption_by_default."
         "kms_master_key_id",
         "aws:aws_s3_bucket_server_side_encryption_configuration:rule.apply_server_side_encryption_by_default."
         "kms_master_key_id")
A_BLOCKED = "aws:aws_s3_bucket_server_side_encryption_configuration:rule.blocked_encryption_types"
A_ACL = ("aws:aws_s3_bucket:acl", "aws:aws_s3_bucket_acl:acl")
A_GRANT_PERMS = "aws:aws_s3_bucket:grant.permissions"
A_GRANT_PERM = "aws:aws_s3_bucket_acl:access_control_policy.grant.permission"
A_GRANTEES = ("aws:aws_s3_bucket:grant.id", "aws:aws_s3_bucket:grant.uri",
              "aws:aws_s3_bucket_acl:access_control_policy.grant.grantee.id",
              "aws:aws_s3_bucket_acl:access_control_policy.grant.grantee.uri")
A_POLICY = ("aws:aws_s3_bucket:policy", "aws:aws_s3_bucket_policy:policy")
A_RULE_BOOL = "aws:aws_s3_bucket:lifecycle_rule.enabled"
A_RULE_STATUS = "aws:aws_s3_bucket_lifecycle_configuration:rule.status"
A_RULE_IDS = ("aws:aws_s3_bucket:lifecycle_rule.id", "aws:aws_s3_bucket_lifecycle_configuration:rule.id")
A_EXP_DAYS = ("aws:aws_s3_bucket:lifecycle_rule.expiration.days",
              "aws:aws_s3_bucket_lifecycle_configuration:rule.expiration.days")
A_TRANS_DAYS = ("aws:aws_s3_bucket:lifecycle_rule.transition.days",
                "aws:aws_s3_bucket_lifecycle_configuration:rule.transition.days")
A_BUCKET_KEY = ("aws:aws_s3_bucket:server_side_encryption_configuration.rule.bucket_key_enabled",
                "aws:aws_s3_bucket_server_side_encryption_configuration:rule.bucket_key_enabled")

# --------------------------------------------------------------------------------------------- átomos google
G_NAME = "google:google_storage_bucket:name"
G_LOCATION = "google:google_storage_bucket:location"
G_VER = "google:google_storage_bucket:versioning.enabled"
G_PREFIX = "google:google_storage_bucket:lifecycle_rule.condition.matches_prefix"
G_ACTION_CLASS = "google:google_storage_bucket:lifecycle_rule.action.storage_class"
G_NONCUR = "google:google_storage_bucket:lifecycle_rule.condition.days_since_noncurrent_time"
G_NEWER = "google:google_storage_bucket:lifecycle_rule.condition.num_newer_versions"
G_ABOVE = "google:google_storage_bucket:lifecycle_rule.condition.size_above_bytes"
G_BELOW = "google:google_storage_bucket:lifecycle_rule.condition.size_below_bytes"
G_KMS = "google:google_storage_bucket:encryption.default_kms_key_name"
G_RESTRICT = tuple(f"google:google_storage_bucket:encryption.{k}_encryption_enforcement_config.restriction_mode"
                   for k in ("customer_managed", "customer_supplied", "google_managed"))
G_PREDEF = "google:google_storage_bucket_acl:predefined_acl"
G_ROLE = "google:google_storage_bucket_access_control:role"
G_ENTITY = "google:google_storage_bucket_access_control:entity"
G_POLICY = "google:google_storage_bucket_iam_policy:policy_data"
G_AGE = "google:google_storage_bucket:lifecycle_rule.condition.age"
G_CLASS = "google:google_storage_bucket:storage_class"
G_ACTION = "google:google_storage_bucket:lifecycle_rule.action.type"

# ---------------------------------------------------------------------------------------------- átomos azure
Z_NAME = "azurerm:azurerm_storage_container:name"
Z_LOCATION = "azurerm:azurerm_storage_account:location"
Z_VER = "azurerm:azurerm_storage_account:blob_properties.versioning_enabled"
Z_RULE_EN = "azurerm:azurerm_storage_management_policy:rule.enabled"
Z_RULE_NAME = "azurerm:azurerm_storage_management_policy:rule.name"
Z_PREFIX = "azurerm:azurerm_storage_management_policy:rule.filters.prefix_match"
Z_BASE = "azurerm:azurerm_storage_management_policy:rule.actions.base_blob."
Z_DELETE = Z_BASE + "delete_after_days_since_creation_greater_than"
Z_TIERS = tuple(Z_BASE + f"tier_to_{t}_after_days_since_creation_greater_than" for t in ("archive", "cold", "cool"))
Z_KMS = ("azurerm:azurerm_storage_account:customer_managed_key.key_vault_key_id",
         "azurerm:azurerm_storage_account_customer_managed_key:key_vault_key_id")
Z_TIER = "azurerm:azurerm_storage_account:access_tier"
Z_ACCESS = "azurerm:azurerm_storage_container:container_access_type"

# ------------------------------------------------------------------------------------------------ átomos oci
O_NAME = "oci:oci_objectstorage_bucket:name"
O_VER = "oci:oci_objectstorage_bucket:versioning"
O_RULE_EN = "oci:oci_objectstorage_object_lifecycle_policy:rules.is_enabled"
O_RULE_NAME = "oci:oci_objectstorage_object_lifecycle_policy:rules.name"
O_PREFIX = "oci:oci_objectstorage_object_lifecycle_policy:rules.object_name_filter.inclusion_prefixes"
O_KMS = "oci:oci_objectstorage_bucket:kms_key_id"
O_BUCKET_KEY = "oci:oci_objectstorage_bucket:is_bucket_key_enabled"
O_TIER = "oci:oci_objectstorage_bucket:storage_tier"
O_TIME = "oci:oci_objectstorage_object_lifecycle_policy:rules.time_amount"
O_ACTION = "oci:oci_objectstorage_object_lifecycle_policy:rules.action"
O_ACCESS = "oci:oci_objectstorage_bucket:access_type"

# Ocorrência em bloco repetido (MAPPER_BRIEF M6): só com campo de identidade sustentado pelo pacote.
#   aws_s3_bucket.lifecycle_rule: key_fields ['id'] declarado na unidade C19 do pacote;
#   aws_s3_bucket_lifecycle_configuration.rule: 'id', sentença publicada "Unique identifier for the rule.";
#   azurerm_storage_management_policy.rule: 'name', sentença publicada "It must be unique within a policy.".
# Sem chave sustentada (ficam sem projeção de bloco, e isso vai ao relatório): google lifecycle_rule (nenhum
# campo de identidade no pacote), oci rules ('name' sem sentença de unicidade), ACL e criptografia do aws.
BLOCKS = (
    ("aws:aws_s3_bucket:lifecycle_rule.", ("id",), "unidade CU-aws-aws_s3_bucket.lifecycle_rule (key_fields)"),
    ("aws:aws_s3_bucket_lifecycle_configuration:rule.", ("id",), "âncora de rule.id: Unique identifier for the rule."),
    ("azurerm:azurerm_storage_management_policy:rule.", ("name",), "âncora de rule.name: unique within a policy"),
)
UNKEYED_BLOCKS = (
    ("google:google_storage_bucket:lifecycle_rule.", "nenhum campo de identidade da regra no pacote"),
    ("oci:oci_objectstorage_object_lifecycle_policy:rules.", "rules.name sem sentença de unicidade no pacote"),
    ("aws:aws_s3_bucket_acl:access_control_policy.grant.", "entrada de ACL sem campo de identidade no pacote"),
)

# Ausências demonstradas (o resto das ausências fica UNRESOLVED): conceitos que só um provedor tem na fatia
# (decisão 'exclusive' do glossário congelado) e que eu confirmo pelo pacote do outro lado (nenhum átomo do
# outro provedor ancorado no conceito nem candidato dele). Fora desta lista ficaram, de propósito, conceitos
# exclusivos que podem estar num VALOR de enum que o pacote não traz (ex.: abortar envio em partes como valor de
# action.type no google; criptografia dupla como valor de sse_algorithm no aws).
DEMONSTRATED_CONCEPTS = ("concept:versioning_mfa_delete", "concept:expired_delete_marker_removal",
                         "concept:container_default_encryption_scope")


def _seq(pair, start, items, fn):
    return [fn(f"CLM-{pair}-STO-{start + i:04d}", x) for i, x in enumerate(items)]


DECISIONS: list[Decision] = []
D = DECISIONS.append

# ==================================================================================================== AWSGCP
D(X("CLM-AWSGCP-STO-0001", "AWSGCP", A_BUCKET, G_NAME, "exact", ID, "partial", "unknown", STR,
    note="nome do contêiner nos dois; regras de formato de nome não estão no pacote: domínio unknown, parcial"))
D(R("CLM-AWSGCP-STO-0002", "AWSGCP", A_REGION, G_LOCATION, "UNRESOLVED", W_REGION))
D(X("CLM-AWSGCP-STO-0003", "AWSGCP", A_VER_BOOL, G_VER, "exact", ID, "lossless", "equal", BOOL))
D(X("CLM-AWSGCP-STO-0004", "AWSGCP", A_VER_STATUS, G_VER, "exact",
    e2b(["Enabled"], ["Suspended", "Disabled"]), "declared_loss", "equal",
    e2b_tests(["Enabled"], ["Suspended", "Disabled"]), loss=[LOSS_SUSP]))
DECISIONS += _seq("AWSGCP", 5, A_PREFIXES,
                  lambda c, a: X(c, "AWSGCP", a, G_PREFIX, "exact", WRAP, "lossless", "subset", WRAPPED, note=N_WRAP))
DECISIONS += _seq("AWSGCP", 9, A_TRANS_CLASS, lambda c, a: R(c, "AWSGCP", a, G_ACTION_CLASS, "UNRESOLVED", W_CLASS))
DECISIONS += _seq("AWSGCP", 11, A_NONCUR_DAYS, lambda c, a: R(c, "AWSGCP", a, G_NONCUR, "UNRESOLVED", W_CTX_ACTION))
D(R("CLM-AWSGCP-STO-0013", "AWSGCP", A_NEWER, G_NEWER, "UNRESOLVED",
    "grandeza e unidade UNKNOWN nos dois lados (C05) e a condição do destino vale para qualquer ação da regra"))
D(X("CLM-AWSGCP-STO-0014", "AWSGCP", A_GT, G_ABOVE, "exact", ID, "partial", "unknown", BYTES,
    note="mínimo estrito ('greater than') nos dois, em bytes"))
D(X("CLM-AWSGCP-STO-0015", "AWSGCP", A_AND_GT, G_ABOVE, "exact", ID, "partial", "unknown", BYTES))
D(X("CLM-AWSGCP-STO-0016", "AWSGCP", A_LT, G_BELOW, "exact", ID, "partial", "unknown", BYTES,
    note="máximo estrito ('less than' / 'smaller than') nos dois, em bytes"))
D(X("CLM-AWSGCP-STO-0017", "AWSGCP", A_AND_LT, G_BELOW, "exact", ID, "partial", "unknown", BYTES))
DECISIONS += _seq("AWSGCP", 18, A_KMS, lambda c, a: R(c, "AWSGCP", a, G_KMS, "UNSUPPORTED_BY_TRANSLATOR", W_KEY))
DECISIONS += _seq("AWSGCP", 20, G_RESTRICT,
                  lambda c, o: R(c, "AWSGCP", A_BLOCKED, o, "UNSUPPORTED_BY_TRANSLATOR", W_LIST_FIELDS))
DECISIONS += _seq("AWSGCP", 23, A_ACL, lambda c, a: R(c, "AWSGCP", a, G_PREDEF, "UNRESOLVED", W_ACL_NAMES))
D(X("CLM-AWSGCP-STO-0025", "AWSGCP", A_GRANT_PERM, G_ROLE, "close",
    {"name": "enum_map", "params": {"table": {"FULL_CONTROL": "OWNER", "WRITE": "WRITER", "READ": "READER"}}},
    "declared_loss", "superset",
    ({"input": "FULL_CONTROL", "expected": "OWNER"}, {"input": "WRITE", "expected": "WRITER"},
     {"input": "READ", "expected": "READER"}),
    loss=[{"kind": "semantic", "why": "os papéis do destino não são definidos pelas mesmas ações que as "
                                      "permissões da origem (tabela do mapeador, sem sentença que a sustente)"},
          {"kind": "not_expressible", "why": "READ_ACP e WRITE_ACP não têm papel próprio no destino"}],
    note="tabela por conhecimento do mapeador; a sentença publicada da origem descreve permissão de log"))
D(R("CLM-AWSGCP-STO-0026", "AWSGCP", A_GRANT_PERMS, G_ROLE, "UNSUPPORTED_BY_TRANSLATOR", W_LIST_ROLE))
DECISIONS += _seq("AWSGCP", 27, A_GRANTEES,
                  lambda c, a: R(c, "AWSGCP", a, G_ENTITY, "UNSUPPORTED_BY_TRANSLATOR", W_IDENTITY))
DECISIONS += _seq("AWSGCP", 31, A_POLICY, lambda c, a: R(c, "AWSGCP", a, G_POLICY, "UNSUPPORTED_BY_TRANSLATOR", W_POLICY))
DECISIONS += _seq("AWSGCP", 33, A_EXP_DAYS + A_TRANS_DAYS,
                  lambda c, a: R(c, "AWSGCP", a, G_AGE, "UNRESOLVED", W_CTX_ACTION,
                                 note="glossário: idade de expiração/transição é mais estreita que a idade-condição"))

# ===================================================================================================== AWSAZ
D(X("CLM-AWSAZ-STO-0001", "AWSAZ", A_BUCKET, Z_NAME, "exact", ID, "partial", "unknown", STR,
    note="nome do contêiner; no destino o nome é único dentro da conta de armazenamento"))
D(R("CLM-AWSAZ-STO-0002", "AWSAZ", A_REGION, Z_LOCATION, "UNRESOLVED", W_REGION_AZ))
D(X("CLM-AWSAZ-STO-0003", "AWSAZ", A_VER_BOOL, Z_VER, "close", ID, "declared_loss", "equal", BOOL,
    loss=[LOSS_SCOPE_AZ]))
D(X("CLM-AWSAZ-STO-0004", "AWSAZ", A_VER_STATUS, Z_VER, "close",
    e2b(["Enabled"], ["Suspended", "Disabled"]), "declared_loss", "equal",
    e2b_tests(["Enabled"], ["Suspended", "Disabled"]), loss=[LOSS_SCOPE_AZ, LOSS_SUSP]))
D(X("CLM-AWSAZ-STO-0005", "AWSAZ", A_RULE_BOOL, Z_RULE_EN, "exact", ID, "lossless", "equal", BOOL))
D(X("CLM-AWSAZ-STO-0006", "AWSAZ", A_RULE_STATUS, Z_RULE_EN, "exact", e2b(["Enabled"], ["Disabled"]),
    "lossless", "equal", e2b_tests(["Enabled"], ["Disabled"]),
    note="bijeção Enabled/Disabled <-> true/false"))
DECISIONS += _seq("AWSAZ", 7, A_RULE_IDS,
                  lambda c, a: X(c, "AWSAZ", a, Z_RULE_NAME, "exact", ID, "partial", "unknown", STR))
DECISIONS += _seq("AWSAZ", 9, A_PREFIXES,
                  lambda c, a: X(c, "AWSAZ", a, Z_PREFIX, "exact", WRAP, "lossless", "subset", WRAPPED, note=N_WRAP))
DECISIONS += _seq("AWSAZ", 13, A_EXP_DAYS,
                  lambda c, a: X(c, "AWSAZ", a, Z_DELETE, "close", ID, "declared_loss", "unknown", DAYS,
                                 loss=list(LOSS_AZ_DAYS)))
DECISIONS += _seq("AWSAZ", 15, [(a, z) for a in A_TRANS_DAYS for z in Z_TIERS],
                  lambda c, az: R(c, "AWSAZ", az[0], az[1], "UNSUPPORTED_BY_TRANSLATOR", W_TRANSITION_AZ))
DECISIONS += _seq("AWSAZ", 21, [(a, z) for a in A_KMS for z in Z_KMS],
                  lambda c, az: R(c, "AWSAZ", az[0], az[1], "UNSUPPORTED_BY_TRANSLATOR", W_KEY))

# ==================================================================================================== AWSOCI
D(X("CLM-AWSOCI-STO-0001", "AWSOCI", A_BUCKET, O_NAME, "exact", ID, "partial", "unknown", STR))
D(R("CLM-AWSOCI-STO-0002", "AWSOCI", A_VER_BOOL, O_VER, "UNRESOLVED", W_OCI_VERS))
D(R("CLM-AWSOCI-STO-0003", "AWSOCI", A_VER_STATUS, O_VER, "UNRESOLVED", W_OCI_VERS))
D(X("CLM-AWSOCI-STO-0004", "AWSOCI", A_RULE_BOOL, O_RULE_EN, "exact", ID, "lossless", "equal", BOOL))
D(X("CLM-AWSOCI-STO-0005", "AWSOCI", A_RULE_STATUS, O_RULE_EN, "exact", e2b(["Enabled"], ["Disabled"]),
    "lossless", "equal", e2b_tests(["Enabled"], ["Disabled"])))
DECISIONS += _seq("AWSOCI", 6, A_RULE_IDS,
                  lambda c, a: X(c, "AWSOCI", a, O_RULE_NAME, "exact", ID, "partial", "unknown", STR))
DECISIONS += _seq("AWSOCI", 8, A_PREFIXES,
                  lambda c, a: X(c, "AWSOCI", a, O_PREFIX, "exact", WRAP, "lossless", "subset", WRAPPED, note=N_WRAP))
DECISIONS += _seq("AWSOCI", 12, A_KMS, lambda c, a: R(c, "AWSOCI", a, O_KMS, "UNSUPPORTED_BY_TRANSLATOR", W_KEY))
DECISIONS += _seq("AWSOCI", 14, A_BUCKET_KEY,
                  lambda c, a: X(c, "AWSOCI", a, O_BUCKET_KEY, "exact", ID, "lossless", "equal", BOOL))
DECISIONS += _seq("AWSOCI", 16, A_EXP_DAYS + A_TRANS_DAYS,
                  lambda c, a: R(c, "AWSOCI", a, O_TIME, "UNSUPPORTED_BY_TRANSLATOR", W_OCI_TIME))

# ===================================================================================================== GCPAZ
D(X("CLM-GCPAZ-STO-0001", "GCPAZ", G_NAME, Z_NAME, "exact", ID, "partial", "unknown", STR))
D(R("CLM-GCPAZ-STO-0002", "GCPAZ", G_LOCATION, Z_LOCATION, "UNRESOLVED", W_REGION_AZ))
D(R("CLM-GCPAZ-STO-0003", "GCPAZ", G_CLASS, Z_TIER, "UNRESOLVED",
    W_CLASS + "; no destino a camada é da conta de armazenamento"))
D(X("CLM-GCPAZ-STO-0004", "GCPAZ", G_VER, Z_VER, "close", ID, "declared_loss", "equal", BOOL, loss=[LOSS_SCOPE_AZ]))
D(X("CLM-GCPAZ-STO-0005", "GCPAZ", G_PREFIX, Z_PREFIX, "exact", ID, "partial", "unknown", LIST,
    note="lista de prefixos nos dois (list<string> pelo C05, C09 3.2.0); restrições de formato fora do pacote"))
DECISIONS += _seq("GCPAZ", 6, Z_KMS, lambda c, z: R(c, "GCPAZ", G_KMS, z, "UNSUPPORTED_BY_TRANSLATOR", W_KEY))
DECISIONS += _seq("GCPAZ", 8, (Z_DELETE,) + Z_TIERS,
                  lambda c, z: R(c, "GCPAZ", G_AGE, z, "UNRESOLVED", W_CTX_ACTION_REV))

# ==================================================================================================== GCPOCI
D(X("CLM-GCPOCI-STO-0001", "GCPOCI", G_NAME, O_NAME, "exact", ID, "partial", "unknown", STR))
D(R("CLM-GCPOCI-STO-0002", "GCPOCI", G_CLASS, O_TIER, "UNRESOLVED", W_CLASS))
D(R("CLM-GCPOCI-STO-0003", "GCPOCI", G_VER, O_VER, "UNRESOLVED", W_OCI_VERS))
D(X("CLM-GCPOCI-STO-0004", "GCPOCI", G_PREFIX, O_PREFIX, "exact", ID, "partial", "unknown", LIST,
    note="lista de prefixos nos dois (list<string> pelo C05, C09 3.2.0); restrições de formato fora do pacote"))
D(R("CLM-GCPOCI-STO-0005", "GCPOCI", G_AGE, O_TIME, "UNSUPPORTED_BY_TRANSLATOR", W_OCI_TIME))
D(R("CLM-GCPOCI-STO-0006", "GCPOCI", G_ACTION, O_ACTION, "UNRESOLVED",
    "os nomes de ação de cada lado não estão no pacote (texto sem enum)"))
D(R("CLM-GCPOCI-STO-0007", "GCPOCI", G_KMS, O_KMS, "UNSUPPORTED_BY_TRANSLATOR", W_KEY))

# ===================================================================================================== AZOCI
D(X("CLM-AZOCI-STO-0001", "AZOCI", Z_NAME, O_NAME, "exact", ID, "partial", "unknown", STR))
D(R("CLM-AZOCI-STO-0002", "AZOCI", Z_TIER, O_TIER, "UNRESOLVED", W_CLASS))
D(R("CLM-AZOCI-STO-0003", "AZOCI", Z_VER, O_VER, "UNRESOLVED", W_OCI_VERS))
D(X("CLM-AZOCI-STO-0004", "AZOCI", Z_RULE_EN, O_RULE_EN, "exact", ID, "lossless", "equal", BOOL))
D(X("CLM-AZOCI-STO-0005", "AZOCI", Z_RULE_NAME, O_RULE_NAME, "exact", ID, "partial", "unknown", STR))
D(X("CLM-AZOCI-STO-0006", "AZOCI", Z_PREFIX, O_PREFIX, "exact", ID, "partial", "unknown", LIST,
    note="lista de prefixos nos dois (list<string> pelo C05, C09 3.2.0); restrições de formato fora do pacote"))
DECISIONS += _seq("AZOCI", 7, Z_KMS, lambda c, z: R(c, "AZOCI", z, O_KMS, "UNSUPPORTED_BY_TRANSLATOR", W_KEY))
D(R("CLM-AZOCI-STO-0009", "AZOCI", Z_ACCESS, O_ACCESS, "UNRESOLVED",
    "os valores de access_type do destino não estão no pacote (texto sem enum)"))
DECISIONS += _seq("AZOCI", 10, (Z_DELETE,) + Z_TIERS,
                  lambda c, z: R(c, "AZOCI", z, O_TIME, "UNSUPPORTED_BY_TRANSLATOR", W_OCI_TIME))
