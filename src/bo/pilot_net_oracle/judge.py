"""CLI do juiz de tradução (para o PILOT-NET-E2E e o PILOT-EXIT).

  python -I -m bo.pilot_net_oracle.judge --source FX.json --target ALVO.json [--losses PERDAS.json] [--reading default]

ALVO.json: {"provider", "config", "targets"} no formato das fixtures (os fluxos vêm da origem). PERDAS.json:
[{"loss_id": "LOSS-NET-...", "flows": [...]}]. Imprime o veredito em JSON; sai 0 salvo REJECT (1).
"""
import argparse
import json
import sys

from . import load_oracle


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="bo.pilot_net_oracle.judge")
    ap.add_argument("--source", required=True)
    ap.add_argument("--target", required=True)
    ap.add_argument("--losses")
    ap.add_argument("--direction")
    ap.add_argument("--reading", default="default")
    a = ap.parse_args(argv)
    no = load_oracle()
    src = json.load(open(a.source, encoding="utf-8"))
    tgt = json.load(open(a.target, encoding="utf-8"))
    tgt.setdefault("flows", src["flows"])
    tgt.setdefault("read", {"completeness": "complete", "not_read": [], "withheld": []})
    losses = json.load(open(a.losses, encoding="utf-8")) if a.losses else []
    j = no.judge(src, tgt, losses, a.direction, reading=a.reading)
    print(json.dumps(j, ensure_ascii=False, indent=1))
    return 1 if j["verdict"] == "REJECT" else 0


if __name__ == "__main__":
    sys.exit(main())
