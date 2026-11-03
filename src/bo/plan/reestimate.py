"""Despachante COORD: bo.plan.reestimate -> bo.<pacote do módulo-alvo>.reestimate (ver bo._dispatch)."""
import sys
from bo._dispatch import run

if __name__ == "__main__":
    sys.exit(run("reestimate", sys.argv[1:]))
