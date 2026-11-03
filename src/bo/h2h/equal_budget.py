"""Despachante COORD: bo.h2h.equal_budget -> bo.<pacote do módulo-alvo>.equal_budget (ver bo._dispatch)."""
import sys
from bo._dispatch import run

if __name__ == "__main__":
    sys.exit(run("equal_budget", sys.argv[1:]))
