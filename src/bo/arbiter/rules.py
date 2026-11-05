"""Regras do árbitro: as do SEMANTICS (reaproveitadas por id, bo.semantics.rules.RULES) e as próprias (ARB-*).

Cada regra: família, camada (A1–A5 do objetivo), saída quando falha e texto. A saída de cada falha é uma de
REFUTED_BY_RULE, UNPROVEN, CONTESTED, AMBIGUOUS. O veredito da alegação é a de maior precedência entre as
falhas dela (PRECEDENCE); sem falha, OK. Não há voto nem desempate: conflito marca TODAS as alegações nele.
"""

from __future__ import annotations

from bo.semantics.rules import RULES as SEM_RULES

R, U, C, A = "REFUTED_BY_RULE", "UNPROVEN", "CONTESTED", "AMBIGUOUS"
PRECEDENCE = ("REFUTED_BY_RULE", "CONTESTED", "UNPROVEN", "AMBIGUOUS", "OK")
VERDICTS = PRECEDENCE

ARB_RULES: dict[str, dict] = {}


def _r(rid, layer, family, on_fail, text, answers):
    ARB_RULES[rid] = {"rule_id": rid, "layer": layer, "family": family, "on_fail": on_fail, "text": text,
                      "answers": answers}


# ---- entrada e identidade ---------------------------------------------------------------------------------
_r("ARB-C09-SCHEMA", "A1", "entrada", R, "A linha confere com o JSON Schema do C09 (correspondence); linha fora do "
   "contrato não é julgada pelo resto.", ["C09"])
_r("ARB-VERSION", "A1", "entrada", R, "C09-IDS: claim_version_id = <claim_id>@n, versão e evento únicos, supersedes aponta "
   "para versão anterior da MESMA alegação; duas versões correntes do mesmo claim_id (bifurcação, inclusive entre "
   "arquivos) refutam as duas.", ["N3"])
_r("ARB-MALFORMED", "A1", "entrada", R, "A biblioteca de referência não consegue ler a alegação (estrutura impossível): "
   "refutada, nunca derruba o árbitro.", ["F2"])
# ---- função de tradução (TRANSFORMS) ----------------------------------------------------------------------
_r("ARB-FN-REG", "A2", "tradução", R, "C09-FN: toda etapa de translation_fn é do núcleo do SEMANTICS ou do registro FECHADO "
   "do TRANSFORMS (escalar ou combinador; comparador não é tradução).", ["F2", "N4"])
_r("ARB-FN-TYPE", "A2", "tradução", R, "Cadeia só do registro do TRANSFORMS: tipada passo a passo (check_chain) do tipo do "
   "sujeito até o do objeto (datatype, grandeza, unidade, janela, convenção de byte).", ["N4"])
# ---- grupos (A1) -----------------------------------------------------------------------------------------
_r("ARB-G-FN", "A1", "grupo", R, "Grupo e translation_fn na mesma alegação são duas normalizações: a do grupo são os passos.", ["F3"])
_r("ARB-G-DUP", "A1", "grupo", R, "Sem duplicata no subgrafo: variável de saída escrita por mais de um passo, duas "
   "variáveis no mesmo (lado, campo, ocorrência) ou passo repetido.", ["F3"])
_r("ARB-G-TYPE", "A2", "grupo", R, "Toda variável do grupo tem componente tipado com o mesmo nome (sem '?') na tupla do "
   "seu lado (subject_value_type/object_value_type): grupo transporta valor, então tem tipo e grandeza.", ["F3", "N4"])
_r("ARB-G-EXEC", "A3", "grupo", U, "Grupo exige testes executáveis {input: {?var_sujeito: v}, expected: {?var_objeto: v}}; "
   "sem teste, UNPROVEN; teste que falha ou cita variável do lado errado, REFUTED.", ["F3"])
_r("ARB-G-CONSIST", "A1", "grupo", R, "C09-GROUP: o mesmo bo_group_id tem a mesma definição em toda linha, e a coluna "
   "bo_group_id é a do grupo.", ["F3"])
