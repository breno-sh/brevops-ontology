"""Valida as saídas publicadas no validador oficial: versions.json (C13), cada atoms_<v>.jsonl.gz (C01) e
types_<v>.jsonl.gz (C02), descomprimidos em $BO_TMP/validate/<v>/ (o validador lê JSONL, não gzip).

  python -I -m bo.hist_azure.validate_outputs [--keep]

Com --keep, os JSONL descomprimidos ficam em $BO_TMP/validate/ (o gate passa o privacy_lint --strict neles,
para varrer o conteúdo de verdade e não só os bytes comprimidos). Sai 0 só se tudo confere.
"""

from __future__ import annotations

import argparse
import gzip
import json
import shutil
import sys

from . import common


def run(keep: bool = False) -> tuple[bool, list[str]]:
    from bo.contracts import validate as V
    lines, ok = [], True
    res = V.validate("versions", common.versions_path())
    ok &= res.ok
    lines.append(f"{'OK  ' if res.ok else 'FAIL'} C13 versions {common.portable(common.versions_path())}"
                 + ("" if res.ok else f" {res.errors[:5]}"))
    rep = json.loads(common.report_path().read_text(encoding="utf-8"))
    base = common.bo_tmp() / "validate"
    if base.exists():
        shutil.rmtree(base)
    n = 0
    for r in rep["versions"]:
        if r.get("status") != "EXTRACTED":
            continue
        v = r["version"]
        d = base / v
        d.mkdir(parents=True)
        for alias, src, name in (("C01_atoms", common.atoms_path(v), "atoms.jsonl"),
                                 ("C02_types", common.types_path(v), "types.jsonl")):
            dst = d / name
            with gzip.open(src, "rb") as fi, open(dst, "wb") as fo:
                shutil.copyfileobj(fi, fo, 1 << 20)
            res = V.validate(alias, dst)
            ok &= res.ok
            if not res.ok:
                lines.append(f"FAIL {alias} {v}: {res.errors[:5]}")
        n += 1
    lines.append(f"{'OK  ' if ok else 'FAIL'} C01/C02 de {n} versão(ões) extraída(s)")
    ok &= n > 0
    if not keep:
        shutil.rmtree(base, ignore_errors=True)
    return ok, lines


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="bo.hist_azure.validate_outputs", description=__doc__.split("\n")[0])
    ap.add_argument("--keep", action="store_true")
    a = ap.parse_args(argv)
    ok, lines = run(a.keep)
    for ln in lines:
        print(ln)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
