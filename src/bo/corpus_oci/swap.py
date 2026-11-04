"""Troca a pasta de staging pela publicada, só com a trava na mão do CORPUS-OCI.

  tools/lock.sh with merge-base --owner CORPUS-OCI --wait 900 -- python -I -m bo.corpus_oci.swap

Antes de trocar: o staging passa no validador oficial do C06 (usage) e no bo.corpus_oci.check. A troca é
os.replace arquivo a arquivo (atômica por arquivo) e o staging some no fim. Sem a trava: sai 3, nada muda.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

from . import build, check

OUTPUTS = ("usage.jsonl", "atom_totals.jsonl", "type_totals.jsonl", "build_report.json")


def lock_owner(name: str) -> str:
    f = build.bo_data() / "locks" / name / "owner"
    try:
        for ln in f.read_text(encoding="utf-8").splitlines():
            if ln.startswith("owner="):
                return ln[len("owner="):]
    except OSError:
        pass
    return ""


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="bo.corpus_oci.swap")
    ap.add_argument("--lock", default="merge-base")
    ap.add_argument("--provider", default=build.PROVIDER)
    a = ap.parse_args(argv)
    owner = lock_owner(a.lock)
    if not owner.startswith(build.MODULE):
        print(f"swap: trava {a.lock} não está com {build.MODULE} (dono: {owner or 'ninguém'}); nada trocado")
        return 3
    pub = build.bo_data() / build.MODULE
    stg = pub / ".staging"
    missing = [f for f in OUTPUTS if not (stg / f).is_file()]
    if missing:
        print(f"swap: staging incompleto, faltam {missing}")
        return 1
    v = subprocess.run([sys.executable, "-I", "-m", "bo.contracts.validate", "usage", str(stg / "usage.jsonl")],
                       capture_output=True, text=True)
    if v.returncode != 0:
        print("swap: staging reprova no validador C06:\n" + v.stdout[-2000:] + v.stderr[-2000:])
        return 1
    errs = check.check(stg, a.provider)
    if errs:
        print("swap: staging não confere:\n  " + "\n  ".join(errs[:20]))
        return 1
    for f in OUTPUTS:
        os.replace(stg / f, pub / f)
    for p in stg.iterdir():
        print(f"swap: sobra no staging, removida: {p.name}")
        p.unlink()
    stg.rmdir()
    print(f"swap: {len(OUTPUTS)} arquivos publicados em {build.portable(pub)} (trava {a.lock}, dono {owner})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
