"""Conteúdo normativo do pré-registro v3 (dados, sem lógica). Tudo o que vai para prereg/ sai daqui.

Muda só por emenda (seção 'emendas' do PREREG.html). AUTHORED_AT muda só quando o conteúdo muda; a saída é
determinística. Nada aqui foi escrito depois de ver dado do estudo: quando este arquivo é escrito não existe
partição de teste, universo, mapeamento nem deploy.
"""

from __future__ import annotations

AUTHORED_AT = "2026-11-03T01:58:00-03:00"
VERSION = "3.0.0"
TITLE = "Pré-registro BrevOps v3"

PROVIDERS = ["aws", "google", "azurerm", "oci"]
PAIRS = ["AWSGCP", "AWSAZ", "AWSOCI", "GCPAZ", "GCPOCI", "AZOCI"]

# ------------------------------------------------------------------------------------------- nota de renomeação
# nota-renomeacao: início (único trecho do módulo onde o termo antigo da v2 pode aparecer)
OLD_TERMS = ["teto", "tetos", "ceiling", "ceilings"]
RENAMING_NOTE = (
    "Na v2 a medida principal se chamava “teto de portabilidade” (portability ceiling). O nome prometia um "
    "máximo que ninguém provou: o número é o alcance do modelo+tradutor no universo U, e o top-k, o "
    "bo:UNGLOSSED, o reparo e um gerador incompleto só o baixam (revisão GPT-6, F7). Na v3 ela se chama "
    "COBERTURA OPERACIONAL do modelo+tradutor no universo U e é um degrau de uma escada de cinco eixos. O termo "
    "antigo não aparece em nenhum outro lugar deste pré-registro, em nenhuma chave de arquivo (C15-OLDTERM) e "
    "só voltaria onde houvesse prova de maximalidade, que este estudo não tem."
)
# nota-renomeacao: fim
NEW_TERM = "cobertura operacional"

# ------------------------------------------------------------------------------------------- textos comuns
POP_TEST = ("unidades de decisão configuradas no provedor de origem A nos repositórios da partição de teste do "
            "SPLIT (famílias deduplicadas, forks e cópias juntos), restritas às unidades canônicas do universo "
            "U(A); unidades expostas nos pilotos (pilot_exposed) ficam na população, marcadas, com leitura de "
            "sensibilidade sem elas (só o hold-out de unidades as exclui)")
DIR_12 = ("por direção ordenada A→B, cada uma das 12 (A ≠ B em aws, google, azurerm, oci), relatada uma a uma; "
          "a média das 12 com pesos iguais é leitura secundária")
DEN_DEC = ("número de unidades de decisão configuradas em A pela regra de inclusão, fixado no lado de origem antes "
           "de rodar o tradutor (o desfecho não muda o denominador); um documento JSON de política conta por "
           "decisão, não por linha: uma decisão por declaração normalizada (efeito, principal, ação, recurso, "
           "condição), invariante a reserializar, reordenar chaves ou partir listas; NAME e TAG fora; "
           "NOT_APPLICABLE fora por regra de inclusão, nunca depois do desfecho")
UNK_OP = ("UNKNOWN_SYMBOLIC_INPUT, UNKNOWN_INPUT, CONDITION_INDETERMINATE e INFRA_ERROR contam como não emitidas "
          "no limite inferior e como emitidas no limite superior; est = emitidas ÷ (n − desconhecidas), sempre "
          "relatada junto com os dois limites; os demais códigos de bloqueio do C23 (e o resultado omitted) "
          "contam como não emitidas nos dois limites")
NAMETAG_OUT = "papéis NAME e TAG (C04) fora; eles têm leitura própria (M-OPCOV-NAMETAG)"

# ------------------------------------------------------------------------------------------- política do desconhecido
# Cada valor de cada enumeração que decide um desfecho cai em exatamente uma classe. O gate bo.prereg.estimands
# confere esta tabela contra as enumerações do C00 em contracts/ (se o contrato mudar, o gate reprova).
BOUND_CLASSES = {
    "success": "conta como sucesso (atravessou, persistiu, observações coincidiram) nos dois limites",
    "failure": "conta como falha nos dois limites",
    "bounded": "conta como falha no limite inferior e como sucesso no limite superior; sai do denominador de est",
}
BOUND_POLICY = {
    "trace_result": {"carried": "success", "omitted": "failure", "blocked": "por código"},
    "block_code": {
        "OUT_OF_SUBSET": "failure", "UNKNOWN_SYMBOLIC_INPUT": "bounded", "TRANSFORM_OUT_OF_DOMAIN": "failure",
        "NO_UNIT": "failure", "NO_REALIZATION": "failure", "SHACL_VIOLATION": "failure",
        "CONDITION_FALSE": "failure", "CONDITION_INDETERMINATE": "bounded", "RELATED_ONLY": "failure",
        "REPAIR_EXCLUDED": "failure", "AMBIGUOUS_TARGET": "failure", "UNPROVEN": "failure",
        "INFRA_ERROR": "bounded", "UNKNOWN_INPUT": "bounded", "REFUTED_BY_RULE": "failure",
    },
    "outcome_persistence": {
        "PERSISTED": "success", "ALTERED": "failure", "REJECTED_BY_API": "failure",
        "NOT_READABLE": "bounded", "INFRA_ERROR": "bounded", "UNKNOWN": "bounded",
    },
    "outcome_behavior": {
        "OBSERVATIONS_MATCH_UNDER_PROTOCOL": "success", "OBSERVATIONS_DIFFER_UNDER_PROTOCOL": "failure",
        "NOT_OBSERVED_IN_WINDOW": "bounded", "PROTOCOL_UNSUPPORTED": "bounded", "INFRA_ERROR": "bounded",
        "UNKNOWN": "bounded",
    },
}
# códigos que a cláusula "Desconhecido" de cada eixo tem de nomear
AXIS_UNKNOWN_CODES = {
    "representability": ["UNKNOWN_SYMBOLIC_INPUT", "UNKNOWN_INPUT"],
    "transportability": ["CONDITION_INDETERMINATE"],
    "operational": ["UNKNOWN_SYMBOLIC_INPUT", "UNKNOWN_INPUT", "CONDITION_INDETERMINATE", "INFRA_ERROR"],
    "persistence": ["NOT_READABLE", "INFRA_ERROR", "UNKNOWN"],
    "behavior": ["NOT_OBSERVED_IN_WINDOW", "PROTOCOL_UNSUPPORTED", "INFRA_ERROR", "UNKNOWN"],
}
UNKNOWN_RULES = [
    ("NOT_READABLE", "A leitura de volta não devolveu o campo (a API não expõe, o provider não lê, o valor é "
     "retido por redação). Fica no intervalo entre os limites; não é falha nem sucesso. Nunca é reclassificado "
     "depois do desfecho; a tabela de campos legíveis por tipo vem do SERVICE-EVIDENCE antes do sorteio e é "
     "publicada com o frame."),
    ("INFRA_ERROR", "Falha de infraestrutura (cota, timeout, região indisponível, erro do runner). Até 2 "
     "retentativas com o mesmo protocolo e o mesmo caso, registradas; persistindo, fica INFRA_ERROR no "
     "intervalo. Estrato com mais de 10% de INFRA_ERROR é sinalizado e pode ser rodado de novo UMA vez, inteiro, "
     "antes do JUDGE; nunca se troca o caso por outro para fugir do erro."),
    ("UNKNOWN", "O juiz não consegue decidir (comparador indefinido para o valor, desfecho incompleto). Fica no "
     "intervalo. No tradutor, UNKNOWN_SYMBOLIC_INPUT e UNKNOWN_INPUT (falta de valor) também: o tradutor nunca "
     "inventa default para fugir do desconhecido."),
    ("NOT_APPLICABLE", "Atributo sem grandeza ou unidade fora da leitura por definição: sai do denominador pela "
     "regra de inclusão, decidida no lado de origem antes de rodar o tradutor. NOT_APPLICABLE nunca vira zero e "
     "nunca é decidido depois do desfecho."),
    ("NONE (ausência)", "Atributo de A sem correspondência declarada: não entra no numerador nem no denominador "
     "da cobertura; vai para a auditoria separada (absence_audit do C15): descobertas adversariais dos "
     "caçadores (contagem, nunca extrapolada) e amostra probabilística do DISPUTE-SAMPLE (frame e pesos "
     "publicados), que estima a taxa de falso NONE (E-NONE-FALSE)."),
    ("est", "Estimativa de caso completo (sucessos ÷ casos com desfecho conhecido), válida só sob ausência ao "
     "acaso; secundária. As hipóteses são julgadas no limite declarado em cada contraste (H1 e H4 no superior, "
     "H8 no inferior, os demais nos dois); quando os dois limites discordam, a conclusão é 'indeterminada pelo "
     "desconhecido', relatada como tal."),
    ("substituição", "Caso sorteado inviável por motivo anterior ao desfecho (SKU indisponível na região, tipo "
     "sem suporte de tag ou TTL quando exigido) é substituído pelo próximo da ordem sorteada com a mesma semente, "
     "no mesmo estrato; a substituição e o motivo vão para o manifesto. Inviabilidade descoberta depois do "
     "apply não substitui: vira INFRA_ERROR."),
]

