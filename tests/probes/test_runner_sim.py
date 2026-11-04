"""Runner sobre a simulação determinística: pré-condições, repetição, censura no fim da janela, supervisor (D16),
limite de taxa (P4) e controle negativo."""

from __future__ import annotations

import pytest

from bo.probes.common import ProbeError
from bo.probes.protocol import KIT_PARAMS, RateLimitSpec, rate_limit_spec
from bo.probes.runner import ProbeCase, Runner
from bo.probes.backends import FakeClock, SimBackend
from probes_helpers import ALL_VALIDATED, FakeSupervisor, sim_run

VALIDATED_CELLS = ["object_versioning/aws", "object_versioning/google", "object_versioning/azurerm",
                   "object_versioning/oci", "object_lifecycle/aws", "object_lifecycle/google", "item_ttl/aws",
                   "item_ttl/google", "queue_retention/aws", "queue_retention/google"]


@pytest.mark.parametrize("cell", VALIDATED_CELLS)
def test_every_validated_cell_observes_and_control_gives_opposite(protos, cell):
    obs, trace, run, _ = sim_run(protos, cell, sim={"list_lag_s": 90, "expiry_lag_s": 3600})
    p = protos[cell.split("/")[0]]
    assert obs["counts"] == {"attempts": p.repetitions, "observed": p.repetitions, "not_observed": 0, "errors": 0}
    assert obs["negative_control_ok"] is True
    assert len(trace) == 2 * p.repetitions  # cada repetição tem caso e controle


@pytest.mark.parametrize("cell", ["object_versioning/aws", "item_ttl/aws", "queue_retention/google"])
def test_negative_control_with_config_still_on_fails(protos, cell):
    # controle "desligado" que na verdade ficou ligado: tem de dar o mesmo efeito do caso e reprovar
    obs, _, _, _ = sim_run(protos, cell, sim={"on": {"case": True, "control": True}})
    assert obs["negative_control_ok"] is False


def test_effect_never_seen_is_censored_not_equal(protos):
    obs, trace, _, _ = sim_run(protos, "item_ttl/aws", sim={"on": {"case": False, "control": False}})
    assert obs["counts"] == {"attempts": 3, "observed": 0, "not_observed": 3, "errors": 0}
    assert all("censura" in t["reason"] for t in trace if t["role"] == "case")


def test_effect_only_at_last_poll_is_not_confirmed(protos):
    # expira entre a penúltima e a última leitura: 1 leitura com efeito não confirma (2 exigidas) -> censura
    p = protos["item_ttl"]
    lag = p.max_wait_s - 3600 - p.poll_interval_s / 2
    clock = FakeClock()
    be = SimBackend("expiry", clock, ttl_s=3600, n=3)
    be.rng.uniform = lambda a, b: lag
    run = Runner(ProbeCase("PC-x", "A", "item_ttl", "aws", ttl_s=3600), p, be, clock=clock, support=ALL_VALIDATED,
                 supervisor=FakeSupervisor(clock), readback={"case": "PERSISTED", "control": "PERSISTED"})
    obs, trace = run.run()
    assert obs["counts"]["not_observed"] == 3
    case = [t for t in trace if t["role"] == "case"][0]
    assert case["polls"][-1]["state"] == "effect" and case["polls"][-2]["state"] != "effect"


def test_repetitions_follow_protocol(protos, monkeypatch):
    from dataclasses import replace
    p5 = replace(protos["object_versioning"], repetitions=5)
    clock = FakeClock()
    be = SimBackend("versions", clock, n=3)
    run = Runner(ProbeCase("PC-r", "A", "object_versioning", "aws"), p5, be, clock=clock, support=ALL_VALIDATED,
                 readback={"case": "PERSISTED", "control": "PERSISTED"})
    obs, trace = run.run()
    assert obs["counts"]["attempts"] == 5 and len(trace) == 10


