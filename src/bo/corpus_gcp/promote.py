"""Troca a .staging pela pasta do módulo, SÓ dentro da trava.

  tools/lock.sh with merge-base --owner CORPUS-GCP -- python -I -m bo.corpus_gcp.promote [--lock merge-base]

Confere que a trava está pega por CORPUS-GCP, que o MANIFEST.sha256 da .staging bate e que o usage.jsonl da
.staging passou no validador oficial (C06 usage): pelo registro do bo.corpus_gcp.stage_check (rodado ANTES, fora
da trava, para não segurar a trava durante a validação) se o sha256 confere, senão validando aqui. Então move
cada arquivo para $BO_DATA/CORPUS-GCP (os.replace, atômico por arquivo, usage.jsonl e manifesto por último) e
apaga a .staging.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys

from . import common as C

ORDER_LAST = ("usage.jsonl", "MANIFEST.sha256")
VALIDATED = "validated.json"


def validated(st) -> bool:
    """O stage_check validou ESTE usage.jsonl (mesmo sha256) e passou."""
    import json
    p = st / VALIDATED
    if not p.is_file():
        return False
    v = json.loads(p.read_text(encoding="utf-8"))
    return v.get("result") == "PASS" and v.get("sha256") == C.sha256_file(st / "usage.jsonl")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="bo.corpus_gcp.promote")
    ap.add_argument("--lock", default="merge-base")
    a = ap.parse_args(argv)
    owner = C.bo_data() / "locks" / a.lock / "owner"
    if not owner.is_file() or f"owner={C.MODULE}" not in owner.read_text(encoding="utf-8"):
        print(f"promote: a trava {a.lock} não está com {C.MODULE}; nada trocado", file=sys.stderr)
        return 2
    st, out = C.staging_dir(), C.out_dir()
    man = st / "MANIFEST.sha256"
    if not man.is_file():
        print("promote: .staging sem MANIFEST.sha256", file=sys.stderr)
        return 1
    names = []
    for ln in man.read_text(encoding="utf-8").splitlines():
        if not ln.strip():
            continue
        sha, name = ln.split("  ", 1)
        if C.sha256_file(st / name) != sha:
            print(f"promote: {name} diverge do manifesto da .staging", file=sys.stderr)
            return 1
        names.append(name)
    if not validated(st):
        r = subprocess.run([sys.executable, "-I", "-m", "bo.contracts.validate", "usage", str(st / "usage.jsonl")],
                           capture_output=True, text=True)
    else:
        r = subprocess.CompletedProcess([], 0, "", "")
    if r.returncode != 0:
        print("promote: usage.jsonl da .staging reprovado no validador C06", file=sys.stderr)
        print((r.stdout + r.stderr)[-2000:], file=sys.stderr)
        return 1
    names = [n for n in names if n not in ORDER_LAST] + list(ORDER_LAST)  # usage.jsonl e manifesto por último
    for n in names:
        os.replace(st / n, out / n)
    (st / VALIDATED).unlink(missing_ok=True)
    for p in sorted(st.rglob("*"), reverse=True):
        p.unlink() if p.is_file() else p.rmdir()
    st.rmdir()
    print(f"[{C.now()}] promote: {len(names)} arquivo(s) trocados em {C.portable(out)} sob a trava {a.lock}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
