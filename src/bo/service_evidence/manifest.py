"""results/SERVICE-EVIDENCE/MANIFEST.sha256 (C17): sha256 das saídas, dos relatórios e do gate, caminhos portáteis.

  python -I -m bo.service_evidence.manifest          grava
  python -I -m bo.service_evidence.manifest --check  confere com bo.repo.receipts.verify_manifest (sai 1 se diverge)
"""

from __future__ import annotations

import sys

from bo.repo import receipts

from . import common

FILES = [
    "$BO_DATA/SERVICE-EVIDENCE/service_evidence.jsonl",
    "$BO_DATA/SERVICE-EVIDENCE/protocol_support.jsonl",
    "$BO_REPO/results/SERVICE-EVIDENCE/evidence_levels.json",
    "$BO_REPO/results/SERVICE-EVIDENCE/sources.json",
    "$BO_REPO/results/SERVICE-EVIDENCE/protocol_support.schema.json",
    "$BO_REPO/results/SERVICE-EVIDENCE/spec_disputes.json",
    "$BO_REPO/results/SERVICE-EVIDENCE/spec_coverage.json",
    "$BO_DATA/downloads/apispec-oci-cc9/SHA256SUMS",
    "$BO_DATA/downloads/apispec-aws-cc9/SHA256SUMS",
    "$BO_DATA/downloads/apispec-google-cc9/SHA256SUMS",
    "$BO_DATA/downloads/apispec-azurerm-cc9/SHA256SUMS",
    "$BO_DATA/downloads/apispec-aws/SHA256SUMS",
    "$BO_DATA/downloads/apispec-google/SHA256SUMS",
    "$BO_DATA/downloads/apispec-azurerm/SHA256SUMS",
    "$BO_DATA/downloads/apispec-oci/SHA256SUMS",
    "$BO_REPO/results/SERVICE-EVIDENCE/CONTRACT_CHANGE.txt",
    "$BO_REPO/gates/SERVICE-EVIDENCE.sh",
]


def path():
    return common.results_dir() / "MANIFEST.sha256"


def _src(p: str):
    """Arquivo de $BO_DATA com versão em .staging (ainda não promovida): o manifesto já leva o hash dela, para
    conferir depois do --promote dentro da trava."""
    real = common.real(p)
    st = common.out_dir() / ".staging" / real.name
    if real.parent == common.out_dir() and st.exists():
        return st
    if not real.exists() and real.parent.parent.name == "downloads":  # lote de spec ainda em <pasta>.staging
        alt = real.parent.parent / (real.parent.name + ".staging") / real.name
        if alt.exists():
            return alt
    return real


def write() -> int:
    lines = [f"{common.sha256_file(_src(p))}  {p}" for p in FILES]
    path().write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"MANIFEST.sha256: {len(lines)} arquivos")
    return 0


def check() -> int:
    probs = receipts.verify_manifest(path(), common.bo_repo())
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
