"""Regeneração idêntica: reconstrói em $BO_TMP e compara byte a byte com o publicado.

  python -I -m bo.corpus_oci.regen_check
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from . import build
from .swap import OUTPUTS


def main(argv=None) -> int:
    tmp = Path(os.environ.get("BO_TMP") or build.bo_data() / "tmp" / build.MODULE) / "regen"
    build.run(build.PROVIDER, tmp)
    pub = build.bo_data() / build.MODULE
    bad = []
    for f in OUTPUTS:
        a, b = build.sha256_file(tmp / f), build.sha256_file(pub / f) if (pub / f).is_file() else None
        print(f"  {f}: {'igual' if a == b else 'DIFERENTE'} ({a[:16]})")
        if a != b:
            bad.append(f)
    print(f"regen_check: {'OK' if not bad else 'DIVERGE ' + ', '.join(bad)}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
