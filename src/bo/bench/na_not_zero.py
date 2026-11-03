"""Despachante COORD: bo.bench.na_not_zero -> bo.<pacote do módulo-alvo>.na_not_zero (ver bo._dispatch)."""
import sys
from bo._dispatch import run

if __name__ == "__main__":
    sys.exit(run("na_not_zero", sys.argv[1:]))
