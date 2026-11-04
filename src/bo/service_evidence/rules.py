"""Regras declaradas do SERVICE-EVIDENCE (cada fato DERIVADO e cada extração mecânica cita o id da regra).

Uma regra de extração lê só a frase citada (ou o nome do atributo no schema fixado) e não usa conhecimento de
fora. Se a frase não diz, o fato fica UNKNOWN. O id da regra vai em value.rule.
"""

from __future__ import annotations

import re

RULES = {
    # ponte API <-> Terraform
    "R-BRIDGE-GCP-APIDOC": "linha '* [API documentation](https://cloud.google.com/...)' da página do tipo: serviço = "
                           "1º segmento do caminho; versão = segmento v<n>[alpha|beta<n>] depois de reference/[rest/]; "
                           "recurso = o resto do caminho (sem âncora). Serviço e recurso aparecem literalmente na frase.",
    "R-BRIDGE-OCI-APIDOC": "linha 'Api doc link for the resource: https://docs.oracle.com/iaas/api/#/en/<svc>/<ver>/<Res>'"
                           ": serviço, versão do link e recurso literais na frase.",
    "R-BRIDGE-AZ-ARMID": "ID de importação ARM da página (C03 import_id): serviço = namespace depois de /providers/; "
                         "recurso = os segmentos de TIPO do caminho (posições pares depois do namespace) unidos por '/'.",
    "R-BRIDGE-AWS-SUBCAT": "AWS: a página do tipo não nomeia o recurso de API; serviço = subcategoria literal do front "
                           "matter; recurso = UNKNOWN.",
    "R-APIREF-AWS": "links docs.aws.amazon.com/.../APIReference/API_<Nome>.html na página: nome literal (operação ou "
                    "tipo de dado; o link não diz qual).",
    # identidade e chave de importação
    "R-IMPORT-DOC": "seção Import da página (formatos, atributos, métodos), como gravada pelo DOCS-* ou relida da "
                    "página fixada (google).",
    "R-ID-SCHEMA": "resource_identity_schemas do schema fixado: atributos required_for_import e optional_for_import.",
    "R-ID-AZ-TEMPLATE": "ID de importação ARM -> modelo: cada segmento de NOME vira {nome do tipo que o precede}; "
                        "a importação usa o 'resource id' ou 'resource manager id' (frase da chave), então a "
                        "identidade é esse ID.",
    "R-ID-GCP-LONGEST": "formato de importação mais longo (mais placeholders) da seção Import.",
    "R-ID-OCI-PLAIN": "importação pelo 'id' simples -> identidade = atributo id do tipo.",
    "R-ID-OCI-FORMAT": "importação por formato composto -> identidade = o formato literal.",
    "R-ID-AWS-ATTRS": "importação AWS por atributos -> identidade = atributos na ordem da frase, com os separadores "
                      "da frase.",
    # dono e alcance
    "R-OWN-AZ-PARENT": "modelo ARM com mais de um par tipo/nome depois do namespace -> pai = o prefixo sem o último "
                       "par; com um par -> contêiner = resourceGroups (ou subscriptions, se não há resourceGroups).",
    "R-OWN-GCP-PARENT": "modelo de importação google: coleção = segmento antes de cada {{placeholder}}, ignorando "
                        "locations, regions, zones e global; pai = a penúltima coleção; projects/organizations/"
                        "folders/billingAccounts = contêiner.",
    "R-OWN-AWS-IDENTITY": "identidade do schema com account_id e/ou region -> alcance conta e/ou região.",
    "R-OWN-DOC-PARENT": "descrição literal de atributo de referência que diz 'belongs to', 'in which', 'that contains' "
                        "ou 'compartment' -> atributo dono citado.",
    "R-SCOPE-DOC": "frase literal com '<account|organization|project|folder|subscription|tenancy|management group|"
                   "enterprise|bucket|container|network|vpc>-level', "
                   "'at the <X> level' ou 'all <coisas> in the <X>' -> alcance efetivo = X.",
    # ciclo de vida
    "R-LIFE-DOC": "frase literal que diz que destruir/remover o recurso só o tira do state, não apaga, ou suspende "
                  "(efeito de destruição diferente de apagar o objeto).",
    "R-LIFE-DELETION-POLICY": "atributo deletion_policy documentado com valores ABANDON/DELETE (quem decide o fim do "
                              "objeto de API ao destruir).",
    # regras de rede
    "R-CONN-DOC": "atributo stateless/stateful/connection tracking, ou descrição que diz stateful/stateless: frase "
                  "literal e default datado do DOCS-*.",
    "R-EFFECT-DOC": "atributo de efeito (access, action, effect, rule_action) com valores permitidos literais que "
                    "incluem allow/deny/accept/drop/reject, ou bloco allow/deny descrito como 'ALLOW/DENY rules'.",
    "R-PREC-DOC": "atributo de ordem (priority, precedence, rule_number, sequence, order) com frase literal; ordem = "
                  "lower_value_first quando a frase diz que valor menor tem precedência ou que se processa em ordem "
                  "crescente; higher_value_first no inverso; senão UNKNOWN.",
    # tag e TTL
    "R-TAG-ATTR": "atributo de tag do provedor no nível de cima do tipo (aws/azurerm: tags; google: labels; oci: "
                  "freeform_tags e defined_tags) presente no schema fixado; frase do doc quando há.",
    "R-TAG-ABSENT": "nenhum atributo de tag do provedor entre as chaves de atributo do nível de cima do schema "
                    "fixado -> o recurso Terraform não aceita tag (outro recurso de tag pode existir).",
    "R-TTL-ATTR": "atributo (qualquer profundidade) cujo nome casa o léxico de expiração; alvo pela frase: self "
                  "(o próprio recurso é apagado/terminado), contained (objetos, mensagens, itens, eventos, versões), "
                  "cache (cache/DNS), senão UNKNOWN.",
    "R-ABSENT-PAGE": "a página fixada do tipo (citada pelo título) foi lida inteira e nenhuma regra acima casou: "
                     "UNKNOWN/not_documented (ausência de frase não é ausência do recurso).",
    "R-ABSENT-NOPAGE": "o tipo está no schema fixado mas não tem página na tag fixada: UNKNOWN/not_documented, citando "
                       "as chaves do bloco do tipo no schema.",
    # blocos aninhados (blocks.py)
    "R-BLOCK-SCHEMA": "forma do bloco aninhado no schema fixado (nesting_mode, min/max_items, atributos com flags "
                      "r/o/c, sub-blocos), citada pelo ponteiro com op=shape.",
    "R-BLOCK-ID": "schema_identity = present se o bloco tem atributo computed id/arn/self_link/ocid, senão absent "
                  "(só o schema; nada sobre a API); element_name_candidates = atributos obrigatórios name/key do "
                  "bloco; max_per_parent = 1 se nesting single ou max_items 1.",
    "R-BLOCK-OWNER": "o bloco só existe dentro da configuração do pai no schema fixado: a configuração é gravada "
                     "pelo recurso Terraform do pai (kind parent, via = pai estrutural, camada terraform).",
    "R-BLOCK-LIFE": "o bloco não tem recurso Terraform próprio: nasce e some com o pai (kind parent, camada "
                    "terraform); o ciclo do objeto na API não é dito.",
    "R-ID-SHARED": "tipos cujo resource_identity_schema tem o mesmo conjunto de campos obrigatórios, fora os "
                   "genéricos (id, name, arn, region, account_id, project, location, zone, subscription_id, "
                   "resource_group_name, compartment_id), são endereçados pela mesma chave de identidade.",
    # curadoria das fatias dos pilotos (curated.py): C-* publicado (o valor está escrito na frase), I-* interpretado
    "C-PILOT-LITERAL": "fato escolhido à mão numa frase da página fixada; o valor repete o que a frase diz.",
    "C-PILOT-GAP": "tipo das fatias dos pilotos sem frase para este tipo de fato na página fixada: UNKNOWN explícito "
                   "(a lacuna é resultado; não se preenche com conhecimento de fora do pin).",
    "I-PILOT-READING": "leitura do modelo sobre a frase citada (granularidade, interação entre níveis, regra "
                       "implícita); value.basis diz o que foi inferido além do texto.",
}

