#!/usr/bin/env python3
"""Manifesto de intenção C16 (SAFETY). Implementação: src/bo/safety/manifest.py (classe Manifest).

  intent_manifest.py status --module M      último estágio de cada intenção (cópia privada)
  intent_manifest.py publish --module M     regrava a cópia pública a partir da privada
  intent_manifest.py check --module M       = python -I -m bo.safety.intent_reconciled M
"""
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[2] / "src"
if (_SRC / "bo" / "safety").is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from bo.safety.manifest import STAGES, Manifest, ManifestRefused, private_root  # noqa: E402,F401


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="intent_manifest")
    ap.add_argument("cmd", choices=["status", "publish", "check"])
    ap.add_argument("--module", required=True)
    a = ap.parse_args(argv)
    if a.cmd == "check":
        from bo.safety.intent_reconciled import main as m
        return m([a.module])
    man = Manifest(a.module)
    if a.cmd == "publish":
        man.repair()
        man.publish()
        print("cópia pública regerada")
        return 0
    for iid, s in sorted(man.load().items()):
        print(f"{iid}  {s.intent['resource_type']:<40} {s.last}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
