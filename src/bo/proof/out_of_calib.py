"""Despachante COORD: bo.proof.out_of_calib -> bo.<pacote do módulo-alvo>.out_of_calib (ver bo._dispatch)."""
import sys
from bo._dispatch import run

if __name__ == "__main__":
    sys.exit(run("out_of_calib", sys.argv[1:]))
