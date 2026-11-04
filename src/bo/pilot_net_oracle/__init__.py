"""PILOT-NET-ORACLE: comandos dos gates (oracle_coverage, build, seal) e autoria das fixtures da fatia NET.

O avaliador em si mora em $BO_REPO/pilot/net/oracle/net_oracle (só biblioteca padrão), para o PILOT-NET-E2E
e o PILOT-EXIT o usarem sem depender deste pacote. load_oracle() devolve esse módulo.
"""
import sys
from pathlib import Path


def load_oracle(repo=None):
    import os
    root = Path(repo or os.environ.get("BO_REPO") or Path(__file__).resolve().parents[3])
    p = str(root / "pilot/net/oracle")
    if p not in sys.path:
        sys.path.insert(0, p)
    import net_oracle
    return net_oracle
