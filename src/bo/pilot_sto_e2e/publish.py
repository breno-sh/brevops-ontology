"""Troca o staging pelos dados publicados do módulo — só dentro da trava de merge.

  tools/lock.sh with merge-base --owner PILOT-STO-E2E -- python -I -m bo.pilot_sto_e2e.publish

Copia de $BO_DATA/PILOT-STO-E2E/.staging/ para $BO_DATA/PILOT-STO-E2E/ os artefatos do contrato (C23, C26, C14) e os
relatórios, e grava $BO_DATA/PILOT-STO-E2E/MANIFEST.sha256 (caminhos relativos à pasta). Recusa sem a trava.
"""

from __future__ import annotations

import json
import os
import shutil
import sys

from bo.pilot.sto import common as C
from bo.pilot.sto import pipeline as PL

FILES = ("translation_trace.jsonl", "graph_ir.jsonl", "lowering_plan.jsonl", "targets.jsonl", "render_status.json",
         "run_record.json", "grain_report.json", "nsi_report.json", "tf_validate_report.json", "robot_report.json")
OWL = ("sto-c1_table.ttl", "sto-c2_taxonomy.ttl", "sto-c3_full.ttl", "classes.jsonl", "properties.jsonl", "realizations.jsonl")


def holds_lock() -> bool:
    owner = C.data_root() / "locks" / "merge-base" / "owner"
    if not owner.exists():
        return False
    try:
        txt = owner.read_text(encoding="utf-8")
    except OSError:
        return False
    return C.MODULE in txt


def main(argv=None) -> int:
    if not holds_lock():
        print(f"[{C.now()}] publish: a trava merge-base não é do {C.MODULE}; nada trocado")
        return 2
    sd, dd = PL.stage_dir(), C.data_dir()
    missing = [f for f in FILES if not (sd / f).exists()] + [f"owl/{f}" for f in OWL if not (sd / "owl" / f).exists()]
    if missing:
        print(f"[{C.now()}] publish: staging incompleto: {missing}")
        return 1
    lines = []
    for f in FILES:
        shutil.copyfile(sd / f, dd / f)
        lines.append(f"{C.sha256_file(dd / f)}  {f}")
    (dd / "owl").mkdir(exist_ok=True)
    for f in OWL:
        shutil.copyfile(sd / "owl" / f, dd / "owl" / f)
        lines.append(f"{C.sha256_file(dd / 'owl' / f)}  owl/{f}")
    (dd / "MANIFEST.sha256").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[{C.now()}] publish: {len(lines)} arquivo(s) em {C.portable(dd)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
