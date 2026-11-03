"""Despachante COORD: bo.lower.no_silent_insert -> bo.<pacote do módulo-alvo>.no_silent_insert (ver bo._dispatch)."""
import sys
from bo._dispatch import run

if __name__ == "__main__":
    sys.exit(run("no_silent_insert", sys.argv[1:]))
