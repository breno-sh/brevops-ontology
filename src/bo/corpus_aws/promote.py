"""Troca $BO_DATA/CORPUS-AWS/.staging pelas saídas publicadas, só dentro da trava merge-base do módulo.

  tools/lock.sh with merge-base --owner CORPUS-AWS -- python -I -m bo.corpus_aws.promote

Antes de trocar: o staging tem carimbo PASS do bo.corpus_aws.check para os mesmos bytes (senão o check roda
agora; ele inclui o validador oficial do C06 usage). Cada arquivo
entra com os.replace (atômico); counts.json vai também para results/CORPUS-AWS/; os dois MANIFEST.sha256 são
regravados ($BO_DATA/CORPUS-AWS/MANIFEST.sha256 e results/CORPUS-AWS/MANIFEST.sha256).
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

from . import common as K

DATA_FILES = ("usage.jsonl", "atom_totals.jsonl", "build_report.json", "counts.json")


def lock_owner() -> str:
    p = K.bo_data() / "locks" / "merge-base" / "owner"
    try:
        for ln in p.read_text(encoding="utf-8").splitlines():
            if ln.startswith("owner="):
                return ln[len("owner="):]
    except OSError:
        return ""
    return ""


def write_manifests() -> None:
    out, res = K.out_dir(), K.results_dir()
    data_lines = [f"{K.sha256_file(out / n)}  {K.portable(out / n)}" for n in DATA_FILES]
    tmp = out / "MANIFEST.sha256.part"
    tmp.write_text("\n".join(data_lines) + "\n", encoding="utf-8")
    os.replace(tmp, out / "MANIFEST.sha256")
    res_files = [res / "counts.json"] + [out / n for n in DATA_FILES]
    lines = [f"{K.sha256_file(p)}  {K.portable(p)}" for p in res_files]
    tmp = res / "MANIFEST.sha256.part"
    tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.replace(tmp, res / "MANIFEST.sha256")


def main(argv=None) -> int:
    owner = lock_owner()
    if not owner.startswith(K.MODULE):
        print(f"promote: a trava merge-base não é do {K.MODULE} (dono: {owner or 'livre'}); nada trocado",
              file=sys.stderr)
        return 3
    st = K.staging_dir()
    miss = [n for n in DATA_FILES if not (st / n).is_file()]
    if miss:
        print(f"promote: staging incompleto, falta {', '.join(miss)}", file=sys.stderr)
        return 2
    from . import check
    if not check.stamp_matches(st):
        # sem carimbo do check para ESTES bytes: confere agora (o carimbo evita refazer o validador na trava)
        rc = check.main([str(st)])
        if rc or not check.stamp_matches(st):
            print("promote: staging reprovado no check; nada trocado", file=sys.stderr)
            return rc or 1
    out = K.out_dir()
    res = K.results_dir()
    res.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(st / "counts.json", res / "counts.json.part")
    os.replace(res / "counts.json.part", res / "counts.json")
    for n in DATA_FILES:
        os.replace(st / n, out / n)
    if (st / "run.json").is_file():
        os.replace(st / "run.json", out / "run.json")
    write_manifests()
    print(f"[{K.now()}] promote: {len(DATA_FILES)} arquivo(s) publicados em {K.portable(out)}; manifestos regravados")
    return 0


if __name__ == "__main__":
    sys.exit(main())
