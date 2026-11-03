"""Despachante COORD: bo.pilot.oracle_coverage -> bo.<pacote do módulo-alvo>.oracle_coverage (ver bo._dispatch)."""
import sys
from bo._dispatch import run

if __name__ == "__main__":
    sys.exit(run("oracle_coverage", sys.argv[1:]))
