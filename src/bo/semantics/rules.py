"""Catálogo das regras executáveis (id -> família, saída quando falha, texto). Fonte única do HTML e do
gate de contraexemplos: toda regra daqui tem de ter contraexemplo rejeitado e controle aceito."""

from __future__ import annotations

R = "REFUTED_BY_RULE"
U = "UNPROVEN"

RULES: dict[str, dict] = {}


def _r(rid, family, on_fail, text, answers):
    RULES[rid] = {"rule_id": rid, "family": family, "on_fail": on_fail, "text": text, "answers": answers}


# ---- alegação: campos, direção SKOS, tipos ------------------------------------------------------------------
_r("SKOS-PRED", "alegação", R, "semantic_relation e predicate_id dizem a mesma coisa (exact=exactMatch, close=closeMatch, "
   "broad=broadMatch, narrow=narrowMatch, related=relatedMatch).", ["F2"])
_r("SKOS-ORIENT", "alegação", R, "Direção SKOS: em 'a broadMatch b' o subconjunto é o sujeito (a ⊂ b, b é o mais amplo); "
   "em 'a narrowMatch b', o objeto. O predicado de pertença declara o lado subconjunto e tem de bater.", ["F2", "R1-M6"])
_r("SKOS-DISJ", "conjunto", "CONTESTED", "exactMatch é disjunta de broadMatch e relatedMatch (SKOS Reference): o mesmo par "
   "com as duas, sob guardas compatíveis, é CONTESTED.", ["F2"])
_r("TYPE-WF", "alegação", R, "Tipo de valor bem formado: datatype conhecido, unidade da grandeza declarada, faixa não vazia, "
   "convenção de byte coerente com a unidade, tupla com componentes tipados.", ["N4"])
_r("KIND-UNKNOWN", "alegação", U, "Grandeza ou unidade UNKNOWN (ou tipo não declarado) em qualquer lado: unknown==unknown não "
   "é prova; UNKNOWN ≠ NOT_APPLICABLE.", ["F2", "N4"])
_r("KIND-EQ", "alegação", R, "Transformação escalar não muda a grandeza (kind_in = kind_out); só vale para escalar.", ["N4"])
_r("KIND-TUPLE", "alegação", R, "Combinador de tupla exige lado com tipo estruturado e a saída tem de respeitar o tipo de "
   "cada componente; não compara a grandeza do todo com a das partes.", ["N4", "F3"])
_r("UNIT-WINDOW", "alegação", R, "A janela de taxa é parte do tipo: por minuto e por segundo só se igualam com conversão de janela.", ["N4"])
_r("UNIT-BYTES", "alegação", R, "A convenção de byte é parte do tipo: GiB (IEC) e GB (SI) só se igualam com o fator exato.", ["N4"])
_r("NORM-PRESERVE", "alegação", R, "A normalização declarada preserva o valor canônico da grandeza nos testes (antes das perdas).", ["F2"])
_r("EXACT-NORM", "alegação", U, "Toda relação que transporta declara a função de tradução (normalização explícita), "
   "do núcleo fechado; sem ela, UNPROVEN.", ["F2"])
_r("EXACT-TESTS", "alegação", R, "A normalização tem testes executáveis e passa neles; sem testes, UNPROVEN; teste que falha, "
   "REFUTED.", ["F2"])
_r("VDR-COMPUTED", "alegação", R, "value_domain_relation (orientação sujeito→objeto) igual à calculada dos domínios declarados, "
   "pela imagem da tradução.", ["F2"])
_r("VDR-UNKNOWN", "alegação", U, "Sem perda exige domínios que o provem; com relação de domínio indeterminada, UNPROVEN.", ["F2"])
_r("FID-COHERENT", "alegação", R, "transport_fidelity coerente: sem perda só com domínio igual ou subconjunto e sem item de "
   "perda; disjunto = nenhuma; perda declarada exige item no contrato; narrow na ida não é sem perda.", ["F2"])
