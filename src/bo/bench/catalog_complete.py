"""Despachante COORD: bo.bench.catalog_complete -> bo.<pacote do módulo-alvo>.catalog_complete (ver bo._dispatch)."""
import sys
from bo._dispatch import run

if __name__ == "__main__":
    sys.exit(run("catalog_complete", sys.argv[1:]))
