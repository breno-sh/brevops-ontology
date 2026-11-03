"""Despachante COORD: bo.glossary.anchor_claims -> bo.<pacote do módulo-alvo>.anchor_claims (ver bo._dispatch)."""
import sys
from bo._dispatch import run

if __name__ == "__main__":
    sys.exit(run("anchor_claims", sys.argv[1:]))
