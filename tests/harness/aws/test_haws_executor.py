"""Executor com respostas gravadas: ordem intenção -> apply -> leitura -> destroy, redator antes de gravar,
segredos só em memória, desfechos C12 e manifestos C16 válidos, CLI real bloqueada sem GO."""
import json
import os
import shutil
import stat
import sys
from pathlib import Path

import pytest

from bo.harness.aws import backends, executor as ex, redact, render

from conftest import FX

D12 = "".join(str(i % 10) for i in range(1, 13))
ARN = "ar" + "n:aws:rds:sa-east-1:" + D12 + ":db:bo-x"
REC = FX / "recorded"


def setup_case(work, rendered, rec_name, schema, matches=True):
    out, man = rendered
    rec = json.loads((REC / f"{rec_name}.json").read_text())
    plans = {p["plan_id"]: p for p in render.read_jsonl(FX / "plans" / "lowering_plan.jsonl")}
    graphs = {g["graph_id"]: g for g in render.read_jsonl(FX / "plans" / "graph_ir.jsonl")}
    plan = plans[rec["plan_id"]]
    case = ex.demo_case(plan, graphs[plan["graph_id"]])
    cfg = ex.RunConfig(run_id=rec["run_id"], batch_id="B-HAWS-TESTE", region="sa-east-1", case=case,
                       bindings=rec.get("bindings", {}), wait_timeout_s=60, poll_interval_s=5)
    kit = ex.OfflineKit(schema, matches=matches)
    sink = ex.Sink(work / "out", kit.redactor())
    return out, rec, plan, graphs[plan["graph_id"]], cfg, kit, sink


def fake_clock():
    t = [0.0]
    return (lambda s: t.__setitem__(0, t[0] + s)), (lambda: t[0])


class KitWithRedactor(ex.OfflineKit):
    """Kit de teste completo: redator do 'kit' (arquivo em $BO_TMP) e allowlist sintética (só em memória)."""

    def __init__(self, schema, path):
        super().__init__(schema)
        path.write_text("def redact(obj, context):\n    return obj\n")
        self.path = path

    def redactor(self):
        return redact.Redactor(redact.load_kit_redactor(self.path), require_kit=True)

    def allowed_account_ids(self):
        return ["conta-sintetica"]


def run(work, rendered, name, schema, backend=None, matches=True, mutate=None, kit=None):
    out, rec, plan, graph, cfg, kit0, sink = setup_case(work, rendered, name, schema, matches)
    if kit is not None:
        sink = ex.Sink(work / "out", kit.redactor())
    kit = kit or kit0
    if mutate:
        mutate(rec, cfg)
    be = backend or backends.RecordedBackend(rec)
    sl, ck = fake_clock()
    r = ex.execute(out, plan["plan_id"], cfg, be, kit, sink, graph, sleep=sl, clock=ck)
    return r, be, sink


def test_offline_demo_matches_expected_and_validates(work):
    from bo.contracts import validate as v
    rep = ex.offline_demo(work / "demo")
    assert len(rep["cases"]) == 12
    assert all(c["outcome"] == c["expect"] for c in rep["cases"]), rep["cases"]
    for f, kind in (("readback.jsonl", "readback"), ("outcomes.jsonl", "outcomes"),
                    ("intent_manifest.jsonl", "intent_manifest"), ("run_manifest.jsonl", "run_manifest")):
        assert v.validate(kind, work / "demo" / f).ok, f


def test_intent_is_written_before_apply(work, rendered, schema):
    order = []

    class Spy(backends.RecordedBackend):
        def apply(self, w, tv):
            order.append(("apply", (work / "out" / "intent_manifest.jsonl").exists()))
            return super().apply(w, tv)
    rec = json.loads((REC / "net01_persisted.json").read_text())
    r, be, _ = run(work, rendered, "net01_persisted", schema, backend=Spy(rec))
    assert order == [("apply", True)]
    stages = [x["stage"] for x in r.runs if x["intent_id"].endswith("-r1")]
    assert stages == ["intent", "creating", "created", "confirmed", "removal_requested", "absent"]


