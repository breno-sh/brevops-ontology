"""Supervisor independente com heartbeat: heartbeat parado ou prazo vencido -> destruição só do que é da
execução; fechado pelo runner -> nada; comando ssh restrito; sem ack, nada de janela longa."""

from __future__ import annotations

import json
from datetime import timedelta

import pytest

from bo.safety import plan_check, residue, skus
from bo.safety.common import iso, now_dt
from bo.safety.fakecloud import FakeCloud
from bo.safety.manifest import Manifest
from bo.safety.sim_runner import paths, setup, sim_check
from bo.safety.supervisor import Client, Supervisor, SupervisorError, handle, parse_ssh_command
from safety_helpers import ctx, plan, rc


class Clock:
    def __init__(self):
        self.t = now_dt()

    def __call__(self):
        return self.t


@pytest.fixture
def world(work):
    t = skus.load_table()
    d = work / "sim"
    fc = setup(d, "aws", t)
    p = paths(d)
    man = Manifest("SMOKE-AWS", p["public"], p["private"])
    mine = []
    for rtype in ("aws_s3_bucket", "aws_db_instance", "aws_kms_alias", "aws_kms_key"):
        f = skus.intent_fields(t, "aws", rtype)
        it = man.record_intent(provider="aws", batch_id="B-AWS-01", resource_type=rtype,
                               identity_check=sim_check(d, "aws"), ttl_hours=2, table_fields=f, region="us-east-1",
                               run_tag="b-aws-01")
        man.stage(it["intent_id"], "creating", identity_check=sim_check(d, "aws"))
        ref = fc.create(rtype, "us-east-1", it["logical_name"], it.get("tags"))
        man.stage(it["intent_id"], "created", identity_check=sim_check(d, "aws"), ref=ref)
        mine.append(ref)
    clock = Clock()
    res = residue.load()
    order = {k: e["delete_order"] for k, e in t["providers"]["aws"]["types"].items()}
    sup = Supervisor(work / "vm", adapter_factory=lambda prov: FakeCloud(p["cloud"]),
                     identity_fn=lambda prov: sim_check(d, prov), clock=clock, order_fn=lambda x: order.get(x, 0),
                     residue_fn=lambda it: residue.owned_expected(res, "aws", it),
                     wait_fn=lambda s: FakeCloud(p["cloud"]).advance(3600), poll_s=3600)
    client = Client(lambda cmd, stdin: (0, json.dumps(handle(sup, cmd, stdin))), man, "b-aws-01")
    return {"fc": fc, "man": man, "mine": mine, "clock": clock, "sup": sup, "client": client}


def foreign(fc):
    return {r for r, i in fc.items().items() if i.get("owner") == "terceiro"}


def test_heartbeat_lost_destroys_only_this_run(world):
    w = world
    before_foreign = foreign(w["fc"])
    ack = w["client"].register("aws", iso(w["clock"]() + timedelta(hours=2)), 600)
    assert ack["status"] == "watching" and ack["counts"]["intent_manifest.jsonl"] == 4
    w["clock"].t += timedelta(minutes=5)
    assert w["client"].beat()["status"] == "watching"
    assert w["sup"].tick() == []                      # heartbeat em dia: nada
    w["clock"].t += timedelta(minutes=11)             # Mac dormiu: 11 min sem heartbeat (> 600 s)
    out = w["sup"].tick()
    assert len(out) == 1 and "heartbeat parado" in out[0]["reason"] and out[0]["complete"], out
    items = w["fc"].items()
    left = [items[m]["state"] for m in w["mine"] if m in items]
    assert left == ["pending_deletion"]               # só o KMS em exclusão agendada (resíduo esperado)
    assert foreign(w["fc"]) == before_foreign and not w["fc"].foreign_deletes()
    assert w["sup"].status("b-aws-01")["status"] == "done"
    assert w["client"].beat()["refused"]              # runner que acorda é mandado parar de criar
    assert w["sup"].tick() == []                      # idempotente


def test_deadline_passes_even_with_heartbeats(world):
    w = world
    w["client"].register("aws", iso(w["clock"]() + timedelta(hours=1)), 600)
    for _ in range(7):
        w["clock"].t += timedelta(minutes=9)
        w["client"].beat()
        out = w["sup"].tick()
        if out:
            break
    assert out and "prazo" in out[0]["reason"]


def test_closed_run_is_not_destroyed(world):
    w = world
    w["client"].register("aws", iso(w["clock"]() + timedelta(hours=2)), 600)
    w["client"].close()
    w["clock"].t += timedelta(hours=5)
    assert w["sup"].tick() == []
    assert all(m in w["fc"].items() for m in w["mine"])


def test_beats_ship_only_new_manifest_lines_and_ignore_replays(world):
    w = world
    w["client"].register("aws", iso(w["clock"]() + timedelta(hours=2)), 600)
    sent = dict(w["client"].sent)
    w["man"].stage(w["man"].load()[next(iter(w["man"].load()))].iid, "confirmed",
                   identity_check=sim_check(paths(w["man"].private.parent)["cloud"].parent, "aws"))
    ack = w["client"].beat()
    assert ack["counts"]["run_manifest.jsonl"] == sent["run_manifest.jsonl"] + 1
    replay = w["sup"].beat("b-aws-01", 1, {"files": {}})
    assert replay.get("ignored")


def test_failure_during_destroy_is_retried(world, monkeypatch):
    w = world
    w["client"].register("aws", iso(w["clock"]() + timedelta(hours=2)), 600)
    w["clock"].t += timedelta(minutes=20)
    good = w["sup"].identity_fn
    w["sup"].identity_fn = lambda p: (_ for _ in ()).throw(RuntimeError("rede caiu"))
    out = w["sup"].tick()
    assert out[0]["complete"] is False and "rede caiu" in out[0]["error"]
    assert w["sup"].status("b-aws-01")["status"] == "tearing_down"
    w["sup"].identity_fn = good
    out = w["sup"].tick()
    assert out[0]["complete"] and w["sup"].status("b-aws-01")["status"] == "done"


@pytest.mark.parametrize("cmd", ["beat --run x --seq 1; rm -rf ~", "bash", "beat --run x --seq $(id)",
                                 "register --run x --evil 1", "tick && ls", "status --run ../../etc"])
def test_ssh_forced_command_is_restricted(work, cmd):
    sup = Supervisor(work / "vm")
    with pytest.raises(SupervisorError):
        handle(sup, cmd, "")


def test_parse_ssh_command_ok():
    assert parse_ssh_command("beat --run b-aws-01 --seq 3") == ("beat", {"run": "b-aws-01", "seq": "3"})


def test_no_long_window_without_supervisor_ack(world):
    w = world
    p = plan(rc("aws_s3_bucket.caso", "aws_s3_bucket", {"force_destroy": True, "tags_all": {"bo-run": "b-aws-01"}}))
    long = ctx(ttl_hours=24, window_hours=24)
    assert not plan_check.check_plan(p, {**long, "supervisor": w["client"].plan_context()})["ok"]
    w["client"].register("aws", iso(w["clock"]() + timedelta(hours=24)), 600)
    assert plan_check.check_plan(p, {**long, "supervisor": w["client"].plan_context()})["ok"]
