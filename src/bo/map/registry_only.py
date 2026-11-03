"""Despachante COORD: bo.map.registry_only -> bo.<pacote do módulo-alvo>.registry_only (ver bo._dispatch)."""
import sys
from bo._dispatch import run

if __name__ == "__main__":
    sys.exit(run("registry_only", sys.argv[1:]))
