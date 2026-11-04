"""Comando: python -I -m bo.probes.join_complete (ver bo.probes.checks)."""
import sys

from .checks import main_join_complete as main

if __name__ == "__main__":
    sys.exit(main())
