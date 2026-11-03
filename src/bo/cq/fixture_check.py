"""Despachante COORD: bo.cq.fixture_check -> bo.<pacote do módulo-alvo>.fixture_check (ver bo._dispatch)."""
import sys
from bo._dispatch import run

if __name__ == "__main__":
    sys.exit(run("fixture_check", sys.argv[1:]))
