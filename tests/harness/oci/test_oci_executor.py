"""Executor offline: apply -> espera -> leitura -> destroy com respostas gravadas sintéticas, redator antes da gravação."""
import json
import os
from pathlib import Path

import pytest
from conftest import EX, REC, make_case, mutate, write_plan

from bo.contracts import validate as V
from bo.harness.oci import executor as E
from bo.harness.oci import kits as K
from bo.harness.oci import runners as RN

NET = ("LP-OCI-NET-0001", "GIR-OCI-NET-0001")
STO = ("LP-OCI-STO-0001", "GIR-OCI-STO-0001")


def run(name, plan, cid=None, comparator=None, plan_path=None, bindings=None, before="DOC_SUPPORTED", kit=None):
    kit = kit or K.OfflineKit()
    case = make_case(cid or f"CASE-T-{name.upper().replace('_', '-')}", *plan, comparator=comparator)
    res = E.run_case(case, plan_path or EX / "lowering_plan.jsonl", RN.RecordedRunner(REC / f"{name}.json"), kit,
                     bindings or EX / "bindings.json", evidence_before=before)
    return res, kit


@pytest.fixture(autouse=True)
def exec_base(tmp_out, monkeypatch):
    base = tmp_out / "exec"
    orig = E.exclusive_workdir
    monkeypatch.setattr(E, "exclusive_workdir", lambda cid, b=None: orig(cid, b or base))
    return base


def test_persisted_after_wait_with_reordered_set(exec_base):
    res, kit = run("net_persisted", NET)
    assert res.outcome == "PERSISTED", res.detail
    assert res.outcome_record["evidence_state_after"] == "PERSISTENCE_VERIFIED"
    ev = [e[0] for e in kit.events]
    assert ev == ["identity_ok", "intent", "created", "confirmed", "removal_requested", "removed"]
    assert res.readback["readback_id"] == res.outcome_record["readback_id"]


def test_altered_detected_on_set_block(exec_base):
    res, _ = run("net_altered", NET)
    assert res.outcome == "ALTERED"
    bad = [f for f in res.fields if f.match is False]
    assert [f.path for f in bad] == ["oci_core_security_list.r2.ingress_security_rules[1].stateless"]
    assert res.outcome_record["evidence_state_after"] == "DOC_SUPPORTED"


def test_wait_timeout_is_infra_error_and_still_destroys(exec_base):
    res, kit = run("net_timeout", NET)
    assert res.outcome == "INFRA_ERROR" and res.detail.startswith("WAIT_TIMEOUT")
    assert [e[0] for e in kit.events][-2:] == ["removal_requested", "removed"]
    assert res.readback is None and "readback_id" not in res.outcome_record


def test_api_errors_classified(exec_base):
    res, _ = run("sto_rejected", STO)
    assert res.outcome == "REJECTED_BY_API" and "400" in res.detail
    res, _ = run("net_throttled", NET)
    assert res.outcome == "INFRA_ERROR" and "429" in res.detail


def test_residue_after_destroy_raises_but_outcome_is_written(exec_base):
    with pytest.raises(E.ResidueError):
        run("sto_residue", STO)
    wd = next(exec_base.glob("CASE-T-STO-RESIDUE-*"))
    assert (wd / "outcomes.jsonl").exists()


def test_c12_files_validate_and_nothing_private_reaches_disk(exec_base):
    kit = K.OfflineKit()
    res, kit = run("sto_persisted", STO, kit=kit)
    assert res.outcome == "PERSISTED"
    for name in ("readback.jsonl", "outcomes.jsonl"):
        r = V.validate(name.split(".")[0], res.workdir / name)
        assert r.ok, r.errors
    private = [v for k, v in kit.context().items() if k != "region"] + list(kit._secrets.values())
    ocid_prefix = "oc" + "id1."
    for p in res.workdir.rglob("*"):
        if p.is_file():
            text = p.read_bytes().decode("utf-8", errors="replace")
            assert ocid_prefix not in text, p
            for v in private:
                assert v not in text, (p, "valor privado gravado")
    rb = json.loads((res.workdir / "readback.jsonl").read_text())
    paths = {f["path"] for f in rb["fields"]}
    assert not any("bucket_url" in x or "kms_key_id" in x or "etag" in x for x in paths)
    vals = {f["path"]: f.get("value") for f in rb["fields"]}
    assert vals["oci_objectstorage_bucket.r1.compartment_id"] == "bind:compartment_id"


def test_render_failure_never_applies(exec_base, tmp_out, example_plans):
    plan = mutate(example_plans["LP-OCI-STO-0001"], 1,
                  lambda s: s.__setitem__("values", [v for v in s["values"] if v["field"] != "name"]))
    pf, bf = write_plan(tmp_out / "in", [plan])
    kit = K.OfflineKit()
    runner = RN.RecordedRunner(REC / "sto_persisted.json")
    res = E.run_case(make_case("CASE-T-NOAPPLY", *STO), pf, runner, kit, bf)
    assert res.outcome == "UNKNOWN" and res.detail == "UNKNOWN_INPUT: MISSING_REQUIRED_FIELD"
    assert runner.calls == [] and kit.events == []
    assert V.validate("outcomes", res.workdir / "outcomes.jsonl").ok