# ------------------------------------------------------------------------------------------- unidades de análise
UNITS = [
    ("campo", "field", "átomo de atributo com valor configurado numa ocorrência de bloco (C01 + C06, marca "
     "configured); um documento JSON de política é um campo só nesta leitura"),
    ("decisão", "decision", "escolha de configuração no nível do conceito do glossário (ex. 'versionamento "
     "ligado'); leitura PRINCIPAL; documento de política conta uma decisão por declaração normalizada"),
    ("grafo", "graph", "componente conexo de recursos de um repositório num provedor, ligados por referência "
     "(C06), dentro de U; atravessa se todas as decisões e referências internas chegam a B com o mesmo destino"),
    ("unidade implantável completa", "complete_unit", "recurso de A com tudo o que precisa para ser criado em B: "
     "plano de lowering (C26) com dependências fechadas, obrigatórios presentes ou sintetizados e declarados, "
     "sem UNKNOWN_INPUT, terraform validate offline verde no provider fixado"),
    ("caso de deploy", "case", "unidade de decisão sorteada pelo DEPSAMPLE (C11), com case_id e group_id"),
    ("par de sonda", "probe_pair", "pair_case_id com as observações locais dos lados A e B sob o mesmo protocolo (C22)"),
    ("caso de consequência", "consequence_case", "caso fora da calibração com resposta esperada independente "
     "(compromissos e CQs congelados do REQUIREMENTS), julgado nos 3 controles"),
    ("repositório", "repository", "repo_id sintético (C00), cluster intermediário"),
    ("família", "family", "family_id (C27): repositórios, forks e cópias com o mesmo conteúdo normalizado; "
     "cluster de topo da reamostragem"),
]
RESAMPLING = [
    "Primária: bootstrap por família (cluster de topo, que contém repositório e grafo), 4000 réplicas, percentil, "
    "semente SEED-BOOT; métricas do mesmo contraste são reamostradas juntas (mesmas famílias) para a incerteza "
    "conjunta (correlated_with no C15).",
    "Sensibilidade: bootstrap por repositório e por grafo; precisão de persistência também por recurso.",
    "Com menos de 30 famílias numa célula, o bootstrap percentil subcobre (R3-M5): a célula usa IC t com erro "
    "robusto por cluster e correção CR2, e é marcada.",
    "Provedores e pares entram como EFEITOS FIXOS (6 pares não sustentam efeito aleatório); a direção também.",
    "Testes de invariância (determinísticos, não estatísticos): renomear provedores, permutar a identidade dos "
    "provedores, trocar a embalagem do schema (inline × separado; bloco × recurso) e reordenar blocos tem de dar "
    "a mesma saída, byte a byte, depois de desfazer a renomeação. Qualquer diferença é defeito, não ruído.",
    "Teste de permutação (sensibilidade de H2): trocar os rótulos de direção dentro do par no nível da família, "
    "10000 permutações, semente SEED-PERM.",
    "McNemar por valor saiu (exagerava a certeza); 'tipo de perda' não é preditor (recodifica o desfecho); o "
    "Gini é rotulado 'equilíbrio de contagens', nunca 'neutralidade'.",
]

# ------------------------------------------------------------------------------------------- métricas
# Cada métrica vira uma linha do metrics_spec.yaml (C15). A definição carrega o estimando inteiro em seis
# cláusulas rotuladas (Definição, População, Direção, Unidade, Denominador, Desconhecido), porque o C15 3.0.0
# não tem campos próprios para direção, denominador e desconhecido; bo.prereg.estimands confere as seis.


def _m(metric_id, name, reading, axis, quantifier, definition, population, direction, unit, denominator,
       unknown, frame, inc_id, inc_text, weights="uniform", uncertainty="bootstrap", priority="P0", rq="RQ1",
       primary=False):
    return {
        "metric_id": metric_id, "name": name, "reading": reading, "axis": axis, "quantifier": quantifier,
        "definition": definition, "population": population, "direction": direction, "unit": unit,
        "denominator": denominator, "unknown": unknown, "frame": frame, "inclusion_id": inc_id,
        "inclusion_text": inc_text, "weights": weights, "uncertainty": uncertainty, "priority": priority,
        "rq": rq, "primary": primary,
    }


FRAME_TEST = "partição de teste do SPLIT, universo U congelado (UNIVERSE), pins do provider congelados"
FRAME_DEP = "frame do DEPSAMPLE (casos carregados e bloqueados, estratos e pesos publicados no congelamento DEPSAMPLE)"
FRAME_PROBE = "amostra de sondas do DEPSAMPLE, só tipos com suporte validado (PROBEKIT + SERVICE-EVIDENCE)"
INC_DEC = ("decisões configuradas em A (marca configured) em unidades canônicas de U(A), " + NAMETAG_OUT +
           "; computed, default não escrito e NOT_APPLICABLE fora")

