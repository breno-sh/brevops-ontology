"""Biblioteca de métricas do BrevOps Ontology v3 (módulo METRICSLIB).

Implementa as definições do pré-registro (prereg/metrics_spec.yaml, C15 3.0.0; prereg/PREREG.html):

  policy      classe de cada desfecho (success | failure | bounded) por métrica e combinação de desfechos
  spec        leitura do metrics_spec.yaml, sementes e ligação métrica -> implementação
  units       unidades de análise: campo, decisão (documento de política por declaração normalizada),
              NAME/TAG, grafo e unidade implantável completa; adaptadores dos contratos C06, C11, C12, C22, C23
  core        limites inferior e superior, est, leituras por direção, escada dos cinco eixos, fração complexa,
              leitura combinada cobertura x persistência, Wilson
  resample    bootstrap por cluster (família, repositório, grafo, recurso), conjunto entre métricas;
              IC t com erro robusto por cluster CR2; teste de permutação de rótulos de direção
  models      contrastes pareados, assimetria, logística com efeitos fixos, McNemar exato, Turnbull, Gini,
              taxa de falso NONE
  contrasts   os 15 contrastes pré-registrados e a regra de decisão de cada um
  invariance  testes determinísticos de renomeação, permutação de provedores, embalagem e reordenação
  c15         documentos C15 (result) a partir das leituras

Nada aqui lê dado do estudo; os testes (tests/metrics) rodam sobre os stubs de contracts/stubs/ e sobre dados
sintéticos gerados com semente fixa.
"""

LIB_VERSION = "3.0.0"
