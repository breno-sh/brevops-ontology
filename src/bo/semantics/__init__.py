"""bo.semantics: semântica das correspondências (módulo SEMANTICS, contratos C09 e C10).

Uma correspondência é uma RELAÇÃO TIPADA ENTRE CONFIGURAÇÕES, não 'a ~ b':
guarda de contexto (guards), função parcial de tradução (transforms), contrato de perda,
três campos separados (semantic_relation, value_domain_relation, transport_fidelity),
obrigação de prova por tipo (obligations), transporte por direção (transport),
composição por tabela formal (composition), projeções por ocorrência (projections).
A teoria OWL/SKOS (o que se infere: owl_theory) fica separada das regras executáveis
(o que se transporta: transport, composition).
"""
