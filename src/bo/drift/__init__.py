"""DRIFT: eventos de schema entre versões amostradas do provider Terraform (C13 events + atom_history).

Estimando declarado: a superfície do plugin (saída de `terraform providers schema -json` guardada pelos HIST-*),
nunca a nuvem. Cada evento sai com o intervalo de versão (after, until] em que pode ter acontecido; versão
faltante é lacuna declarada e o intervalo a abrange, sem interpolação.

  python -I -m bo.drift.build [--out DIR]   gera events.jsonl, atom_history.jsonl, rename_candidates.jsonl e
                                            churn.json (padrão: $BO_DATA/DRIFT/.staging)
  python -I -m bo.drift.promote             troca .staging pelas saídas finais (só com a trava merge-base do DRIFT)
  python -I -m bo.drift.regen_check         refaz tudo em $BO_TMP e confere byte a byte com o MANIFEST
"""
