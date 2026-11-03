"""Despachante COORD: bo.induce.multi_realization -> bo.<pacote do módulo-alvo>.multi_realization (ver bo._dispatch)."""
import sys
from bo._dispatch import run

if __name__ == "__main__":
    sys.exit(run("multi_realization", sys.argv[1:]))
