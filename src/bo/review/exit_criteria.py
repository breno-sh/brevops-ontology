"""Despachante COORD: bo.review.exit_criteria -> bo.<pacote do módulo-alvo>.exit_criteria (ver bo._dispatch)."""
import sys
from bo._dispatch import run

if __name__ == "__main__":
    sys.exit(run("exit_criteria", sys.argv[1:]))
