"""Confere o definitivo: as saídas trocadas batem com o build_record e o pipeline_report, e os vereditos gravados
são os que o árbitro dá hoje para o mapeamento gravado (comparação sem hora, sha nem texto: engine.verdict_map).

Uso: python -I -m bo.pilot_sto_map.verify
O verdicts.jsonl pode ter sido regravado pelo gate do catálogo (bo.arbiter.run com a hora do gate); por isso a
comparação é pelo conteúdo que não depende de hora."""

from __future__ import annotations

import json
import sys

from bo.arbiter import engine
from bo.arbiter.inputs import load

from .common import emit, now, out_dir, sha256_file
from . import decisions as DEC


def main(argv=None) -> int:
    d = out_dir()
    bad = []
    need = ("mapping.sssom.tsv", "build_record.json", "verdicts.jsonl", "pipeline_report.json")
    miss = [n for n in need if not (d / n).is_file()]
    if miss:
        emit(f"[{now()}] verify: definitivo incompleto em {d}: {miss}")
        return 1
    rec = json.loads((d / "build_record.json").read_text(encoding="utf-8"))
    rep = json.loads((d / "pipeline_report.json").read_text(encoding="utf-8"))
    if sha256_file(d / "mapping.sssom.tsv") != rec["mapping_sha256"]:
        bad.append("mapping.sssom.tsv não é o do build_record")
    for n in ("mapping.sssom.tsv", "build_record.json"):
        if rep["outputs"].get(n) != sha256_file(d / n):
            bad.append(f"{n} não é o do pipeline_report")
    res = engine.arbitrate(load([str(d / "mapping.sssom.tsv")]), decided_at=DEC.DECIDED_AT,
                           arbiter_sha256="0" * 64)
    fresh = engine.verdict_map(res["verdicts"])
    stored = engine.verdict_map([json.loads(l) for l in (d / "verdicts.jsonl").read_text(encoding="utf-8")
                                 .splitlines() if l.strip()])
    diff = sorted(k for k in set(fresh) | set(stored) if fresh.get(k) != stored.get(k))
    if diff:
        bad.append(f"{len(diff)} veredito(s) gravados diferem do árbitro de hoje, ex. {diff[:3]}")
    for b in bad:
        emit(f"  FALHA {b}")
    emit(f"[{now()}] verify: {len(stored)} veredito(s) conferidos contra o árbitro; "
         f"{'definitivo coerente' if not bad else 'INCOERENTE'}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