def test_recording_bound_to_rendered_hcl(exec_base, tmp_out, example_plans):
    def f(s):
        for v in s["values"]:
            if v["field"] == "versioning":
                v["term"]["value"] = "Disabled"
    pf, bf = write_plan(tmp_out / "in", [mutate(example_plans["LP-OCI-STO-0001"], 1, f)])
    with pytest.raises(RN.RecordingMismatch, match="sha256"):
        E.run_case(make_case("CASE-T-MISMATCH", *STO), pf, RN.RecordedRunner(REC / "sto_persisted.json"),
                   K.OfflineKit(), bf)


def test_comparator_from_case(exec_base):
    res, _ = run("net_persisted", NET, cid="CASE-T-TOL", comparator={"name": "numeric_tolerance", "tolerance": 0})
    # numeric_tolerance não compara texto: os carried de texto ficam sem comparação -> UNKNOWN, nunca PERSISTED
    assert res.outcome == "UNKNOWN"


def test_evidence_ladder_never_downgrades(exec_base):
    res, _ = run("net_persisted", NET, cid="CASE-T-LADDER", before="OBSERVATION_TESTED")
    assert res.outcome_record["evidence_state_after"] == "OBSERVATION_TESTED"


def test_workdir_confined_to_bo_tmp():
    with pytest.raises(E.WorkdirError):
        E.exclusive_workdir("CASE-X", Path("/tmp/bo-harness-oci"))
    with pytest.raises(E.WorkdirError):
        E.exclusive_workdir("CASE-X", Path(os.environ["BO_DATA"]) / "HARNESS-OCI")


def test_workdirs_are_exclusive(exec_base):
    a = E.exclusive_workdir("CASE-X", exec_base)
    b = E.exclusive_workdir("CASE-X", exec_base)
    assert a != b and a.exists() and b.exists()


def test_live_paths_refused():
    kit = K.OfflineKit()
    with pytest.raises(PermissionError):
        RN.LiveRunner(kit, lock_held=True)
    with pytest.raises(K.SafetyKitMissing):
        K.live_kit()

    class FakeLive:
        recorded, live, identity = False, True, "sandbox-synthetic"
    with pytest.raises(K.IdentityMismatch):
        kit.check_identity(FakeLive())


def test_intent_must_precede_creation():
    kit = K.OfflineKit()
    with pytest.raises(RuntimeError, match="intenção"):
        kit.record("created", "CASE-Z")


def test_unsynthetic_recording_refused(tmp_out):
    rec = json.loads((REC / "sto_persisted.json").read_text())
    rec["synthetic"] = False
    p = tmp_out / "rec.json"
    p.write_text(json.dumps(rec))
    with pytest.raises(RN.RecordingMismatch):
        RN.RecordedRunner(p)


def test_classify_and_parse_errors():
    assert RN.classify_error(400, "InvalidParameter").outcome == "REJECTED_BY_API"
    assert RN.classify_error(400, "LimitExceeded").outcome == "INFRA_ERROR"
    for st in (401, 404, 409, 429, 500, None):
        assert RN.classify_error(st, "X").outcome == "INFRA_ERROR"
    err = ("Error: 400-InvalidParameter, bad cidr\nService error:InvalidParameter. Invalid cidr. "
           "http status code: 400. Opc request id: abc")
    assert RN.parse_service_error(err) == (400, "InvalidParameter")
    assert RN.parse_service_error("boom") == (None, None)


def test_recordings_are_regenerated_exactly():
    import make_recordings
    assert make_recordings.main(["--check"]) == 0


# ------------------------------------------------------------------ termo list (C00 3.1.0) e forma antiga (C26-LIST)
LST = ("LP-OCI-NET-0002", "GIR-OCI-NET-0002")
IDX = ("LP-OCI-NET-0003", "GIR-OCI-NET-0003")


def test_list_of_references_persisted_with_set_reordered(exec_base):
    res, _ = run("list_persisted", LST)
    assert res.outcome == "PERSISTED", res.detail
    f = next(x for x in res.fields if x.path == "oci_core_subnet.r4.security_list_ids")
    assert f.state == "read" and f.match is True and f.structural


def test_list_missing_item_is_altered(exec_base):
    res, _ = run("list_altered", LST)
    assert res.outcome == "ALTERED"
    assert [f.path for f in res.fields if f.match is False] == ["oci_core_subnet.r4.security_list_ids"]


def test_indexed_legacy_list_persisted(exec_base):
    res, _ = run("list_indexed_persisted", IDX)
    assert res.outcome == "PERSISTED", res.detail
    paths = [f.path for f in res.fields if "security_list_ids" in f.path]
    assert paths == ["oci_core_subnet.r4.security_list_ids[0]", "oci_core_subnet.r4.security_list_ids[1]"]
    assert V.validate("readback", _dump_readback(exec_base, res)).ok


def _dump_readback(base, res):
    p = Path(base) / "rb_idx.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(res.readback) + "\n", encoding="utf-8")
    return p
