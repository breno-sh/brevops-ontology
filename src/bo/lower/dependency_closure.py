"""Despachante COORD: bo.lower.dependency_closure -> bo.<pacote do módulo-alvo>.dependency_closure (ver bo._dispatch)."""
import sys
from bo._dispatch import run

if __name__ == "__main__":
    sys.exit(run("dependency_closure", sys.argv[1:]))