_r("CLOSE-LOSS", "alegação", R, "close declara o que se perde e nunca é sem perda (conversão exata é exact).", ["F2"])
_r("BN-PRED", "alegação", U, "broad/narrow exigem predicado de pertença EXECUTÁVEL (linguagem fechada) com testes de membro e "
   "de não membro; texto livre não é predicado.", ["F2"])
_r("BN-PRED-TESTS", "alegação", R, "O predicado acerta os testes e, com domínios finitos, coincide com a pertença à imagem do "
   "lado mais estreito em todo valor do lado mais amplo.", ["F2"])
_r("RELATED-NT", "alegação", R, "related não habilita transporte: fidelidade nenhuma e sem função de tradução.", ["F2"])
_r("FIXED-DATED", "alegação", U, "FIXED/DEFAULT (destino sem atributo) exigem valor, contexto tipado e evidência datada com fonte.", ["F2"])
_r("EVIDENCE", "alegação", U, "Transporte na leitura primária exige DOC_SUPPORTED (ou observação sob protocolo) com citação; "
   "a leitura de volta (PERSISTENCE_VERIFIED) não promove significado.", ["F2", "F4"])
_r("ANCHOR-NOT-PROOF", "alegação", U, "Mesmo conceito no glossário não prova: alegação baseada em âncoras exige as duas âncoras "
   "com DOC_SUPPORTED (átomo→conceito←átomo já é mapeamento).", ["F4"])
_r("GUARD-TYPE", "alegação", R, "Guarda na gramática tipada: só eq, in, present, refers_to_kind, region_in, edition_in, "
   "version_range; termos com papel; termos vizinhos com tipo declarado.", ["F2"])
_r("GUARD-SAT", "alegação", R, "A guarda da alegação é satisfazível (UNSAT = alegação vazia, REFUTED); indecidida = UNPROVEN.", ["F2"])
_r("CTX-DEP", "alegação", R, "Se a tradução depende de edição, região ou versão, esses termos estão na guarda.", ["F2"])
_r("SENTINEL", "alegação", R, "Toda sentinela da origem (ex. 0 = nunca expira) tem mapeamento declarado; aritmética sobre "
   "sentinela muda o significado.", ["F2"])
# ---- transporte ---------------------------------------------------------------------------------------------
_r("T-RELATED", "transporte", "RELATED_ONLY", "Transporte por related é bloqueado (CMT-LOSS-N02).", ["F2"])
_r("T-UNPROVEN", "transporte", "UNPROVEN", "Alegação UNPROVEN ou REFUTED não transporta (CMT-LOSS-U02).", ["F2"])
_r("T-GUARD", "transporte", "CONDITION_FALSE|CONDITION_INDETERMINATE", "Guarda falsa bloqueia; termo não lido deixa a guarda "
   "indeterminada e o caso vai para o intervalo entre os limites, nunca para 'atravessou'.", ["F2"])
_r("T-ABSENCE", "transporte", "UNKNOWN_INPUT", "Obrigatório no destino sem valor na origem: bloqueia; nenhum padrão "
   "inventado (CMT-LOSS-N01).", ["F2"])
_r("T-SYMBOLIC", "transporte", "UNKNOWN_SYMBOLIC_INPUT", "Valor simbólico não resolvido não é transportado como valor.", ["F2"])
_r("T-DOMAIN", "transporte", "TRANSFORM_OUT_OF_DOMAIN", "Fora do domínio da função parcial (ex. mês -> segundos sem "
   "contexto de calendário, CMT-LOSS-U01): bloqueia.", ["F2", "N4"])
_r("T-SATURATION", "transporte", "declared_loss", "Acima do máximo do destino: satura com perda declarada, nunca sem perda "
   "(CMT-LOSS-P01); sem saturação declarada, bloqueia.", ["F2"])
_r("T-ROUNDING", "transporte", "declared_loss", "Valor não representável no passo do destino: arredonda com perda declarada; "
   "sem arredondamento declarado, bloqueia.", ["F2"])
