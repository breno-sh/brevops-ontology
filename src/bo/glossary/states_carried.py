"""Despachante COORD: bo.glossary.states_carried -> bo.<pacote do módulo-alvo>.states_carried (ver bo._dispatch)."""
import sys
from bo._dispatch import run

if __name__ == "__main__":
    sys.exit(run("states_carried", sys.argv[1:]))
