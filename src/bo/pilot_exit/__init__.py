"""PILOT-EXIT: o avaliador roda o código congelado dos pilotos nas fixtures retidas e aplica E1–E8 (§3b).

Comandos (via despachantes de família, com BO_ID=PILOT-EXIT):
  bo.pilot.heldout_run --slices sto,net   -> bo.pilot_exit.heldout_run
  bo.pilot.exit_check --criteria ARQ      -> bo.pilot_exit.exit_check
  bo.plan.reestimate --from DIR           -> bo.pilot_exit.reestimate
O pacote não conserta nem ajusta o código avaliado: só o executa congelado e conta.
"""
