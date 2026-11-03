"""Despachante COORD: bo.tools.regen_check -> bo.<pacote do módulo-alvo>.regen_check (ver bo._dispatch)."""
import sys
from bo._dispatch import run

if __name__ == "__main__":
    sys.exit(run("regen_check", sys.argv[1:]))
