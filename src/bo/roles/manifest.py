"""results/ROLES/MANIFEST.sha256 (C17): sha256 das saídas, das regras e do gate, com caminhos portáteis.

  python -I -m bo.roles.manifest          grava
  python -I -m bo.roles.manifest --check  confere com bo.repo.receipts.verify_manifest (sai 1 se diverge)
"""

from __future__ import annotations

import sys
from pathlib import Path

from bo.repo import receipts

from . import build

FILES = [
    "$BO_DATA/ROLES/roles.jsonl",
    "$BO_REPO/roles/rules.yaml",
    "$BO_REPO/results/ROLES/by_provider.json",
    "$BO_REPO/results/ROLES/audit.json",
    "$BO_REPO/gates/ROLES.sh",
]


def real(p: str) -> Path:
    return Path(p.replace("$BO_DATA", str(build.bo_data())).replace("$BO_REPO", str(build.bo_repo())))


def path() -> Path:
    return build.results_dir() / "MANIFEST.sha256"


def write() -> int:
    lines = [f"{build.sha256_file(real(p))}  {p}" for p in FILES]
    path().write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"MANIFEST.sha256: {len(lines)} arquivos")
    return 0


def check() -> int:
    if not path().exists():
        print("MANIFEST.sha256 ausente")
        return 1
    probs = receipts.verify_manifest(path(), build.bo_repo())
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
