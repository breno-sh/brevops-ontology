#!/usr/bin/env python3
"""Redator do kit de segurança (SAFETY). Implementação: src/bo/safety/redaction.py.

Interface dos harnesses: redact(obj, context) -> obj redigido (context: nome do fluxo ou
{"kind": "plan|state|state_file|record|auto", "symbols": {real: símbolo}}).
CLI (filtro, para usar dentro do canal efêmero; nada é gravado por aqui):
  terraform show -json plano.tfplan | python3 -I deploy/safety/redactor.py --kind plan > redigido.json
"""
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[2] / "src"
if (_SRC / "bo" / "safety").is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from bo.safety.redaction import (IDENT, WITHHELD, Redacted, RedactionRefused, find_raw_tf_artifacts,  # noqa: E402,F401
                                 redact, redact_tf, serialize, write_redacted)


def main(argv=None) -> int:
    import argparse
    import json
    ap = argparse.ArgumentParser(prog="redactor")
    ap.add_argument("--kind", default="auto", choices=["auto", "plan", "state", "state_file", "record"])
    a = ap.parse_args(argv)
    red = redact_tf(json.load(sys.stdin), a.kind)
    sys.stdout.write(serialize(red))
    sys.stderr.write(json.dumps(red.meta, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
