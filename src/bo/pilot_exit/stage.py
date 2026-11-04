"""Troca do dado do módulo: $BO_DATA/PILOT-EXIT/.staging/heldout -> $BO_DATA/PILOT-EXIT/heldout.

  python -I -m bo.pilot_exit.stage promote     só dentro da trava merge-base (tools/lock.sh with merge-base)
  python -I -m bo.pilot_exit.stage status

A troca é um rename atômico; a versão anterior (se houver) vai para heldout.prev e é apagada depois.
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys

from . import common as C


def lock_held() -> bool:
    p = C.data() / "locks" / "merge-base" / "owner"
    try:
        return f"owner={C.MODULE}" in p.read_text(encoding="utf-8")
    except OSError:
        return False


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="bo.pilot_exit.stage")
    ap.add_argument("cmd", choices=("promote", "status"))
    a = ap.parse_args(argv)
    st, final = C.staging_dir() / "heldout", C.data_dir() / "heldout"
    if a.cmd == "status":
        C.say(f"stage: .staging {'existe' if st.is_dir() else 'vazio'}; promovido {'existe' if final.is_dir() else 'não'}")
        return 0
    if not lock_held():
        C.say("stage: a troca só acontece com a trava merge-base pega pelo PILOT-EXIT")
        return 2
    if not st.is_dir():
        C.say("stage: nada em .staging (já promovido)")
        return 0
    prev = C.data_dir() / "heldout.prev"
    if prev.exists():
        shutil.rmtree(prev)
    if final.exists():
        os.rename(final, prev)
    os.rename(st, final)
    if prev.exists():
        shutil.rmtree(prev)
    try:
        C.staging_dir().rmdir()
    except OSError:
        pass
    C.say(f"stage: promovido para {C.portable(final)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
