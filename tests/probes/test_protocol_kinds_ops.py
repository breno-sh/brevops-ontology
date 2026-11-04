"""Protocolo congelado (PREREG), efeito por família, operações e parsers sobre respostas gravadas, e o backend ao
vivo recusando sem GO."""

from __future__ import annotations

import pytest

from bo.probes import ops
from bo.probes.backends import BackendError, LiveBackend, RecordedBackend
from bo.probes.common import ProbeError, duration_s, fmt_duration
from bo.probes.kinds import EFFECT, OPPOSITE, PARTIAL, Kind, within
from bo.probes.protocol import KIT_PARAMS
from probes_helpers import load_recording


def test_prereg_loads_through_official_validator(protos):
    assert set(protos) == {"object_versioning", "object_lifecycle", "item_ttl", "queue_retention", "rate_limit",
                           "log_retention"}
    p = protos["item_ttl"]
    assert (p.poll_interval_s, p.max_wait_s, p.window_s, p.margin_over_ttl_s) == (7200, 259200, 259200, 255600)
    assert p.needs_supervisor and not protos["object_versioning"].needs_supervisor


@pytest.mark.parametrize("s,v", [("PT1M", 60), ("PT72H", 259200), ("P1D", 86400), ("PT1.5S", 1.5), ("P1W", 604800)])
def test_durations(s, v):
    assert duration_s(s) == v


@pytest.mark.parametrize("bad", ["P1M", "P1Y", "1H", "PT", ""])
def test_durations_without_fixed_length_are_refused(bad):
    with pytest.raises(ProbeError):
        duration_s(bad)


def test_fmt_duration_round_trip():
    for s in (60, 3600, 86400 + 61, 259200):
        assert duration_s(fmt_duration(s)) == s


def test_coherence_window_separated_from_ttl(protos):
    for t, ttl in (("object_versioning", 0), ("object_lifecycle", 86400), ("item_ttl", 3600),
                   ("queue_retention", 600), ("log_retention", 86400)):
        assert protos[t].coherence(ttl) == []
    assert any(x.startswith("P2") for x in protos["object_lifecycle"].coherence(86400 + 1))
    assert any(x.startswith("P2") for x in protos["log_retention"].coherence(30 * 86400))


def test_tolerance_kinds():
    assert within(3, 3, "exact", 0) and not within(2, 3, "exact", 0)
    assert within(24, 30, "relative", 0.2) and not within(23, 30, "relative", 0.2)
    assert within(4, 3, "absolute", 1) and not within(5, 3, "absolute", 1)


def test_states_per_family():
    v = Kind("object_versioning", "exact", 0, 3)
    assert v.state({"versions": 3}) == EFFECT and v.state({"versions": 1}) == OPPOSITE
    assert v.state({"versions": 2}) == PARTIAL
    e = Kind("item_ttl", "exact", 0, 3)
    assert e.state({"present": 0}) == EFFECT and e.state({"present": 3}) == OPPOSITE
    assert e.state({"present": 1}) == PARTIAL and e.state({"present": 4}) == PARTIAL
    r = Kind("rate_limit", "relative", 0.2, 90)
    assert r.state({"accepted": 90, "throttled": 0}, 30) == OPPOSITE
    assert r.state({"accepted": 31, "throttled": 59}, 30) == EFFECT
    assert r.state({"accepted": 10, "throttled": 80}, 30) == PARTIAL


@pytest.mark.parametrize("bad", [{"present": -1}, {"present": "3"}, {"present": True}, {}, {"present": 1, "body": 1}])
def test_samples_are_counts_only(bad):
    with pytest.raises(ValueError):
        Kind("item_ttl", "exact", 0, 3).check_sample(bad)


