"""Despachante COORD: bo.baselines.adapt.budget -> bo.<pacote do módulo-alvo>.budget (ver bo._dispatch)."""
import sys
from bo._dispatch import run

if __name__ == "__main__":
    sys.exit(run("budget", sys.argv[1:]))
