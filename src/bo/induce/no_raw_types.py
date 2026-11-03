"""Despachante COORD: bo.induce.no_raw_types -> bo.<pacote do módulo-alvo>.no_raw_types (ver bo._dispatch)."""
import sys
from bo._dispatch import run

if __name__ == "__main__":
    sys.exit(run("no_raw_types", sys.argv[1:]))
