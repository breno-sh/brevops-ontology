"""Corrida recalculada e conferida contra o staging (o que os gates de render conferem é o que foi gravado)."""

from __future__ import annotations

from bo.pilot.sto import common as C
from bo.pilot.sto import pipeline as PL
from bo.pilot.sto import stage as ST


def study_and_canary(name: str) -> tuple[dict | None, dict, str | None]:
    sd = PL.stage_dir()
    if not (sd / "lowering_plan.jsonl").exists():
        return None, {}, "staging sem lowering_plan.jsonl: rode bo.pilot.run antes"
    staged = C.sha256_file(sd / "lowering_plan.jsonl")
    out = ST.run_all(write=False)
    plans = [r.plan for runs in out["res"]["runs"].values() for r in runs if r.plan]
    if C.sha256_text("".join(C.canon(p) + "\n" for p in plans)) != staged:
        return None, {}, "planos recalculados ≠ staging: rode bo.pilot.run de novo"
    can = ST.canary(name + "-canary")
    return out, can, None
