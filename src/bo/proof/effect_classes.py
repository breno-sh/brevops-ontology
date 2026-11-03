"""Despachante COORD: bo.proof.effect_classes -> bo.<pacote do módulo-alvo>.effect_classes (ver bo._dispatch)."""
import sys
from bo._dispatch import run

if __name__ == "__main__":
    sys.exit(run("effect_classes", sys.argv[1:]))
