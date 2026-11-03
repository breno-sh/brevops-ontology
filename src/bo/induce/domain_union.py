"""Despachante COORD: bo.induce.domain_union -> bo.<pacote do módulo-alvo>.domain_union (ver bo._dispatch)."""
import sys
from bo._dispatch import run

if __name__ == "__main__":
    sys.exit(run("domain_union", sys.argv[1:]))