METRICS = [
    _m("M-REPR-DEC", "representabilidade por decisão", "decision", "representability", "observed_fraction",
       "fração das unidades de decisão configuradas em A que o lifting representa como indivíduos e valores da "
       "ontologia congelada (FREEZE2), sem bo:UNGLOSSED e sem classe nova",
       POP_TEST, "não direcional: uma leitura por provedor de origem A (4), repetida na escada das 3 direções que "
       "saem de A", "decisão", DEN_DEC,
       "UNKNOWN_SYMBOLIC_INPUT e UNKNOWN_INPUT no lifting contam como não representadas no limite inferior e "
       "como representadas no limite superior; est = representadas ÷ (n − desconhecidas)",
       FRAME_TEST, "INC-DEC-01", INC_DEC),
    _m("M-TRANS-DEC-EXIST", "transportabilidade existencial por decisão", "decision", "transportability",
       "existential",
       "fração das unidades de decisão configuradas em A com alegação de veredito OK (C21) e estado de "
       "evidência DOC_SUPPORTED ou acima que admite transporte A→B pela relação declarada para ALGUM valor do "
       "domínio de A (quantificador existencial, nível de schema; broad/narrow contam se o predicado de "
       "pertença é satisfazível)", POP_TEST, DIR_12, "decisão", DEN_DEC,
       "guarda CONDITION_INDETERMINATE (satisfatibilidade não decidida) conta como não transportável no limite "
       "inferior e como transportável no limite superior; grandeza UNKNOWN é UNPROVEN e não transporta nos dois "
       "limites (regra KIND-UNKNOWN do SEMANTICS); UNPROVEN, REFUTED_BY_RULE, CONTESTED, AMBIGUOUS e excluída "
       "por reparo não transportam", FRAME_TEST, "INC-DEC-01", INC_DEC),
    _m("M-TRANS-DEC-UNIV", "transportabilidade universal por decisão", "decision", "transportability",
       "universal",
       "fração das unidades de decisão configuradas em A cuja alegação de veredito OK e DOC_SUPPORTED ou acima "
       "transporta A→B TODO valor do domínio de A (quantificador universal, nível de schema; broad conta por "
       "inclusão, narrow só se o predicado de pertença é verdadeiro em todo o domínio)", POP_TEST, DIR_12,
       "decisão", DEN_DEC,
       "guarda CONDITION_INDETERMINATE conta como não transportável no limite inferior e como transportável no "
       "limite superior; grandeza UNKNOWN é UNPROVEN e não transporta nos dois limites",
       FRAME_TEST, "INC-DEC-01", INC_DEC),
    _m("M-TRANS-DEC-OBS", "transportabilidade no uso observado", "decision", "transportability",
       "observed_fraction",
       "fração dos valores observados no uso (C06, partição de teste) para os quais a relação declarada admite "
       "transporte A→B: predicado de pertença verdadeiro (broad/narrow), função parcial definida (exact/close), "
       "guarda verdadeira (quantificador de uso)", POP_TEST, DIR_12, "decisão", DEN_DEC,
       "valor simbólico não resolvido (UNKNOWN_SYMBOLIC_INPUT) e guarda CONDITION_INDETERMINATE contam como não "
       "transportáveis no limite inferior e como transportáveis no limite superior",
       FRAME_TEST, "INC-DEC-01", INC_DEC),
    _m("M-OPCOV-DEC", "cobertura operacional por decisão (principal)", "decision", "operational",
       "observed_fraction",
       "cobertura operacional do modelo+tradutor no universo U, controle c3 (axiomatização completa): unidades "
       "de decisão configuradas em A cujo valor o tradutor real emite em B (C23 result = carried, valor no plano "
       "de lowering) ÷ unidades de decisão configuradas em A; calculada rodando o tradutor, nunca lida da tabela "
       "de correspondências", POP_TEST, DIR_12, "decisão", DEN_DEC, UNK_OP,
       FRAME_TEST, "INC-DEC-01", INC_DEC, primary=True),
    _m("M-OPCOV-FIELD", "cobertura operacional por campo", "field", "operational", "observed_fraction",
       "átomos de atributo configurados em A cujo valor o tradutor emite em B ÷ átomos de atributo configurados "
       "em A (uma ocorrência de bloco = um campo)", POP_TEST.replace("unidades de decisão configuradas", "campos configurados"), DIR_12,
       "campo",
       "número de campos configurados em A pela regra de inclusão, fixado antes do tradutor; um documento JSON "
       "de política é UM campo (não por linha), para a embalagem não mudar o denominador; NAME e TAG fora",
       UNK_OP.replace("emitidas", "emitidos"), FRAME_TEST, "INC-FIELD-01",
       "campos configurados em A em unidades canônicas de U(A), " + NAMETAG_OUT + "; computed fora"),
    _m("M-OPCOV-GRAPH", "cobertura operacional por grafo", "graph", "operational", "observed_fraction",
       "grafos de configuração de A (componente conexo de recursos de um repositório ligados por referência) "
       "cujas decisões e referências internas o tradutor emite TODAS em B com o mesmo destino ÷ grafos de A "
       "(conservação de relações)", "grafos de configuração dos repositórios da partição de teste com ao menos "
       "uma decisão em U(A)", DIR_12, "grafo",
       "número de grafos de A com ao menos uma decisão incluída, fixado antes do tradutor; decisões contadas "
       "como na leitura por decisão (JSON de política por decisão, não por linha); NAME e TAG fora",
       "grafo com alguma decisão ou referência desconhecida (UNKNOWN_SYMBOLIC_INPUT, UNKNOWN_INPUT, "
       "CONDITION_INDETERMINATE, INFRA_ERROR) e nenhuma falha definida conta como não emitido no limite inferior "
       "e como emitido no limite superior; uma falha definida reprova o grafo nos dois limites",
       FRAME_TEST, "INC-GRAPH-01", "grafos com ao menos uma decisão de INC-DEC-01; " + NAMETAG_OUT),
    _m("M-OPCOV-UNIT", "cobertura operacional por unidade implantável completa", "complete_unit", "operational",
       "observed_fraction",
       "recursos de A para os quais o tradutor emite em B uma unidade implantável completa (plano de lowering "
       "C26 com dependências fechadas, obrigatórios presentes ou sintetizados e declarados, sem UNKNOWN_INPUT, "
       "terraform validate offline verde) ÷ recursos de A", "recursos Terraform de A na partição de teste cujas "
       "unidades canônicas estão em U(A)", DIR_12, "unidade implantável completa",
       "número de recursos de A incluídos, fixado antes do tradutor; um recurso conta uma vez, qualquer que seja "
       "o número de blocos ou de linhas de política",
       "recurso com UNKNOWN_SYMBOLIC_INPUT, CONDITION_INDETERMINATE ou INFRA_ERROR (inclusive no terraform "
       "validate) e nenhuma falha definida conta como não emitido no limite inferior e como emitido no limite "
       "superior; UNKNOWN_INPUT em atributo obrigatório do destino é falha definida (a unidade não é completa)",
       FRAME_TEST, "INC-UNIT-01", "recursos de A em U(A); " + NAMETAG_OUT + " no critério de completude"),
    _m("M-OPCOV-NAMETAG", "cobertura operacional de NAME e TAG (leitura própria)", "field", "operational",
       "observed_fraction",
       "campos de papel NAME ou TAG (C04) configurados em A cujo valor o tradutor emite em B ÷ campos NAME/TAG "
       "configurados em A; separada para não dominar as outras leituras",
       "campos de papel NAME ou TAG nos repositórios da partição de teste, em unidades canônicas de U(A)", DIR_12,
       "campo", "número de campos NAME/TAG configurados em A, fixado antes do tradutor; um mapa de tags conta "
       "uma vez por chave", UNK_OP.replace("emitidas", "emitidos"), FRAME_TEST, "INC-NAMETAG-01",
       "só papéis NAME e TAG (C04); excluídos de todas as outras leituras"),
    _m("M-OPCOV-DEC-DIRECT", "cobertura do caminho direto par-a-par", "decision", "operational",
       "observed_fraction",
       "como M-OPCOV-DEC, mas pelo tradutor par-a-par do PAIRWISE (só as alegações congeladas, sem ontologia), "
       "com a mesma IR de grafo, o mesmo lowering, os mesmos contratos de perda e o mesmo oráculo",
       POP_TEST, DIR_12, "decisão", DEN_DEC, UNK_OP, FRAME_TEST, "INC-DEC-01", INC_DEC),
    _m("M-OPCOV-DEC-C1", "cobertura do controle c1 (tabela sem inferência)", "decision", "operational",
       "observed_fraction",
       "como M-OPCOV-DEC, com o controle c1: tabela JSON/RDF das correspondências sem inferência; mesma "
       "entrada, mesma política de perda, mesmas transformações", POP_TEST, DIR_12, "decisão", DEN_DEC, UNK_OP,
       FRAME_TEST, "INC-DEC-01", INC_DEC),
    _m("M-OPCOV-DEC-C2", "cobertura do controle c2 (taxonomia e realizações)", "decision", "operational",
       "observed_fraction",
       "como M-OPCOV-DEC, com o controle c2: só a taxonomia e as realizações, sem os demais axiomas; mesma "
       "entrada, mesma política de perda, mesmas transformações", POP_TEST, DIR_12, "decisão", DEN_DEC, UNK_OP,
       FRAME_TEST, "INC-DEC-01", INC_DEC),
    _m("M-OPCOV-DEC-COMPLEX", "fração da cobertura via correspondência complexa", "decision", "operational",
       "observed_fraction",
       "entre as decisões emitidas em B no limite inferior pelo controle c3, a fração cujo transporte usou "
       "correspondência complexa (grupo como regra sobre subgrafo, 1:N, N:M ou guarda condicional; C09 "
       "bo_group_id ou guard não vazio)", "decisões emitidas em B no limite inferior de M-OPCOV-DEC, partição de "
       "teste", DIR_12, "decisão",
       "número de decisões emitidas no limite inferior de M-OPCOV-DEC (o limite inferior é a base porque a "
       "complexidade de uma decisão desconhecida não é observável); JSON de política por decisão, não por "
       "linha; NAME e TAG fora",
       "decisões desconhecidas (UNKNOWN_SYMBOLIC_INPUT, UNKNOWN_INPUT, CONDITION_INDETERMINATE, INFRA_ERROR) "
       "ficam fora da base; limite inferior = fração entre as emitidas com todas as desconhecidas tratadas como "
       "simples e limite superior = com todas tratadas como complexas e emitidas",
       FRAME_TEST, "INC-DEC-02", "decisões de INC-DEC-01 emitidas no limite inferior de M-OPCOV-DEC; " + NAMETAG_OUT),
    _m("M-LOPO-OPCOV-DEC", "cobertura com a ontologia sem OCI (leave-one-provider-out)", "decision",
       "operational", "observed_fraction",
       "como M-OPCOV-DEC nas 6 direções com OCI, mas com a ontologia reinduzida só com as 18 alegações sem OCI e "
       "o glossário sem âncoras OCI, mapeada por um mapeador novo (HOLDOUT)",
       POP_TEST + "; só origem ou destino OCI", "por direção com OCI (oci→aws, oci→google, oci→azurerm, "
       "aws→oci, google→oci, azurerm→oci), uma a uma", "decisão", DEN_DEC, UNK_OP, FRAME_TEST, "INC-DEC-01",
       INC_DEC),
    _m("M-ABL-SEEDAWS-DEC", "ablação: semente só AWS", "decision", "operational", "observed_fraction",
       "como M-OPCOV-DEC, com o pipeline completo reconstruído com sementes só da AWS (ABLATION a), no conjunto "
       "selado", POP_TEST, DIR_12, "decisão", DEN_DEC, UNK_OP, FRAME_TEST, "INC-DEC-01", INC_DEC),
    _m("M-ABL-THR-ALT1-DEC", "ablação: primeiro limiar alternativo de admissão", "decision", "operational",
       "observed_fraction",
       "como M-OPCOV-DEC, com o primeiro limiar alternativo de admissão (dos três: 1, 2 ou 3 provedores, o menor "
       "dos dois que não é o do pipeline congelado; ABLATION b)", POP_TEST, DIR_12, "decisão", DEN_DEC, UNK_OP,
       FRAME_TEST, "INC-DEC-01", INC_DEC),
    _m("M-ABL-THR-ALT2-DEC", "ablação: segundo limiar alternativo de admissão", "decision", "operational",
       "observed_fraction",
       "como M-OPCOV-DEC, com o segundo limiar alternativo de admissão (o maior dos dois que não é o do pipeline "
       "congelado; ABLATION b)", POP_TEST, DIR_12, "decisão", DEN_DEC, UNK_OP, FRAME_TEST, "INC-DEC-01", INC_DEC),
    _m("M-ABL-RAWTYPES-DEC", "ablação: tipos Terraform crus", "decision", "operational", "observed_fraction",
       "como M-OPCOV-DEC, com tipos Terraform crus no lugar do grão canônico (ABLATION c); o denominador continua "
       "o das decisões canônicas de A", POP_TEST, DIR_12, "decisão", DEN_DEC, UNK_OP, FRAME_TEST, "INC-DEC-01",
       INC_DEC),
    _m("M-ABL-NOGUARD-DEC", "ablação: sem guardas e sem transformações", "decision", "operational",
       "observed_fraction",
       "como M-OPCOV-DEC, sem guardas e sem transformações, só o predicado (ABLATION d)", POP_TEST, DIR_12,
       "decisão", DEN_DEC, UNK_OP, FRAME_TEST, "INC-DEC-01", INC_DEC),
    _m("M-ABL-AWSRAW-DEC", "ablação conjunta: semente só AWS com tipos crus (H6)", "decision", "operational",
       "observed_fraction",
       "como M-OPCOV-DEC, com semente só AWS E tipos Terraform crus ao mesmo tempo (comparação de H6)",
       POP_TEST, DIR_12, "decisão", DEN_DEC, UNK_OP, FRAME_TEST, "INC-DEC-01", INC_DEC),
    _m("M-H2H-TRANS-DEC", "eixo de tradução de cada comparador (orçamento igual)", "decision", "operational",
       "observed_fraction",
       "como M-OPCOV-DEC, pelo pacote de tradução de cada comparador com artefato, escrito com o orçamento igual "
       "do h2h_fairness.yaml, sobre a ABox gerada dos mesmos fatos de origem, sob o mesmo oráculo; Kalinin como "
       "faixa da família de reconstruções; sem artefato = NOT_APPLICABLE, nunca 0",
       POP_TEST, DIR_12 + "; uma leitura por comparador", "decisão", DEN_DEC, UNK_OP, FRAME_TEST, "INC-DEC-01",
       INC_DEC, rq="RQ5"),
    _m("M-TOOL-LLM-DEC", "acerto do LLM com prompt congelado (suplementar)", "decision", "operational",
       "observed_fraction",
       "como M-OPCOV-DEC, traduzindo com um LLM de prompt congelado, na amostra de teste do TOOL-ACCURACY "
       "(200 decisões por direção, semente SEED-TOOL), sob o mesmo oráculo",
       "amostra aleatória simples de 200 decisões por direção da população de M-OPCOV-DEC", DIR_12, "decisão",
       DEN_DEC, UNK_OP, "amostra do TOOL-ACCURACY sobre a partição de teste", "INC-DEC-03",
       "decisões sorteadas de INC-DEC-01 com SEED-TOOL; " + NAMETAG_OUT, priority="suplementar"),
    _m("M-PERS-DEC", "precisão de persistência", "decision", "persistence", "observed_fraction",
       "precisão de persistência π: casos PERSISTED ÷ casos de decisão amostrados e levados a deploy, por "
       "estrato par×domínio×cardinalidade×relação×direção, e combinada com os pesos do frame",
       "casos de decisão carregados pelo tradutor (lado de destino gerado pela saída do tradutor) no frame do "
       "DEPSAMPLE; os bloqueados amostrados vão à auditoria offline, não a deploy",
       "por direção A→B do caso (destino = lado implantado); estratos não somados entre direções",
       "decisão", "número de casos sorteados e levados a deploy no estrato (todos os desfechos publicados); um "
       "documento JSON de política conta por decisão, não por linha",
       "NOT_READABLE, INFRA_ERROR e UNKNOWN contam como não persistidos no limite inferior e como persistidos no "
       "limite superior; ALTERED e REJECTED_BY_API são falha nos dois limites",
       FRAME_DEP, "INC-CASE-01", "casos carregados do DEPSAMPLE (origin = sample) com plano de lowering; " +
       NAMETAG_OUT, weights="inverse_probability"),
    _m("M-OPCOV-PERS-DEC", "leitura combinada: emitida e persistida", "decision", "persistence",
       "observed_fraction",
       "fração das unidades de decisão de A que o tradutor emite em B E que a API de B guarda: cobertura "
       "operacional × precisão de persistência do estrato, com a incerteza conjunta propagada (bootstrap "
       "conjunto por família)", POP_TEST, DIR_12, "decisão", DEN_DEC,
       "limite inferior = limite inferior de M-OPCOV-DEC × limite inferior de M-PERS-DEC (NOT_READABLE, "
       "INFRA_ERROR e UNKNOWN como falha); limite superior = produto dos limites superiores",
       FRAME_TEST + "; π do " + FRAME_DEP, "INC-DEC-01", INC_DEC, weights="frame"),
    _m("M-BEHAV-DEC", "observações coincidentes sob protocolo", "decision", "behavior", "observed_fraction",
       "pares de sonda com OBSERVATIONS_MATCH_UNDER_PROTOCOL (PROBE-JOIN) ÷ pares de sonda sorteados, por tipo "
       "de sonda; vale só para os casos sondados e não é extrapolado",
       "pares de sonda sorteados entre casos carregados de tipos com suporte validado nos dois provedores",
       "por direção do caso, relatada por tipo de sonda", "decisão",
       "número de pares de sonda sorteados (pair_case_id), um por decisão sondada",
       "NOT_OBSERVED_IN_WINDOW (censura), PROTOCOL_UNSUPPORTED, INFRA_ERROR e UNKNOWN contam como não "
       "coincidentes no limite inferior e como coincidentes no limite superior; DIFFER é falha nos dois",
       FRAME_PROBE, "INC-PROBE-01", "pares de sonda do DEPSAMPLE com controle negativo válido nos dois lados",
       weights="inverse_probability", uncertainty="wilson"),
    _m("M-HOLDOUT-REPR-DEC", "hold-out de unidades: representação às cegas", "decision", "representability",
       "observed_fraction",
       "fração das decisões das unidades canônicas do hold-out (abertas no UNSEAL) que o mapeador às cegas "
       "representa na ontologia congelada sem poder criar classe",
       "unidades canônicas sorteadas para hold-out no SPLIT (sem pilot_exposed)", "não direcional: por "
       "provedor da unidade", "decisão", DEN_DEC,
       "UNKNOWN_SYMBOLIC_INPUT e UNKNOWN_INPUT contam como não representadas no limite inferior e como "
       "representadas no limite superior", "hold-out de unidades do SPLIT", "INC-HOLD-01",
       "decisões das unidades do hold-out; " + NAMETAG_OUT),
    _m("M-LOPO-REPR-DEC", "LOPO: representação da OCI sem OCI", "decision", "representability",
       "observed_fraction",
       "fração das decisões OCI da partição de teste representáveis na ontologia de 3 provedores (sem OCI) sem "
       "classe nova", POP_TEST + "; só A = oci", "não direcional: só provedor oci", "decisão", DEN_DEC,
       "UNKNOWN_SYMBOLIC_INPUT e UNKNOWN_INPUT contam como não representadas no limite inferior e como "
       "representadas no limite superior", FRAME_TEST, "INC-DEC-01", INC_DEC),
    _m("M-CQ-ANSWER", "respostas corretas das CQs congeladas", "graph", "representability", "observed_fraction",
       "fração das fixtures das CQs congeladas (C24: conforme, não conforme, incompleta) cuja consulta SPARQL "
       "sobre a ABox gerada devolve a resposta esperada, inclusive UNKNOWN onde a esperada é UNKNOWN",
       "fixtures das 29 CQs do REQUIREMENTS e as fixtures retidas dos pilotos, reexecutadas a cada reparo",
       "não direcional: por provedor da fixture, quando houver", "grafo",
       "número de fixtures (cada fixture é um grafo pequeno), fixo no REQUIREMENTS; nenhuma é retirada depois",
       "consulta que não termina ou erro de infraestrutura (INFRA_ERROR) conta como errada no limite inferior e "
       "como certa no limite superior; UNKNOWN_INPUT e UNKNOWN_SYMBOLIC_INPUT na ABox idem; resposta UNKNOWN "
       "quando a esperada é definida é errada nos dois limites", "CQs congeladas do REQUIREMENTS (FREEZE0)",
       "INC-CQ-01", "todas as fixtures de cq_spec.jsonl, sem exceção", uncertainty="exact"),
]

