"""Despachante COORD: bo.baselines.kalinin.family_run -> bo.<pacote do módulo-alvo>.family_run (ver bo._dispatch)."""
import sys
from bo._dispatch import run

if __name__ == "__main__":
    sys.exit(run("family_run", sys.argv[1:]))
