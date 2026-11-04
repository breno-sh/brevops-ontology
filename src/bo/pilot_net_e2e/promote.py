"""Troca $BO_DATA/PILOT-NET-E2E/.staging pelo definitivo. Só dentro da trava merge-base deste módulo.

  tools/lock.sh with merge-base --owner PILOT-NET-E2E -- python -I -m bo.pilot_net_e2e.promote
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from bo.pilot.net import pipeline as P

from .common import say


def _holds_lock() -> bool:
    lock = Path(os.environ.get("BO_DATA", "/Users/breno/doutorado/brevops-data")) / "locks" / "merge-base"
    if not lock.is_dir():
        return False
    for f in ("owner", "owner.json"):
        p = lock / f
        if p.exists():
            txt = p.read_text(encoding="utf-8")
            try:
                return json.loads(txt).get("owner") == "PILOT-NET-E2E"
            except json.JSONDecodeError:
                return "PILOT-NET-E2E" in txt
    return False


def main(argv=None) -> int:
    if not _holds_lock():
        say("promote: a trava merge-base não é do PILOT-NET-E2E; nada trocado")
        return 3
    P.promote()
    say(f"promote: staging -> {P.data_dir()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
