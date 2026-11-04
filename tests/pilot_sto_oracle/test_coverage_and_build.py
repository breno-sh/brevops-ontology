"""O gate de cobertura reprova o que promete reprovar (cópias em $BO_TMP; nada do repositório é alterado)."""
import json
import os
import shutil
from pathlib import Path

import pytest

from bo.pilot_sto_oracle import build, oracle_coverage, schema_check

REPO = Path(os.environ.get("BO_REPO", "/Users/breno/doutorado/brevops-ontology"))
DATA = Path(os.environ.get("BO_DATA", "/Users/breno/doutorado/brevops-data"))
TMP = Path(os.environ.get("BO_TMP", str(DATA / "tmp" / "PILOT-STO-ORACLE"))) / "pytest_cov"


@pytest.fixture()
def sandbox(monkeypatch):
    if TMP.exists():
        shutil.rmtree(TMP)
    repo, data = TMP / "repo", TMP / "data"
    shutil.copytree(REPO / "pilot" / "sto", repo / "pilot" / "sto", ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copytree(DATA / "PILOT-STO-ORACLE" / "sealed", data / "PILOT-STO-ORACLE" / "sealed")
    monkeypatch.setenv("BO_REPO", str(repo))
    monkeypatch.setenv("BO_DATA", str(data))
    monkeypatch.setenv("BO_TMP", str(TMP / "bo_tmp"))
    yield repo, data
    shutil.rmtree(TMP, ignore_errors=True)


def _errs():
    errs, _, _ = oracle_coverage.run("sto")
    return errs


def test_baseline_passes(sandbox):
    assert _errs() == []


def test_missing_polarity_fails(sandbox):
    repo, _ = sandbox
    p = repo / "pilot" / "sto" / "expected_answers.json"
    ea = json.loads(p.read_text())
    ea["fixtures"] = {k: v for k, v in ea["fixtures"].items() if not (v["case"] == "MC-VER" and v["polarity"] == "unknown")}
    p.write_text(json.dumps(ea))
    assert any("MC-VER: sem unknown na partição calib" in e for e in _errs())


def test_low_heldout_fraction_fails(sandbox):
    _, data = sandbox
    p = data / "PILOT-STO-ORACLE" / "sealed" / "SEALED_INDEX.json"
    idx = json.loads(p.read_text())
    idx["items"] = idx["items"][:20]
    p.write_text(json.dumps(idx))
    assert any("fração retida" in e for e in _errs())


def test_tampered_ciphertext_fails(sandbox):
    _, data = sandbox
    p = data / "PILOT-STO-ORACLE" / "sealed" / "heldout.cms.pem"
    p.write_text(p.read_text().replace("A", "B", 1))
    assert any("não bate com o sha do índice" in e for e in _errs())


def test_plaintext_leak_and_overlap_fail(sandbox):
    repo, data = sandbox
    ea = json.loads((repo / "pilot" / "sto" / "expected_answers.json").read_text())
    fid, meta = next(iter(sorted(ea["fixtures"].items())))
    fx = json.loads((repo / meta["file"]).read_text())
    ip = data / "PILOT-STO-ORACLE" / "sealed" / "SEALED_INDEX.json"
    idx = json.loads(ip.read_text())
    idx["items"].append({"item_id": "FX-STO-H-FAKE", "kind": "fixture", "case": "MC-VER", "polarity": "positive",
                         "provider": "aws", "sha256": build.item_hash(fx)})
    ip.write_text(json.dumps(idx))
    errs = _errs()
    assert any("texto claro de item retido" in e for e in errs)
    assert any("igual a uma retida" in e for e in errs)


def test_extra_file_in_sealed_dir_fails(sandbox):
    _, data = sandbox
    (data / "PILOT-STO-ORACLE" / "sealed" / "heldout.json").write_text("{}")
    assert any("arquivo inesperado" in e for e in _errs())


def test_wrong_slice_fails(sandbox):
    assert oracle_coverage.run("net")[0]


def test_calibration_fixtures_match_pinned_schema():
    assert schema_check.main([str(REPO / "pilot" / "sto" / "fixtures_calib")]) == 0


def test_schema_check_rejects_unknown_attribute():
    fx = {"fixture_id": "X", "provider": "aws", "terraform": {"resource": {"aws_s3_bucket": {"b": {"bucket": "fx", "nope": 1}}}}}
    assert schema_check.check_fixture(fx)


def test_sealed_dir_holds_only_ciphertext_index_and_public_cert():
    sd = DATA / "PILOT-STO-ORACLE" / "sealed"
    assert sorted(p.name for p in sd.iterdir()) == ["SEALED_INDEX.json", "heldout.cms.pem", "recipient_cert.pem"]
    assert "PRIVATE" not in (sd / "recipient_cert.pem").read_text()
    assert (sd / "heldout.cms.pem").read_text().startswith("-----BEGIN CMS-----")
