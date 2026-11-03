"""Despachante COORD: bo.glossary.audit_complete -> bo.<pacote do módulo-alvo>.audit_complete (ver bo._dispatch)."""
import sys
from bo._dispatch import run

if __name__ == "__main__":
    sys.exit(run("audit_complete", sys.argv[1:]))
