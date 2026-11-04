"""Comandos do PILOT-NET-E2E (chamados pelos despachantes de família do coordenador: bo.pilot.*, bo.lower.*).

  run              fixtures x 12 direções x 3 controles -> staging; confere mesma entrada, perda e transformações
  oracle_eval      juiz do oráculo: zero perda silenciosa e zero negativo transportado no controle principal
  grain_check      decomposição = gabarito; invariância a reordenação e embalagem
  no_silent_insert HCL relido = plano + inserções declaradas do harness
  tf_validate      terraform validate offline, provider fixado, sandbox sem credenciais
  promote          troca o staging pelo definitivo (só com a trava merge-base)
O código do piloto mora em bo.pilot.net (semente das bibliotecas de escala).
"""
