"""Despachante COORD: bo.bench.kalinin_family -> bo.<pacote do módulo-alvo>.kalinin_family (ver bo._dispatch)."""
import sys
from bo._dispatch import run

if __name__ == "__main__":
    sys.exit(run("kalinin_family", sys.argv[1:]))
