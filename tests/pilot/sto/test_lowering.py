"""Canário de 12 direções: plano C26 válido, alvo julgado = plano, nada sintetizado sem marca, perda nunca cobrível
nunca declarada; política e transformações iguais nos três controles."""
from bo.contracts import validate as V

from bo.pilot.sto import canary as CN
from bo.pilot.sto import common as C
from bo.pilot.sto import lower as LW
from bo.pilot.sto import pipeline as PL
from bo.pilot.sto import policy as P


def test_canary_all_directions(tmp_path):
    ctx = PL.prepare(claims=CN.claimset(), out_dir=tmp_path / "owl")
    runs = [PL.run_entry(ctx, e, "c3_full") for e in CN.entries()]
    assert len(runs) == 12 and all(r.status == "LOWERED" for r in runs), [(r.entry_id, r.block) for r in runs if r.block]
    plans = [r.plan for r in runs]
    C.write_jsonl(tmp_path / "lowering_plan.jsonl", plans)
    C.write_jsonl(tmp_path / "graph_ir.jsonl", [r.graph_ir for r in runs])
    assert V.validate("lowering_plan", tmp_path / "lowering_plan.jsonl").ok
    assert V.validate("graph_ir", tmp_path / "graph_ir.jsonl").ok
    for r in runs:
        for s in r.plan["steps"]:
            for v in s["values"]:
                if v["origin"] != "carried":
                    assert v["marked"], (r.entry_id, v["field"])
        assert not set(r.translation.effects) & set(P.NEVER_DECLARED)
        assert r.plan["dependency_closure"]["closed"]
    az = [r for r in runs if r.plan["target_provider"] == "azurerm"]
    assert all(any(s["resource_type"] == "azurerm_resource_group" for s in r.plan["steps"]) for r in az)


def test_judged_target_is_the_plan(tmp_path):
    from bo.pilot_sto_e2e import no_silent_insert as N
    ctx = PL.prepare(claims=CN.claimset(), out_dir=tmp_path / "owl")
    for e in CN.entries():
        r = PL.run_entry(ctx, e, "c3_full")
        assert N.judged_equals_plan(r) == [], e["entry_id"]
        assert N.mutation_caught(r)


def test_trace_contract(tmp_path):
    ctx = PL.prepare(claims=CN.claimset(), out_dir=tmp_path / "owl")
    rows = []
    for e in CN.entries()[:4]:
        for ctl in C.CONTROLS:
            rows += PL.run_entry(ctx, e, ctl).traces
    C.write_jsonl(tmp_path / "translation_trace.jsonl", rows)
    r = V.validate("translation_trace", tmp_path / "translation_trace.jsonl")
    assert r.ok, r.errors[:3]
    assert {x["control"] for x in rows} == {"c1", "c2", "c3"}
