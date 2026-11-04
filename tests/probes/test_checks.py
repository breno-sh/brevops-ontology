"""Checagens dos módulos que usam o kit: heartbeat contínuo (PROBE-*), junção completa e controles negativos
(PROBE-JOIN). Nenhuma delas julga comportamento."""

from __future__ import annotations

import json

from bo.probes import checks
from bo.probes.runner import write_local
from probes_helpers import FakeSupervisor, recorded_run, sim_run


def _jl(path, rows):
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


def pj(pc, a, b, value, jid=None):
    return {"judgement_id": jid or f"PJ-{pc[3:]}", "pair_case_id": pc, "case_id": "CASE-1", "group_id": "GRP-1",
            "observations": {"A": a, "B": b}, "outcome": {"axis": "behavior", "value": value},
            "protocol_version": "1.0.0", "judged_by": "PROBE-JOIN", "judged_at": "2026-11-04T09:00:00-03:00"}


def test_supervisor_heartbeat_ok_and_gap(protos, work):
    d = work / "PROBE-X"
    obs, trace, _, _ = recorded_run(protos, "item_ttl_aws.json")
    write_local(d, obs, trace)
    assert checks.main_supervisor_heartbeat(["PROBE-X", "--dir", str(d)]) == 0
    # rastro adulterado: janela longa com 3 h sem batida e resultado aceito -> reprova
    rows = [json.loads(x) for x in (d / "probe_trace.jsonl").read_text().splitlines()]
    rows[0]["heartbeat"]["max_gap_s"] = 3 * 3600
    _jl(d / "probe_trace.jsonl", rows)
    assert checks.main_supervisor_heartbeat(["PROBE-X", "--dir", str(d)]) == 1
    assert checks.main_supervisor_heartbeat(["PROBE-X", "--dir", str(work / "vazio")]) == 1


def test_supervisor_lost_run_passes_because_reps_are_errors(protos, work):
    d = work / "PROBE-Y"
    obs, trace, run, _ = sim_run(protos, "object_lifecycle/aws", supervisor=None)
    # sem supervisor: pré-condição falhou, repetições são erro, nenhuma janela rodou sem heartbeat
    write_local(d, obs, trace)
    assert checks.main_supervisor_heartbeat(["PROBE-Y", "--dir", str(d)]) == 0
    assert obs["counts"]["errors"] == 3


def test_join_complete_and_negative_controls(work):
    obs = [{"observation_id": "OBS-1-A", "pair_case_id": "PC-1", "side": "A", "negative_control_ok": True},
           {"observation_id": "OBS-1-B", "pair_case_id": "PC-1", "side": "B", "negative_control_ok": True},
           {"observation_id": "OBS-2-A", "pair_case_id": "PC-2", "side": "A", "negative_control_ok": False},
           {"observation_id": "OBS-2-B", "pair_case_id": "PC-2", "side": "B", "negative_control_ok": True},
           {"observation_id": "OBS-3-A", "pair_case_id": "PC-3", "side": "A", "negative_control_ok": True}]
    _jl(work / "observations.jsonl", obs)
    good = [pj("PC-1", "OBS-1-A", "OBS-1-B", "OBSERVATIONS_MATCH_UNDER_PROTOCOL"),
            pj("PC-2", "OBS-2-A", "OBS-2-B", "INFRA_ERROR"),
            pj("PC-3", "OBS-3-A", "OBS-3-B", "INFRA_ERROR")]
    _jl(work / "pair_judgements.jsonl", good)
    args = ["--judgements", str(work / "pair_judgements.jsonl"), "--observations", str(work / "observations.jsonl"),
            "--cases"]
    assert checks.main_join_complete(args) == 0
    assert checks.main_negative_controls(args) == 0
    bad = [pj("PC-1", "OBS-1-A", "OBS-1-B", "OBSERVATIONS_MATCH_UNDER_PROTOCOL"),
           pj("PC-2", "OBS-2-A", "OBS-2-B", "OBSERVATIONS_DIFFER_UNDER_PROTOCOL"),
           pj("PC-3", "OBS-3-A", "OBS-3-B", "OBSERVATIONS_MATCH_UNDER_PROTOCOL")]
    _jl(work / "pair_judgements.jsonl", bad)
    assert checks.main_join_complete(args) == 1  # PC-3 sem o lado B
    assert checks.main_negative_controls(args) == 1  # PC-2 com controle falho e desfecho comparativo
    _jl(work / "pair_judgements.jsonl", good[:2])
    assert checks.main_join_complete(args) == 1  # PC-3 observado e sem julgamento
    cases = work / "probe_cases_aws.jsonl"
    _jl(cases, [{"pair_case_id": "PC-9"}])
    _jl(work / "pair_judgements.jsonl", good)
    assert checks.main_join_complete(args[:-1] + ["--cases", str(cases)]) == 1  # sorteado e nunca julgado


def test_fake_supervisor_counts():
    s = FakeSupervisor()
    s.beat()
    assert s.n == 1
