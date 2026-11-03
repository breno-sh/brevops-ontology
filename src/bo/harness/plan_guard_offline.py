"""Despachante COORD: bo.harness.plan_guard_offline -> bo.<pacote do módulo-alvo>.plan_guard_offline (ver bo._dispatch)."""
import sys
from bo._dispatch import run

if __name__ == "__main__":
    sys.exit(run("plan_guard_offline", sys.argv[1:]))
