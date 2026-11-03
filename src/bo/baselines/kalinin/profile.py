"""Despachante COORD: bo.baselines.kalinin.profile -> bo.<pacote do módulo-alvo>.profile (ver bo._dispatch)."""
import sys
from bo._dispatch import run

if __name__ == "__main__":
    sys.exit(run("profile", sys.argv[1:]))
