"""Despachante COORD: bo.pilot.heldout_run -> bo.<pacote do módulo-alvo>.heldout_run (ver bo._dispatch)."""
import sys
from bo._dispatch import run

if __name__ == "__main__":
    sys.exit(run("heldout_run", sys.argv[1:]))
