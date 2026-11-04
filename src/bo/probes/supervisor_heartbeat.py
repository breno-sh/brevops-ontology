"""Comando: python -I -m bo.probes.supervisor_heartbeat (ver bo.probes.checks)."""
import sys

from .checks import main_supervisor_heartbeat as main

if __name__ == "__main__":
    sys.exit(main())
