"""Despachante COORD: bo.glossary.train_only -> bo.<pacote do módulo-alvo>.train_only (ver bo._dispatch)."""
import sys
from bo._dispatch import run

if __name__ == "__main__":
    sys.exit(run("train_only", sys.argv[1:]))
