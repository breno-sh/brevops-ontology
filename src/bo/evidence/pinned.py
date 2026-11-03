"""Despachante COORD: bo.evidence.pinned -> bo.<pacote do módulo-alvo>.pinned (ver bo._dispatch)."""
import sys
from bo._dispatch import run

if __name__ == "__main__":
    sys.exit(run("pinned", sys.argv[1:]))
