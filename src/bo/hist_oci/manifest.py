"""Manifestos C17 do HIST-OCI: $BO_DATA/HIST-OCI/MANIFEST.sha256 (dados) e results/HIST-OCI/MANIFEST.sha256.

  python -I -m bo.hist_oci.manifest [--write-data] [--write-results]

Sem opção: confere os dois manifestos com o verificador do REPO (bo.repo.receipts.verify_manifest) e que cada
um cobre tudo o que deve cobrir. Sai 1 se algum não bater.
O manifesto de dados lista só saídas estáveis do módulo (versions.json, extraction.json, atoms_*.jsonl.gz,
extraction/*.json, locks/*) e, por caminho portátil, o que elas citam em downloads/hist-oci (schema extraído,
recibo, metadado do registro, SHA256SUMS e assinatura). Fica de fora o que muda a cada rodada de gate ou de
integração (gate_report.json, consume_ledger.json, integration/, *.log): log volátil não entra em manifesto.
Binário não entra: é apagado depois da extração (o sha256 dele fica em extraction/<versão>.json).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import common

#: o que nunca entra no manifesto de dados (escrito pelas ferramentas do REPO a cada rodada)
VOLATILE = {"gate_report.json", "consume_ledger.json", "MANIFEST.sha256"}
VOLATILE_DIRS = {"integration"}


def data_files(out: Path | None = None) -> list[str]:
    out = out or common.out_dir()
    rels = []
    for p in sorted(out.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(out)
        if rel.parts[0] in VOLATILE_DIRS or rel.name in VOLATILE or p.suffix in (".log", ".part"):
            continue
        rels.append(rel.as_posix())
    return rels


def download_files() -> list[Path]:
    root = common.downloads()
    files = []
    for sub in ("release", "tfschema"):
        d = root / sub
        if d.is_dir():
            files += sorted(p for p in d.rglob("*") if p.is_file() and p.suffix != ".part")
    return files


def write_data() -> Path:
    out = common.out_dir()
    lines = [f"{common.sha256_file(out / rel)}  {rel}" for rel in data_files(out)]
    lines += [f"{common.sha256_file(p)}  {common.portable(p)}" for p in download_files()]
    mf = out / "MANIFEST.sha256"
    mf.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return mf


def results_files(repo: Path) -> list[str]:
    rels = [f"gates/{common.MODULE}.sh"]
    for root in ("src/bo/hist_oci", "tests/hist_oci", f"results/{common.MODULE}"):
        rels += sorted(p.relative_to(repo).as_posix() for p in (repo / root).rglob("*")
                       if p.is_file() and "__pycache__" not in p.parts and p.name != "MANIFEST.sha256")
    return rels


def write_results(repo: Path | None = None) -> Path:
    repo = repo or common.bo_repo()
    mf = repo / "results" / common.MODULE / "MANIFEST.sha256"
    mf.parent.mkdir(parents=True, exist_ok=True)
    mf.write_text("".join(f"{common.sha256_file(repo / r)}  {r}\n" for r in results_files(repo)), encoding="utf-8")
    return mf


def _listed(mf: Path) -> set[str]:
    return {ln.split(None, 1)[1] for ln in mf.read_text(encoding="utf-8").splitlines() if ln.strip()}


def verify(repo: Path | None = None) -> list[str]:
    from bo.repo import receipts
    repo = repo or common.bo_repo()
    data_mf = common.out_dir() / "MANIFEST.sha256"
    res_mf = repo / "results" / common.MODULE / "MANIFEST.sha256"
    probs = []
    for mf in (data_mf, res_mf):
        if not mf.is_file():
            probs.append(f"{mf}: não existe")
            continue
        probs += [f"{p['path']}: {p['problem']}" for p in receipts.verify_manifest(mf, repo)]
    if probs:
        return probs
    want_data = set(data_files()) | {common.portable(p) for p in download_files()}
    got = _listed(data_mf)
    probs += [f"MANIFEST de dados: falta {m}" for m in sorted(want_data - got)]
    probs += [f"MANIFEST de dados: item volátil listado {m}" for m in sorted(got)
              if Path(m).name in VOLATILE or Path(m).parts[0] in VOLATILE_DIRS or m.endswith(".log")]
    probs += [f"results/{common.MODULE}/MANIFEST.sha256: falta {m}"
              for m in sorted(set(results_files(repo)) - _listed(res_mf))]
    return probs


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="bo.hist_oci.manifest", description=__doc__.split("\n")[0])
    ap.add_argument("--write-data", action="store_true")
    ap.add_argument("--write-results", action="store_true")
    a = ap.parse_args(argv)
    if a.write_data:
        print(f"gravado {write_data()}")
    if a.write_results:
        print(f"gravado {write_results()}")
    if a.write_data or a.write_results:
        return 0
    probs = verify()
    for p in probs:
        print(f"  FALHA {p}")
    print(f"manifestos {common.MODULE}: {'OK' if not probs else f'{len(probs)} problema(s)'}")
    return 0 if not probs else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
