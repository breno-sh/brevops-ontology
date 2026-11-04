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
    "R-SCOPE-DOC": "prevalece sobre R-SCOPE-SELF e R-SCOPE-PARENT. Frase literal de anexação (a página diz a que "
                   "o recurso se anexa ou a que alvos se aplica: rede, sub-redes, instâncias, recurso pai) ou "
                   "frase com '<account|organization|project|folder|subscription|tenancy|management group|"
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
    "R-BLOCK-ID": "schema_identity = present se o bloco tem atributo computed id/arn/self_link/ocid (numa coleção "
                  "de objeto em atributo, só a presença do campo, sem flags), senão absent "
                  "(só o schema; nada sobre a API); element_name_candidates = atributos obrigatórios name/key do "
                  "bloco; max_per_parent = 1 se nesting single ou max_items 1.",
    "R-BLOCK-OWNER": "o bloco só existe dentro da configuração do pai no schema fixado: a configuração é gravada "
                     "pelo recurso Terraform do pai (kind parent, via = pai estrutural, camada terraform).",
    "R-BLOCK-LIFE": "o bloco não tem recurso Terraform próprio: nasce e some com o pai (kind parent, camada "
                    "terraform); o ciclo do objeto na API não é dito.",
    "R-ID-SHARED": "tipos cujo resource_identity_schema tem o mesmo conjunto de campos obrigatórios, fora os "
                   "genéricos (id, name, arn, region, account_id, project, location, zone, subscription_id, "
                   "resource_group_name, compartment_id), são endereçados pela mesma chave de identidade.",
    # fatos de grão pedidos pelo GRAIN (grainfacts.py); value sem aspect = alegação direta (kind/via)
    "R-OWN-TOP": "tipo de recurso Terraform de topo com ID de importação publicado (import_key afirmado e não "
                 "'does not support import') é dono da própria configuração: {kind: self} (camada terraform).",
    "R-LIFE-TIMEOUTS": "o bloco timeouts do tipo no schema fixado lista as operações do provider (create, read, "
                       "update, delete), citado pelas chaves (op=keys).",
    "R-LIFE-TF": "tipo de topo cujo timeouts tem create e delete tem ciclo de vida próprio NO TERRAFORM: {kind: "
                 "self, layer: terraform}. Não diz quem cria ou apaga o objeto na API.",
    "R-BRIDGE-DOC": "ponte só quando a página cita a API: link de referência de API na introdução (google: "
                    "cloud.google.com/.../reference|json_api|rest; aws: APIReference/API_<Op>, recurso = o que vem "
                    "depois do verbo Create|Put|Register|Allocate|Associate|Enable|Start|Run|Import|Request). Sem "
                    "citação, a ponte continua UNKNOWN.",
    "R-TWIN": "bloco (ou coleção) B do tipo T tem gêmeo separado U quando uma linha da página de T ou de U cita `B` "
              "e `U` (ou `T`) entre crases e o nome passa na regra declarada (termos de B no nome de U; U tem um "
              "termo próprio de T; o resto de U fora de B e T é só rule/configuration/vpc); o bloco herda de U a "
              "ponte de API e "
              "a identidade do schema (derived_from = o vínculo publicado + o fato de U).",
    "R-REF-PHRASE": "descrição literal de atributo de papel REFERENCE (ROLES) no padrão '<ID|ARN|OCID|name|...> "
                    "of the <coisa>': a coisa nomeada.",
    "R-REF-TARGET": "tipo-alvo da referência: <provedor>_<coisa> (termos com _) se existe no schema fixado; "
                    "senão os tipos que terminam em _<coisa> (até 3); mais que isso, sem alvo.",
    "R-SCOPE-SELF": "tipo de recurso de topo sem alcance publicado (R-SCOPE-DOC) tem alcance sobre ele mesmo: "
                    "{kind: self}; layer api quando o tipo é primário de R-OWN-API (derived_from inclui a ponte), "
                    "senão terraform; derived_from = fato publicado do tipo no pin (importação, identidade ou tag), que "
                    "mostra que ele é recurso de topo do schema fixado.",
    "R-SCOPE-PARENT": "PREMISSA: um bloco aninhado (ou coleção como bloco) só existe dentro da configuração do pai, "
                      "então, sem frase própria de alcance, o que ele configura vale para o pai: {kind: parent} "
                      "(via ausente = pai estrutural); layer api quando o tipo é primário de R-OWN-API, senão "
                      "terraform. Bloco com R-SCOPE-DOC não recebe esta regra.",
    "R-OWN-API": "camada de API: tipo com ponte para recurso de API (R-BRIDGE-*, resource conhecido) que é o único "
                 "do seu grupo de ponte (mesmo serviço e recurso) sem referência resolvida (R-REF-TARGET) a outro "
                 "membro: a configuração é do próprio objeto de API, {kind: self, layer: api}. Sem ponte, ou com mais "
                 "de um membro assim, nada (UNKNOWN).",
    "R-LIFE-API": "camada de API: o tipo de R-OWN-API que também tem R-LIFE-TF (create e delete do provider) cria e "
                  "apaga o objeto de API da ponte: {kind: self, layer: api}.",
    "R-OWN-API-SHARED": "camada de API: membro do grupo de ponte que referencia o primário configura o objeto do "
                        "primário: {kind: parent, via: [atributo de referência], layer: api}.",
    "R-LIFE-API-SHARED": "camada de API: idem para o ciclo de vida: o objeto é do primário, {kind: parent, via, "
                         "layer: api}.",
    # CC-8: especificação de API do provedor (apispec.py, specfacts.py)
    "R-SPEC-OP": "operação da spec fixada do provedor (Smithy aws, Discovery google, OpenAPI azure, SDK oci lido "
                 "como texto), citada por arquivo, ponteiro e nome da operação.",
    "R-BRIDGE-SPEC": "ponte tipo Terraform <-> recurso da spec só com casamento ÚNICO: aws nome do tipo sem aws_ "
                     "(e sem s3_/ec2_/vpc_) = substantivo da operação em snake_case (faceta: pai_faceta); google "
                     "<prefixo>_<coleção folha no singular>, prefixo = nome da API ou o termo do tipo que a regra de "
                     "seleção do lote ligou a ela (selection.json); coleção com insert/create e delete; azure tipos ARM da ponte da doc = tipos do caminho da spec; "
                     "oci: módulo do SDK cujo nome é o começo do tipo (o mais longo) ou o 1º termo sem _, e o resto do "
                     "nome (ou a ponte da doc) = substantivo do método. Mais de um: candidatos, "
                     "sem fato de camada API. Recurso da spec que casa com mais de um tipo: fica com a ponte só o "
                     "único tipo do grupo que não referencia (R-REF-TARGET, ou atributo REFERENCE de topo chamado "
                     "<recurso no singular>_id) outro membro; na aws, se isso não decide, o único cujo nome inteiro "
                     "(sem aws_ e s3_/ec2_/vpc_) é o do recurso. aws com todos os serviços: candidatos de mais de um "
                     "serviço ficam só os da pasta igual ao 1º termo do tipo ou à cabeça da subcategoria; senão os "
                     "de sdkId/arnNamespace/endpointPrefix iguais; ainda vários: o serviço da maioria (>= 3) dos "
                     "casamentos únicos da mesma subcategoria; nome: do mais específico (inteiro) ao menos (sem 1 ou "
                     "2 termos), parando no 1º nível que casa; os demais ficam como "
                     "candidatos.",
    "R-LIFE-SPEC": "o recurso da spec tem create e delete próprios sobre o próprio identificador (aws Create<N> e "
                   "Delete<N>, ou Run<N>s e Terminate<N>s; oci launch_<n> conta como create; google insert e delete; azure PUT e DELETE no caminho da instância; oci delete_<n> (ou "
                   "terminate_<n>) com "
                   "caminho terminado em {identificador} e create_<n> ou put_<n>): ciclo de vida próprio na API, {kind: self, layer: api}.",
    "R-OWN-SPEC": "recurso de R-LIFE-SPEC: a configuração está no próprio objeto, {kind: self, layer: api}; faceta "
                  "(sem create/delete próprios e configurada só por operação sobre o identificador do pai: aws "
                  "Put/Authorize/Revoke com os rótulos do Delete do pai no mesmo caminho-base, ou nome com o prefixo "
                  "do pai; azure PUT sem DELETE com o último nome constante; oci put/update/add/remove com caminho "
                  "que estende o do delete do pai): {kind: parent, layer: api, via: atributo de referência}.",
    "R-LIFE-SPEC-PARENT": "faceta de R-OWN-SPEC: sem create/delete próprios, o objeto nasce e some com o pai na "
                          "API: {kind: parent, layer: api}.",
    "R-SCOPE-SPEC": "faceta de R-OWN-SPEC (inclusive bloco que é faceta da spec, como ingress do aws_security_group = SecurityGroupIngress) (configurada só por operação sobre o identificador do pai): o alcance "
                    "efetivo é o pai, {kind: parent, layer: api, via: atributo de referência}.",
    "R-OWN-SPEC-BLOCK": "bloco/coleção de topo de um tipo cujo recurso tem create/delete próprios na spec, sem "
                        "faceta própria na spec mas com operação de update/modify/patch do recurso: o bloco é "
                        "configurado por ela; dono, ciclo e alcance = pai, {kind: parent, layer: api}.",
    "R-BRIDGE-SPEC-BLOCK": "bloco ligado ao campo ou sub-recurso da spec que ele configura (google: campo do corpo "
                           "do insert, lowerCamel do nome ou 1º termo + resto, ex. lifecycle_rule -> lifecycle.rule; "
                           "azure: <x>_properties -> sub-recurso <x>Services do pai e sub-blocos -> campos do corpo "
                           "dele; oci: campo do swagger_types do modelo models/<recurso>.py do SDK; aws: membro de lista do payload de faceta do pai, termos da faceta + membro no "
                           "singular, ou caminho de membros no tipo-faceta), com um nível intermediário único e "
                           "plural aceitos. Dono, ciclo e alcance do bloco = pai (R-OWN-SPEC-BLOCK).",
    "R-ATTACH-SPEC": "atributo de anexação: a spec tem um campo/membro que liga o objeto dono a um conjunto de "
                     "regras de outro tipo (aws ModifyInstanceAttribute.Groups; oci CreateVnicDetails/UpdateVnicDetails"
                     ".nsg_ids; azure SubnetPropertiesFormat/NetworkInterfacePropertiesFormat.networkSecurityGroup). O "
                     "campo é publicado (citação); a ligação atributo Terraform <-> campo é leitura do modelo "
                     "(interpretada, value.basis).",
    "R-ID-SPEC-ATTACH": "associação azure: o campo da spec que guarda a anexação é UMA referência ($ref, não "
                        "lista) no objeto do lado da subnet/NIC; a associação é identificada por esse lado "
                        "(subnet_id / network_interface_id).",
    "R-FACET-SPEC": "spec_facet_member: a API só aceita os blocos como membros de um objeto-faceta único do pai, "
                    "gravado por uma operação sobre o pai (aws Put<Faceta> com o payload; google patch/update do "
                    "recurso com o campo do objeto; azure PUT do recurso/sub-recurso), e o bloco não tem create/"
                    "delete próprios: {facet, facet_resource, operation, member, single_operation: true}.",
    "R-TWIN-SPEC": "bloco embutido e bloco do tipo separado que caem no mesmo membro da spec (ex.: aws_s3_bucket"
                   ".lifecycle_rule e aws_s3_bucket_lifecycle_configuration.rule -> BucketLifecycleConfiguration"
                   ".Rules) são gêmeos: twin_type com twin e twin_block_path.",
    "R-ID-SPEC": "azure: parâmetros do caminho da instância (sem subscriptionId): último -> name, demais -> atributo "
                 "de mesmo nome em snake_case. item de lista de bloco: a estrutura do item na spec tem membro ID/id (aws) ou id/name "
                 "(google/azure) -> essa chave (within_parent) se o bloco tem o atributo; sem membro de identidade -> "
                 "ausente. aws: regra criada por Authorize e removida por Revoke tem identidade própria quando a estrutura "
                 "<Pai>Rule da spec tem o membro <Pai>RuleId (ex.: SecurityGroupRule.SecurityGroupRuleId) e o tipo "
                 "tem o atributo de mesmo nome em snake_case. oci: os parâmetros do caminho do delete_<n> do recurso são a chave de identidade; o último é o "
                 "próprio objeto (…Id -> atributo id; …Name -> name ou <coisa>), os demais casam com atributo de topo "
                 "de mesmo nome; within_parent se algum dos demais é atributo REFERENCE. Parâmetro sem atributo: "
                 "nada (UNKNOWN).",
    # nível OBSERVED (adendo 04/11 §2; observed.py)
    "R-OBS-ID": "experimento OBS-GAPS (2 repetições + controle): regra da security list OCI sem id (lista trocada "
                "inteira, aceita duplicata) -> identity absent; regra do NSG OCI listada com id e alterada/removida "
                "pelo id -> identity present (id).",
    "R-OBS-OWNER": "a API recusa regra de NSG OCI com NSG inexistente ou sem nsg-id e não há comando de regra solta: "
                   "dono = o NSG (kind parent); azure: a referência ao NSG fica gravada na NIC/subnet -> dono da "
                   "associação = NIC/subnet. Divergência com a camada de API pela doc vira disputa observada × doc.",
    "R-OBS-CASCADE": "regras do NSG OCI somem com o NSG (delete do NSG, list/update das regras depois falham): "
                     "ciclo de vida = pai. Só com o report.json do OBS-GAPS fechando o experimento.",
    "R-OBS-ASSOC-LIFE": "OBS-GAPS-AZ: a associação NSG<->NIC/subnet não é recurso (sem tipo ARM nem comando próprio), "
                        "some com a NIC/subnet: ciclo de vida = o do dono do campo (kind parent, via o atributo).",
    "R-OBS-BLOCK-DELETE": "OBS-GAPS-AZ: apagar o NSG associado é recusado (InUseNetworkSecurityGroupCannotBeDeleted) e "
                          "a dissociação não é automática.",
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
