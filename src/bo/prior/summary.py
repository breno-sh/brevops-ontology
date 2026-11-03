"""Bloco results (C15) do results/PRIOR/summary.json a partir de results/PRIOR/metrics.json.

  python -I -m bo.prior.summary --write    copia as métricas para summary.json (a proveniência C17 do
                                           tools/provenance.py record fica como está)
  python -I -m bo.prior.summary --check    exige summary.results == metrics.results e NOT_APPLICABLE fora de results
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from .build import _repo


def _paths() -> tuple[Path, Path]:
    r = Path(_repo()) / "results" / "PRIOR"
    return r / "summary.json", r / "metrics.json"


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    sp, mp = _paths()
    met = json.loads(mp.read_text(encoding="utf-8"))
    summ = json.loads(sp.read_text(encoding="utf-8")) if sp.is_file() else {}
    if argv[:1] == ["--write"]:
        summ["results"] = met["results"]
        sp.write_text(json.dumps(summ, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"summary.json: {len(met['results'])} métrica(s) C15; NOT_APPLICABLE: {sorted(met['not_applicable'])}")
        return 0
    probs = []
    if summ.get("results") != met["results"]:
        probs.append("summary.json results difere de metrics.json (rode --write)")
    ids = {r["metric_id"] for r in met["results"]}
    for m in met["not_applicable"]:
        if any(m.upper().replace("-", "_") == i.rsplit("-", 1)[-1] for i in ids):
            probs.append(f"{m} está NOT_APPLICABLE e também tem métrica")
    for p in probs:
        print(f"FAIL {p}")
    print("summary.results: " + ("OK" if not probs else "REPROVADO") + f" ({len(ids)} métrica(s))")
    return 1 if probs else 0


if __name__ == "__main__":
    sys.exit(main())
