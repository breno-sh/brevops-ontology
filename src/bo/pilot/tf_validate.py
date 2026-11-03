"""Despachante COORD: bo.pilot.tf_validate -> bo.<pacote do módulo-alvo>.tf_validate (ver bo._dispatch)."""
import sys
from bo._dispatch import run

if __name__ == "__main__":
    sys.exit(run("tf_validate", sys.argv[1:]))
