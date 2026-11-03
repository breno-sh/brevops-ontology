"""bo.arbiter: árbitro mecânico v3 (módulo ARBITERLIB, contrato de saída C21).

Código, sem LLM e sem voto. Lê alegações C09 (SSSOM TSV ou JSONL) e, opcionalmente, o glossário auditado
(C20) e os átomos (C01); devolve um veredito por alegação: OK, REFUTED_BY_RULE, UNPROVEN, CONTESTED ou
AMBIGUOUS, com as regras que decidiram, a composição usada e o sha do árbitro congelado.

Camadas (todas reaproveitam a implementação de referência do SEMANTICS e o registro fechado do TRANSFORMS):
  claimcheck  obrigações por alegação: bo.semantics.obligations.assess + adaptação de grupo, projeção,
              registro do TRANSFORMS, âncoras auditadas (F4) e esquema C09            (A1, A2, A3)
  setcheck    regras de conjunto: SKOS-DISJ, tipo do mesmo átomo, mesmo par, projeções sobrepostas entre
              alegações, ocorrência identificada, realizações múltiplas, consistência de grupo, alternativas (A1, A5)
  k4          composição no K4 pela tabela formal (bo.semantics.composition.closure) e conflito de ciclo
              entre composto e alegação direta                                          (A4)
  engine      junta tudo; precedência REFUTED_BY_RULE > CONTESTED > UNPROVEN > AMBIGUOUS > OK
Gates: run, unproven, no_llm, permutation, determinism; build gera arbiter/RULES.html e arbiter/ARBITER.sha256.
"""
