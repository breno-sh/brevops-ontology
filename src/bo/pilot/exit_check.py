"""Despachante COORD: bo.pilot.exit_check -> bo.<pacote do módulo-alvo>.exit_check (ver bo._dispatch)."""
import sys
from bo._dispatch import run

if __name__ == "__main__":
    sys.exit(run("exit_check", sys.argv[1:]))
