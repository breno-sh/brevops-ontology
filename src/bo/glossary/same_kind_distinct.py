"""Despachante COORD: bo.glossary.same_kind_distinct -> bo.<pacote do módulo-alvo>.same_kind_distinct (ver bo._dispatch)."""
import sys
from bo._dispatch import run

if __name__ == "__main__":
    sys.exit(run("same_kind_distinct", sys.argv[1:]))
