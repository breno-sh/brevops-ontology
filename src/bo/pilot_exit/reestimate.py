"""E7: esforço medido dos pilotos -> esforço recalibrado dos módulos de escala -> cronograma refeito.

  python -I -m bo.plan.reestimate --from $BO_REPO/results     (despacha para bo.pilot_exit.reestimate)

Medida (fixada antes de ver os números, declarada no arquivo de saída):
  módulo do piloto   esforço = hora do 1º commit '[ID]' em bo/base − hora de criação da branch bo/<id> (reflog);
                     retrabalho (commits [ID] depois da 1ª entrega) é relatado à parte, não entra na razão
  passo do E2E       results/PILOT-*-E2E/effort.json (o que o E2E mediu de cada passo); passo sem número conta em
                     steps_without_effort
  razão por classe   média das duas fatias de (medido ÷ effort_h do catálogo)
Classes (por papel, como na §3b): GLOSS -> GLOSSARY-<domínio> e DECOMPOSE; MAP -> MAP-*; E2E -> OWL, ABOX-LIFT,
GRAPH-LOWERING, TRANSLATOR, REASONING-PROOF. Módulo de escala sem análogo medido fica com o esforço do plano e
é listado como tal (nunca extrapolado). Cronograma: lista com teto de 12 agentes, travas do catálogo (lock) e
wall_h, igual para o plano e para o recalibrado; caminho crítico sem teto também.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import subprocess
from collections import defaultdict
from pathlib import Path

from . import common as C

CLASS_OF_PILOT = {"PILOT-STO-GLOSS": "GLOSS", "PILOT-NET-GLOSS": "GLOSS", "PILOT-STO-MAP": "MAP",
                  "PILOT-NET-MAP": "MAP", "PILOT-STO-E2E": "E2E", "PILOT-NET-E2E": "E2E",
                  "PILOT-STO-ORACLE": "ORACLE", "PILOT-NET-ORACLE": "ORACLE"}
E2E_ANALOGS = ("OWL", "ABOX-LIFT", "GRAPH-LOWERING", "TRANSLATOR", "REASONING-PROOF")
DURATION_KEYS = ("agent_hours", "hours", "effort_h", "wall_h", "h", "minutes", "min", "seconds", "s", "elapsed_s", "wall_s",
                 "duration_s", "elapsed_seconds", "duration_seconds")


def scale_class(mid: str) -> str | None:
    if re.fullmatch(r"GLOSSARY-(CMP|DB|NET|OPS|SEC|STO)", mid) or mid == "DECOMPOSE":
        return "GLOSS"
    if mid.startswith("MAP-"):
        return "MAP"
    if mid in E2E_ANALOGS:
        return "E2E"
    return None


def catalog() -> dict:
    p = os.environ.get("BO_MODULES") or "/Users/breno/doutorado/pesquisa/superficie/reports/brevops_ontology/modulos.json"
    return json.load(open(p, encoding="utf-8"))


def _git(root: Path, *a) -> str:
    r = subprocess.run(["git", "-C", str(root), *a], capture_output=True, text=True)
    return r.stdout if r.returncode == 0 else ""


def _t(s: str) -> dt.datetime:
    return dt.datetime.fromisoformat(s)


def measured_module(root: Path, mid: str, base: str = "bo/base") -> dict:
    br = "bo/" + mid.lower()
    created = None
    for line in _git(root, "reflog", "show", "--date=iso-strict", "--format=%gd%x09%gs", br).splitlines():
        if "\tbranch: Created from" in line:
            created = line.split("@{", 1)[1].split("}", 1)[0]
    commits = [l.split("\t", 1) for l in _git(root, "log", "--format=%cI%x09%s", base).splitlines()]
    mine = sorted(at for at, s in commits if s.startswith(f"[{mid}]"))
    if not mine or not created:
        return {"module": mid, "measured_h": None, "why": "sem criação da branch no reflog ou sem commit em bo/base"}
    first, last = _t(mine[0]), _t(mine[-1])
    h = (first - _t(created)).total_seconds() / 3600
    return {"module": mid, "branch_created": created, "first_delivery": mine[0], "last_commit": mine[-1],
            "measured_h": round(h, 2), "rework_span_h": round((last - first).total_seconds() / 3600, 2),
            "n_commits": len(mine)}


SECONDS_KEYS = ("seconds", "s", "elapsed_s", "wall_s", "duration_s", "elapsed_seconds", "duration_seconds")


def _hours(step: dict):
    for k in DURATION_KEYS:
        v = step.get(k)
        if isinstance(v, (int, float)) and not isinstance(v, bool) and v >= 0:
            if k in ("minutes", "min"):
                return v / 60
            if k in SECONDS_KEYS:
                return v / 3600
            return float(v)
    return None


def e2e_steps(results: Path, mid: str) -> dict:
    p = results / mid / "effort.json"
    d = C.read_json(p)
    if d is None:
        return {"module": mid, "file": C.portable(p), "present": False, "steps": [], "without_effort": None}
    raw = d
    if isinstance(d, dict):
        dd = d.get("data") or {}
        raw = d.get("steps") or (dd.get("agent") or {}).get("steps") or dd.get("steps") or []
    if isinstance(raw, dict):
        raw = [dict(v, step=k) if isinstance(v, dict) else {"step": k, "hours": v} for k, v in raw.items()]
    steps = []
    for s in raw or []:
        if not isinstance(s, dict):
            continue
        name = s.get("step") or s.get("name") or s.get("id")
        steps.append({"step": name, "hours": None if _hours(s) is None else round(_hours(s), 4)})
    return {"module": mid, "file": C.portable(p), "present": True, "steps": steps,
            "without_effort": sum(1 for s in steps if s["hours"] is None) if steps else None}


def schedule(mods: dict, effort: dict, done: set, cap: int) -> dict:
    """Lista: pronto = deps feitas; maior caminho restante primeiro; teto de agentes; trava exclusiva."""
    rem = {m: (0.0 if m in done else float(effort[m]) + float(mods[m].get("wall_h") or 0)) for m in mods}
    succ = defaultdict(list)
    for m, v in mods.items():
        for d in v["deps"]:
            if d in mods:
                succ[d].append(m)
    tail = {}

    def tl(m):
        if m not in tail:
            tail[m] = rem[m] + max((tl(s) for s in succ[m]), default=0.0)
        return tail[m]
    for m in mods:
        tl(m)
    finish, running, t = {}, [], 0.0
    pending = {m for m in mods}
    for m in list(pending):
        if rem[m] == 0.0 and all(d in done or d not in mods for d in mods[m]["deps"]) and m in done:
            finish[m] = 0.0
            pending.discard(m)
    while pending:
        ready = sorted((m for m in pending if all(d in finish and finish[d] <= t for d in mods[m]["deps"] if d in mods)),
                       key=lambda m: (-tail[m], m))
        locks = {mods[r]["lock"] for r, _ in running if mods[r].get("lock")}
        for m in ready:
            if len(running) >= cap:
                break
            lk = mods[m].get("lock")
            if lk and lk in locks:
                continue
            if rem[m] == 0.0:
                finish[m] = t
                pending.discard(m)
                continue
            running.append((m, t + rem[m]))
            pending.discard(m)
            if lk:
                locks.add(lk)
        if not running:
            if pending and not ready:
                raise RuntimeError("cronograma travado (ciclo ou dep fora do catálogo)")
            continue
        running.sort(key=lambda x: x[1])
        m, end = running.pop(0)
        t = end
        finish[m] = end
        while running and running[0][1] <= t:
            m2, e2 = running.pop(0)
            finish[m2] = e2
    crit_len = max(tail.values()) if tail else 0.0
    live = [m for m in tail if rem[m] > 0] or list(tail)
    start = max(live, key=lambda m: (tail[m], m))
    path = [start]
    while succ[path[-1]]:
        nxt = max(succ[path[-1]], key=lambda s: (tail[s], s))
        if tail[nxt] <= 0 or rem[nxt] <= 0:
            break
        path.append(nxt)
    return {"makespan_h": round(max(finish.values()) if finish else 0.0, 2),
            "critical_path_h": round(crit_len, 2), "critical_path": path}


def pinned_base(root: Path) -> str:
    """Commit de bo/base da execução registrada (cálculo reprodutível); sem registro, bo/base de agora."""
    rec = C.read_json(C.results_dir(root) / "heldout_run.json") or {}
    h = ((rec.get("frozen_code") or {}).get("sto") or {}).get("base_head")
    return h or "bo/base"


def build(results: Path, root: Path, base: str | None = None) -> dict:
    base = base or pinned_base(root)
    cat = catalog()
    mods = {m["stable_id"]: m for m in cat["modules"]}
    pilots = {m: measured_module(root, m, base) for m in CLASS_OF_PILOT if m in mods}
    steps = {m: e2e_steps(results, m) for m in ("PILOT-STO-E2E", "PILOT-NET-E2E")}
    ratios, used = {}, defaultdict(list)
    for m, r in pilots.items():
        if r.get("measured_h") is not None and mods[m]["effort_h"]:
            used[CLASS_OF_PILOT[m]].append(r["measured_h"] / float(mods[m]["effort_h"]))
    for k, v in used.items():
        ratios[k] = round(sum(v) / len(v), 4)
    from bo.repo import catalog as RC
    done = RC.merged_modules(root, base)
    rev = defaultdict(set)
    for m, v in mods.items():
        for d in v["deps"]:
            rev[d].add(m)
    scale, st = set(), [C.MODULE]
    while st:
        x = st.pop()
        for y in rev[x]:
            if y not in scale:
                scale.add(y)
                st.append(y)
    recal, rows = {}, []
    for m in sorted(mods):
        e = float(mods[m]["effort_h"] or 0)
        cls = scale_class(m) if m in scale else None
        f = ratios.get(cls) if cls else None
        recal[m] = round(e * f, 2) if f is not None else e
        if m in scale:
            rows.append({"module": m, "class": cls, "effort_h_plan": e, "factor": f, "effort_h_recalibrated": recal[m],
                         "basis": "razão medida da classe" if f is not None else
                         ("classe sem medida" if cls else "sem análogo medido nos pilotos: esforço do plano")})
    cap = int(cat.get("summary", {}).get("concurrency_cap") or 12)
    plan_eff = {m: float(v["effort_h"] or 0) for m, v in mods.items()}
    sched_plan = schedule(mods, plan_eff, done, cap)
    sched_new = schedule(mods, recal, done, cap)
    steps_without = sum((s["without_effort"] if s["without_effort"] is not None else 1) for s in steps.values())
    times = [r.get("last_commit") for r in pilots.values() if r.get("last_commit")]
    gen = max(times) if times else C.now()
    return {"generated_at": _t(gen).astimezone(C.TZ).isoformat(timespec="seconds"),
            "method": __doc__.split("\n\n", 1)[1].strip(),
            "pilot_modules": pilots, "e2e_steps": steps, "class_ratio": ratios,
            "steps_without_effort": steps_without,
            "scale_modules": rows, "n_scale_modules": len(rows),
            "n_recalibrated": sum(1 for r in rows if r["factor"] is not None),
            "schedule": {"concurrency_cap": cap, "merged_modules": len(done & set(mods)),
                         "plan": sched_plan, "recalibrated": sched_new},
            "schedule_recomputed": True, "as_of_base": _git(root, "rev-parse", base).strip()}


def c15(doc: dict) -> dict:
    n = sum(len(s["steps"]) for s in doc["e2e_steps"].values())
    k = n - sum(s["without_effort"] or 0 for s in doc["e2e_steps"].values() if s["present"])
    from bo.metrics.core import wilson
    lo, hi = wilson(k, n) if n else (0.0, 1.0)
    return {"schema": "bo.result/1", "contract": "C15", "contract_version": "3.1.0", "module": C.MODULE,
            "generated_at": doc["generated_at"],
            "metrics": [{"metric_id": "M-PILOT-EFFORT-MEASURED", "name": "fração dos passos do E2E com esforço medido",
                         "reading": "complete_unit", "axis": "operational", "quantifier": "observed_fraction",
                         "operational_coverage": {"lower": round(lo, 4), "upper": round(hi, 4),
                                                  "est": round(k / n, 4) if n else None, "n": n, "n_known": n},
                         "frame": {"description": "passos registrados em results/PILOT-*-E2E/effort.json"},
                         "inclusion": {"rule_id": "INC-EFFORT-01", "text": "todo passo listado pelo E2E"},
                         "weights": {"scheme": "uniform"},
                         "joint_uncertainty": {"method": "wilson", "level": 0.95}}],
            "notes": "E7 do PILOT-EXIT: esforço medido, razão por classe, esforço recalibrado e cronograma refeito",
            "data": {k2: v for k2, v in doc.items() if k2 != "generated_at"}}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="bo.pilot_exit.reestimate")
    ap.add_argument("--from", dest="src", required=True)
    ap.add_argument("ids", nargs="*")
    a = ap.parse_args(argv)
    root = C.repo()
    doc = build(Path(a.src), root)
    out = C.results_dir(root) / "effort_calibration.json"
    C.write_json(out, c15(doc))
    C.say(f"reestimate: {doc['n_recalibrated']}/{doc['n_scale_modules']} módulos de escala recalibrados; "
          f"razões {doc['class_ratio']}; passos do E2E sem esforço {doc['steps_without_effort']}; "
          f"makespan plano {doc['schedule']['plan']['makespan_h']} h -> recalibrado "
          f"{doc['schedule']['recalibrated']['makespan_h']} h -> {C.portable(out)}")
    return 0 if doc["steps_without_effort"] == 0 and doc["schedule_recomputed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