def test_unsupported_cell_refused_before_any_action(protos):
    calls = []

    class Spy(SimBackend):
        def act(self, *a):
            calls.append(a)
            return super().act(*a)

    clock = FakeClock()
    support = {**ALL_VALIDATED, "log_retention/aws": "unsupported"}
    run = Runner(ProbeCase("PC-u", "A", "log_retention", "aws", ttl_s=86400), protos["log_retention"],
                 Spy("expiry", clock), clock=clock, support=support, supervisor=FakeSupervisor(clock),
                 readback={"case": "PERSISTED", "control": "PERSISTED"})
    with pytest.raises(ProbeError) as e:
        run.run()
    assert e.value.code == "PROTOCOL_UNSUPPORTED" and calls == []


def test_window_not_separated_from_ttl_is_refused(protos):
    # TTL configurado que come a margem: max_wait < TTL + margem (P2)
    with pytest.raises(ProbeError, match="P2"):
        sim_run(protos, "item_ttl/aws", ttl_s=2 * 3600)


@pytest.mark.parametrize("readback", [{"case": "PERSISTED", "control": "ALTERED"}, {"case": "REJECTED_BY_API"}])
def test_readback_not_persisted_gives_errors(protos, readback):
    obs, trace, _, be = sim_run(protos, "object_versioning/aws", readback=readback)
    assert obs["counts"]["errors"] == 3 and obs["negative_control_ok"] is False
    assert be.state == {}  # nada foi agido


def test_long_window_requires_supervisor(protos):
    obs, trace, _, be = sim_run(protos, "object_lifecycle/aws", supervisor=None)
    assert obs["counts"]["errors"] == 3 and be.state == {}
    assert "supervisor" in trace[0]["reason"]


def test_supervisor_lost_mid_window_turns_open_reps_into_errors(protos):
    clock = FakeClock()
    sup = FakeSupervisor(clock, down_from=10 * 3600)  # cai em 10 h e não volta
    be = SimBackend("expiry", clock, ttl_s=86400, n=3, expiry_lag_s=3600)
    run = Runner(ProbeCase("PC-s", "A", "object_lifecycle", "aws", ttl_s=86400), protos["object_lifecycle"], be,
                 clock=clock, support=ALL_VALIDATED, supervisor=sup,
                 readback={"case": "PERSISTED", "control": "PERSISTED"})
    obs, trace = run.run()
    assert obs["counts"]["errors"] == 3 and obs["negative_control_ok"] is False
    hb = run.heartbeat_summary()
    assert hb["max_gap_s"] >= hb["grace_s"]
    assert clock.monotonic() < 11 * 3600  # parou logo depois da carência, sem esperar a janela inteira


def test_short_supervisor_blip_within_grace_is_tolerated(protos):
    clock = FakeClock()
    sup = FakeSupervisor(clock, down_from=3600, down_until=3600 + 300)  # 5 min fora, carência 10 min
    be = SimBackend("expiry", clock, ttl_s=86400, n=3, expiry_lag_s=3600)
    run = Runner(ProbeCase("PC-b", "A", "object_lifecycle", "google", ttl_s=86400), protos["object_lifecycle"], be,
                 clock=clock, support=ALL_VALIDATED, supervisor=sup,
                 readback={"case": "PERSISTED", "control": "PERSISTED"})
    obs, _ = run.run()
    assert obs["counts"]["observed"] == 3
    assert any(e["event"] == "heartbeat_failed" for e in run.events)


def test_lost_polls_above_limit_is_error(protos):
    obs, trace, _, _ = sim_run(protos, "object_versioning/aws", sim={"error_rate": 0.97, "list_lag_s": 10 ** 9})
    assert obs["counts"]["errors"] >= 1


def test_action_retried_before_error(protos):
    # 2 falhas seguidas da ação ainda passam (op_retries = 2); 3 viram erro
    assert KIT_PARAMS["op_retries"] == 2
    obs, _, _, _ = sim_run(protos, "object_versioning/aws", sim={"fail": {("case", 1, "act"): 2}})
    assert obs["counts"]["errors"] == 0
    obs, _, _, _ = sim_run(protos, "object_versioning/aws", sim={"fail": {("case", 1, "act"): 3}})
    assert obs["counts"]["errors"] == 1


# ------------------------------------------------------------------------------------- limite de taxa (P4)
SPEC = RateLimitSpec(window_s=1.0, key="api_key", burst=20, mechanism="token_bucket", rate_per_s=10.0)


