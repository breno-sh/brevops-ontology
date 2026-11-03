"""Despachante COORD: bo.map.exhaustive -> bo.<pacote do módulo-alvo>.exhaustive (ver bo._dispatch)."""
import sys
from bo._dispatch import run

if __name__ == "__main__":
    sys.exit(run("exhaustive", sys.argv[1:]))