def test_unknown_input_and_unbound_symbol_never_touch_backend(work, rendered, schema):
    for name, frag in (("db01_unknown_input", "UNKNOWN_INPUT: instance_class"), ("sto01_unbound", "UNKNOWN_INPUT")):
        r, be, sink = run(work, rendered, name, schema)
        assert be.calls == [] and r.intents == [] and r.outcome["outcome"]["value"] == "UNKNOWN"
        assert r.outcome["outcome"]["detail"].startswith(frag)
        shutil.rmtree(work / "out")


def test_identity_outside_allowlist_creates_nothing(work, rendered, schema):
    r, be, _ = run(work, rendered, "net01_persisted", schema, matches=False)
    assert be.calls == [] and r.outcome["outcome"]["value"] == "INFRA_ERROR" and r.intents == []


def test_region_context_mismatch_is_unknown_input(work, rendered, schema):
    out, rec, plan, graph, cfg, kit, sink = setup_case(work, rendered, "net01_persisted", schema)
    graph = dict(graph, contexts=[{"key": "region", "state": "known", "value": "us-east-1"}])
    be = backends.RecordedBackend(rec)
    r = ex.execute(out, plan["plan_id"], cfg, be, kit, sink, graph)
    assert be.calls == [] and "região" in r.outcome["outcome"]["detail"]


def test_secret_generated_in_memory_and_never_written(work, rendered, schema):
    seen = {}

    class Spy(backends.RecordedBackend):
        def apply(self, w, tv):
            seen.update(tv)
            return super().apply(w, tv)
    rec = json.loads((REC / "db02_persisted.json").read_text())
    r, be, sink = run(work, rendered, "db02_persisted", schema, backend=Spy(rec))
    secret = seen["lp_aws_db_02_secret_1"]
    assert len(secret) >= 24
    for f in (work / "out").glob("*.jsonl"):
        assert secret not in f.read_text()
    pw = next(x for x in r.readback["fields"] if x["path"] == "r1.password")
    assert pw == {"path": "r1.password", "state": "withheld", "redaction": {"rule_id": "REDACT-SECRET-01",
                                                                            "at_source": True}}
    assert r.outcome["outcome"]["value"] == "PERSISTED"
    assert not list((ex.pins.tmp_root() / "ephemeral").glob("RUN-HAWS-009*"))


def test_real_ids_only_symbolic_in_readback(work, rendered, schema):
    r, _, _ = run(work, rendered, "net01_persisted", schema)
    f = {x["path"]: x for x in r.readback["fields"]}
    assert f["r2.vpc_id"] == {"path": "r2.vpc_id", "state": "read", "value": "ref:r1"}
    text = (work / "out" / "readback.jsonl").read_text()
    assert "vpc-0" not in text and "subnet-0" not in text


def test_foreign_identifier_is_withheld_and_diagnostic_scrubbed(work, rendered, schema):
    def mut(rec, cfg):
        for rd in rec["reads"]:
            for res in rd["values"]["root_module"]["resources"]:
                if res["type"] == "aws_subnet":
                    res["values"]["vpc_id"] = ARN
    r, _, _ = run(work, rendered, "net01_persisted", schema, mutate=mut)
    f = {x["path"]: x for x in r.readback["fields"]}
    assert f["r2.vpc_id"]["state"] == "withheld" and f["r2.vpc_id"]["redaction"]["rule_id"] == "REDACT-IDENT-01"
    assert r.outcome["outcome"]["value"] == "NOT_READABLE"
    shutil.rmtree(work / "out")

    def mut2(rec, cfg):
        rec["apply"] = {"ok": False, "diagnostics": [{"severity": "error", "summary": "x",
                                                      "detail": f"User {ARN} StatusCode: 400 InvalidParameterValue"}]}
    r, _, _ = run(work, rendered, "db02_rejected", schema, mutate=mut2)
    assert r.outcome["outcome"]["value"] == "REJECTED_BY_API"
    assert D12 not in json.dumps(r.outcome) and "<arn>" in r.outcome["outcome"]["detail"]
    assert D12 not in (work / "out" / "outcomes.jsonl").read_text()


