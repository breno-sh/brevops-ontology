"""Manifesto results/CORPUS-OCI/MANIFEST.sha256 (formato shasum -a 256, caminhos portáteis).

  python -I -m bo.corpus_oci.manifest write|verify

Cobre os dados publicados em $BO_DATA/CORPUS-OCI, o summary.json, o código, os testes e o gate do módulo.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from . import build
from .swap import OUTPUTS


def repo() -> Path:
    return Path(os.environ.get("BO_REPO") or Path(__file__).resolve().parents[3])


def entries() -> list[Path]:
    r = repo()
    files = [build.bo_data() / build.MODULE / f for f in OUTPUTS]
    files.append(r / "results" / build.MODULE / "summary.json")
    for sub in ("src/bo/corpus_oci", "tests/corpus_oci"):
        files += sorted(p for p in (r / sub).rglob("*") if p.is_file() and "__pycache__" not in p.parts)
    files.append(r / "gates" / f"{build.MODULE}.sh")
    return files


def label(p: Path) -> str:
    r = str(repo()).rstrip("/") + "/"
    s = str(p)
    return "$BO_REPO/" + s[len(r):] if s.startswith(r) else build.portable(p)


def resolve(lbl: str) -> Path:
    if lbl.startswith("$BO_REPO/"):
        return repo() / lbl[len("$BO_REPO/"):]
    if lbl.startswith("$BO_DATA/"):
        return build.bo_data() / lbl[len("$BO_DATA/"):]
    return Path(lbl)


def path() -> Path:
    return repo() / "results" / build.MODULE / "MANIFEST.sha256"


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    cmd = argv[0] if argv else "verify"
    if cmd == "write":
        lines = [f"{build.sha256_file(p)}  {label(p)}" for p in entries()]
        path().write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"manifesto: {len(lines)} arquivo(s) -> {label(path())}")
        return 0
    if cmd != "verify":
        print("uso: python -I -m bo.corpus_oci.manifest write|verify")
        return 2
    bad = n = 0
    listed = set()
    for ln in path().read_text(encoding="utf-8").splitlines():
        if not ln.strip():
            continue
        sha, lbl = ln.split("  ", 1)
        listed.add(lbl)
        n += 1
        p = resolve(lbl)
        if not p.is_file() or build.sha256_file(p) != sha:
            bad += 1
            print("DIVERGE", lbl)
    extra = sorted({label(p) for p in entries()} - listed)
    for lbl in extra:
        print("FORA DO MANIFESTO", lbl)
    print(f"manifesto: {n} arquivo(s), {bad} divergência(s), {len(extra)} fora")
    return 1 if bad or extra or not n else 0


if __name__ == "__main__":
    sys.exit(main())
