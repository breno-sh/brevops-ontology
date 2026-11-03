"""Despachante COORD: bo.proof.controls -> bo.<pacote do módulo-alvo>.controls (ver bo._dispatch)."""
import sys
from bo._dispatch import run

if __name__ == "__main__":
    sys.exit(run("controls", sys.argv[1:]))
