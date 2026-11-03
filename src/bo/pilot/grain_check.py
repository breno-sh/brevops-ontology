"""Despachante COORD: bo.pilot.grain_check -> bo.<pacote do módulo-alvo>.grain_check (ver bo._dispatch)."""
import sys
from bo._dispatch import run

if __name__ == "__main__":
    sys.exit(run("grain_check", sys.argv[1:]))
