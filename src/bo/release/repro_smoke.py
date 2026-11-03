"""Despachante COORD: bo.release.repro_smoke -> bo.<pacote do módulo-alvo>.repro_smoke (ver bo._dispatch)."""
import sys
from bo._dispatch import run

if __name__ == "__main__":
    sys.exit(run("repro_smoke", sys.argv[1:]))
