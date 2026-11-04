"""C01 de todos os atoms_<versão>.jsonl.gz no validador único (que não lê .gz), e cópia descomprimida para lint.

  python -I -m bo.hist_gcp.c01 [--keep DIR]

Descomprime cada arquivo de átomos das versões extraídas (extraction.json) em $BO_TMP, valida com
bo.contracts.validate C01_atoms e apaga a cópia; com --keep DIR, deixa as cópias em DIR (dentro de $BO_TMP) para o
privacy_lint varrer o conteúdo de verdade, e não os bytes comprimidos. Sai 0 se todas conferem.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

from . import common as C


def main(argv=None) -> int:
    from bo.contracts import validate as V
    args = [a for a in (argv or []) if a != C.ID]
    keep = None
    if args[:1] == ["--keep"] and len(args) == 2:
        keep = Path(args[1]).resolve()
        if C.bo_tmp().resolve() not in keep.parents:
            print("c01: --keep tem de ficar dentro de $BO_TMP", file=sys.stderr)
            return 2
        if keep.exists():
            shutil.rmtree(keep)
        keep.mkdir(parents=True)
    elif args:
        print(f"c01: argumentos desconhecidos: {args}", file=sys.stderr)
        return 2
    xd = json.loads((C.out_dir() / "extraction.json").read_text(encoding="utf-8"))
    work = keep or (C.bo_tmp() / "c01")
    work.mkdir(parents=True, exist_ok=True)
    bad, n, total = [], 0, 0
    for row in xd["versions"]:
        if row["status"] != "extracted":
            continue
        v = row["version"]
        p = work / f"atoms_{v}.jsonl"
        p.write_bytes(C.gunzip_bytes(C.atoms_path(v)))
        res = V.validate("C01_atoms", p)
        n += 1
        total += res.n
        if not res.ok:
            bad.append(f"{v}: {res.errors[:3]}")
        if keep is None:
            p.unlink()
    print(f"[{C.now()}] C01 {C.ID}: {n} arquivo(s) de átomos, {total} átomo(s), {len(bad)} reprovado(s) -> "
          f"{'OK' if not bad else 'FAIL'}")
    for b in bad:
        print(f"  FAIL {b}")
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
