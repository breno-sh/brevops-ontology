"""MANIFEST.sha256 (C17) do DOCS-GCP: código, testes, gate, saídas e a ficha da fonte.

  python -I -m bo.docs_gcp.manifest           grava results/DOCS-GCP/MANIFEST.sha256
  python -I -m bo.docs_gcp.manifest --check   confere (sai 1 se algum hash não bate ou arquivo falta)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from bo.repo import receipts

from . import build as B
from . import sources as S

DL_FILES = ("SOURCE.txt", "SHA256SUMS", "fetch_verification.json")


def entries() -> list[tuple[str, Path]]:
    repo = S.bo_repo()
    out = []
    for p in sorted((repo / "src" / "bo" / "docs_gcp").glob("*.py")):
        out.append((str(p.relative_to(repo)), p))
    for p in sorted((repo / "tests" / "docs_gcp").glob("*.py")):
        out.append((str(p.relative_to(repo)), p))
    out.append(("gates/DOCS-GCP.sh", repo / "gates" / "DOCS-GCP.sh"))
    for n in ("coverage.json", "CONTRACT_CHANGE.txt"):
        out.append((f"results/{S.MODULE}/{n}", S.results_dir() / n))
    for n in B.OUT_FILES:
        out.append((f"$BO_DATA/{S.MODULE}/{n}", S.out_dir() / n))
    for n in DL_FILES:
        out.append((f"$BO_DATA/downloads/docs-google/{n}", S.download_dir() / n))
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="bo.docs_gcp.manifest")
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)
    mf = S.results_dir() / "MANIFEST.sha256"
    if a.check:
        probs = receipts.verify_manifest(mf, S.bo_repo())
        for p in probs:
            print("  FAIL", p["path"], p["problem"])
        print(f"manifesto: {'confere' if not probs else f'{len(probs)} problema(s)'}")
        return 1 if probs else 0
    lines = [f"{S.sha256_file(p)}  {rel}\n" for rel, p in entries()]
    mf.write_text("".join(lines), encoding="utf-8")
    print(f"{len(lines)} entradas em {mf}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
