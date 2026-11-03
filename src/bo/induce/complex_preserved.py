"""Despachante COORD: bo.induce.complex_preserved -> bo.<pacote do módulo-alvo>.complex_preserved (ver bo._dispatch)."""
import sys
from bo._dispatch import run

if __name__ == "__main__":
    sys.exit(run("complex_preserved", sys.argv[1:]))
