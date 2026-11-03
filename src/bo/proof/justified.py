"""Despachante COORD: bo.proof.justified -> bo.<pacote do módulo-alvo>.justified (ver bo._dispatch)."""
import sys
from bo._dispatch import run

if __name__ == "__main__":
    sys.exit(run("justified", sys.argv[1:]))