# Estimandos que não são uma métrica do C15 (diferenças, razões, sobrevivência, Gini, auditoria de ausências).
# Mesmos seis atributos, conferidos pelo mesmo gate.
OTHER_ESTIMANDS = [
    {"estimand_id": "E-HUBLOSS", "name": "perda do hub",
     "definition": "M-OPCOV-DEC-DIRECT − M-OPCOV-DEC e a razão M-OPCOV-DEC ÷ M-OPCOV-DEC-DIRECT, pareadas por decisão",
     "population": POP_TEST, "direction": DIR_12, "unit": "decisão", "denominator": DEN_DEC,
     "unknown": "calculada nos dois limites (inferior com inferior, superior com superior); discordância entre "
                "eles é 'indeterminada pelo desconhecido'", "contrast": "C-H7"},
    {"estimand_id": "E-ASYM", "name": "assimetria entre direções",
     "definition": "M-OPCOV-DEC(A→B) − M-OPCOV-DEC(B→A), por par; causa decomposta pelos códigos do C23",
     "population": "as duas populações de origem do par (independentes)", "direction": "por par não ordenado (6)",
     "unit": "decisão", "denominator": "os dois denominadores de M-OPCOV-DEC, um por direção",
     "unknown": "calculada nos dois limites; o critério de H2 exige o mesmo sinal nos dois", "contrast": "C-H2"},
    {"estimand_id": "E-OR-AUTH", "name": "razão de chances autorização/borda × dimensionamento",
     "definition": "razão de chances de emissão em B (decisões de autorização e borda CDN/WAF contra decisões "
                   "de dimensionamento de compute e storage) no modelo logístico com efeitos fixos de par, "
                   "direção, domínio, tipo de grão, papel e cardinalidade",
     "population": POP_TEST, "direction": "12 direções juntas, direção como efeito fixo", "unit": "decisão",
     "denominator": "decisões dos dois grupos (classe de decisão fixada no glossário antes do mapeamento)",
     "unknown": "modelo ajustado duas vezes, com o desfecho no limite inferior e no superior", "contrast": "C-H3"},
    {"estimand_id": "E-GINI-BALANCE", "name": "equilíbrio de contagens entre provedores",
     "definition": "Gini das contagens de classes realizadas por provedor (e de classes exclusivas), no artefato "
                   "completo e no ablado; rotulado equilíbrio de contagens, nunca neutralidade",
     "population": "classes da ontologia congelada e da ablada (artefatos, não amostra)",
     "direction": "não direcional", "unit": "classe",
     "denominator": "as 4 contagens por provedor (Gini sobre 4 valores)",
     "unknown": "classe com realização AMBIGUOUS conta nos dois sentidos: Gini mínimo e máximo relatados",
     "contrast": "C-H6-GINI"},
    {"estimand_id": "E-DRIFT-LAG", "name": "atraso de disponibilidade no provider Terraform",
     "definition": "tempo entre a primeira versão do provider de um provedor com o conceito e a primeira versão "
                   "do provider de outro provedor com o conceito correspondente (eventos tipados C13); mediana "
                   "por Turnbull com censura intervalar e truncamento à esquerda",
     "population": "pares conceito×provedor do glossário congelado com evento de adição nas versões amostradas",
     "direction": "por par ordenado (quem chegou antes → quem chegou depois)", "unit": "evento",
     "denominator": "eventos de chegada observados; os não chegados até a última versão são censurados à direita",
     "unknown": "evento só datado por intervalo entre duas versões amostradas entra como censura intervalar; "
                "conceito presente já na primeira versão amostrada entra com truncamento à esquerda",
     "contrast": "C-H5"},
    {"estimand_id": "E-NONE-FALSE", "name": "taxa de falso NONE (auditoria de ausências)",
     "definition": "fração das ausências (NONE) da amostra probabilística do DISPUTE-SAMPLE para as quais existe "
                   "alvo correto em B; descobertas adversariais dos caçadores relatadas só como contagem",
     "population": "atributos de A com NONE declarado, frame do DISPUTE-SAMPLE",
     "direction": DIR_12, "unit": "decisão",
     "denominator": "ausências sorteadas (pesos de inclusão publicados); nunca somadas à cobertura",
     "unknown": "ausência cujo alvo não pôde ser decidido (UNKNOWN) conta como NONE verdadeiro no limite inferior "
                "e como falso no superior", "contrast": None},
]

