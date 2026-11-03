"""Despachante COORD: bo.cq.src_check -> bo.<pacote do módulo-alvo>.src_check (ver bo._dispatch)."""
import sys
from bo._dispatch import run

if __name__ == "__main__":
    sys.exit(run("src_check", sys.argv[1:]))
