"""Gate: python -I -m bo.requirements.beyond_cis [--dir PASTA] [--min N]

Reprova se alguma das 7 famílias além do CIS (identidade e ciclo de vida, composição, efeito de autorização,
caminho de rede, configuração x observação, perda, provedor novo) tiver menos de N CQs (padrão 1) no
cq_spec.jsonl, ou se houver CQ de família desconhecida.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

from . import common, model


def check(d: Path, minimum: int = 1) -> tuple[list[str], Counter]:
    cqs = common.load_jsonl(d / common.KIND_FILE["cq_spec"])
    cnt = Counter(q.get("family") for q in cqs)
    errs = [f"família desconhecida: {f!r}" for f in cnt if f not in model.FAMILIES]
    for fam, label in model.FAMILIES_BEYOND_CIS.items():
        if cnt.get(fam, 0) < minimum:
            errs.append(f"família '{fam}' ({label}) com {cnt.get(fam, 0)} CQ(s); mínimo {minimum}")
    return errs, cnt


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="bo.requirements.beyond_cis")
    ap.add_argument("--dir", default=None)
    ap.add_argument("--min", type=int, default=1)
    a = ap.parse_args(argv)
    d = Path(a.dir) if a.dir else common.out_dir()
    errs, cnt = check(d, a.min)
    for fam, label in model.FAMILIES_BEYOND_CIS.items():
        print(f"  {fam:22s} {cnt.get(fam, 0):2d}  ({label})")
    print(f"  {'cis':22s} {cnt.get('cis', 0):2d}  (vem do CQSRC)")
    if errs:
        return common.fail(errs, "beyond_cis")
    print(f"beyond_cis: OK ({sum(cnt.get(f, 0) for f in model.FAMILIES_BEYOND_CIS)} CQs nas 7 famílias)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