# ------------------------------------------------------------------------------------------- quantificador
QUANTIFIER_RULES = [
    ("existential", "nível de schema: a decisão atravessa se ALGUM valor do domínio de A atravessa (broad/narrow: "
     "predicado de pertença satisfazível)"),
    ("universal", "nível de schema: a decisão atravessa se TODO valor do domínio de A atravessa (broad A→B por "
     "inclusão; narrow só se o predicado é verdadeiro no domínio inteiro)"),
    ("observed_fraction", "nível de uso: fração dos valores observados (C06) que satisfazem o predicado de "
     "pertença ou o domínio da função parcial; é a leitura das métricas operacionais, que rodam o tradutor nos "
     "valores reais"),
]
LADDER = [
    ("representability", "representabilidade", "a ontologia representa a configuração de A"),
    ("transportability", "transportabilidade", "existe correspondência provada que admite transporte para B"),
    ("operational", "cobertura operacional", "o tradutor real (modelo+tradutor, no universo U) emite em B; "
     "medida principal"),
    ("persistence", "persistência", "a API de B aceitou e guardou (deploy e leitura de volta)"),
    ("behavior", "comportamento", "uma sonda observou o mesmo efeito sob protocolo (OBSERVATIONS_MATCH_UNDER_PROTOCOL)"),
]

# ------------------------------------------------------------------------------------------- pilotos e controles
CONTROLS_RULE = {
    "controls": ["c1_table", "c2_taxonomy", "c3_full"],
    "invariants": [
        "mesma entrada (mesmo C06 e mesmas fixtures), mesma política de perda, mesmas transformações e mesmo "
        "lowering nos 3 controles",
        "casos fora da calibração, com resposta esperada independente (compromissos e CQs congelados do REQUIREMENTS)",
        "toda consequência de c3 contada traz justifying_axioms (C23) separados de consulted_metadata",
        "positivos, negativos e desconhecidos contados à parte; efeito de cada família de axioma classificado em "
        "transporte, detecção de erro, redundância ou não uso",
    ],
    "outcomes": [
        {"id": "R-CTRL-1", "condition": "c3 supera c1 E c2 em pelo menos uma família de consequências (C-H9: "
         "McNemar exato, p ≤ 0,05/7 contra cada controle, n por família ≥ o de power.json)",
         "consequence": "H9 sustentada só nessas famílias; o texto diz 'os axiomas produzem consequências corretas "
                        "que a tabela e a taxonomia não produzem' restrito a elas"},
        {"id": "R-CTRL-2", "condition": "c3 não supera c2 em nenhuma família, mas c2 supera c1",
         "consequence": "o efeito é atribuído à taxonomia e às realizações, não aos axiomas; os axiomas são "
                        "rebaixados a documentação e detecção de erro; H9 refutada"},
        {"id": "R-CTRL-3", "condition": "nenhuma diferença entre os 3 controles com n por família ≥ o necessário",
         "consequence": "resultado nulo publicado como tal: na tradução a ontologia equivale a uma tabela; as "
                        "contribuições ficam na medição (cobertura, invariância) e o OWL vale como documentação "
                        "e detecção de erro; H9 refutada"},
        {"id": "R-CTRL-4", "condition": "n por família abaixo do necessário e nenhuma família significativa",
         "consequence": "H9 'inconclusiva' (nunca 'nula'); contagens e justificativas descritivas; o papel dos "
                        "axiomas é rebaixado do mesmo jeito, porque benefício exige evidência positiva"},
        {"id": "R-CTRL-5", "condition": "c3 produz consequência incorreta que c1 ou c2 não produz",
         "consequence": "regressão: relatada como achado contra a hipótese, ligada ao compromisso violado; reparo "
                        "depois do FREEZE2 não entra na leitura primária"},
        {"id": "R-CTRL-6", "condition": "c3 rejeita fixture negativa que c1/c2 aceitam, sem mudar transporte",
         "consequence": "contado como efeito em DETECÇÃO DE ERRO, em linha própria, nunca somado ao transporte"},
    ],
    "pilot_reading": ("nos pilotos (fixtures retidas, n pequeno) a regra é aplicada só como contagem descritiva e "
                      "o resultado vai para o adendo antes da escala; a decisão sobre H9 é tomada só na partição "
                      "de teste, depois do UNSEAL"),
}

