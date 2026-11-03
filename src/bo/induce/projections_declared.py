"""Despachante COORD: bo.induce.projections_declared -> bo.<pacote do módulo-alvo>.projections_declared (ver bo._dispatch)."""
import sys
from bo._dispatch import run

if __name__ == "__main__":
    sys.exit(run("projections_declared", sys.argv[1:]))
