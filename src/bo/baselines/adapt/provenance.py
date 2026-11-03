"""Despachante COORD: bo.baselines.adapt.provenance -> bo.<pacote do módulo-alvo>.provenance (ver bo._dispatch)."""
import sys
from bo._dispatch import run

if __name__ == "__main__":
    sys.exit(run("provenance", sys.argv[1:]))
