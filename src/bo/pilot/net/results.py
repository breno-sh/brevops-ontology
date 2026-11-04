"""Resultados C15 do piloto NET: controls.json, oracle_calib.json e effort.json, a partir do staging de uma execução.

Leituras (C15 3.1.0, quantifier observed_fraction):
  complete_unit  caso = fixture de calibração x direção; atravessou = plano completo, HCL renderizado e juiz do
                 oráculo ACCEPT ou ACCEPT_WITH_DECLARED_LOSS. Limite inferior: UNDETERMINED não atravessou;
                 superior: atravessou.
  decision       fluxo da fixture em cada caso; atravessou = decisão do destino igual à da origem. Inferior: só
                 iguais; superior: iguais + cobertos por perda declarada + indeterminados.
Nada aqui é limiar: a fração é relatada; o gate do oráculo olha perda silenciosa e contraexemplo (E4).
As consequências que só o c3 obteve são de CALIBRAÇÃO (exploratórias): H9 conta só nas retidas (PILOT-EXIT).
"""

from __future__ import annotations

import json
from pathlib import Path

from . import CONTROLS, DIRECTIONS, MODULE

FRAME = {"ref": {"path": "$BO_REPO/pilot/net/fixtures_calib/", "sha256": None},
         "description": "fixtures de calibração do PILOT-NET-ORACLE x 12 direções"}
ACCEPTED = ("ACCEPT", "ACCEPT_WITH_DECLARED_LOSS")


