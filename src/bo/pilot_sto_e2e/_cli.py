"""Argumentos comuns dos comandos do PILOT-STO-E2E."""

from __future__ import annotations

import argparse
import json
import sys

from bo.pilot.sto import common as C


def parser(prog: str, doc: str) -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog=prog, description=doc)
    ap.add_argument("--slice", default="sto", help="fatia (só sto neste módulo)")
    ap.add_argument("ids", nargs="*", help="stable_id do módulo (o despachante aceita)")
    return ap


def check_slice(a) -> None:
    if a.slice != "sto":
        raise SystemExit(f"{C.MODULE} só implementa a fatia sto (pedido: {a.slice})")


def say(tag: str, obj) -> None:
    print(f"[{C.now()}] {tag}: " + (json.dumps(obj, ensure_ascii=False, sort_keys=True) if not isinstance(obj, str) else obj))
    sys.stdout.flush()
