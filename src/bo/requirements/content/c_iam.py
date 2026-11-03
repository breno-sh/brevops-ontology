"""Caso adversarial IAM: principal, permissão, atribuição, escopo e avaliação; a mesma concessão conta uma vez."""

from ..model import cm, fx, ground

CONS = ["DOMAIN-CONTRACTS", "SERVICE-EVIDENCE", "GRAIN", "GRAIN-REPRO", "AXIOMS", "SEMANTIC-REGRESSION", "CQFIX",
        "METRICSLIB", "CATEG"]

G_FORMS = [
    ground("google", "a mesma concessão por google_project_iam_member (aditivo, um membro), google_project_iam_binding (autoritativo para o papel, lista de membros) ou google_project_iam_policy (documento autoritativo inteiro): uma decisão, três realizações"),
    ground("aws", "a mesma permissão por aws_iam_role_policy_attachment de política gerida ou por documento embutido (aws_iam_role_policy): uma decisão"),
    ground("azurerm", "azurerm_role_assignment liga principal_id, role_definition_id e scope; uma atribuição por recurso"),
    ground("oci", "oci_identity_policy é documento de declarações textuais (Allow group ... to ... in compartment ...): uma declaração pode conter várias concessões"),
]
G_MODEL = [
    ground("aws", "papel (aws_iam_role) é PRINCIPAL assumível; o conjunto de permissões é a política (aws_iam_policy); o nome \"role\" colide com o do outro provedor"),
    ground("google", "papel (role) é CONJUNTO de permissões; o principal é membro (user:, serviceAccount:, group:)"),
    ground("azurerm", "role definition é conjunto de permissões; o principal mora no diretório de identidades, fora do provider azurerm"),
    ground("oci", "o principal é grupo ou usuário (oci_identity_group/user); permissão expressa em verbo + tipo de recurso dentro do documento"),
]
G_INHERIT = [
    ground("google", "herança organização -> pasta -> projeto -> recurso; políticas de negação (google_iam_deny_policy) prevalecem; condições em CEL"),
    ground("azurerm", "herança grupo de gerenciamento -> assinatura -> grupo de recursos -> recurso"),
    ground("oci", "concessão num compartment vale nos sub-compartments; só Allow"),
    ground("aws", "negação explícita em qualquer política aplicável prevalece; limites de organização (SCP) restringem sem conceder"),
]
G_PIN = [
    ground("azurerm", "usuários e grupos ficam no diretório gerido pelo provider azuread, fora do pin azurerm: OUT_OF_PIN"),
    ground("google", "grupos do diretório de identidades corporativo são referenciados por e-mail sintético e não são lidos pelo provider: pertença OUT_OF_PIN"),
]


def _grant(fid, summary, form, extra_ents="", extra_rels=(), extra_attrs=()):
    return fx(fid, summary,
              "p1:principal ps1:permission_set perm1:permission s1:scope_node a1:assignment " + extra_ents,
              ["a1 assigns_principal p1", "a1 assigns_set ps1", "a1 at_scope s1", "ps1 includes perm1"] + list(extra_rels),
              ["p1.principal_type=service_identity", "perm1.action=read", f"a1.expression_form={form}"] + list(extra_attrs))


def _hier(fid, summary, assign_scope, req_scope="s_child", extra_ents="", extra_rels=(), extra_attrs=(), **kw):
    return fx(fid, summary,
              "p1:principal ps1:permission_set perm1:permission s_parent:scope_node s_child:scope_node "
              "r1:object_container q1:access_request a1:assignment " + extra_ents,
              ["s_child child_scope_of s_parent", f"r1 in_scope {req_scope}", "a1 assigns_principal p1",
               "a1 assigns_set ps1", f"a1 at_scope {assign_scope}", "ps1 includes perm1"] + list(extra_rels),
              ["perm1.action=read", "q1.action=read", "q1.resource_ref=r1"] + list(extra_attrs), **kw)


