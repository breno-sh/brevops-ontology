"""Runner seguro com Terraform simulado: intenção antes da criação, identidade imediatamente antes do apply,
plan_guard sobre o plano que vai ser aplicado, nada cru fora do canal, e recusa de nuvem sem GO."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from bo.safety import ephemeral, plan_check, runner
from bo.safety.manifest import Manifest
from safety_helpers import fresh_check, plan, rc


class FakeTerraform:
    """Responde init/plan/show/apply como o Terraform, a partir de uma lista de recursos (tipo, atributos)."""

    def __init__(self, resources):
        self.resources = resources
        self.calls: list[str] = []
        self.applied = False

    def __call__(self, argv, cwd, env):
        assert "TF_DATA_DIR" in env and env["TF_LOG"] == ""
        sub = argv[1]
        self.calls.append(sub)
        if sub in ("init",):
            return 0, ""
        if sub == "plan":
            vf = argv[argv.index("-var-file") + 1]
            self.vars = json.loads(Path(vf).read_text())
            Path(argv[argv.index("-out") + 1]).write_bytes(b"PK-plano-binario")
            return 0, ""
        if sub == "show" and len(argv) > 3:
            chs = []
            for addr, rtype, after in self.resources:
                a = dict(after)
                if "name" in a and a["name"] == "{nome}":
                    a["name"] = self.vars["bo_names"].get(addr, "sem-nome")
                if "tags_all" in a:
                    a["tags_all"] = {"bo-run": self.vars["bo_run_id"]}
                chs.append(rc(addr, rtype, a))
            return 0, json.dumps(plan(*chs))
        if sub == "apply":
            self.applied = True
            return 0, ""
        if sub == "show":
            res = [{"address": a, "type": t, "values": {"id": f"id-{t}", "password": "p4ss-" + "x" * 8}}
                   for a, t, _ in self.resources]
            return 0, json.dumps({"format_version": "1.0", "values": {"root_module": {"resources": res}}})
        return 1, ""


def make_run(work, resources, **kw):
    tf_dir = work / "cfg"
    tf_dir.mkdir(exist_ok=True)
    (tf_dir / "main.tf").write_text('resource "aws_s3_bucket" "caso" {}\n')
    ch = ephemeral.EphemeralChannel(ephemeral.SimulatedBackend(work / "eph"))
    ch.__enter__()
    man = Manifest("SMOKE-AWS", work / "public", work / "private")
    exe = FakeTerraform(resources)
    r = runner.SafeRun(module="SMOKE-AWS", provider="aws", batch_id="B-AWS-01", ttl_hours=2, window_hours=1,
                       tf_dir=tf_dir, region="us-east-1", executor=exe, identity_fn=lambda p: fresh_check(),
                       channel=ch, manifest=man, out_dir=work / "out", readback_fn=lambda b, r: True,
                       simulation=True, **kw)
    return r, exe, man, ch


BUCKET = ("aws_s3_bucket.caso", "aws_s3_bucket", {"force_destroy": True, "tags_all": {}})
ALIAS = ("aws_kms_alias.a", "aws_kms_alias", {"name": "{nome}"})


def test_happy_path_intent_before_creating_and_redacted_outputs(work):
    r, exe, man, ch = make_run(work, [BUCKET, ALIAS])
    rep = r.plan_and_record()
    assert rep["ok"], rep["findings"]
    assert not exe.applied and all(s.last == "intent" for s in man.load().values())
    r.apply()
    assert exe.applied and [s.last for s in man.load().values()] == ["confirmed", "confirmed"]
    for s in man.load().values():
        st = [x["stage"] for x in s.runs]
        assert st == ["creating", "created", "confirmed"]
    state_txt = (work / "out" / "state_redacted.json").read_text()
    assert "p4ss-" not in state_txt
    assert redaction_free(work / "out")
    assert exe.vars["bo_names"]["aws_kms_alias.a"] == "bo-aws-01-0002"  # nome sintético chegou ao plano
    ch.close()


def redaction_free(d):
    from bo.safety.redaction import find_raw_tf_artifacts
    return find_raw_tf_artifacts([d]) == []


def test_expensive_plan_refused_before_any_apply(work):
    db = ("aws_db_instance.caso", "aws_db_instance", {"instance_class": "db.r6g.16xlarge", "tags_all": {}})
    r, exe, man, ch = make_run(work, [db])
    with pytest.raises(plan_check.PlanRefused):
        r.plan_and_record()
    assert not exe.applied and "apply" not in exe.calls
    assert [s.last for s in man.load().values()] == ["absent"]  # intenção fechada sem criação
    ch.close()


def test_raw_state_in_persistent_dir_refused(work):
    r, exe, man, ch = make_run(work, [BUCKET])
    (work / "cfg" / "terraform.tfstate").write_text("{}")
    with pytest.raises(runner.RunRefused, match="cru"):
        r.plan_and_record()
    assert exe.calls == []
    ch.close()


def test_stale_identity_before_apply_refused(work):
    from bo.safety import identity
    r, exe, man, ch = make_run(work, [BUCKET])
    r.plan_and_record()
    old = dict(fresh_check(), checked_at="2026-01-01T00:00:00-03:00")
    r.identity_fn = lambda p: old
    with pytest.raises(identity.IdentityRefused):
        r.apply()
    assert not exe.applied
    ch.close()


def test_cloud_run_refused_without_go_lock_and_ram_channel(work, monkeypatch):
    monkeypatch.delenv("BO_CLOUD_GO", raising=False)
    r, exe, man, ch = make_run(work, [BUCKET])
    r.simulation = False
    with pytest.raises(runner.RunRefused) as e:
        r.plan_and_record()
    msg = str(e.value)
    assert "GO" in msg and "cloud-aws" in msg and "RAM" in msg
    assert exe.calls == []
    probs = runner.cloud_preconditions("SMOKE-AWS", "aws", {"BO_CLOUD_GO": "1", "TF_LOG": "DEBUG"})
    assert any("TF_LOG" in p for p in probs)
    ch.close()


def test_simulated_channel_is_never_live():
    b = ephemeral.SimulatedBackend()
    ch = ephemeral.EphemeralChannel(b)
    assert ch.live_ok is False
    assert ephemeral.MacRamBackend.ram and ephemeral.MacRamBackend.encrypted
