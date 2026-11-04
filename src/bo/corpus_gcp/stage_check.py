"""Valida o usage.jsonl da .staging com o validador oficial (C06 usage), FORA da trava, e registra o resultado.

  python -I -m bo.corpus_gcp.stage_check

Grava $BO_DATA/CORPUS-GCP/.staging/validated.json com o sha256 do arquivo validado; o bo.corpus_gcp.promote só
aceita o registro se o sha256 ainda for o do arquivo (senão valida de novo dentro da trava).
"""

from __future__ import annotations

import subprocess
import sys

from . import common as C
from .promote import VALIDATED


def main(argv=None) -> int:
    st = C.staging_dir()
    f = st / "usage.jsonl"
    sha = C.sha256_file(f)
    r = subprocess.run([sys.executable, "-I", "-m", "bo.contracts.validate", "usage", str(f)],
                       capture_output=True, text=True)
    last = [ln for ln in (r.stdout + r.stderr).splitlines() if ln.strip()][-1:]
    res = "PASS" if r.returncode == 0 else "FAIL"
    C.write_json(st / VALIDATED, {"at": C.now(), "validator": "python -I -m bo.contracts.validate usage",
                                  "sha256": sha, "result": res})
    print(f"[{C.now()}] stage_check: {last[0] if last else ''} -> {res}")
    return 0 if res == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
