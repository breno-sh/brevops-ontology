"""Despachante COORD: bo.dispute.frame -> bo.<pacote do módulo-alvo>.frame (ver bo._dispatch)."""
import sys
from bo._dispatch import run

if __name__ == "__main__":
    sys.exit(run("frame", sys.argv[1:]))