TAG_ATTRS = {"aws": ("tags",), "google": ("labels",), "azurerm": ("tags",), "oci": ("freeform_tags", "defined_tags")}

TTL_LEAF = re.compile(
    r"(^|_)(ttl|time_to_live|expir\w*|retention\w*|max_run_duration|termination_time|auto_delete\w*|"
    r"delete_after\w*|deletion_time|scheduled_deletion\w*|auto_shutdown\w*|auto_stop\w*|lifetime\w*)($|_)")
TTL_EXCLUDE = re.compile(r"password|certificate|cert_|_cert|secret|token|credential|signature|cookie|"
                         r"key_expir|_key$|login|session_|grace")
TTL_SELF = re.compile(r"\b(this|the) (resource|instance|cluster|vm|virtual machine|node pool|job|notebook|runtime|"
                      r"workstation|environment|server|machine|deployment|session|reservation|lease)\b[^.]{0,80}"
                      r"\b(is |will be |gets |are )?(automatically )?(deleted|terminated|destroyed|removed|stopped)\b",
                      re.I)
TTL_CONTAINED = re.compile(r"\b(objects?|messages?|items?|events?|log events|logs|versions?|snapshots?|backups?|"
                           r"records?|entries|documents?|rows?|blobs?|files?|data)\b", re.I)
