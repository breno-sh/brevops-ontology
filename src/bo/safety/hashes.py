"""results/SAFETY/MANIFEST.sha256 (C17): sha256 das saídas do SAFETY, com caminhos portáteis.

  python -I -m bo.safety.hashes           grava
  python -I -m bo.safety.hashes --check   confere com bo.repo.receipts.verify_manifest (sai 1 se diverge)
"""

from __future__ import annotations

import sys

from .common import bo_repo, real, results_dir, sha256_file

PROVIDERS = ("aws", "google", "azurerm", "oci")
FILES = (["$BO_REPO/deploy/safety/allowlist_skus.yaml", "$BO_REPO/deploy/safety/EXPECTED_RESIDUE.json",
          "$BO_REPO/deploy/safety/plan_guard.py", "$BO_REPO/deploy/safety/redactor.py",
          "$BO_REPO/deploy/safety/identity_guard.py", "$BO_REPO/deploy/safety/intent_manifest.py",
          "$BO_REPO/deploy/safety/sweep_all.sh", "$BO_REPO/deploy/safety/SAFETY.html"]
         + [f"$BO_REPO/deploy/safety/{k}_{p}.sh" for k in ("teardown", "sweep") for p in PROVIDERS]
         + [f"$BO_REPO/deploy/safety/supervisor/{f}" for f in ("bo_supervisor.py", "bo-supervisor.service",
                                                                "bo-supervisor.timer", "authorized_keys.example",
                                                                "bundle.sh", "INSTALL.txt")]
         + ["$BO_REPO/results/SAFETY/sku_table_summary.json", "$BO_REPO/results/SAFETY/sweep_coverage.json",
            "$BO_REPO/results/SAFETY/failure_injection.json", "$BO_REPO/results/SAFETY/no_baseline_delete.json",
            "$BO_REPO/results/SAFETY/CROSS_MODULE_NOTES.txt", "$BO_REPO/gates/SAFETY.sh"])


def path():
    return results_dir() / "MANIFEST.sha256"


def write() -> int:
    lines = [f"{sha256_file(real(p))}  {p}" for p in FILES]
    path().write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"MANIFEST.sha256: {len(lines)} arquivos")
    return 0


def check() -> int:
    from bo.repo import receipts
    probs = receipts.verify_manifest(path(), bo_repo())
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
