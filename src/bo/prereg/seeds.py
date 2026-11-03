"""Sementes pré-registradas: derivação e conferência de prereg/SEEDS.txt.

  python -I -m bo.prereg.seeds            confere SEEDS.txt (toda linha = derivação do nome; nomes = conteúdo)

seed = int(sha256(UTF-8('brevops-prereg-v3/' + NOME)).hexdigest(), 16) mod 2147483647
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

from . import common, content as C


def derive(name: str) -> int:
    return int(hashlib.sha256((C.SEED_SALT + name).encode("utf-8")).hexdigest(), 16) % C.SEED_MOD


def read(path: Path) -> list[dict]:
    rows = []
    header = None
    for ln in path.read_text(encoding="utf-8").splitlines():
        if not ln.strip() or ln.startswith("#"):
            continue
        cells = ln.split("\t")
        if header is None:
            header = cells
            continue
        rows.append(dict(zip(header, cells)))
    return rows


def check(path: Path) -> list[str]:
    errs = []
    rows = read(path)
    names = [r.get("name") for r in rows]
    want = [n for n, _, _ in C.SEEDS]
    if names != want:
        errs.append(f"nomes de SEEDS.txt {names} != pré-registrados {want}")
    for r in rows:
        try:
            v = int(r["seed"])
        except (KeyError, ValueError):
            errs.append(f"{r.get('name')}: semente não inteira")
            continue
        if v != derive(r["name"]):
            errs.append(f"{r['name']}: semente {v} != derivação {derive(r['name'])}")
        if len(str(v)) >= 12:
            errs.append(f"{r['name']}: 12 dígitos ou mais (privacy_lint)")
        if not r.get("consumer") or not r.get("purpose"):
            errs.append(f"{r['name']}: sem consumidor ou propósito")
    if len(set(int(r["seed"]) for r in rows if r.get("seed", "").isdigit())) != len(rows):
        errs.append("sementes repetidas")
    return errs


def main(argv=None) -> int:
    errs = check(common.FILES["seeds"])
    for x in errs:
        print("FAIL", x)
    if errs:
        print(f"RESULTADO: REPROVADO ({len(errs)})")
        return 1
    print(f"RESULTADO: OK ({len(C.SEEDS)} sementes conferem com a derivação)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