def test_rate_limit_requires_window_key_burst_mechanism():
    for miss in ("window", "key", "burst", "mechanism", "rate_per_s"):
        d = {"window": "PT1S", "key": "api_key", "burst": 20, "mechanism": "token bucket", "rate_per_s": 10}
        d[miss] = None
        with pytest.raises(ProbeError) as e:
            rate_limit_spec(d)
        assert e.value.code == "PROTOCOL_UNSUPPORTED"
    s = rate_limit_spec({"window": "PT1S", "key": "api_key", "burst": 20, "mechanism": "token bucket",
                         "rate_per_s": 10})
    assert s.n_requests() == 90 and s.expected_accepted() == 30


def test_rate_limit_runner_refuses_without_spec(protos):
    with pytest.raises(ProbeError, match="P4"):
        Runner(ProbeCase("PC-q", "A", "rate_limit", "provider_x"), protos["rate_limit"], None, clock=FakeClock(),
               support={"rate_limit/provider_x": "validated"})


def test_rate_limit_effect_and_negative_control(protos):
    sup = {"rate_limit/provider_x": "validated"}
    obs, trace, _, _ = sim_run(protos, "rate_limit/provider_x", support=sup, rate_limit=SPEC,
                               sim={"rate": 10.0, "burst_cap": 20})
    assert obs["counts"] == {"attempts": 3, "observed": 3, "not_observed": 0, "errors": 0}
    assert obs["negative_control_ok"] is True
    case = [t for t in trace if t["role"] == "case"][0]["polls"][0]
    assert case["accepted"] == 30 and case["throttled"] == 60
    # limite real bem menor que o declarado: limitação acontece mas os aceitos saem da tolerância de 20%
    obs, _, _, _ = sim_run(protos, "rate_limit/provider_x", support=sup, rate_limit=SPEC,
                           sim={"rate": 5.0, "burst_cap": 10})
    assert obs["counts"]["not_observed"] == 3
    # controle sem limite que mesmo assim limita
    obs, _, _, _ = sim_run(protos, "rate_limit/provider_x", support=sup, rate_limit=SPEC,
                           sim={"rate": 10.0, "burst_cap": 20, "on": {"case": True, "control": True}})
    assert obs["negative_control_ok"] is False


def test_rate_limit_repetitions_that_do_not_fit_are_censored(protos):
    slow = RateLimitSpec(window_s=240.0, key="ip", burst=1, mechanism="fixed_window", rate_per_s=0.1)
    obs, _, _, _ = sim_run(protos, "rate_limit/provider_x", support={"rate_limit/provider_x": "validated"},
                           rate_limit=slow, sim={"rate": 0.1, "burst_cap": 0})
    assert obs["counts"]["not_observed"] >= 1  # janela de 10 min não comporta 3 renovações de 4 min com recarga


def test_lost_poll_breaks_the_confirmation_sequence(protos):
    # efeito, perdida, efeito, efeito: a confirmação só vem nas duas últimas (a perdida zera a sequência)
    clock = FakeClock()
    be = SimBackend("versions", clock, n=3)
    real = be.observe

    def observe(role, rep):
        if role == "case" and rep == 1 and clock.monotonic() == 120:  # as 3 tentativas da 2ª leitura falham
            from bo.probes.backends import BackendError
            raise BackendError("perdida", "OBSERVE")
        return real(role, rep)
    be.observe = observe
    run = Runner(ProbeCase("PC-l", "A", "object_versioning", "aws"), protos["object_versioning"], be, clock=clock,
                 support=ALL_VALIDATED, readback={"case": "PERSISTED", "control": "PERSISTED"})
    obs, trace = run.run()
    r1 = [t for t in trace if t["role"] == "case" and t["rep"] == 1][0]
    assert r1["result"] == "observed" and r1["effect_at_s"] == 180 and r1["lost_polls"] == 1


