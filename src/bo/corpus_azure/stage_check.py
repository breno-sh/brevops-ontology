"""Valida a staging no validador oficial (fora da trava) e registra o resultado com o sha256 do arquivo.

  python -I -m bo.corpus_azure.stage_check

Grava $BO_DATA/CORPUS-AZURE/.staging/contract_report.json; o swap dentro da trava só confere o sha (a validação
do C06 de ~1,2 milhão de linhas leva minutos e não deve segurar a merge-base).
"""
from __future__ import annotations

import json
import subprocess
import sys

from . import MODULE
from .build import bo_data, now
from .swap import sha256_file


def main(argv=None) -> int:
    stg = bo_data() / MODULE / ".staging"
    f = stg / "usage.jsonl"
    if not f.is_file():
        print(f"{MODULE}: sem {f}", file=sys.stderr)
        return 1
    sha = sha256_file(f)
    r = subprocess.run([sys.executable, "-I", "-m", "bo.contracts.validate", "usage", str(f)],
                       capture_output=True, text=True)
    tail = (r.stdout + r.stderr).strip().splitlines()[-1:]
    print("\n".join(tail))
    ok = r.returncode == 0 and sha256_file(f) == sha
    rep = {"module": MODULE, "kind": "C06:usage", "file": f"$BO_DATA/{MODULE}/usage.jsonl", "sha256": sha,
           "result": "PASS" if ok else "FAIL", "validator": "python -I -m bo.contracts.validate usage",
           "checked_at": now()}
    (stg / "contract_report.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
