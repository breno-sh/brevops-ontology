"""PREREG: pré-registro v3 do BrevOps Ontology (estimandos, unidades, contrastes, poder, pilotos e congelamentos).

O conteúdo normativo é escrito em src/bo/prereg/content.py (dados Python, sem lógica) e materializado por
`python -I -m bo.prereg.build` em $BO_REPO/prereg/ (PREREG.html, metrics_spec.yaml, probe_types.yaml,
h2h_fairness.yaml, pilot_exit.yaml, SEEDS.txt) e, via prereg/power.py, em prereg/power.json. A geração é
determinística: `build --check` prova que os arquivos gravados são exatamente os que o conteúdo produz.

Gates do módulo: bo.prereg.estimands (cada métrica declara população, direção, unidade, denominador e
tratamento do desconhecido), bo.prereg.no_oldterm (o termo antigo da v2 só na nota de renomeação),
bo.prereg.pilot_exit (estrutura de prereg/pilot_exit.yaml) e bo.prereg.seeds (derivação das sementes).
"""

MODULE = "PREREG"
