"""Despachante COORD: bo.baselines.adapt.no_borrow -> bo.<pacote do módulo-alvo>.no_borrow (ver bo._dispatch)."""
import sys
from bo._dispatch import run

if __name__ == "__main__":
    sys.exit(run("no_borrow", sys.argv[1:]))