def read_rows(staging: Path) -> list:
    return [json.loads(l) for l in (staging / "cases.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]


def _metric(mid, name, reading, n, ok, und, frame, note):
    est = None if n == 0 else round(ok / n, 4)
    return {"metric_id": mid, "name": name, "reading": reading, "axis": "operational",
            "quantifier": "observed_fraction",
            "operational_coverage": {"lower": 0.0 if n == 0 else round(ok / n, 4),
                                     "upper": 1.0 if n == 0 else round((ok + und) / n, 4), "est": est, "n": n},
            "frame": frame, "inclusion": {"rule_id": "INC-NET-CALIB", "text": note},
            "weights": {"scheme": "uniform"}, "joint_uncertainty": {"method": "none"}}


def _frame(fixtures_sha):
    f = json.loads(json.dumps(FRAME))
    f["ref"]["sha256"] = fixtures_sha
    return f


def controls(staging: Path, rep: dict) -> dict:
    rows = read_rows(staging)
    fr = _frame(rep["fixtures"]["sha256"])
    metrics, per = [], {}
    for c in CONTROLS:
        rc = [r for r in rows if r["control"] == c]
        if not rc:
            continue
        ok = sum(1 for r in rc if r["verdict"] in ACCEPTED)
        und = sum(1 for r in rc if r["verdict"] == "UNDETERMINED")
        code = c.split("_")[0].upper()
        metrics.append(_metric(f"M-NET-{code}-UNIT", f"unidade completa atravessada ({c})", "complete_unit", len(rc),
                               ok, und, fr, "caso fixture x direção; plano completo, HCL e juiz do oráculo"))
        n = eq = cov = un = 0
        for r in rc:
            flows = (r.get("judge") or {}).get("per_flow")
            nfl = r.get("n_flows", 0)
            if flows is None:
                n += nfl
                continue
            n += len(flows)
            eq += sum(1 for v in flows.values() if v["result"] == "equal")
            cov += sum(1 for v in flows.values() if v["result"] == "covered")
            un += sum(1 for v in flows.values() if v["result"] == "undetermined")
        metrics.append(_metric(f"M-NET-{code}-DECISION", f"decisão de fluxo atravessada ({c})", "decision", n, eq,
                               cov + un, fr, "fluxo da fixture em cada caso; igual = atravessou"))
        per[c] = {"by_direction": {d: _dir_counts([r for r in rc if r["direction"] == d]) for d in DIRECTIONS},
                  "status": _count(r["status"] for r in rc), "verdicts": _count(r["verdict"] for r in rc if r["verdict"]),
                  "block_codes": _count((r["reasons"][0]["code"] if r["reasons"] else r["render_status"])
                                        for r in rc if r["status"] != "TRANSLATED"),
                  "unsafe": [{"case_id": r["case_id"], "verdict": r["verdict"],
                              "negatives_carried": r["judge"]["negatives_carried"],
                              "silent_losses": r["judge"]["silent_losses"]}
                             for r in rc if r["verdict"] == "REJECT"]}
    only_c3 = _only_c3(rows)
    return {"schema": "bo.result/1", "contract": "C15", "contract_version": "3.1.0", "module": MODULE,
            "generated_at": rep["recorded_at"], "metrics": metrics,
            "notes": "três controles com a mesma entrada (ABox), a mesma política de perda e as mesmas transformações; "
                     "consequências só do c3 relatadas sobre a CALIBRAÇÃO (exploratório; H9 conta nas retidas)",
            "data": {"claims": rep["claims"], "invariants": rep["invariants"], "loss_policy": rep["loss_policy"],
                     "per_control": per, "c3_only_consequences": only_c3}}


def _only_c3(rows) -> dict:
    by = {}
    for r in rows:
        by.setdefault((r["fixture_id"], r["direction"]), {})[r["control"]] = r
    fam, cases = {}, []
    for (fid, d), m in sorted(by.items()):
        c3 = m.get("c3_full")
        if not c3:
            continue
        others_ok = any(m.get(c, {}).get("verdict") in ACCEPTED for c in ("c1_table", "c2_taxonomy"))
        c3_ok = c3["verdict"] in ACCEPTED or c3["status"] == "REFUSED"
        if c3_ok and not others_ok:
            kinds = sorted({x["kind"] for x in c3["consequences"]})
            axs = sorted({a for x in c3["consequences"] for a in x.get("axioms", [])})
            for k in kinds:
                fam[k] = fam.get(k, 0) + 1
            cases.append({"fixture_id": fid, "direction": d, "c3": c3["verdict"] or c3["status"],
                          "c2": m.get("c2_taxonomy", {}).get("verdict") or m.get("c2_taxonomy", {}).get("status"),
                          "c1": m.get("c1_table", {}).get("verdict") or m.get("c1_table", {}).get("status"),
                          "consequences": kinds, "justifying_axioms": axs})
    return {"families": fam, "cases": cases, "n_cases": len(cases)}


def _count(it) -> dict:
    out = {}
    for x in it:
        out[str(x)] = out.get(str(x), 0) + 1
    return dict(sorted(out.items()))


def _dir_counts(rs) -> dict:
    return {"n": len(rs), "accepted": sum(1 for r in rs if r["verdict"] in ACCEPTED),
            "rejected": sum(1 for r in rs if r["verdict"] == "REJECT"),
            "unsupported": sum(1 for r in rs if r["status"] in ("UNSUPPORTED", "RENDER_BLOCKED")),
            "refused": sum(1 for r in rs if r["status"] == "REFUSED")}


def oracle_calib(staging: Path, rep: dict, ev: dict) -> dict:
    rows = read_rows(staging)
    fr = _frame(rep["fixtures"]["sha256"])
    prim = [r for r in rows if r["control"] == "c3_full"]
    judged = [r for r in prim if r["verdict"]]
    silent = [r for r in judged if r["judge"]["silent_losses"]]
    neg = [r for r in judged if r["judge"]["negatives_carried"]]
    metrics = [
        _metric("M-NET-ORACLE-NOSILENT", "caso julgado sem perda silenciosa (c3_full)", "complete_unit", len(judged),
                len(judged) - len(silent), 0, fr, "caso renderizado e julgado; sem divergência descoberta"),
        _metric("M-NET-ORACLE-NONEG", "caso julgado sem negativo transportado (c3_full)", "complete_unit", len(judged),
                len(judged) - len(neg), 0, fr, "caso renderizado e julgado; nenhum DENY -> ALLOW"),
    ]
    return {"schema": "bo.result/1", "contract": "C15", "contract_version": "3.1.0", "module": MODULE,
            "generated_at": rep["recorded_at"], "metrics": metrics,
            "notes": "oráculo congelado do PILOT-NET-ORACLE nas fixtures de calibração; perdas declaradas pela política "
                     "única; fração relatada, não limiar (E4 é sobre perda silenciosa e contraexemplo)",
            "data": {"oracle_files_sha256": rep["oracle"], "criteria": ev["criteria"], "failures": ev["failures"],
                     "negative_fixtures": ev["negatives"], "reference_cases": ev["reference"],
                     "verdicts": {c: _count(r["verdict"] for r in rows if r["control"] == c and r["verdict"])
                                  for c in CONTROLS},
                     "cases": [{"case_id": r["case_id"], "verdict": r["verdict"], "status": r["status"],
                                "declared_losses": [d["loss_id"] for d in (r["judge"] or {}).get("declared_losses", [])],
                                "undeclarable": (r["judge"] or {}).get("undeclarable_losses", [])}
                               for r in rows]}}


def _ledger_sha() -> str:
    import hashlib
    p = Path(__file__).resolve().parents[2] / "pilot_net_e2e" / "effort_ledger.py"
    return hashlib.sha256(p.read_bytes()).hexdigest()


def effort(rep: dict, ledger: dict) -> dict:
    steps = ledger["steps"]
    n = len(steps)
    measured = sum(1 for s in steps if s.get("agent_hours") is not None)
    return {"schema": "bo.result/1", "contract": "C15", "contract_version": "3.1.0", "module": MODULE,
            "generated_at": rep["recorded_at"],
            "metrics": [{"metric_id": "M-NET-EFFORT-MEASURED", "name": "passos do piloto com esforço medido",
                         "reading": "field", "axis": "operational", "quantifier": "observed_fraction",
                         "operational_coverage": {"lower": round(measured / n, 4), "upper": round(measured / n, 4),
                                                  "est": round(measured / n, 4), "n": n},
                         "frame": {"ref": {"path": "$BO_REPO/src/bo/pilot_net_e2e/effort_ledger.py",
                                           "sha256": _ledger_sha()},
                                   "description": "passos do brief do PILOT-NET-E2E (livro de esforço)"},
                         "inclusion": {"rule_id": "INC-NET-EFFORT", "text": "passo do brief com hora de início e fim"},
                         "weights": {"scheme": "uniform"}, "joint_uncertainty": {"method": "none"}}],
            "notes": "esforço real do agente por passo (relógio de parede, America/Recife) e tempo de máquina medido "
                     "na execução; base para o PILOT-EXIT recalibrar o cronograma",
            "data": {"expected_h": 6, "agent": ledger, "machine_seconds": rep["timing_s"]}}
