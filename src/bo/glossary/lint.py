"""Despachante COORD: bo.glossary.lint -> bo.<pacote do módulo-alvo>.lint (ver bo._dispatch)."""
import sys
from bo._dispatch import run

if __name__ == "__main__":
    sys.exit(run("lint", sys.argv[1:]))
