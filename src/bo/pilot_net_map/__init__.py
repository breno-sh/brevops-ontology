"""PILOT-NET-MAP: mapeamento da fatia net (regras de filtragem de tráfego) nos 6 pares, papel mapeador.

O mapeador lê só o pacote fechado do glossarista (PILOT-NET-GLOSS/bundle) e as bibliotecas congeladas
(bo.semantics, bo.contracts, bo.arbiter, transforms/). Decide cada correspondência com os três campos, guarda,
tradução do registro, contrato de perda, predicado de pertença e grupo; o árbitro congelado julga.
Estes mapeamentos não entram no estudo principal.

Módulos:
  common     caminhos, hora (America/Recife), pares, prefixos
  bundle     leitura e conferência do pacote (MANIFEST.sha256 ou bundle.json), tipos e evidência por átomo
  decisions  as decisões do mapeador (formas de regra, faixas de alegação, políticas por faixa, ausências)
  generate   gera as linhas C09 a partir do pacote e das decisões (determinístico)
  build      pipeline: gera em .staging, valida (C09, SKOS ida e volta), roda o árbitro, troca sob trava
  verify     conferências do gate do módulo (regeneração idêntica, exaustividade, só pacote, só registro)
"""
