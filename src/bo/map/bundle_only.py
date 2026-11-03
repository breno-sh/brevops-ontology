"""Despachante COORD: bo.map.bundle_only -> bo.<pacote do módulo-alvo>.bundle_only (ver bo._dispatch)."""
import sys
from bo._dispatch import run

if __name__ == "__main__":
    sys.exit(run("bundle_only", sys.argv[1:]))