_r("T-SUBSET", "transporte", "OUT_OF_SUBSET", "Em direção ao lado mais estreito só passa valor com pertença verdadeira; o "
   "resto (e o não exprimível) é OUT_OF_SUBSET.", ["F2"])
_r("T-SENTINEL", "transporte", "TRANSFORM_OUT_OF_DOMAIN", "Sentinela vai pela tabela declarada; sem equivalente, perda "
   "declarada e nada emitido.", ["F2"])
_r("T-FIXED", "transporte", "OUT_OF_SUBSET", "Destino com comportamento fixo/padrão: transporta só se o valor coincide.", ["F2"])
_r("T-INVERSE", "transporte", "UNPROVEN", "A direção contrária só transporta com inversa parcial da tradução.", ["F2"])
# ---- composição ---------------------------------------------------------------------------------------------
_r("K-JOIN", "composição", "NOT_COMPOSABLE", "Só se compõe pelo mesmo nó (objeto de m1 = sujeito de m2).", ["F2"])
_r("K-LEGS", "composição", "UNPROVEN", "As duas pernas OK; composição nunca promove (perna UNPROVEN dá UNPROVEN).", ["F2"])
_r("K-TABLE", "composição", "UNPROVEN", "Relação do composto só pela tabela formal: close∘close não vira exact (nem close), "
   "broad∘narrow e related∘related não dão relação.", ["F2"])
_r("K-GUARD-EMPTY", "composição", "EMPTY", "Guardas incompatíveis (interseção UNSAT) dão composição vazia.", ["F2"])
_r("K-GUARD-UNKNOWN", "composição", "UNPROVEN", "Interseção de guardas indecidida dá UNPROVEN.", ["F2"])
_r("K-DOMAIN", "composição", "UNPROVEN", "Domínio incompatível no nó do meio (tipo diferente ou desconhecido, ou imagem da ida "
   "fora do domínio da volta) dá UNPROVEN.", ["F2", "N4"])
_r("K-VDR", "composição", "UNPROVEN", "Relação de domínio do composto dentro da composição RCC5 calculada.", ["F2"])
_r("K-FIDELITY", "composição", "pior perna", "Fidelidade do composto é a pior das pernas, nunca melhor.", ["F2"])
_r("K-HUB", "composição", "UNPROVEN", "átomo→conceito←átomo é composição âncora_a ∘ inversa(âncora_b) e herda as obrigações das "
   "âncoras (F4).", ["F4", "F2"])
# ---- projeções, alternativas, grupos ------------------------------------------------------------------------
_r("P-OCC", "projeção", R, "Campo em bloco repetido exige chave de ocorrência por campos de identidade, nunca pela posição.", ["F3"])
_r("P-EXEC", "projeção", R, "O extrator da projeção roda nos testes e a saída respeita o tipo declarado.", ["F3"])
_r("P-OVERLAP", "projeção", R, "Projeções do mesmo campo e ocorrência que leem a mesma parte declaram a sobreposição; "
   "partes distintas não precisam (a injetividade saiu).", ["F3"])
_r("A-EXCL", "realização", "AMBIGUOUS", "Várias realizações do mesmo alvo: exclusividade só com guardas de interseção UNSAT; "
   "senão AMBIGUOUS; exclusividade declarada sem prova é REFUTED.", ["F3"])
_r("G-VARS", "grupo", R, "Grupo = regra sobre subgrafo: variáveis nomeadas, únicas e ligadas; argumentos nomeados; ocorrências "
   "declaradas; nenhuma variável solta.", ["F3"])
_r("G-ARITY", "grupo", R, "Argumentos do combinador = assinatura dele; cardinalidade declarada (1:1, 1:N, N:1, N:M) = contagem.", ["F3"])
_r("G-OCC", "grupo", R, "Entradas de um passo vêm da mesma ocorrência ou de ocorrências ligadas por junção declarada (inclusive "
   "cruzando facetas).", ["F3"])


def family_of(rid: str) -> str:
    return RULES[rid]["family"]
