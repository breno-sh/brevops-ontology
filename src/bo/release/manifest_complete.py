"""Despachante COORD: bo.release.manifest_complete -> bo.<pacote do módulo-alvo>.manifest_complete (ver bo._dispatch)."""
import sys
from bo._dispatch import run

if __name__ == "__main__":
    sys.exit(run("manifest_complete", sys.argv[1:]))