PILOT_EXIT = {
    "slices": ["sto", "net"],
    "directions": 12,
    "attempts_max": 2,
    "coverage_threshold": ("nenhum: os critérios não têm limiar sobre cobertura (seria ajuste, §9.5); a fração "
                           "de acerto nas retidas é relatada"),
    "runner": "PILOT-EXIT, agente que não implementou os pilotos, roda o código congelado do E2E nas fixtures RETIDAS",
    "criteria": [
        {"id": "E1", "name": "caminho completo",
         "requirement": ("as duas fatias rodam nas 12 direções (ou com UNSUPPORTED declarado), com traço C23 por "
                         "valor e plano de lowering C26, sem nenhuma inserção silenciosa (HCL = plano + valores "
                         "sintetizados declarados)"),
         "measures": ["direções com saída ou UNSUPPORTED declarado por fatia (esperado 12)",
                      "valores sem traço C23 (esperado 0)",
                      "atributos no HCL fora do plano e dos sintetizados declarados (esperado 0)"],
         "pass_rule": "directions_covered == 12 and values_without_trace == 0 and silent_insertions == 0",
         "evidence": ["$BO_REPO/results/PILOT-STO-E2E/", "$BO_REPO/results/PILOT-NET-E2E/"],
         "on_fail": "corrigir por emenda versionada e repetir (conta uma tentativa)"},
        {"id": "E2", "name": "grão",
         "requirement": ("decomposição igual ao gabarito do oráculo em 100% dos casos obrigatórios da fatia; "
                         "invariância a reordenação de blocos, à embalagem (inline × standalone; bloco × recurso "
                         "separado) e a renomeação de provedores"),
         "measures": ["casos obrigatórios com decomposição ≠ gabarito (esperado 0)",
                      "variantes de invariância com saída diferente depois de desfazer a variação (esperado 0)"],
         "pass_rule": "grain_mismatches == 0 and invariance_failures == 0",
         "evidence": ["$BO_DATA/PILOT-STO-ORACLE/sealed/", "$BO_DATA/PILOT-NET-ORACLE/sealed/"],
         "on_fail": "emenda da regra de grão (GRAIN) com invalidação dos dependentes"},
        {"id": "E3", "name": "correspondências",
         "requirement": ("toda alegação com os três campos (semantic_relation, value_domain_relation, "
                         "transport_fidelity), guarda e prova; o árbitro devolve UNPROVEN onde falta prova; teste "
                         "SKOS de ida e volta verde; composição só pela tabela formal"),
         "measures": ["alegações sem algum dos três campos, guarda ou prova (esperado 0)",
                      "alegações sem prova com veredito ≠ UNPROVEN (esperado 0)",
                      "composições fora da tabela formal (esperado 0)", "ida e volta SKOS (esperado verde)"],
         "pass_rule": "claims_incomplete == 0 and unproven_misjudged == 0 and off_table_compositions == 0 and skos_roundtrip_ok",
         "evidence": ["$BO_REPO/results/PILOT-STO-E2E/", "$BO_REPO/results/PILOT-NET-E2E/"],
         "on_fail": "emenda do árbitro (ARBITERLIB) ou do brief do mapeador"},
        {"id": "E4", "name": "oráculo",
         "requirement": ("nas fixtures retidas: zero perda silenciosa (toda divergência entre oráculo e saída "
                         "coberta por perda declarada) e zero transporte em caso negativo (todo contraexemplo "
                         "continua rejeitado); a fração de acerto é relatada, não é limiar"),
         "measures": ["divergências oráculo × saída sem perda declarada (esperado 0)",
                      "contraexemplos transportados (esperado 0)", "fração de acerto (relatada, sem limiar)"],
         "pass_rule": "silent_losses == 0 and negatives_carried == 0",
         "evidence": ["$BO_REPO/results/PILOT-EXIT/exit_report.json"],
         "on_fail": "corrigir o tradutor ou o contrato de perda por emenda; a fração de acerto nunca decide"},
        {"id": "E5", "name": "controles",
         "requirement": ("os 3 controles rodaram com a mesma entrada, perda e transformações; as consequências de "
                         "cada um nas retidas estão contadas e justificadas; a consequência do resultado "
                         "(inclusive nulo) para H9 está escrita no adendo antes da escala"),
         "measures": ["controles rodados com entrada idêntica (sha da entrada igual nos 3)",
                      "consequências contadas por controle e por polaridade",
                      "adendo ADDENDUM_PILOTS.html com a linha R-CTRL aplicada"],
         "pass_rule": "controls_same_input and consequences_counted and addendum_written_before_scale",
         "evidence": ["$BO_REPO/prereg/ADDENDUM_PILOTS.html"],
         "on_fail": "rodar de novo os controles; sem adendo a escala não começa"},
        {"id": "E6", "name": "delta de contrato",
         "requirement": ("toda mudança exigida pelos pilotos aplicada como emenda versionada (contrato, regra de "
                         "grão, brief, árbitro), com os dependentes invalidados automaticamente e o catálogo de "
                         "artefatos verde"),
         "measures": ["mudanças sem emenda versionada (esperado 0)",
                      "dependentes não marcados STALE depois da emenda (esperado 0)", "catálogo do gerador verde"],
         "pass_rule": "unversioned_changes == 0 and stale_not_marked == 0 and catalog_ok",
         "evidence": ["$BO_REPO/freeze/FREEZE-P/freeze_receipt.json"],
         "on_fail": "registrar a emenda e rodar tools/invalidate.py check --apply"},
        {"id": "E7", "name": "esforço",
         "requirement": ("esforço real de cada passo gravado e usado para recalibrar o esforço dos módulos de "
                         "escala e refazer o cronograma"),
         "measures": ["passos sem esforço medido (esperado 0)", "cronograma recalculado com o esforço medido"],
         "pass_rule": "steps_without_effort == 0 and schedule_recomputed",
         "evidence": ["$BO_REPO/results/PILOT-EXIT/effort_calibration.json"],
         "on_fail": "medir e recalcular antes de liberar a escala"},
        {"id": "E8", "name": "limite de tentativas",
         "requirement": ("se E1–E6 falharem duas vezes, a expansão não começa: o plano volta para revisão (v4) e o "
                         "Breno é avisado"),
         "measures": ["tentativas de E1–E6 (máximo 2)"],
         "pass_rule": "attempts <= 2 or (expansion_blocked and plan_returned_v4 and breno_notified)",
         "evidence": ["$BO_REPO/results/PILOT-EXIT/exit_report.json"],
         "on_fail": "bloquear a expansão (DECOMPOSE, 6 glossários, 36 mapeadores, 16 módulos de nuvem)"},
    ],
    "addendum": {
        "path": "$BO_REPO/prereg/ADDENDUM_PILOTS.html", "writer": "PILOT-EXIT",
        "must_contain": ["resultado dos 3 controles nas retidas (contagens por polaridade e justificativas)",
                         "a linha R-CTRL aplicada e a consequência pré-declarada para H9",
                         "cada emenda de E6 com motivo e as duas leituras", "esforço medido (E7)"],
    },
}

# ------------------------------------------------------------------------------------------- leave-one-provider-out
LOPO = {
    "left_out": "oci",
    "why_oci": ("pré-registrado antes de qualquer dado: OCI é o provedor com menos uso no TerraDS e o que entrou "
                "no lugar de Yandex e Cloud.ru frente a Kalinin; escolher depois de ver o resultado seria ajuste"),
    "steps": [
        "reinduzir classes e propriedades só com as 18 alegações sem OCI (3 pares × 6 domínios) e o glossário sem "
        "as âncoras OCI, com o mesmo código congelado do caminho principal",
        "um mapeador NOVO, que não mapeou nenhum par com OCI, mapeia as unidades OCI da projeção de treino contra "
        "a ontologia de 3 provedores, sem poder criar classe; o que não cabe vira bo:UNGLOSSED",
        "rodar o tradutor nas 6 direções com OCI na partição de teste com as duas ontologias (3 e 4 provedores)",
        "comparar M-LOPO-OPCOV-DEC com M-OPCOV-DEC pareado por decisão (C-LOPO) e relatar M-LOPO-REPR-DEC e o "
        "número de classes novas que a ontologia de 4 provedores tem e a de 3 não tem",
    ],
    "criterion": "C-LOPO: Y_3 ≥ 0,90 × Y_4 em pelo menos 4 das 6 direções com OCI, nos dois limites",
    "contamination": ("declarada: os glossaristas viram documentação da OCI ao escrever os conceitos; as âncoras "
                      "OCI saem, mas a lista de conceitos não é reescrita. O viés favorece a acomodação, isto é, "
                      "a hipótese; por isso o resultado é rotulado 'provedor novo com contaminação de glossário' e "
                      "Azure e OCI não são chamados de hold-out de provedor"),
    "holdouts": [
        ("teste global", "famílias deduplicadas e divididas uma vez no SPLIT com SEED-SPLIT; partição de teste "
         "cifrada com a chave pública do Breno; aberta só no UNSEAL, depois do FREEZE2"),
        ("unidade canônica", "sorteada no SPLIT com SEED-HOLDOUT-UNITS, sem as unidades pilot_exposed; mapeada às "
         "cegas no HOLDOUT (M-HOLDOUT-REPR-DEC)"),
        ("provedor novo", "este desenho (OCI)"),
        ("temporal", "versões publicadas depois do FREEZE1 (SCHEMA-POST, P1)"),
    ],
}

# ------------------------------------------------------------------------------------------- sementes
SEED_SALT = "brevops-prereg-v3/"
SEED_MOD = 2147483647
SEEDS = [
    ("SEED-SPLIT", "SPLIT", "atribuição calibração/teste por família deduplicada"),
    ("SEED-HOLDOUT-UNITS", "SPLIT", "sorteio do hold-out de unidades canônicas (sem pilot_exposed)"),
    ("SEED-DEPSAMPLE", "DEPSAMPLE", "sorteio dos casos carregados e bloqueados e ordem de substituição por estrato"),
    ("SEED-PROBESAMPLE", "DEPSAMPLE", "sorteio da amostra de sondas entre tipos com suporte validado"),
    ("SEED-DISPUTE", "DISPUTE-SAMPLE", "amostra probabilística de ausências (taxa de falso NONE)"),
    ("SEED-BOOT", "METRICSLIB", "bootstrap por família, repositório e grafo"),
    ("SEED-PERM", "METRICSLIB", "testes de permutação (rótulos de direção dentro do par)"),
    ("SEED-KALININ", "KALININ-RECON", "ordem e desempates da família de reconstruções"),
    ("SEED-TOOL", "TOOL-ACCURACY", "amostra de 200 decisões por direção e ordem de apresentação ao LLM"),
    ("SEED-POWER-SIM", "PREREG", "simulação de Monte Carlo que confere o cálculo de poder (tests/prereg)"),
]
SEED_RULE = ("seed = int(sha256(UTF-8('brevops-prereg-v3/' + NOME)).hexdigest(), 16) mod 2147483647. A semente "
             "é função do nome, fixado aqui antes de qualquer dado; trocar a semente exige trocar o nome, o que é "
             "emenda. Bootstrap: 4000 réplicas; permutação: 10000.")

