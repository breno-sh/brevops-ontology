"""Despachante COORD: bo.docs.coverage -> bo.<pacote do módulo-alvo>.coverage (ver bo._dispatch)."""
import sys
from bo._dispatch import run

if __name__ == "__main__":
    sys.exit(run("coverage", sys.argv[1:]))
