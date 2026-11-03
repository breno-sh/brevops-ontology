"""Duas execuções, mesmo sha: o árbitro é determinístico (gate do ARBITER).

Uso: python -I -m bo.arbiter.determinism [--record run_record.json]

Sem --record, usa $BO_DATA/$BO_ID/run_record.json (gravado pelo bo.arbiter.run) quando existe; senão, o mundo
plantado da bateria. Julga duas vezes com a mesma hora de decisão e uma terceira com as linhas em ordem inversa;
os três verdicts.jsonl e cycles.jsonl têm de ter o mesmo sha256. Com record, confere também que as entradas ainda
têm o sha gravado e que o verdicts.jsonl gravado é o mesmo que sai agora.
Relatório: $BO_DATA/ARBITERLIB/determinism.json (e em $BO_DATA/$BO_ID/ quando outro módulo chama).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from . import battery as B
from . import engine
from .common import data_root, dump_json, dump_jsonl, emit, load_jsonl, now, sha256_bytes, sha256_file, write_report
from .freeze import arbiter_sha
from .inputs import Glossary, load


def _sha(res) -> tuple[str, str]:
    return (sha256_bytes(dump_jsonl(res["verdicts"]).encode("utf-8")),
            sha256_bytes(dump_jsonl(res["cycles"]).encode("utf-8")))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="bo.arbiter.determinism")
    ap.add_argument("--record")
    a = ap.parse_args(argv)
    mid = os.environ.get("BO_ID") or "ARBITERLIB"
    rec_path = Path(a.record) if a.record else data_root() / mid / "run_record.json"
    problems = []
    if rec_path.exists() and (a.record or mid != "ARBITERLIB"):
        rec = json.loads(rec_path.read_text(encoding="utf-8"))
        for i in rec["inputs"]:
            if sha256_file(Path(i["path"])) != i["sha256"]:
                problems.append(f"entrada mudou desde o run: {i['path']}")
        items = load([i["path"] for i in rec["inputs"]])
        glossary = Glossary.from_dir(Path(rec["glossary"])) if rec.get("glossary") else None
        atoms = [x for p in rec.get("atoms") or [] for x in load_jsonl(Path(p))]
        decided, cycle, source = rec["decided_at"], rec.get("cycle", 1), str(rec_path)
    else:
        claims, _, _ = B.world()
        items, glossary, atoms = B.items_of(claims), None, []
        decided, cycle, source, rec = "2026-11-03T00:00:00-03:00", 1, "battery:mundo", None
    sha = arbiter_sha()
    runs = []
    for its in (items, items, list(reversed(items))):
        res = engine.arbitrate(its, glossary=glossary, atoms=atoms, cycle=cycle, decided_at=decided, arbiter_sha256=sha)
        runs.append(_sha(res))
    same = len(set(runs)) == 1
    if not same:
        problems.append(f"execuções diferentes: {runs}")
    if rec is not None and rec.get("verdicts_sha256") and runs[0][0] != rec["verdicts_sha256"]:
        problems.append("o verdicts.jsonl gravado pelo run não é o que o árbitro dá agora")
    obj = {"source": source, "runs": [{"verdicts_sha256": v, "cycles_sha256": c} for v, c in runs],
           "problems": problems, "pass": not problems, "arbiter_sha256": sha}
    p = write_report("determinism", obj)
    if mid != "ARBITERLIB":
        d = data_root() / mid
        d.mkdir(parents=True, exist_ok=True)
        (d / "determinism.json").write_text(dump_json(dict(obj, generated_at=now())), encoding="utf-8")
    for x in problems:
        emit(f"  FALHA {x}")
    emit(f"[{now()}] determinism ({source}): 3 execuções (2 iguais + ordem inversa), verdicts sha {runs[0][0][:12]}…; "
         f"{'iguais' if same else 'DIFERENTES'}; relatório {p}")
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())