# ------------------------------------------------------------------------------------------- congelamentos
FREEZE_OWNER = "coordenador"
FREEZES = [
    ("FREEZE0", "fim da fundação", "requisitos e compromissos, semântica, contratos, transformações, padrões OWL, "
     "regras de grão provisórias, este pré-registro (todos os arquivos de prereg/), briefs, sementes",
     "REQUIREMENTS, SEMANTICS, CONTRACTS, TRANSFORMS, ONTPAT, GRAIN, PREREG, BRIEFS", "OTS + OSF (D4)"),
    ("FREEZE-M", "ARBITERLIB, METRICSLIB, PROBEKIT", "árbitro, biblioteca de métricas e kit de sondas, antes de "
     "qualquer mapeamento ou dado real", "ARBITERLIB, METRICSLIB, PROBEKIT", "OTS"),
    ("FREEZE-P", "PILOT-EXIT", "emendas exigidas pelos pilotos e adendo do pré-registro com o resultado dos "
     "controles", "PILOT-EXIT", "OTS + OSF (adendo)"),
    ("FREEZE-GRAIN", "GRAIN-REPRO", "regras de grão definitivas, depois da concordância com a 2ª implementação",
     "GRAIN-REPRO", "OTS"),
    ("SPLIT", "SPLIT", "split global e partição de teste cifrada (só o cifrado fica no disco)", "SPLIT", "OTS"),
    ("FREEZE-G", "GLOSSARY-FREEZE", "glossário com os estados da auditoria", "GLOSSARY-FREEZE", "OTS"),
    ("FREEZE1", "RECONCILE", "alegações dos 6 pares (SSSOM + EDOAL) com vereditos", "RECONCILE", "OTS + OSF (D4)"),
    ("FREEZE2", "SEMANTIC-REGRESSION", "TBox, formas e bateria de regressão, só depois de ela passar",
     "SEMANTIC-REGRESSION", "OTS"),
    ("UNSEAL", "UNSEAL", "recibo de abertura do teste, com data posterior ao FREEZE2", "UNSEAL", "OTS"),
    ("GOLD", "GOLD-AUDIT", "ouro externo auditado, antes de qualquer pontuação", "GOLD-AUDIT", "OTS"),
    ("DEPSAMPLE", "DEPSAMPLE", "frame, pesos, casos sorteados (inclusive bloqueados) e amostra de sondas",
     "DEPSAMPLE", "OTS"),
    ("RELEASE-EXP", "ARTIFACT", "release experimental imutável", "ARTIFACT", "OTS + DOI"),
    ("RELEASE-FIX", "RELEASE-CORRECTED", "release corrigida depois da revisão", "RELEASE-CORRECTED", "OTS + DOI"),
]
FREEZE_RULES = [
    "Cada congelamento grava $BO_REPO/freeze/<NOME>/freeze_receipt.json (C17 3.0.0) com tools/freeze.py create: "
    "dono, hora (America/Recife), hashes transitivos de todas as entradas, tag git anotada bo-freeze-<NOME> e "
    "carimbo OpenTimestamps (PENDING explícito sem o cliente ots; freeze.py stamp tenta de novo).",
    "O dono de todo comprovante é o coordenador; o módulo da coluna 'produtor' é quem pede o congelamento e "
    "responde pelo conteúdo.",
    "Todo módulo confere as entradas contra os comprovantes ao começar e no gate (tools/consume_check.py).",
    "Comprovante é único: não se edita. Emenda gera congelamento de nome novo (ex. FREEZE0-A1).",
    "Âncora externa: OSF para FREEZE0, FREEZE-P e FREEZE1 (D4, registro feito pelo Breno; o ID vai em "
    "results/PREREG/OSF_ID.txt, hoje PENDING); OpenTimestamps para todos.",
    "Ordem que nenhum congelamento pode inverter (a do grafo de dependências): FREEZE0 < FREEZE-M < FREEZE-P < "
    "{SPLIT, FREEZE-GRAIN} < FREEZE-G < FREEZE1 < FREEZE2 < UNSEAL; GOLD antes de qualquer pontuação contra o "
    "ouro; DEPSAMPLE antes do primeiro apply. Comprovante com data fora desta ordem invalida os dependentes.",
]

# ------------------------------------------------------------------------------------------- emendas e invalidação
AMENDMENT_RULES = [
    "Emenda é entrada nova, numerada (AMD-NNN), em $BO_REPO/prereg/AMENDMENTS.html, nunca edição deste arquivo: "
    "data e hora, quem pede, o que muda, por quê, se algum desfecho da partição de teste já tinha sido visto "
    "(desenho adaptativo declarado), as duas leituras (congelada e emendada) e a lista de dependentes invalidados.",
    "A leitura PRIMÁRIA é sempre a congelada. A emendada é secundária, salvo emenda feita antes de qualquer "
    "desfecho da partição de teste e motivada só por calibração ou piloto (E6), que vira a nova primária com o "
    "congelamento de nome novo.",
    "Toda emenda roda tools/invalidate.py check --apply: os consumidores do artefato mudado e o fecho reverso das "
    "dependências viram STALE; o congelamento afetado vira BROKEN; só tools/invalidate.py clear ID --reason "
    "devolve a CURRENT, depois de refeito.",
    "Contraste, métrica, limiar, margem, alfa, unidade, frame ou peso decididos depois de ver desfecho do teste "
    "são EXPLORATÓRIOS, rotulados assim no texto e nunca entram em numbers.tex como confirmatórios.",
    "A reestimação cega de power.json (contagens estruturais do teste, correlação da calibração) não é emenda: "
    "está pré-declarada e só pode rebaixar contraste a descritivo.",
]
INVALIDATION_RULES = [
    "Resultado calculado com entrada STALE ou comprovante BROKEN é inválido até ser refeito com entradas CURRENT.",
    "Leitura da partição de teste antes do recibo do UNSEAL: todo contraste que depende dela vira exploratório; é "
    "preciso um novo hold-out (novas famílias) para a leitura confirmatória.",
    "Mudança em artefato congelado sem emenda: o congelamento vira BROKEN, os dependentes STALE, e o desvio é "
    "relatado.",
    "Número digitado à mão no texto (fora de numbers.tex gerado pelo STATS com sha): o número é inválido.",
    "Desvio de protocolo sem emenda (substituição fora da regra, caso retirado depois do desfecho, retentativa "
    "além de 2): a leitura afetada vira exploratória e o desvio é publicado.",
    "Se os critérios de saída dos pilotos falharem duas vezes (E8), todo o plano de escala é inválido até a v4.",
]

# ------------------------------------------------------------------------------------------- comparação justa
H2H = {
    "budget_per_comparator": 0.75,
    "budget_note": ("0,75 hora-agente por comparador para o pacote de tradução (o BASELINE-ADAPT tem 6 h para "
                    "todos); hora não gasta não passa para outro comparador. O tradutor do BrevOps foi construído "
                    "com muito mais esforço: a assimetria é declarada e a comparação é rotulada 'pacote de "
                    "tradução com orçamento igual de adaptação', não 'esforço igual'."),
    "comparators": ["kalinin", "cpg", "certgraph", "devops-infra", "fixinventory", "cartography", "steampipe",
                    "cloudquery", "mosaic", "cso", "cocoon", "tosca-edmm"],
    "rules": [
        "mesmo orçamento de adaptação (horas-agente) e o mesmo brief 'melhor esforço a favor do baseline' para "
        "todos os comparadores",
        "mesmo universo U e mesmas CQs congeladas para todos",
        "ABox de cada modelo gerada dos mesmos fatos de origem (grafo factual independente), nunca da ABox "
        "normalizada pelo BrevOps",
        "três comparações separadas: artefato e tarefa nativos; representação no mesmo grafo factual; tradução "
        "com orçamento igual",
        "NOT_APPLICABLE nunca vira zero; sem artefato a comparação é documental e não tem número no eixo de tradução",
        "onde o modelo não diz, o adaptador não inventa: toda realização cita arquivo:linha do próprio modelo",
        "Kalinin entra como família pré-definida de reconstruções e é relatado como faixa; no eixo de tradução "
        "compara-se contra a melhor variante por direção (escolha que favorece o baseline)",
        "a interface C14 não é imposta ao comparador; o adaptador pode usar o formato nativo do modelo",
        "critério de novidade escrito antes: conta medir invariância e semântica executável, não preencher mais campos",
    ],
}

