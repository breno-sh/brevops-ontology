"""Grava os resultados do piloto NET no repositório (results/PILOT-NET-E2E) a partir do mapeamento REAL.

  python -I -m bo.pilot_net_e2e.publish [--recorded-at ISO] [--check]

Roda o pipeline com as alegações do PILOT-NET-MAP (nunca sintéticas), o juiz do oráculo e escreve controls.json,
oracle_calib.json e effort.json (C15), com o carimbo fixo --recorded-at (regeneração idêntica). --check regenera
num temporário e compara com o que está no repositório (gates/PILOT-NET-E2E.sh): sai 1 se diferir. effort.json
entra na comparação sem os segundos de máquina (variam de uma execução para outra).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from bo.pilot.net import pipeline as P
from bo.pilot.net import results as RS

from . import effort_ledger
from .common import dump, results_dir, say, validate
from .oracle_eval import evaluate

FILES = ("controls.json", "oracle_calib.json", "effort.json")


def build(recorded_at: str, out: Path) -> dict:
    rep = P.run(claims_mode="mapping", out=out, recorded_at=recorded_at)
    if rep["claims"]["mode"] != "mapping":
        raise SystemExit("publish só com o mapeamento real")
    ev = evaluate(out, rep)
    return {"controls.json": RS.controls(out, rep), "oracle_calib.json": RS.oracle_calib(out, rep, ev),
            "effort.json": RS.effort(rep, effort_ledger.LEDGER)}


def _stable(name, doc):
    d = json.loads(json.dumps(doc))
    if name == "effort.json":
        d["data"].pop("machine_seconds", None)
    return d


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="bo.pilot_net_e2e.publish", description=__doc__.split("\n")[0])
    ap.add_argument("--recorded-at", default=None)
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)
    rd = results_dir()
    if a.check:
        cur = {f: json.loads((rd / f).read_text(encoding="utf-8")) for f in FILES}
        rec = cur["controls.json"]["generated_at"]
        docs = build(rec, P.tmp() / "publish_check")
        diff = [f for f in FILES if _stable(f, docs[f]) != _stable(f, cur[f])]
        say(f"publish --check: {'idêntico' if not diff else 'DIFERE em ' + ', '.join(diff)}")
        return 0 if not diff else 1
    rec = a.recorded_at or P.now()
    docs = build(rec, P.staging())
    for f, d in docs.items():
        dump(rd / f, d)
        rc, last = validate("result", rd / f)
        if rc:
            say(f"{f} reprova no C15: {last}")
            return 1
    say(f"publish: {', '.join(FILES)} gravados com carimbo {rec}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
