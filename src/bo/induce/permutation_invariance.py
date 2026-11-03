"""Despachante COORD: bo.induce.permutation_invariance -> bo.<pacote do módulo-alvo>.permutation_invariance (ver bo._dispatch)."""
import sys
from bo._dispatch import run

if __name__ == "__main__":
    sys.exit(run("permutation_invariance", sys.argv[1:]))
