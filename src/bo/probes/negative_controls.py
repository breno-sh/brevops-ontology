"""Comando: python -I -m bo.probes.negative_controls (ver bo.probes.checks)."""
import sys

from .checks import main_negative_controls as main

if __name__ == "__main__":
    sys.exit(main())
