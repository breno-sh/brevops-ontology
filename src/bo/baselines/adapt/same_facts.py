"""Despachante COORD: bo.baselines.adapt.same_facts -> bo.<pacote do módulo-alvo>.same_facts (ver bo._dispatch)."""
import sys
from bo._dispatch import run

if __name__ == "__main__":
    sys.exit(run("same_facts", sys.argv[1:]))
