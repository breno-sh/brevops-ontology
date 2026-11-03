"""Harness do Google Cloud (HARNESS-GCP), offline nesta fase.

render            plano de lowering (C26) -> HCL, sem inserir nada que o plano não declare (UNKNOWN_INPUT se falta)
no_silent_insert  prova, com um parser independente (python-hcl2), que HCL = plano + valores sintetizados declarados
schema_index      índice compacto do schema do provider google fixado (universe/pins.json) para os tipos do harness
redact            redator na origem: nada sensível sai da memória; withheld nunca tem valor nem hash (C12)
readback          leitura de volta (C12 readback) e desfecho de persistência (união do C00) com os comparadores do C11
executor          apply -> espera -> leitura -> destroy, com identidade, intenção e redator antes de qualquer gravação;
                  aqui só roda com respostas gravadas (RecordedRunner); o runner do Terraform recusa nuvem sem a
                  autorização explícita do lote
"""
