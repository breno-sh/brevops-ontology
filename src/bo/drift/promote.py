"""Troca $BO_DATA/DRIFT/.staging pelas saídas finais. Só roda com a trava merge-base pega pelo DRIFT.

  tools/lock.sh with merge-base --owner DRIFT -- python -I -m bo.drift.promote

Move events.jsonl, atom_history.jsonl e rename_candidates.jsonl para $BO_DATA/DRIFT/, grava o
MANIFEST.sha256 deles e copia churn.json para $BO_REPO/results/DRIFT/. Nada é apagado antes de tudo existir.
"""
from __future__ import annotations

import os
import shutil
import sys

from . import common

DATA_FILES = ("events.jsonl", "atom_history.jsonl", "rename_candidates.jsonl")


def lock_owner(name: str = "merge-base") -> str | None:
    f = common.bo_data() / "locks" / name / "owner"
    if not f.is_file():
        return None
    for line in f.read_text(encoding="utf-8").splitlines():
        if line.startswith("owner="):
            return line.split("=", 1)[1].strip()
    return None


def write_data_manifest() -> None:
    out = common.out_dir()
    lines = [f"{common.sha256_file(out / n)}  {n}" for n in DATA_FILES]
    (out / "MANIFEST.sha256").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv=None) -> int:
    owner = lock_owner()
    if not owner or owner.split("@", 1)[0] != common.MODULE:
        print(f"promote: a trava merge-base não é do {common.MODULE} (dono: {owner}); nada trocado", file=sys.stderr)
        return 3
    st, out = common.staging_dir(), common.out_dir()
    need = [st / n for n in DATA_FILES + ("churn.json",)]
    miss = [str(p) for p in need if not p.is_file()]
    if miss:
        print(f"promote: staging incompleto: {miss}", file=sys.stderr)
        return 2
    for n in DATA_FILES:
        os.replace(st / n, out / n)            # mesmo sistema de arquivos: troca atômica por arquivo
    res = common.results_dir()
    res.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(st / "churn.json", res / "churn.json")
    (st / "churn.json").unlink()
    shutil.rmtree(st)
    write_data_manifest()
    print(f"[{common.now()}] promote: {', '.join(DATA_FILES)} em {common.portable(out)}; churn.json em "
          f"{common.portable(res)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