# ---- projeções e ocorrências (A1, A5) ---------------------------------------------------------------------
_r("ARB-PROJ-PART", "A5", "projeção", R, "Alegação com várias projeções do mesmo campo diz qual parte transporta (a "
   "projeção cujo concept é o conceito da alegação); senão a parte transportada é indefinida.", ["F3"])
_r("ARB-PROJ-DECL", "A5", "projeção", R, "Campo usado para dois ou mais conceitos do glossário: cada uso declara a sua "
   "projeção; uso sem projeção junto de outro conceito é sobreposição não declarada.", ["F3"])
_r("ARB-OCC-ID", "A1", "projeção", R, "Campo sabidamente em bloco repetido (C01 ou outra projeção com scope=block) só é "
   "usado com a ocorrência identificada por campos-chave (projeção scope=block), nunca pela posição nem implícita.", ["F3"])
# ---- âncoras (F4) ----------------------------------------------------------------------------------------
_r("ARB-ANCHOR", "A3", "âncora", U, "Âncora é alegação auditada do C20: resolvida pela versão corrente e pela auditoria "
   "(não pelo estado que o mapeador declarou). Sem glossário auditado, âncora não encontrada ou abaixo de "
   "DOC_SUPPORTED: UNPROVEN. Âncora de outro átomo ou outro conceito: REFUTED.", ["F4"])
_r("ARB-RELATED-EV", "A3", "âncora", U, "related não transporta, mas continua sendo alegação de alinhamento: sem "
   "DOC_SUPPORTED (ou observação) com citação, é hipótese (UNPROVEN), não OK.", ["F4"])
_r("ARB-SEM-FLOOR", "A3", "alegação", "UNPROVEN|REFUTED_BY_RULE", "Piso semântico: o veredito do árbitro nunca é mais "
   "permissivo que o da semântica congelada (bo.semantics.obligations.assess) na mesma forma da alegação; cálculo "
   "próprio do árbitro (domínio pelo registro, K4, conjunto) só acrescenta falha, nunca tira (E3 do PILOT-EXIT 2/2).",
   ["F2", "R1-M6"])
# ---- ausência tipada (C09-NONE, C09 3.2.0; CC-7 do PILOT-STO-MAP) ----------------------------------------
_r("ARB-ABSENCE-WF", "A1", "ausência", R, "Ausência tipada bem formada: campo absence; sssom:NoTermFound no lado oposto "
   "ao de absence.side (padrão subject); skos:relatedMatch/related, fidelidade none, sem translation_fn.", ["F3"])
_r("ARB-ABSENCE-KIND", "A3", "ausência", U, "Ausência UNRESOLVED (a busca não decidiu) é hipótese, não ausência provada.", ["F4"])
_r("ARB-ABSENCE-EV", "A3", "ausência", U, "Ausência ABSENCE_DEMONSTRATED, OUT_OF_PIN ou UNSUPPORTED_BY_TRANSLATOR exige "
   "evidência citada (fonte e sentença) em absence.evidence ou proof.evidence. Ausência não é related: não passa "
   "pela ARB-RELATED-EV nem entra nas regras de conjunto, no K4 ou na contagem das alegações.", ["F4"])
# ---- conflitos de conjunto (CONTESTED) e realizações (AMBIGUOUS) ------------------------------------------
_r("ARB-ATOM-TYPE", "A2", "conjunto", C, "O mesmo átomo (ou parte projetada) tem um só tipo: assinatura (datatype, "
   "grandeza, unidade, janela, byte) e domínio (enum, faixa, passo, sentinelas) iguais em toda alegação cujas guardas "
   "daquele lado podem valer juntas.", ["F2", "N4"])
_r("ARB-PAIR-REL", "A4", "conjunto", C, "Mesmo par com relações de conjunto incompatíveis sob guardas compatíveis "
   "(broad e narrow estritos no mesmo sentido); exact×broad/narrow/related é a SKOS-DISJ.", ["F2"])
_r("ARB-PAIR-VALUE", "A4", "conjunto", C, "Mesmo par, guardas compatíveis, as duas OK: o mesmo valor de entrada não pode "
   "sair diferente nas duas quando ambas transportam sem perda.", ["F2"])
