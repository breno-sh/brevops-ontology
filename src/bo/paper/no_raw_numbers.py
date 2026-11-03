"""Despachante COORD: bo.paper.no_raw_numbers -> bo.<pacote do módulo-alvo>.no_raw_numbers (ver bo._dispatch)."""
import sys
from bo._dispatch import run

if __name__ == "__main__":
    sys.exit(run("no_raw_numbers", sys.argv[1:]))