def test_parsers_on_recorded_outputs():
    rec = load_recording("parsers.json")
    for cell, cases in rec["parsers"].items():
        for raw, want in cases:
            ctx = ops.runner_ctx(cell, "case", 1, {"n": 3})
            assert ops.OPS[cell]["observe"].parse(raw, ctx) == want, cell
    for cell, raws in rec["parse_errors"].items():
        for raw in raws:
            with pytest.raises(ops.ParseError):
                ops.OPS[cell]["observe"].parse(raw, ops.runner_ctx(cell, "case", 1, {"n": 3}))


def test_firestore_parser_needs_one_answer_per_item():
    p = ops.OPS["item_ttl/google"]["observe"].parse
    ctx = {"n": 3}
    assert p([{"status": 200}, {"status": 404}, {"status": 404}], ctx) == {"present": 1}
    with pytest.raises(ops.ParseError):
        p([{"status": 200}], ctx)
    with pytest.raises(ops.ParseError):
        p([{"status": 200}, {"status": 500}, {"status": 404}], ctx)


def test_ops_render_markers_and_refuse_missing():
    op = ops.OPS["object_versioning/aws"]["observe"]
    ctx = ops.runner_ctx("object_versioning/aws", "control", 2, {"case": {"bucket": "bo-x-0001"},
                                                                   "control": {"bucket": "bo-x-0002"}})
    r = op.render(ctx)
    assert r["argv"][:3] == ["aws", "s3api", "list-object-versions"]
    assert "bo-x-0002" in r["argv"] and "bo-probe/control/r2/obj" in r["argv"]
    with pytest.raises(ProbeError, match="marcador"):
        op.render(ops.runner_ctx("object_versioning/aws", "case", 1, {}))
    act = ops.OPS["item_ttl/aws"]["act"].render({**ctx, "i": 1, "expire_epoch": "1", "table": "t"})
    assert '"bo_expire_at":{"N":"1"}' in act["argv"][act["argv"].index("--item") + 1]


def test_queue_targets_are_per_repetition():
    base = {"case": [{"queue_url": f"q{i}"} for i in (1, 2, 3)], "control": [{"queue_url": "c1"}]}
    assert ops.runner_ctx("queue_retention/aws", "case", 3, base)["queue_url"] == "q3"
    with pytest.raises(ProbeError):
        ops.runner_ctx("queue_retention/aws", "control", 2, base)


def test_cells_without_ops_are_refused():
    for cell in ("rate_limit/aws", "log_retention/aws", "object_lifecycle/azurerm"):
        with pytest.raises(ProbeError) as e:
            ops.ops_for(cell)
        assert e.value.code == "PROTOCOL_UNSUPPORTED"


def test_live_backend_refuses_without_go(monkeypatch):
    monkeypatch.delenv("BO_CLOUD_GO", raising=False)
    with pytest.raises(ProbeError) as e:
        LiveBackend("PROBE-AWS", "object_versioning/aws", {"case": {}, "control": {}})
    assert e.value.code == "NO_GO" and "GO do Breno" in str(e.value)
    # mesmo com a variável, o PROBEKIT não é módulo de nuvem e não há trava cloud-aws tomada
    with pytest.raises(ProbeError, match="não é módulo de nuvem|trava"):
        LiveBackend("PROBEKIT", "object_versioning/aws", {}, env={"BO_CLOUD_GO": "1"})


def test_recording_must_be_marked_synthetic():
    with pytest.raises(ProbeError):
        RecordedBackend({"schema": "bo.probe_recording/1", "cell": "object_versioning/aws", "calls": {}})


def test_recorded_failure_is_backend_error():
    rb = RecordedBackend({"schema": "bo.probe_recording/1", "cell": "object_versioning/aws", "synthetic": True,
                          "calls": {"case/1": {"act": [{"rc": 1}], "observe": [{"raw": {"rc": 1}}]}}})
    with pytest.raises(BackendError):
        rb.act("case", 1, {})
    with pytest.raises(BackendError):
        rb.observe("case", 1)


def test_kit_params_are_declared():
    assert KIT_PARAMS["confirmations"] >= 2 and KIT_PARAMS["object_size_bytes"] == 1024