# ------------------------------------------------------------------------------------------- sondas
# probe_types.yaml (C22). O suporte por provedor fica 'unknown' com evidência vazia: quem valida é o PROBEKIT,
# com a tabela do SERVICE-EVIDENCE, ANTES do sorteio. O limite de custo é por execução de um par (dois lados),
# em dólares, incluindo armazenamento, tráfego e requisições, dentro do limite total D3.
LONG_WINDOW = "supervisor independente com heartbeat ativo (D16); sem ele, o tipo sai da amostra"
PROBE_TYPES = [
    {"probe_type": "object_versioning",
     "preconditions": ["bucket ou contêiner novo da execução, com a configuração de versionamento do caso aplicada "
                       "e lida de volta como PERSISTED",
                       "objeto sintético de 1 KiB, sem conteúdo real; gravado 3 vezes com a mesma chave"],
     "negative_control": {"description": "mesmo protocolo em contêiner com versionamento desligado ou suspenso",
                          "expected": "uma única versão listada da chave"},
     "repetitions": 3, "tolerance": {"kind": "exact", "value": 0},
     "polling": {"interval": "PT1M", "max_wait": "PT30M"},
     "window": {"duration": "PT1H", "margin_over_ttl": "PT30M"},
     "cost_limit": 0.5},
    {"probe_type": "object_lifecycle",
     "preconditions": ["regra de ciclo de vida do caso com a menor idade permitida pelo provedor (1 dia onde a "
                       "unidade é dia), lida de volta como PERSISTED", "objetos sintéticos com idade conhecida",
                       LONG_WINDOW],
     "negative_control": {"description": "mesmo protocolo em contêiner sem regra de ciclo de vida",
                          "expected": "objetos continuam presentes no fim da janela"},
     "repetitions": 3, "tolerance": {"kind": "exact", "value": 0},
     "polling": {"interval": "PT6H", "max_wait": "PT72H"},
     "window": {"duration": "PT72H", "margin_over_ttl": "PT48H"},
     "cost_limit": 1.0},
    {"probe_type": "item_ttl",
     "preconditions": ["tabela ou coleção com TTL habilitado no atributo declarado, lida de volta como PERSISTED",
                       "itens sintéticos com expiração 1 h depois da gravação", LONG_WINDOW],
     "negative_control": {"description": "itens iguais sem o atributo de TTL (ou TTL desligado)",
                          "expected": "itens continuam legíveis no fim da janela"},
     "repetitions": 3, "tolerance": {"kind": "exact", "value": 0},
     "polling": {"interval": "PT2H", "max_wait": "PT72H"},
     "window": {"duration": "PT72H", "margin_over_ttl": "PT71H"},
     "cost_limit": 1.0},
    {"probe_type": "queue_retention",
     "preconditions": ["fila com a retenção do caso no menor valor permitido pelo provedor; se o mínimo passa de "
                       "24 h, PROTOCOL_UNSUPPORTED antes do sorteio", "mensagens sintéticas sem conteúdo real; "
                       "nenhum consumidor durante a janela", LONG_WINDOW],
     "negative_control": {"description": "mesma fila com retenção maior que a janela",
                          "expected": "mensagens continuam disponíveis no fim da janela"},
     "repetitions": 3, "tolerance": {"kind": "exact", "value": 0},
     "polling": {"interval": "PT1H", "max_wait": "PT48H"},
     "window": {"duration": "PT48H", "margin_over_ttl": "PT24H"},
     "cost_limit": 0.5},
    {"probe_type": "rate_limit",
     "preconditions": ["limite de taxa do caso declarado com JANELA (período de renovação), CHAVE (por chave de "
                       "assinatura, por IP de origem ou total), RAJADA (capacidade do balde) e MECANISMO (balde de "
                       "fichas ou janela fixa), lidos do SERVICE-EVIDENCE",
                       "endpoint sintético sem backend real; uma única chave de cliente por repetição",
                       "N = 3 × (rajada + taxa × janela) pedidos enviados numa janela"],
     "negative_control": {"description": "mesmo protocolo sem limite configurado (ou limite 100 vezes maior)",
                          "expected": "nenhuma resposta de limitação (HTTP 429) na janela"},
     "repetitions": 3, "tolerance": {"kind": "relative", "value": 0.2},
     "polling": {"interval": "PT1S", "max_wait": "PT10M"},
     "window": {"duration": "PT10M", "margin_over_ttl": "PT5M"},
     "cost_limit": 1.0},
    {"probe_type": "log_retention",
     "preconditions": ["grupo ou bucket de log com a retenção do caso no menor valor permitido (1 dia onde "
                       "existe); se o mínimo passa de 3 dias, PROTOCOL_UNSUPPORTED antes do sorteio",
                       "eventos sintéticos sem conteúdo real; o conteúdo dos logs nunca é gravado, só contagens "
                       "e datas", LONG_WINDOW],
     "negative_control": {"description": "mesmo protocolo com retenção maior que a janela",
                          "expected": "eventos continuam consultáveis no fim da janela"},
     "repetitions": 3, "tolerance": {"kind": "exact", "value": 0},
     "polling": {"interval": "PT6H", "max_wait": "PT96H"},
     "window": {"duration": "PT96H", "margin_over_ttl": "PT72H"},
     "cost_limit": 1.0},
]
PROBE_RULES = [
    "Janela de observação separada do TTL, com margem declarada (margin_over_ttl): o efeito nominal (TTL, idade "
    "da regra, retenção) acontece no início da janela e a margem cobre a consistência eventual documentada.",
    "Efeito não visto no fim da janela é NOT_OBSERVED_IN_WINDOW (censura), nunca 'igual' nem 'diferente'.",
    "Controle negativo em todo par: sem o efeito oposto no controle, a observação não vale "
    "(negative_control_ok = false) e o par sai como UNKNOWN.",
    "O runner de cada provedor só grava observações locais (pair_case_id, side, timestamp, protocol_version, "
    "contagens); só o PROBE-JOIN julga.",
    "Retenção de backup de banco fica fora.",
    "Sondas de janela longa (ciclo de vida, TTL, retenção) só com o supervisor independente (D16).",
]

# ------------------------------------------------------------------------------------------- rastreio das objeções
OBJECTIONS = [
    ("R1-M8", "CQs escritas depois do desenho e sem gabarito", "métricas M-CQ-ANSWER e bloqueio por compromisso; "
     "CQs e respostas do REQUIREMENTS entram no FREEZE0 antes da indução", "metricas"),
    ("R2-W9", "viabilidade e venue", "venue fora; viabilidade pelos pilotos (E1–E8, E7 recalibra o esforço) e "
     "pela regra de parada E8", "pilotos"),
    ("R3-M1", "circularidade", "cobertura calculada rodando o tradutor; persistência e comportamento julgados por "
     "código sobre deploy e sondas; ouro selado; ausências auditadas nos dois sentidos", "escada"),
    ("R3-M5", "amostras pequenas sem poder", "poder por contraste com correlação por família e repositório "
     "(power.json); n necessário e regra de rebaixamento", "poder"),
    ("R3-M7", "pré-registro sem âncora externa", "comprovantes C17 com OTS e OSF; emendas com as duas leituras; "
     "invalidação automática", "congelamentos"),
    ("R4-W2", "higiene sem ablação", "C-ABL como evidência principal; sem efeito e com equivalência o componente é "
     "relatado como higiene", "contrastes"),
    ("A1", "OWL como epifenômeno", "3 controles e regra R-CTRL pré-declarada", "pilotos"),
    ("A2", "persistência confundida com comportamento", "eixos separados; sondas com protocolo, controle "
     "negativo e censura", "escada"),
    ("A4", "1:N e condicionais descartados", "complexas na leitura primária; H8 (M-OPCOV-DEC-COMPLEX); leituras "
     "por grafo e unidade completa", "metricas"),
    ("A7", "comparação com Kalinin não é de frente", "h2h_fairness.yaml: três eixos, orçamento igual, família "
     "Kalinin, NOT_APPLICABLE ≠ 0", "comparacao"),
    ("F7", "a medida principal era o alcance do tradutor", "renomeação, escada de cinco eixos, limites para o "
     "desconhecido, quatro leituras, hub × direto, NONE à parte", "renomeacao"),
    ("S5", "hold-outs nomeados, não isolados", "SEED-SPLIT, hold-out de unidades, LOPO com OCI e contaminação "
     "declarada", "lopo"),
    ("S7", "amostragem não identifica precisão direcional", "população, direção e unidade em cada estimando; "
     "bloqueados amostrados; NOT_READABLE e INFRA_ERROR em limites; poder", "desconhecido"),
    ("S10", "paralelização sem pilotos", "critérios de saída E1–E8 em pilot_exit.yaml", "pilotos"),
    ("S15", "muitos valores, poucas decisões independentes", "unidade = decisão; reamostragem por família, grafo "
     "e repositório; efeitos fixos; invariância e permutação", "unidades"),
]

SOURCES_READ = [
    ("$BO_REPO/requirements/", "CQs (29, 7 famílias) e compromissos (90) congelados: fonte das respostas esperadas"),
    ("$BO_REPO/semantics/", "transporte por relação, guarda indeterminada no intervalo, UNPROVEN"),
    ("$BO_REPO/lit/RELATED_WORK.html", "comparadores e o que não é contribuição"),
    ("ontologia_neutra/revisao_adversarial/R3_validade_empirica.html", "M1 (circularidade), M5 (poder), M7 (âncora)"),
    ("ontologia_neutra/COBERTURA_NEUTRA.html", "ordem de grandeza para os valores de planejamento (medida circular)"),
    ("revisao_adversarial_plano/REVISAO_PLANO_GEMINI_3_8_FLASH.html", "A1, A2, A4, A7"),
    ("revisao_adversarial_plano/REVISAO_PLANO_v2_GPT6_CODEX.txt", "F7, S5, S7, S10, S15"),
]
