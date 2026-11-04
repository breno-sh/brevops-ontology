"""results/PILOT-STO-MAP/: report.json (resumo do pipeline do definitivo, só contagens) e MANIFEST.sha256.

Uso: python -I -m bo.pilot_sto_map.results
Roda depois do --promote e do tools/provenance.py record (o summary.json entra no manifesto)."""

from __future__ import annotations

import json
import sys

from .common import MODULE, dump_json, emit, now, out_dir, results_dir, sha256_file


def main(argv=None) -> int:
    rep_p = out_dir() / "pipeline_report.json"
    if not rep_p.is_file():
        emit(f"[{now()}] results: falta {rep_p} (rode o pipeline e o --promote-only antes)")
        return 1
    rep = json.loads(rep_p.read_text(encoding="utf-8"))
    rd = results_dir()
    rd.mkdir(parents=True, exist_ok=True)
    out = {"schema": "bo.pilot_sto_map.report/1", "module": MODULE, "generated_at": now(),
           "timezone": "America/Recife", "pipeline_generated_at": rep["generated_at"],
           "decided_at": rep["decided_at"], "inputs": rep["inputs"], "outputs": rep["outputs"],
           "counts": rep["counts"], "verdicts": rep["verdicts"],
           "steps": [{k: v for k, v in s.items() if k != "tail"} for s in rep["steps"]],
           "blocked": rep["blocked"], "contract_change": f"results/{MODULE}/CONTRACT_CHANGE.txt"}
    (rd / "report.json").write_text(dump_json(out), encoding="utf-8")
    files = sorted(p for p in rd.iterdir() if p.is_file() and p.name != "MANIFEST.sha256")
    (rd / "MANIFEST.sha256").write_text("".join(f"{sha256_file(p)}  results/{MODULE}/{p.name}\n" for p in files),
                                        encoding="utf-8")
    emit(f"[{now()}] results: report.json e MANIFEST.sha256 ({len(files)} arquivo(s)) em {rd}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
