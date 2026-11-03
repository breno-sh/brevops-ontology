"""Despachante COORD: bo.evidence.levels -> bo.<pacote do módulo-alvo>.levels (ver bo._dispatch)."""
import sys
from bo._dispatch import run

if __name__ == "__main__":
    sys.exit(run("levels", sys.argv[1:]))
