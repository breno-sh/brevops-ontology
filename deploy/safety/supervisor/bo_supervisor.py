#!/usr/bin/env python3
"""Entrada do supervisor independente com heartbeat (D16), para a VM do Breno. Lógica: src/bo/safety/supervisor.py.

Na VM, o pacote fica ao lado deste arquivo (src/bo/safety, copiado pelo bundle.sh); no repositório, usa ../../../src.
  bo_supervisor.py ssh-entry        forced command do authorized_keys (lê SSH_ORIGINAL_COMMAND)
  bo_supervisor.py tick             timer do systemd: destrói execução com heartbeat parado ou prazo vencido
  bo_supervisor.py status --run R
Só biblioteca padrão. Credenciais da VM: só as contas sandbox (identity.check confere contra a allowlist da VM).
"""
import sys
from pathlib import Path

here = Path(__file__).resolve().parent
for cand in (here / "src", here.parents[2] / "src"):
    if (cand / "bo" / "safety").is_dir():
        sys.path.insert(0, str(cand))
        break

from bo.safety.supervisor import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
