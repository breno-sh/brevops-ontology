"""REQUIREMENTS: requisitos, compromissos semânticos e CQs em vocabulário independente (contrato C24 1.0.0).

O conteúdo é escrito em src/bo/requirements/content/ (dados Python, sem lógica) e materializado por
`python -I -m bo.requirements.build` em $BO_REPO/requirements/{requirements,commitments,cq_spec}.jsonl,
REQUIREMENTS.html e REQUIREMENTS.sha256. A geração é determinística: `build --check` prova que os
arquivos gravados são exatamente os que o conteúdo produz.
"""

CONTRACT = "C24"
CONTRACT_VERSION = "1.0.0"