C = [
    cm("CMT-IAM-P01", "IAM", "positive", "entails",
       "A atribuição é um vínculo: um indivíduo distinto do principal, do conjunto de permissões e do escopo, "
       "cuja identidade é a tupla dos três.",
       "kind(a1) = BINDING AND identity(a1) = <p1, ps1, s1> AND a1 ∉ {p1, ps1, s1}",
       _grant("FX-IAM-P01", "uma concessão simples", "member"),
       "ENTAILED", "regra G1 (vínculo) e REQ-AUTH-01", ["REQ-AUTH-01", "REQ-ENT-01"], ["S13", "F1"],
       "atribuição como vínculo", grounding=G_MODEL, consumers=CONS),
    cm("CMT-IAM-P02", "IAM", "positive", "invariant",
       "A mesma concessão <principal, conjunto, escopo> expressa como membro individual, como ligação com lista "
       "de membros ou como documento de política dá a mesma única unidade de decisão.",
       "decision_units(member) == decision_units(binding) == decision_units(document) == {<p1, ps1, s1>}",
       [_grant("FX-IAM-P02-MEMBER", "concessão como membro individual", "member", extra_attrs=["a1.authoritative=false"]),
        _grant("FX-IAM-P02-BINDING", "concessão como ligação com lista de membros", "binding", extra_attrs=["a1.authoritative=true"]),
        _grant("FX-IAM-P02-DOCUMENT", "concessão dentro de documento de política", "document",
               extra_ents="doc1:policy_document", extra_rels=["a1 statement_in doc1"], extra_attrs=["a1.authoritative=true"])],
       "INVARIANT", "a embalagem não muda o denominador (unidade de decisão, §0)", ["REQ-AUTH-02"], ["F1", "S13"],
       "unidade de decisão independente da embalagem", layer="terraform", grounding=G_FORMS, consumers=CONS),
    cm("CMT-IAM-P03", "IAM", "positive", "count",
       "Se o código declara a mesma concessão duas vezes (um membro aditivo e uma declaração num documento), "
       "ela conta uma unidade de decisão.",
       "COUNT decision_units = 1",
       fx("FX-IAM-P03", "mesma concessão por membro e por documento",
          "p1:principal ps1:permission_set perm1:permission s1:scope_node a1:assignment a2:assignment doc1:policy_document",
          ["a1 assigns_principal p1", "a1 assigns_set ps1", "a1 at_scope s1", "a2 assigns_principal p1",
           "a2 assigns_set ps1", "a2 at_scope s1", "a2 statement_in doc1", "ps1 includes perm1"],
          ["a1.expression_form=member", "a2.expression_form=document", "perm1.action=read"]),
       1, "não contar a mesma política 3 vezes (F1)", ["REQ-AUTH-02"], ["F1"], "deduplicação de concessões",
       grounding=G_FORMS[:1], consumers=CONS),
    cm("CMT-IAM-P04", "IAM", "positive", "entails",
       "Atribuição no escopo pai vale para recurso no escopo filho (herança descendente).",
       "decision(q1) = allow",
       _hier("FX-IAM-P04", "concessão no pai, pedido no filho", "s_parent",
             extra_rels=["q1 requested_by p1"]),
       "ENTAILED", "herança de escopo (S13)", ["REQ-AUTH-01"], ["S13"], "herança descendente",
       layer="evaluation", grounding=G_INHERIT, consumers=CONS),
    cm("CMT-IAM-P05", "IAM", "positive", "entails",
       "Negação explícita aplicável vence permissão concedida, onde o modelo de avaliação do provedor o declara.",
       "decision(q1) = deny",
       _hier("FX-IAM-P05", "concessão no pai, negação no filho", "s_parent",
             extra_ents="d1:deny_statement",
             extra_rels=["q1 requested_by p1", "d1 denies perm1", "d1 at_scope s_child", "d1 assigns_principal p1"]),
       "ENTAILED", "combinação: negação prevalece (S13)", ["REQ-AUTH-01"], ["S13"], "efeito deny na combinação",
       layer="evaluation", grounding=G_INHERIT, consumers=CONS),
    cm("CMT-IAM-P06", "IAM", "positive", "entails",
       "Atribuição condicional: com a condição satisfeita pelo contexto do pedido, permite; com a condição não "
       "satisfeita, não permite.",
       "decision(q1) = allow AND decision(q2) != allow",
       fx("FX-IAM-P06", "atribuição condicionada à origem do pedido",
          "p1:principal ps1:permission_set perm1:permission s1:scope_node a1:assignment c1:access_condition "
          "r1:object_container q1:access_request q2:access_request",
          ["a1 assigns_principal p1", "a1 assigns_set ps1", "a1 at_scope s1", "ps1 includes perm1",
           "a1 conditioned_by c1", "r1 in_scope s1", "q1 requested_by p1", "q2 requested_by p1"],
          ["perm1.action=read", "c1.condition=origin_in_198.51.100.0/24", "c1.condition_attribute_modeled=true",
           "q1.action=read", "q1.resource_ref=r1", "q1.context=origin_198.51.100.7",
           "q2.action=read", "q2.resource_ref=r1", "q2.context=origin_203.0.113.9"]),
       "ENTAILED", "contexto faz parte da decisão (S13)", ["REQ-AUTH-01"], ["S13"], "condição de contexto",
       layer="evaluation", grounding=G_INHERIT[:1], consumers=CONS),
    cm("CMT-IAM-N01", "IAM", "negative", "rejects",
       "Negação de autorização não vira permissão: traduzir para destino sem negação explícita exige bloquear ou "
       "declarar perda preservando a decisão; tradução que permite o pedido negado é rejeitada.",
       "toda tradução T com decision_T(q1) = allow é rejeitada",
       _hier("FX-IAM-N01", "origem com negação; destino sem negação", "s_parent",
             extra_ents="d1:deny_statement tgt:target_setting",
             extra_rels=["q1 requested_by p1", "d1 denies perm1", "d1 at_scope s_child",
                         "d1 assigns_principal p1", "a1 translates_to tgt"],
             extra_attrs=["tgt.supports_deny=false"]),
       "REJECTED", "deny não vira allow (brief)", ["REQ-AUTH-01", "REQ-LOSS-01"], ["S13", "F9"],
       "preservação do efeito de negação", layer="translation", grounding=G_INHERIT[2:3],
       consumers=CONS + ["TRANSLATOR"]),
    cm("CMT-IAM-N02", "IAM", "negative", "not_entails",
       "Atribuição feita no escopo filho não concede acesso no escopo pai: a herança não sobe.",
       "NOT decision(q1) = allow",
       _hier("FX-IAM-N02", "concessão no filho, pedido sobre recurso do pai", "s_child", req_scope="s_parent",
             extra_rels=["q1 requested_by p1"]),
       "NOT_ENTAILED", "direção da herança", ["REQ-AUTH-01"], ["S13"], "herança só descendente",
       layer="evaluation", consumers=CONS),
    cm("CMT-IAM-N03", "IAM", "negative", "rejects",
       "Principal e conjunto de permissões são disjuntos, ainda que um provedor chame de \"papel\" um principal e "
       "outro chame de \"papel\" um conjunto de permissões.",
       "fixture com x1 de tipo principal e permission_set é inconsistente",
       fx("FX-IAM-N03", "indivíduo declarado principal e conjunto de permissões",
          "x1:principal+permission_set", [], ["x1.local_key=ops"]),
       "REJECTED", "colisão de nome não é identidade de tipo", ["REQ-ENT-02", "REQ-AUTH-01"], ["F9", "S13"],
       "disjunção principal x conjunto de permissões", code="INCONSISTENT", grounding=G_MODEL[:2], consumers=CONS),
    cm("CMT-IAM-N04", "IAM", "negative", "rejects",
       "Decomposição que produz três unidades de decisão para a mesma concessão expressa de três formas é "
       "rejeitada pelo verificador de contagem.",
       "decompor esta fixture em 3 unidades de decisão é rejeitado (esperado: 1)",
       fx("FX-IAM-N04", "a mesma concessão em três formas no mesmo escopo",
          "p1:principal ps1:permission_set perm1:permission s1:scope_node a1:assignment a2:assignment "
          "a3:assignment doc1:policy_document",
          ["a1 assigns_principal p1", "a1 assigns_set ps1", "a1 at_scope s1",
           "a2 assigns_principal p1", "a2 assigns_set ps1", "a2 at_scope s1",
           "a3 assigns_principal p1", "a3 assigns_set ps1", "a3 at_scope s1", "a3 statement_in doc1",
           "ps1 includes perm1"],
          ["a1.expression_form=member", "a2.expression_form=binding", "a3.expression_form=document"]),
       "REJECTED", "o denominador não pode mudar com a embalagem", ["REQ-AUTH-02"], ["F1"],
       "contagem de unidades de decisão", grounding=G_FORMS[:1], consumers=CONS),
    cm("CMT-IAM-U01", "IAM", "unknown", "unknown",
       "Concessão feita a um grupo mantido em diretório fora dos providers fixados: se o principal do pedido é "
       "membro do grupo não pode ser lido, e a decisão é UNKNOWN com código OUT_OF_PIN; não é negado nem ausente.",
       "decision(q1) = UNKNOWN AND code = OUT_OF_PIN",
       fx("FX-IAM-U01", "concessão a grupo do diretório externo",
          "g1:principal u1:principal dir1:external_directory ps1:permission_set perm1:permission s1:scope_node "
          "a1:assignment r1:object_container q1:access_request",
          ["g1 principal_held_in dir1", "u1 principal_held_in dir1", "a1 assigns_principal g1", "a1 assigns_set ps1",
           "a1 at_scope s1", "ps1 includes perm1", "r1 in_scope s1", "q1 requested_by u1"],
          ["g1.principal_type=group", "u1.principal_type=user", "perm1.action=read", "q1.action=read",
           "q1.resource_ref=r1"],
          complete=False, not_read=["u1.group_membership"]),
       "UNKNOWN", "alegação limitada aos pins (S13)", ["REQ-AUTH-03"], ["S13"], "OUT_OF_PIN não vira ausência",
       code="OUT_OF_PIN", layer="evaluation", grounding=G_PIN, consumers=CONS),
    cm("CMT-IAM-U02", "IAM", "unknown", "unknown",
       "Sem atribuição direta no escopo filho e com o escopo pai não lido, a decisão sobre o recurso do filho é "
       "UNKNOWN, não negada.",
       "decision(q1) = UNKNOWN",
       fx("FX-IAM-U02", "pai não lido",
          "p1:principal s_parent:scope_node s_child:scope_node r1:object_container q1:access_request",
          ["s_child child_scope_of s_parent", "r1 in_scope s_child", "q1 requested_by p1"],
          ["q1.action=read", "q1.resource_ref=r1"], complete=False, not_read=["s_parent.scope"]),
       "UNKNOWN", "a herança pode conceder; sem ler o pai não há decisão", ["REQ-AUTH-01", "REQ-ABS-01"], ["S13"],
       "UNKNOWN sob escopo não lido", code="INCOMPLETE_READ", layer="evaluation", consumers=CONS),
    cm("CMT-IAM-U03", "IAM", "unknown", "unknown",
       "Atribuição condicionada a atributo de contexto que o vocabulário não tem: a decisão é UNKNOWN com código "
       "CONDITION_INDETERMINATE.",
       "decision(q1) = UNKNOWN AND code = CONDITION_INDETERMINATE",
       fx("FX-IAM-U03", "condição sobre atributo não modelado",
          "p1:principal ps1:permission_set perm1:permission s1:scope_node a1:assignment c1:access_condition "
          "r1:object_container q1:access_request",
          ["a1 assigns_principal p1", "a1 assigns_set ps1", "a1 at_scope s1", "ps1 includes perm1",
           "a1 conditioned_by c1", "r1 in_scope s1", "q1 requested_by p1"],
          ["perm1.action=read", "c1.condition=device_posture_compliant", "c1.condition_attribute_modeled=false",
           "q1.action=read", "q1.resource_ref=r1"],
          complete=False, not_read=["c1.condition_attribute"]),
       "UNKNOWN", "condição indeterminada não é verdadeira nem falsa", ["REQ-AUTH-03"], ["S13"],
       "condição indeterminada", code="CONDITION_INDETERMINATE", layer="evaluation", grounding=G_INHERIT[:1],
       consumers=CONS),
]
