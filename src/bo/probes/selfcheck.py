"""Corrida local do kit nos casos sorteáveis, só com simulação (nada de nuvem, nada de credencial).

  python -I -m bo.probes.selfcheck            roda em $BO_TMP/selfcheck e compara com results/PROBEKIT/selfcheck.json
  python -I -m bo.probes.selfcheck --write    regrava o resumo e põe a corrida em $BO_DATA/PROBEKIT/.staging/selfcheck
  python -I -m bo.probes.selfcheck --publish  (só dentro da trava merge-base) troca .staging/selfcheck por selfcheck

Para cada caso validated de deploy/probes/protocol_support.json: lado A com a simulação determinística da família
(atraso de listagem e de expiração dentro da margem do protocolo) e relógio simulado; grava observations.jsonl (C22,
validador oficial) e probe_trace.jsonl.
Prova que o runner fecha os 10 casos com o protocolo congelado; não é medida de comportamento de provedor nenhum.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

from . import KIT_VERSION, MODULE_ID
from .backends import FakeClock, SimBackend
from .cells import IMPL
from .common import ProbeError, compare_or_write, data_dir, now, results_dir, tmp
from .kinds import FAMILY
from .protocol import load
from .runner import ProbeCase, Runner, write_local
from .support_matrix import drawable, load_support


class _AlwaysUp:
    def beat(self):
        return {"status": "watching"}


def run_all(out: Path) -> dict:
    protos = load()
    support = load_support()
    shutil.rmtree(out, ignore_errors=True)
    rows = []
    for cell in drawable():
        t, p = cell.split("/")
        clock = FakeClock()
        proto = protos[t]
        be = SimBackend(FAMILY[t], clock, ttl_s=IMPL[cell].ttl_s, seed=7, list_lag_s=90,
                        expiry_lag_s=proto.margin_over_ttl_s / 4)
        case = ProbeCase(f"PC-SELF-{t}-{p}", "A", t, p, ttl_s=IMPL[cell].ttl_s)
        run = Runner(case, proto, be, clock=clock, support=support, supervisor=_AlwaysUp(),
                     readback={"case": "PERSISTED", "control": "PERSISTED"})
        be.n = run.kind.n
        obs, trace = run.run()
        write_local(out, obs, trace)
        rows.append({"cell": cell, "counts": obs["counts"], "negative_control_ok": obs["negative_control_ok"],
                     "simulated_duration_s": run.heartbeat_summary()["duration_s"],
                     "polls": sum(len(x["polls"]) for x in trace)})
    return {"schema": "bo.probekit.selfcheck/1", "module": MODULE_ID, "kit_version": KIT_VERSION,
            "generated_at": now(), "backend": "simulado (SimBackend, semente 7)", "cells": rows,
            "observations": "$BO_DATA/PROBEKIT/selfcheck/observations.jsonl",
            "all_observed_and_controls_ok": all(r["counts"]["observed"] == r["counts"]["attempts"] and
                                                r["negative_control_ok"] for r in rows)}


def publish() -> None:
    """Troca .staging/selfcheck por selfcheck. Só com a trava merge-base tomada (dados trocados dentro da trava)."""
    lock = data_dir().parent / "locks" / "merge-base"
    if not lock.is_dir():
        raise ProbeError("publicar só dentro da trava merge-base (tools/lock.sh with merge-base)", "LOCK")
    st, dst = data_dir() / ".staging" / "selfcheck", data_dir() / "selfcheck"
    if not (st / "observations.jsonl").is_file():
        raise ProbeError("nada em .staging/selfcheck (rode com --write)", "STAGING")
    old = data_dir() / ".staging" / f"selfcheck.old-{os.getpid()}"
    if dst.exists():
        os.replace(dst, old)
    os.replace(st, dst)
    shutil.rmtree(old, ignore_errors=True)


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--publish" in argv:
        try:
            publish()
        except ProbeError as e:
            print(f"selfcheck: RECUSA ({e.code}): {e}")
            return 1
        print("selfcheck: publicado em $BO_DATA/PROBEKIT/selfcheck")
        return 0
    write = "--write" in argv
    out = (data_dir() / ".staging" / "selfcheck") if write else (tmp() / "selfcheck")
    doc = run_all(out)
    probs = compare_or_write(results_dir() / "selfcheck.json", doc, write)
    if not doc["all_observed_and_controls_ok"]:
        probs.append("simulação com caso não observado ou controle negativo falho")
    for r in doc["cells"]:
        c = r["counts"]
        print(f"  {r['cell']:<26} {c['observed']}/{c['attempts']} observadas, controle "
              f"{'ok' if r['negative_control_ok'] else 'FALHO'}, {r['polls']} leituras")
    for p in probs:
        print("  PROBLEMA:", p)
    print(f"selfcheck: corrida em {out}")
    print("selfcheck:", "OK" if not probs else "REPROVADO")
    return 0 if not probs else 1


if __name__ == "__main__":
    sys.exit(main())
