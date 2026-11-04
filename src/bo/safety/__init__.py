"""SAFETY: kit de segurança de nuvem (§10.2 do plano, S16 do GPT-6). Nada aqui fala com nuvem nesta fase.

Pacotes (todos só com a biblioteca padrão, salvo skus/build/plan_check, que usam PyYAML):
  common        caminhos, relógio America/Recife, sha256, gravação atômica com fsync, nome sintético
  redaction     redator de state/plan/readback (antes da 1ª serialização) e porta única de gravação
  ephemeral     canal privado efêmero: disco de RAM cifrado (macOS) ou tmpfs sem swap (Linux), apagado no fim
  identity      identidade efetiva lida da sessão e conferida contra a allowlist privada (~/.config/bo/allowlist)
  skus          tabela de tipos e SKUs (allowlist_skus.yaml) com tag/TTL do SERVICE-EVIDENCE e custo por tipo
  plan_check    checador de plano (tipo, SKU, tag, TTL, custo com armazenamento/tráfego/requisições, backend)
  manifest      manifesto de intenção C16 (intenção ANTES da criação), cópia pública redigida, reconciliação
  ownership     filtro de propriedade e limpeza sob a trava cleanup-global (nunca por diferença de baseline)
  locks         travas mkdir compatíveis com tools/lock.sh
  providers     comandos de leitura, varredura e remoção por provedor (regiões lidas da conta)
  sweep         varredura de todas as regiões e tipos; compara com EXPECTED_RESIDUE.json
  teardown      teardown por manifesto e por tag, com estados de remoção
  supervisor    lógica do supervisor independente com heartbeat (roda na VM, D16)
  runner        sequência segura de um lote (preflight -> intenção -> apply -> confirmação -> remoção)
  fakecloud     nuvem simulada em arquivo, para as injeções de falha e os testes
  sim_runner    runner simulado que pode ser morto (SIGKILL) em qualquer etapa
  failure_injection, no_baseline_delete, intent_reconciled   gates
  build         gera allowlist_skus.yaml, EXPECTED_RESIDUE.json e relatórios; --check compara byte a byte
"""