_r("ARB-K4-REL", "A4", "composição", C, "Composto pela tabela formal (cadeia de alegações OK no K4) e alegação direta "
   "do mesmo par com relação de conjunto incompatível (exact×broad/narrow/related, broad×narrow) sob guardas "
   "compatíveis: o ciclo é inconsistente; todas as alegações do ciclo ficam CONTESTED.", ["F2", "R1-M6"])
_r("ARB-K4-VDR", "A4", "composição", C, "A relação de domínios da alegação direta está fora das possíveis do composto "
   "(composição RCC5 ou relação calculada do composto).", ["F2"])
_r("ARB-K4-VALUE", "A4", "composição", C, "Composto e alegação direta transportam o mesmo valor, sem perda nas duas, para "
   "valores diferentes: o ciclo é inconsistente.", ["F2"])
_r("ARB-ALT-MUTUAL", "A5", "realização", R, "C09-ALT: alternative_to é mútuo, aponta para alegação existente e do mesmo "
   "subject_id.", ["F3"])
_r("ARB-REAL-MULTI", "A5", "realização", A, "Realizações múltiplas do mesmo alvo: o mesmo átomo (ou parte, na mesma "
   "ocorrência) realiza a MESMA propriedade (conceito do outro lado; sem ele, o deste) num mesmo provedor do outro "
   "lado por alegações distintas que transportam. Exclusividade só com interseção das guardas UNSAT (A-EXCL); "
   "senão AMBIGUOUS. Exclusividade declarada sem prova é REFUTED (A-EXCL). Partes, ocorrências ou conceitos "
   "distintos não competem (1:N legítimo).", ["F3"])

# regras do SEMANTICS que o árbitro aplica em nível de conjunto (as de alegação vêm do assess)
SET_RULES_FROM_SEM = ("SKOS-DISJ", "A-EXCL", "P-OVERLAP", "P-OCC", "P-EXEC", "G-VARS", "G-ARITY", "G-OCC")


# Id de regra do C21: '^[A-Z][A-Z0-9]*(-[A-Z0-9]+)+$' (C00 rule_id). Duas regras do SEMANTICS têm id de uma
# palavra e não casam; o árbitro não muda o SEMANTICS (não é dono): publica com o id conforme abaixo e aceita o
# antigo como alias (em 'disabled', na leitura de vereditos antigos e no RULES.html). Motivo: CC-2 do
# PILOT-STO-MAP (04/11/2026); a semântica da regra não muda.
RULE_ID_PATTERN = r"^[A-Z][A-Z0-9]*(-[A-Z0-9]+)+$"
RULE_ALIASES = {"EVIDENCE": "EVIDENCE-DOC", "SENTINEL": "SENTINEL-MAP"}     # id do SEMANTICS -> id publicado
ALIAS_OF = {v: k for k, v in RULE_ALIASES.items()}                           # id publicado -> id do SEMANTICS


def published_id(rid: str) -> str:
    return RULE_ALIASES.get(rid, rid)


def semantics_ids(disabled) -> frozenset:
    """'disabled' aceita o id publicado e o antigo; o SEMANTICS só conhece o antigo."""
    out = set(disabled)
    for rid in list(out):
        if rid in ALIAS_OF:
            out.add(ALIAS_OF[rid])
        if rid in RULE_ALIASES:
            out.add(RULE_ALIASES[rid])
    return frozenset(out)


def all_rules() -> dict[str, dict]:
    out = {}
    for rid, r in SEM_RULES.items():
        pid = published_id(rid)
        out[pid] = {**r, "rule_id": pid, "source": "bo.semantics.rules",
                    **({"alias_of": rid} if pid != rid else {})}
    for rid, r in ARB_RULES.items():
        out[rid] = {**r, "source": "bo.arbiter.rules"}
    return out


def rule_known(rid: str) -> bool:
    return rid in SEM_RULES or rid in ARB_RULES


def verdict_of(outcomes) -> str:
    """Maior precedência entre as saídas das falhas; outcomes que não são veredito (ex. EMPTY) não contam."""
    outs = set(outcomes)
    for v in PRECEDENCE[:-1]:
        if v in outs:
            return v
    return "OK"
