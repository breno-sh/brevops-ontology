"""PILOT-STO-MAP: mapeamento da fatia sto nos 6 pares (C09) e vereditos do árbitro (C21).

common     caminhos, hora (America/Recife), leitura do pacote do glossarista com conferência do MANIFEST
decisions  as decisões do mapeador (o juízo), por átomo e par, com o porquê de cada uma
build      pacote + decisões -> linhas C09 (tipos do C05, sentenças publicadas do pacote, ausências tipadas)
pipeline   um comando: build -> validador C09 -> ida e volta SKOS -> árbitro -> relatório (em .staging);
           --promote troca para o definitivo, só com a trava merge-base deste módulo
"""
