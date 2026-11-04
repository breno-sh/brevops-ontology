"""Regeneração idêntica: refaz o build inteiro em $BO_TMP/regen e compara o sha256 das saídas determinísticas
com o build_report.json gravado em $BO_DATA/CORPUS-GCP.

  python -I -m bo.corpus_gcp.regen_check [--workers N]
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys

from . import common as C
from .build import DETERMINISTIC, run


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="bo.corpus_gcp.regen_check")
    ap.add_argument("--workers", type=int, default=C.PARAMS["workers"])
    a = ap.parse_args(argv)
    rep = json.load(open(C.out_dir() / "build_report.json", encoding="utf-8"))
    tmp = C.tmp_dir() / "regen"
    shutil.rmtree(tmp, ignore_errors=True)
    new = run(tmp, a.workers)
    bad = [n for n in DETERMINISTIC if new["outputs"][n] != rep["outputs"][n]
           or C.sha256_file(C.out_dir() / n) != new["outputs"][n]]
    for n in DETERMINISTIC:
        print(f"  {'IGUAL' if n not in bad else 'DIFERE'} {n} {new['outputs'][n][:16]}")
    if not bad:
        shutil.rmtree(tmp, ignore_errors=True)
    print(f"[{C.now()}] corpus_gcp.regen_check: {len(DETERMINISTIC) - len(bad)}/{len(DETERMINISTIC)} saídas "
          f"idênticas -> {'OK' if not bad else 'REPROVADO'}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
