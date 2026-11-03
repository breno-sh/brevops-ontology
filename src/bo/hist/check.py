"""Despachante COORD: bo.hist.check -> bo.<pacote do módulo-alvo>.check (ver bo._dispatch)."""
import sys
from bo._dispatch import run

if __name__ == "__main__":
    sys.exit(run("check", sys.argv[1:]))