def test_destroy_failure_leaves_removal_pending(work, rendered, schema):
    r, be, _ = run(work, rendered, "net01_residue", schema)
    assert r.outcome["outcome"]["value"] == "PERSISTED"
    assert r.runs[-1]["stage"] == "removal_pending" and r.notes


def test_destroy_runs_even_when_apply_fails(work, rendered, schema):
    r, be, _ = run(work, rendered, "sec02_throttled", schema)
    assert r.outcome["outcome"]["value"] == "INFRA_ERROR" and be.calls[-2:] == ["destroy", "state_list"]


def test_sink_refuses_outside_paths_and_privacy_findings(work, schema):
    with pytest.raises(ex.SinkError):
        ex.Sink(Path("/Users/breno/doutorado/brevops-data/OUTRO-MODULO"), redact.Redactor())
    sink = ex.Sink(work / "o", redact.Redactor())
    bad = {"outcome_id": "OUT-1", "case_id": "CASE-1", "group_id": "G-1", "claim_id": "CLM-X-01", "side": "object",
           "outcome": {"axis": "persistence", "value": "UNKNOWN", "detail": "custo de US" + "$" + " 12" + ".50 na fatura"},
           "evidence_state_before": "DOC_SUPPORTED", "evidence_state_after": "DOC_SUPPORTED",
           "rule_id": "HAWS-JUDGE-01", "decided_at": "2026-11-03T07:00:00-03:00"}
    with pytest.raises(ex.SinkError, match="privacy"):
        sink.append("outcomes.jsonl", "outcomes", [bad])
    bad["outcome"]["detail"] = "ok ok"
    bad["evidence_state_after"] = "PERSISTENCE_VERIFIED"      # C12-LADDER: só sobe com PERSISTED
    with pytest.raises(ex.SinkError, match="contrato"):
        sink.append("outcomes.jsonl", "outcomes", [bad])
    assert not (work / "o" / "outcomes.jsonl").exists()


def test_classify_rules():
    e = lambda d: [{"severity": "error", "summary": "", "detail": d}]  # noqa: E731
    assert ex.classify(e("ThrottlingException: Rate exceeded"))[0] == "INFRA_ERROR"
    assert ex.classify(e("StatusCode: 400, api error InvalidParameterValue"))[0] == "REJECTED_BY_API"
    assert ex.classify(e("AccessDenied"))[0] == "INFRA_ERROR"
    assert ex.classify(e("algo novo"))[0] == "UNKNOWN"


# ------------------------------------------------------------------------------------------ CLI (binário falso)
def test_cli_backend_refuses_without_go(monkeypatch):
    monkeypatch.delenv("BO_CLOUD_GO", raising=False)
    with pytest.raises(backends.GoRefused):
        backends.TerraformCLIBackend("/bin/false", backends.GoToken("RUN-X", True))
    monkeypatch.setenv("BO_CLOUD_GO", "RUN-X")
    with pytest.raises(backends.GoRefused):
        backends.TerraformCLIBackend("/bin/false", backends.GoToken("RUN-X", False))


