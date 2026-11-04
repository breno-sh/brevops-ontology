"""Regeneração idêntica: refaz a contagem inteira em $BO_TMP/regen e compara byte a byte com o publicado.

  python -I -m bo.corpus_aws.regen_check [--workers N]

Compara usage.jsonl, atom_totals.jsonl, build_report.json e counts.json ($BO_DATA/CORPUS-AWS/) e
results/CORPUS-AWS/counts.json. Usa outro número de processos que o padrão, para provar que a ordem do pool não
entra na saída. Grava o resultado em $BO_DATA/CORPUS-AWS/regen_check.json.
"""

from __future__ import annotations

import shutil
import sys

from . import build
from . import common as K

FILES = ("usage.jsonl", "atom_totals.jsonl", "build_report.json", "counts.json")


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    workers = 5
    if "--workers" in argv:
        workers = int(argv[argv.index("--workers") + 1])
    out = K.tmp_dir() / "regen"
    if out.exists():
        shutil.rmtree(out)
    rc = build.main(["--workers", str(workers), "--out", str(out)])
    if rc:
        return rc
    pub = K.out_dir()
    res = {}
    bad = []
    for n in FILES:
        a, b = K.sha256_file(out / n), (K.sha256_file(pub / n) if (pub / n).is_file() else None)
        res[n] = {"regen": a, "published": b, "same": a == b}
        if a != b:
            bad.append(n)
    rc_counts = K.results_dir() / "counts.json"
    same_res = rc_counts.is_file() and K.sha256_file(rc_counts) == K.sha256_file(out / "counts.json")
    res["results/counts.json"] = {"same": same_res}
    if not same_res:
        bad.append("results/CORPUS-AWS/counts.json")
    K.write_json(pub / "regen_check.json", {"module": K.MODULE, "checked_at": K.now(), "workers": workers,
                                            "files": res, "result": "FAIL" if bad else "PASS"})
    shutil.rmtree(out)
    print(f"[{K.now()}] regen_check: {'PASS' if not bad else 'FAIL ' + ', '.join(bad)} "
          f"({len(FILES) + 1} arquivo(s), {workers} processos)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
