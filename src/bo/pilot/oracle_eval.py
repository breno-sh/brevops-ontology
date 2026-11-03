"""Despachante COORD: bo.pilot.oracle_eval -> bo.<pacote do módulo-alvo>.oracle_eval (ver bo._dispatch)."""
import sys
from bo._dispatch import run

if __name__ == "__main__":
    sys.exit(run("oracle_eval", sys.argv[1:]))
