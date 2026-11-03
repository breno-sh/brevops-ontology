"""Manifestos C17 do SCHEMA-OCI: $BO_DATA/SCHEMA-OCI/MANIFEST.sha256 (dados) e results/SCHEMA-OCI/MANIFEST.sha256.

  python -I -m bo.schema_oci.manifest [--write-results]

Sem opção: confere os dois manifestos com o verificador do REPO (bo.repo.receipts.verify_manifest), que
resolve caminhos relativos ao manifesto e portáteis ($BO_DATA/..., $BO_REPO/...). Sai 1 se algum não bater.
--write-results: regrava results/SCHEMA-OCI/MANIFEST.sha256 (gate, código, testes e results do módulo).
O manifesto de dados é gravado pela bo.schema_oci.pipeline (write).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import common

#: arquivos do próprio módulo em $BO_DATA/SCHEMA-OCI (relativos ao manifesto)
OWN = ("atoms.jsonl", "types.jsonl", "schema.json.sha256", "build_report.json", "crosscheck_classificacao.json",
       "plugin_cache/terraform.lock.hcl", "plugin_cache/terraformrc", "plugin_cache/provider.json",
       "plugin_cache/README.txt")


def own_files(out: Path) -> list[str]:
    cx = sorted(p.name for p in out.glob("crosscheck_oci-*.json"))
    return sorted([*OWN, *cx])


def write(out: Path, extra: list[Path]) -> Path:
    lines = [f"{common.sha256_file(out / rel)}  {rel}" for rel in own_files(out)]
    lines += [f"{common.sha256_file(p)}  {common.portable(p)}" for p in extra]
    mf = out / "MANIFEST.sha256"
    mf.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return mf


def results_files(repo: Path) -> list[str]:
    rels = ["gates/SCHEMA-OCI.sh"]
    for root in ("src/bo/schema_oci", "tests/schema_oci", "results/SCHEMA-OCI"):
        rels += sorted(p.relative_to(repo).as_posix() for p in (repo / root).rglob("*")
                       if p.is_file() and "__pycache__" not in p.parts and p.name != "MANIFEST.sha256")
    return rels


def write_results(repo: Path) -> Path:
    mf = repo / "results" / common.MODULE / "MANIFEST.sha256"
    mf.parent.mkdir(parents=True, exist_ok=True)
    mf.write_text("".join(f"{common.sha256_file(repo / r)}  {r}\n" for r in results_files(repo)), encoding="utf-8")
    return mf


def verify(repo: Path) -> list[str]:
    from bo.repo import receipts
    probs = []
    for mf in (common.out_dir() / "MANIFEST.sha256", repo / "results" / common.MODULE / "MANIFEST.sha256"):
        if not mf.is_file():
            probs.append(f"{mf}: não existe")
            continue
        probs += [f"{p['path']}: {p['problem']}" for p in receipts.verify_manifest(mf, repo)]
    # o manifesto de results tem de cobrir todos os arquivos versionados do módulo
    listed = {ln.split(None, 1)[1] for ln in (repo / "results" / common.MODULE / "MANIFEST.sha256")
              .read_text(encoding="utf-8").splitlines() if ln.strip()} if not probs else set()
    if listed:
        missing = sorted(set(results_files(repo)) - listed)
        probs += [f"results/{common.MODULE}/MANIFEST.sha256: falta {m}" for m in missing]
    return probs


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="bo.schema_oci.manifest", description=__doc__.split("\n")[0])
    ap.add_argument("--write-results", action="store_true")
    a = ap.parse_args(argv)
    repo = common.bo_repo()
    if a.write_results:
        print(f"gravado {write_results(repo)}")
        return 0
    probs = verify(repo)
    for p in probs:
        print(f"  FALHA {p}")
    print(f"manifestos SCHEMA-OCI: {'OK' if not probs else f'{len(probs)} problema(s)'}")
    return 0 if not probs else 1


if __name__ == "__main__":
    sys.exit(main())
