"""Despachante COORD: bo.glossary.acyclic -> bo.<pacote do módulo-alvo>.acyclic (ver bo._dispatch)."""
import sys
from bo._dispatch import run

if __name__ == "__main__":
    sys.exit(run("acyclic", sys.argv[1:]))
