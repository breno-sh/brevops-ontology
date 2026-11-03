"""results/DOCS-OCI/MANIFEST.sha256 (C17): sha256 das saídas, da fonte e do gate, com caminhos portáteis.

  python -I -m bo.docs_oci.manifest          grava
  python -I -m bo.docs_oci.manifest --check  confere com bo.repo.receipts.verify_manifest (sai 1 se diverge)
"""

from __future__ import annotations

import sys
from pathlib import Path

from bo.repo import receipts

from . import build, source

FILES = [
    "$BO_DATA/downloads/docs-oci/SOURCE.txt",
    "$BO_DATA/downloads/docs-oci/MANIFEST.sha256",
    "$BO_DATA/downloads/docs-oci/verification.json",
    "$BO_DATA/downloads/docs-oci/upstream/commit.json",
    "$BO_DATA/downloads/docs-oci/upstream/ls-remote.txt",
    "$BO_DATA/downloads/docs-oci/upstream/ls-tree.txt",
    "$BO_DATA/DOCS-OCI/docs_facts.jsonl",
    "$BO_DATA/DOCS-OCI/type_subcategory.jsonl",
    "$BO_REPO/results/DOCS-OCI/coverage.json",
    "$BO_REPO/results/DOCS-OCI/precision_audit.json",
    "$BO_REPO/results/DOCS-OCI/CONTRACT_CHANGE.txt",
    "$BO_REPO/gates/DOCS-OCI.sh",
]


def real(p: str) -> Path:
    return Path(p.replace("$BO_DATA", str(source.bo_data())).replace("$BO_REPO", str(source.bo_repo())))


def path() -> Path:
    return build.results_dir() / "MANIFEST.sha256"


def write() -> int:
    lines = [f"{source.sha256_file(real(p))}  {p}" for p in FILES]
    path().write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"MANIFEST.sha256: {len(lines)} arquivos")
    return 0


def check() -> int:
    probs = receipts.verify_manifest(path(), source.bo_repo())
    listed = [x.split("  ", 1)[1] for x in path().read_text(encoding="utf-8").splitlines() if x.strip()]
    if listed != FILES:
        probs.append({"problem": "lista de arquivos do MANIFEST difere da esperada"})
    if probs:
        print("MANIFEST não confere: " + "; ".join(str(p.get("problem", p)) for p in probs))
        return 1
    print(f"MANIFEST.sha256: {len(listed)} arquivos conferem")
    return 0


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    return check() if "--check" in argv else write()


if __name__ == "__main__":
    sys.exit(main())