def test_slow_reads_skip_overdue_ticks_instead_of_bunching(protos):
    clock = FakeClock()
    be = SimBackend("versions", clock, n=3, list_lag_s=10 ** 9)
    real = be.observe

    def slow(role, rep):
        clock.sleep(20)  # 6 leituras de 20 s por tick: 120 s por rodada, intervalo de 60 s
        return real(role, rep)
    be.observe = slow
    run = Runner(ProbeCase("PC-t", "A", "object_versioning", "aws"), protos["object_versioning"], be, clock=clock,
                 support=ALL_VALIDATED, readback={"case": "PERSISTED", "control": "PERSISTED"})
    obs, trace = run.run()
    ts = [p["t_s"] for p in trace[0]["polls"]]
    assert all(b - a >= 60 - 1e-9 for a, b in zip(ts, ts[1:]))  # nunca duas leituras coladas
    assert any(e["event"] == "tick_skipped" for e in run.events)
    assert ts[-1] >= protos["object_versioning"].max_wait_s  # a leitura final é no fim da janela


def test_act_retry_only_repeats_the_failed_write(protos):
    """Backend ao vivo com execução falsa (construído sem __init__: só teste, nada roda fora da memória)."""
    from bo.probes.backends import LiveBackend
    from bo.probes.ops import ops_for
    calls = []
    fails = {3: 1}

    def exec_fn(argv):
        calls.append(argv)
        n = sum(1 for a in calls if a[2] == "put-object")
        if fails.get(n):
            fails.pop(n)
            return {"rc": 255, "stdout": ""}
        return {"rc": 0, "stdout": "{}"}
    lb = object.__new__(LiveBackend)
    lb.cell, lb.ops, lb.targets = "object_versioning/aws", ops_for("object_versioning/aws"), {
        "case": {"bucket": "bo-x-0001"}, "control": {"bucket": "bo-x-0002"}}
    lb.exec_fn, lb.http_fn, lb.started_utc, lb.payload = exec_fn, None, None, "payload.bin"
    lb.act("case", 1, {"ttl_s": 0, "now_epoch": 0, "n": 3}, retries=2)
    puts = [a for a in calls if a[2] == "put-object"]
    assert len(puts) == 4  # 3 gravações + 1 nova tentativa da que falhou (nunca 5 versões)


def test_burst_counts_must_add_up(protos):
    class Empty(SimBackend):
        def burst(self, role, rep, n, window_s):
            return {"accepted": 0, "throttled": 0, "other": 0}
    clock = FakeClock()
    run = Runner(ProbeCase("PC-e", "A", "rate_limit", "provider_x", rate_limit=SPEC), protos["rate_limit"],
                 Empty("throttle", clock), clock=clock, support={"rate_limit/provider_x": "validated"},
                 readback={"case": "PERSISTED", "control": "PERSISTED"})
    obs, _ = run.run()
    assert obs["counts"]["errors"] == 3 and obs["negative_control_ok"] is False


def test_heartbeat_rule_matches_gate(protos):
    from bo.probes.checks import heartbeat_problems
    clock = FakeClock()
    # 500 s fora: a última batida aceita foi 60 s antes da queda, então o intervalo fica em 540 s < 600 s
    sup = FakeSupervisor(clock, down_from=3600, down_until=3600 + 500)
    be = SimBackend("expiry", clock, ttl_s=86400, n=3, expiry_lag_s=3600)
    run = Runner(ProbeCase("PC-h", "A", "object_lifecycle", "aws", ttl_s=86400), protos["object_lifecycle"], be,
                 clock=clock, support=ALL_VALIDATED, supervisor=sup,
                 readback={"case": "PERSISTED", "control": "PERSISTED"})
    obs, trace = run.run()
    assert obs["counts"]["observed"] == 3 and heartbeat_problems(trace) == []
    clock = FakeClock()
    sup = FakeSupervisor(clock, down_from=3600, down_until=3600 + 700)  # 700 s fora: perdeu
    be = SimBackend("expiry", clock, ttl_s=86400, n=3, expiry_lag_s=3600)
    run = Runner(ProbeCase("PC-h2", "A", "object_lifecycle", "aws", ttl_s=86400), protos["object_lifecycle"], be,
                 clock=clock, support=ALL_VALIDATED, supervisor=sup,
                 readback={"case": "PERSISTED", "control": "PERSISTED"})
    obs, trace = run.run()
    assert obs["counts"]["errors"] == 3 and heartbeat_problems(trace) == []
