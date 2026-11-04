"""Gate G4: HCL = plano + valores sintetizados declarados (nada inserido, nada perdido, nada trocado).

  python -I -m bo.lower.no_silent_insert --slice sto

Para os planos do estudo (staging) e para o canário de 12 direções (alegações sintéticas, controle positivo para o
gate não passar por vacuidade): renderiza pelos harness e roda o verificador independente de cada provedor (lê o
HCL com python-hcl2 e compara com o PLANO). Confere também, folha a folha, que a configuração-alvo julgada pelo
oráculo é exatamente o plano, e que uma folha plantada nela é pega (mutação).
"""

from __future__ import annotations

import copy

from bo.pilot.sto import atoms as ATM
from bo.pilot.sto import common as C
from bo.pilot.sto import pipeline as PL
from bo.pilot.sto import render as RD

from ._cli import check_slice, parser, say
from ._runs import study_and_canary


def _plan_leaves(plan: dict) -> dict:
    atoms = ATM.load()
    out = {}
    for s in plan["steps"]:
        ta = atoms.get(s["resource_type"])
        for v in s["values"]:
            parts = v["field"].split(".")
            norm, i = [], 0
            while i < len(parts):
                norm.append(parts[i])
                blk = ".".join(p for p in norm if not p.isdigit())
                if ta and ta.is_block(blk) and i + 1 < len(parts) and not parts[i + 1].isdigit():
                    norm.append("0")
                i += 1
            t = v["term"]
            val = t.get("value") if t["kind"] == "literal" else (
                "${%s.%s.%s}" % (t["target_type"], t["target_node"], t.get("attribute") or "id") if t["kind"] == "reference"
                else "${var.v_%s}" % t["symbol_id"][4:].lower() if t["kind"] == "symbol" else C.canon(t.get("tree")))
            out[(s["resource_type"], s["node_id"], ".".join(norm))] = C.canon(val)
    return out


def _tf_leaves(tf: dict, skip: set) -> dict:
    out = {}

    def walk(rt, n, x, pre):
        if isinstance(x, dict) and pre and isinstance(x, dict) and not any(isinstance(v, (dict, list)) for v in x.values()) \
                and pre[-1] not in ("0",) and False:
            pass
        if isinstance(x, list) and x and all(isinstance(i, dict) for i in x):
            for i, b in enumerate(x):
                for k, v in b.items():
                    walk(rt, n, v, pre + [str(i), k])
        elif isinstance(x, dict) and pre and _is_block_dict(rt, pre):
            for k, v in x.items():
                walk(rt, n, v, pre + [k])
        else:
            out[(rt, n, ".".join(pre))] = C.canon(x)

    for rt, insts in (tf.get("resource") or {}).items():
        for n, body in insts.items():
            if (rt, n) in skip:
                continue
            for k, v in body.items():
                walk(rt, n, v, [k])
    return out


def _is_block_dict(rt, pre) -> bool:
    ta = ATM.load().get(rt)
    return bool(ta and ta.is_block(".".join(p for p in pre if not p.isdigit())))


def judged_equals_plan(run) -> list[str]:
    skip = {tuple(b["container"].split(".", 1)) for b in run.translation.env_bystanders}
    pl, tl = _plan_leaves(run.plan), _tf_leaves(run.target["terraform"], skip)
    probs = []
    for k in sorted(set(pl) | set(tl)):
        if pl.get(k) != tl.get(k):
            probs.append(f"{run.plan['plan_id']}: {'.'.join(k)} plano={pl.get(k)} julgado={tl.get(k)}")
    return probs


def mutation_caught(run) -> bool:
    bad = copy.deepcopy(run)
    tf = copy.deepcopy(run.target)
    rt, insts = next(iter(tf["terraform"]["resource"].items()))
    n = next(iter(insts))
    insts[n]["bo_planted"] = "x"
    bad.target = tf
    return bool(judged_equals_plan(bad))


def main(argv=None) -> int:
    a = parser("bo.lower.no_silent_insert", __doc__).parse_args(argv)
    check_slice(a)
    study, can, err = study_and_canary("nsi")
    if err:
        say("no_silent_insert", err)
        return 2
    rep = {"generated_at": C.now(), "study": {}, "canary": {}, "judged_vs_plan": [], "mutation": None}
    problems = []
    for label, out in (("study", study), ("canary", can)):
        for prov, rr in sorted(out["render"]["renders"].items()):
            n = RD.no_silent_insert(rr)
            rep[label][prov] = {"plans": len(rr["status"]), "rendered": sum(1 for s in rr["status"].values() if s == "RENDERED"),
                                "checked": n["checked"], "problems": n["problems"][:20]}
            problems += [f"{label}/{prov}: {p}" for p in n["problems"]]
        for runs in out["res"]["runs"].values():
            for r in runs:
                if r.status == "LOWERED":
                    rep["judged_vs_plan"] += judged_equals_plan(r)
    lowered = [r for r in can["res"]["runs"]["c3_full"] if r.status == "LOWERED"]
    rep["mutation"] = bool(lowered) and mutation_caught(lowered[0])
    problems += rep["judged_vs_plan"]
    if not rep["mutation"]:
        problems.append("mutação plantada na configuração julgada não foi pega")
    missing = [p for p in C.PROVIDERS if rep["canary"].get(p, {}).get("checked", 0) == 0]
    if missing:
        problems.append("canário sem plano renderizado e conferido para: " + ", ".join(missing))
    rep["problems"] = problems
    C.write_json(PL.stage_dir() / "nsi_report.json", rep)
    say("no_silent_insert", {"study": {p: (v["rendered"], v["checked"]) for p, v in rep["study"].items()},
                             "canary": {p: (v["rendered"], v["checked"]) for p, v in rep["canary"].items()},
                             "problems": problems[:5]})
    return 0 if not problems else 1


if __name__ == "__main__":
    raise SystemExit(main())