TTL_CACHE = re.compile(r"\b(cache[ds]?|caching|dns|resolver|cdn|edge)\b", re.I)

STATE_LEAF = re.compile(r"^(stateless|stateful|is_stateless|connection_tracking\w*|tracking_mode|conntrack\w*)$")
STATE_DESC = re.compile(r"\bstate(ful|less)\b", re.I)

EFFECT_LEAF = re.compile(r"^(access|action|effect|rule_action|policy_action|default_action)$")
EFFECT_VALUES = re.compile(r"^(allow|deny|accept|drop|reject|block|permit)$", re.I)
EFFECT_BLOCK = re.compile(r"^(allow|deny|allowed|denied)$")
EFFECT_BLOCK_DESC = re.compile(r"\b(ALLOW|DENY|allow|deny)\b rules?\b")

PREC_LEAF = re.compile(r"^(priority|precedence|rule_number|rule_priority|sequence|sequence_number|order|"
                       r"evaluation_order|rule_order)$")
PREC_LOWER = re.compile(r"\b(lower|smaller|lowest)\b[^.]{0,80}\b(higher|highest|greater|first)\b[^.]{0,20}"
                        r"\b(priority|precedence|evaluated|processed)\b|\bascending order\b|"
                        r"\b(lower|smaller)\b (number|value|values)s? (is|are|will be) (evaluated|processed) first",
                        re.I)
PREC_HIGHER = re.compile(r"\b(higher|larger|greater|highest)\b (number|value)s?[^.]{0,40}\b(higher|highest)\b "
                         r"(priority|precedence)|\bdescending order\b", re.I)

SCOPE_RX = re.compile(
    r"\b(?P<a>account|organization|organisation|project|folder|subscription|tenancy|management group|"
    r"enterprise|bucket|container|network|vpc)[- ]level\b|"
    r"\bat the (?P<b>account|organization|organisation|project|folder|subscription|tenancy|management group) level\b|"
    r"\b(?:all|every) (?:\w+ ){1,3}in (?:the|an|a|your|this) (?P<c>account|organization|project|folder|subscription|"
    r"tenancy|region)\b", re.I)

OWNER_DESC = re.compile(r"\b(belongs? to|in which|that contains|containing the|to which (?:the )?\w+ belongs|"
                        r"parent)\b", re.I)

LIFE_RX = re.compile(
    r"\b(destroy\w*|delet\w*|remov\w*)\b[^.]{0,120}\b(only|just|simply|merely)\b[^.]{0,40}\bremove[sd]?\b[^.]{0,60}"
    r"\bfrom (the )?(Terraform )?state\b|"
    r"\b(will|does) not (actually )?(delete|destroy|remove)\b[^.]{0,80}|"
    r"\bremove[sd]? (it |the resource |this resource )?from (the )?Terraform state\b[^.]{0,80}|"
    r"\b(destroy\w*|delet\w*|remov\w*)\b[^.]{0,80}\bwill (either )?suspend\b",
    re.I)


def leaf(path: str) -> str:
    return path.rsplit(".", 1)[-1]


def ttl_target(sentence: str) -> str:
    if TTL_CACHE.search(sentence):
        return "cache"
    if TTL_SELF.search(sentence):
        return "self"
    if TTL_CONTAINED.search(sentence):
        return "contained"
    return "UNKNOWN"


def prec_order(sentence: str) -> str:
    if PREC_LOWER.search(sentence):
        return "lower_value_first"
    if PREC_HIGHER.search(sentence):
        return "higher_value_first"
    return "UNKNOWN"


def scope_of(sentence: str) -> str | None:
    m = SCOPE_RX.search(sentence)
    if not m:
        return None
    s = (m.group("a") or m.group("b") or m.group("c")).lower()
    return {"organisation": "organization", "management group": "management_group"}.get(s, s)
