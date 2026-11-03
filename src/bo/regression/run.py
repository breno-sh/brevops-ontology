"""Despachante COORD: bo.regression.run -> bo.<pacote do módulo-alvo>.run (ver bo._dispatch)."""
import sys
from bo._dispatch import run

if __name__ == "__main__":
    sys.exit(run("run", sys.argv[1:]))