def test_cli_backend_full_cycle_with_fake_terraform(work, rendered, schema, monkeypatch):
    fake = work / "bin" / "terraform"
    fake.parent.mkdir()
    fake.write_text(f"#!/bin/sh\nexec {sys.executable} -I {FX / 'fake_terraform.py'} \"$@\"\n")
    fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
    log = work / "fake.log"
    monkeypatch.setenv("BO_CLOUD_GO", "RUN-HAWS-009")
    monkeypatch.setenv("AWS_PROFILE", "nao-deve-vazar")
    be = backends.TerraformCLIBackend(str(fake), backends.GoToken("RUN-HAWS-009", True),
                                      credential_env={"BO_FAKE_TF_REC": str(REC / "db02_persisted.json"),
                                                      "BO_FAKE_TF_LOG": str(log)})
    r, _, _ = run(work, rendered, "db02_persisted", schema, backend=be, kit=KitWithRedactor(schema, work / "kr.py"))
    assert r.outcome["outcome"]["value"] == "PERSISTED"
    calls = [json.loads(x) for x in log.read_text().splitlines()]
    cmds = [c["args"][0] + ("-refresh" if "-refresh-only" in c["args"] else "") for c in calls]
    assert cmds[:3] == ["init", "apply", "apply-refresh"] and cmds[-2:] == ["destroy", "state"]
    envs = set().union(*[set(c["env"]) for c in calls])
    assert "AWS_PROFILE" not in envs and "TF_VAR_lp_aws_db_02_secret_1" in envs
    assert "TF_VAR_bo_allowed_account_ids" in envs and "conta-sintetica" not in log.read_text()
    assert {"LP-AWS-DB-02.tf", "providers.tf", "variables.tf", "versions.tf"} <= set(calls[1]["cwd_files"])
    assert not any(f.startswith("LP-AWS-NET") for f in calls[1]["cwd_files"])


def test_cli_run_refused_without_kit_redactor_or_allowlist(work, rendered, schema, monkeypatch):
    monkeypatch.setenv("BO_CLOUD_GO", "RUN-HAWS-009")
    be = backends.TerraformCLIBackend("/bin/false", backends.GoToken("RUN-HAWS-009", True))
    r, _, sink = run(work, rendered, "db02_persisted", schema, backend=be)
    o = r.outcome["outcome"]
    # Duas recusas válidas, na ordem do executor: sem o redator do kit (deploy/safety/redactor.py ausente) ou,
    # com o kit presente, pela allowlist de contas vazia do kit offline. Cada estado do kit tem a sua.
    esperado = "redator do kit" if sink.red.kit_fn is None else "allowlist de contas vazia"
    assert o["value"] == "INFRA_ERROR" and r.outcome["rule_id"] == "HAWS-IDENT-01"
    assert esperado in o["detail"] and "nada foi criado" in o["detail"]
    # nada criado: nenhuma intenção, nenhum manifesto de intenção (só o desfecho foi gravado)
    assert r.intents == [] and "intent_manifest.jsonl" not in sink.written
    assert set(sink.written) == {"outcomes.jsonl"}


def test_object_literal_missing_required_key_is_unknown_input(work):
    from bo.harness.aws import schema as sch
    full = sch.load_pinned()
    # procura no schema fixado um atributo objeto configurável com chave obrigatória
    found = None
    for t in full.types():
        for n, a in full.resource(t).attributes.items():
            if a.configurable and render._object_required_keys(a.type):
                found = (t, n, sorted(render._object_required_keys(a.type)))
                break
        if found:
            break
    assert found, "o schema fixado não tem atributo objeto com chave obrigatória"
    t, n, keys = found
    plan = {"plan_id": "LP-OBJ-01", "graph_id": "GIR-OBJ-01", "target_provider": "aws",
            "dependency_closure": {"closed": True, "missing": []},
            "steps": [{"order": 1, "action": "create", "node_id": "r1", "resource_type": t, "depends_on": [],
                       "typed_choices": [], "losses": [], "symbolic_unknowns": [],
                       "values": [{"field": n, "origin": "carried", "marked": False,
                                   "term": {"kind": "literal", "datatype": "map", "value": {}}}]}]}
    pr = render.render_plan(plan, None, full)
    assert pr.status == "UNKNOWN_INPUT"
    assert {m["field"] for m in pr.missing} >= {f"{n}.{k}" for k in keys}
