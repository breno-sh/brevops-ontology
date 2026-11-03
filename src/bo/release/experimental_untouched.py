"""Despachante COORD: bo.release.experimental_untouched -> bo.<pacote do módulo-alvo>.experimental_untouched (ver bo._dispatch)."""
import sys
from bo._dispatch import run

if __name__ == "__main__":
    sys.exit(run("experimental_untouched", sys.argv[1:]))
