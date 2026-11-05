"""Conferência geral do piso semântico: para todo veredito OK do árbitro, a semântica congelada concorda.

Uso: python -I -m bo.arbiter.semcheck [--in ARQ ...]     (sem --in: o mundo plantado da bateria)

Para cada alegação afirmada (não ausência) com veredito OK:
  forma   a referência (bo.semantics.obligations.assess) na forma que o árbitro julga (projeção pela parte; grupo
          sem translation_fn, com os passos julgados pelo check_group da semântica) devolve OK;
  crua    para alegação que não é grupo, assess sobre a linha CRUA não devolve UNPROVEN (o critério do E3 do
          PILOT-EXIT: 'veredito gravado ≠ UNPROVEN quando o árbitro congelado devolve UNPROVEN').
Grupo fica fora do critério cru: a linha crua de grupo não tem translation_fn e a semântica a julga pelos passos
(G-VARS, G-ARITY, G-OCC), não pela normalização escalar.
Relatório: $BO_DATA/ARBITERLIB/semcheck.json. Saída 1 se algum OK discorda.
"""

from __future__ import annotations

import argparse
import sys

from bo.semantics.obligations import assess

from . import battery as B
from . import engine
from .common import emit, now, write_report
from .inputs import load


def check(items: list[dict]) -> dict:
    res = engine.arbitrate(items, decided_at="2026-11-04T00:00:00-03:00", arbiter_sha256="0" * 64)
    ok = {v["claim_version_id"] for v in res["verdicts"] if v["verdict"] == "OK"}
    form_bad, raw_bad, n = [], [], 0
    for c in res["checked"]:
        if c.vid not in ok or c.form == "absence":
            continue
        n += 1
        if c.computed.get("sem_verdict", "OK") != "OK":
            form_bad.append({"claim_id": c.cid, "semantics": c.computed.get("sem_verdict")})
        if c.form != "group":
            try:
                a = assess(c.rec).verdict
            except Exception as e:      # noqa: BLE001 - a referência não julga: não é concordância
                a = f"ERROR {type(e).__name__}"
            if a == "UNPROVEN" or a.startswith("ERROR"):
                raw_bad.append({"claim_id": c.cid, "semantics_raw": a})
    return {"ok_claims": n, "form_disagree": form_bad, "raw_unproven": raw_bad,
            "pass": not form_bad and not raw_bad}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="bo.arbiter.semcheck")
    ap.add_argument("--in", dest="inputs", action="append", default=[])
    a = ap.parse_args(argv)
    runs = {}
    if a.inputs:
        for p in a.inputs:
            runs[p] = check(load([p]))
    else:
        claims, _, _ = B.world()
        runs["battery:mundo"] = check(B.items_of(claims))
    for src, r in runs.items():
        emit(f"  {'ok  ' if r['pass'] else 'FALHA'} {src}: {r['ok_claims']} OK; forma discorda {len(r['form_disagree'])}; "
             f"crua UNPROVEN {len(r['raw_unproven'])}")
        for x in (r["form_disagree"] + r["raw_unproven"])[:10]:
            emit(f"        {x}")
    p = write_report("semcheck", {"runs": runs})
    ok = all(r["pass"] for r in runs.values())
    emit(f"[{now()}] semcheck: {sum(r['ok_claims'] for r in runs.values())} veredito(s) OK conferidos em {len(runs)} "
         f"entrada(s); {'a semântica concorda com todos' if ok else 'há OK que a semântica não sustenta'}; relatório {p}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
