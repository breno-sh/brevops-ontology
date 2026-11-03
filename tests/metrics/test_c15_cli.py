"""Documento C15 válido no validador único, lacuna do est, comandos de consumo, regeneração idêntica."""
import json
import os
import subprocess
import sys

import pytest

from bo.metrics import bounds_present, build, c15, core, denominator_invariance
from bo.metrics.spec import load_spec, spec_by_id
from conftest import ROOT

SPEC = spec_by_id(load_spec())


def _validate(path):
    env = {**os.environ, "BO_REPO": str(ROOT)}
    r = subprocess.run([sys.executable, "-I", "-m", "bo.contracts.validate", "results", str(path)],
                       capture_output=True, text=True, env=env)
    return r.returncode, r.stdout + r.stderr


def test_stub_document_is_valid_c15(tmp_path):
    doc = build.stub_readings(ROOT)
    p = tmp_path / "r.json"
    p.write_text(json.dumps(doc), encoding="utf-8")
    rc, out = _validate(p)
    assert rc == 0, out
    assert {m["metric_id"] for m in doc["metrics"]} == {"M-OPCOV-DEC__aws__google", "M-BEHAV-DEC__aws__google"}
    assert {x["metric_id"] for x in doc["data"]["est_undefined"]} == {"M-PERS-DEC__aws__google",
                                                                     "M-OPCOV-PERS-DEC__aws__google"}


def test_entries_cover_all_28_metrics_and_validate(tmp_path):
    entries = []
    for mid in SPEC:
        e = c15.metric_entry(mid, "aws->google", core.Bounds(0.2, 0.6, 0.4, 10), SPEC[mid])
        assert not any("ceiling" in k or "teto" in k for k in json.dumps(e))
        entries.append(e)
    doc = c15.result_document("METRICSLIB", "2026-11-03T07:30:00-03:00", entries)
    p = tmp_path / "all.json"
    p.write_text(json.dumps(doc), encoding="utf-8")
    rc, out = _validate(p)
    assert rc == 0, out
    assert len(doc["metrics"]) == 28


def test_correlated_with_only_cites_ids_in_document():
    ok, _ = c15.entries_for("M-OPCOV-PERS-DEC", {"aws->google": core.Bounds(0.1, 0.5, 0.3, 4)},
                            SPEC["M-OPCOV-PERS-DEC"], correlated=["M-OPCOV-DEC", "M-PERS-DEC"])
    doc = c15.result_document("METRICSLIB", "2026-11-03T07:30:00-03:00", ok)
    assert "correlated_with" not in doc["metrics"][0]["joint_uncertainty"]


def test_contract_gap_est_undefined_is_not_invented():
    with pytest.raises(c15.ContractGap):
        c15.metric_entry("M-PERS-DEC", "aws->google", core.Bounds(0.0, 1.0, None, 3), SPEC["M-PERS-DEC"])
    ok, und = c15.entries_for("M-PERS-DEC", {"aws->google": core.Bounds(0.0, 1.0, None, 3)}, SPEC["M-PERS-DEC"])
    assert ok == [] and und[0]["lower"] == 0.0 and und[0]["upper"] == 1.0 and und[0]["n"] == 3


def test_bounds_present_on_directory(tmp_path):
    doc = build.stub_readings(ROOT)
    (tmp_path / "a.json").write_text(json.dumps(doc), encoding="utf-8")
    n, errs = bounds_present.check_dir(tmp_path)
    assert n == 4 and errs == []
    doc["metrics"][0]["operational_coverage"]["est"] = 1.5
    del doc["metrics"][1]["operational_coverage"]["upper"]
    (tmp_path / "a.json").write_text(json.dumps(doc), encoding="utf-8")
    n, errs = bounds_present.check_dir(tmp_path)
    assert len(errs) == 2
    empty = tmp_path / "vazio"
    empty.mkdir()
    assert bounds_present.check_dir(empty)[0] == 0


def test_denominator_invariance_command_on_stubs():
    assert denominator_invariance.main(["METRICSLIB", "--stubs"]) == 0


def test_build_check_regenerates_identically():
    assert build.main(["--check"]) == 0
