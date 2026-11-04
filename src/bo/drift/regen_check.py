"""Regeneração idêntica: refaz tudo em $BO_TMP/regen e confere com as saídas gravadas.

  python -I -m bo.drift.regen_check

events.jsonl, atom_history.jsonl e rename_candidates.jsonl têm de bater byte a byte com o
$BO_DATA/DRIFT/MANIFEST.sha256; churn.json tem de ser igual ao de results/DRIFT fora o generated_at.
"""
from __future__ import annotations

import json
import shutil
import sys

from . import build, common
from .promote import DATA_FILES


def main(argv=None) -> int:
    tmp = common.bo_tmp() / "regen"
    if tmp.exists():
        shutil.rmtree(tmp)
    try:
        build.build(tmp)
        mf = {}
        for line in (common.out_dir() / "MANIFEST.sha256").read_text(encoding="utf-8").splitlines():
            if line.strip():
                sha, rel = line.split(None, 1)
                mf[rel.strip()] = sha
        bad = []
        if set(mf) != set(DATA_FILES):
            bad.append(f"MANIFEST lista {sorted(mf)} e não {sorted(DATA_FILES)}")
        for n in DATA_FILES:
            got = common.sha256_file(tmp / n)
            if mf.get(n) != got:
                bad.append(f"{n}: refeito {got[:12]} != gravado {str(mf.get(n))[:12]}")
        a = json.loads((tmp / "churn.json").read_text(encoding="utf-8"))
        b = json.loads((common.results_dir() / "churn.json").read_text(encoding="utf-8"))
        a.pop("generated_at", None)
        b.pop("generated_at", None)
        if a != b:
            bad.append("churn.json refeito difere do gravado (fora generated_at)")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    for x in bad:
        print("  ", x)
    print(f"  regeneração: {len(DATA_FILES)} arquivo(s) de dados + churn.json, {len(bad)} divergência(s)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
