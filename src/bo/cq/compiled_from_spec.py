"""Despachante COORD: bo.cq.compiled_from_spec -> bo.<pacote do módulo-alvo>.compiled_from_spec (ver bo._dispatch)."""
import sys
from bo._dispatch import run

if __name__ == "__main__":
    sys.exit(run("compiled_from_spec", sys.argv[1:]))
