"""O gate de resolução reprova adulterações (não passa por vacuidade)."""
import json

import pytest

from bo.gold_libcloud import build as B
from bo.gold_libcloud import resolve as R


@pytest.fixture()
def files(tmp_path):
    d = B.out_dir()
    out = {}
    for n in ("libcloud.sssom.tsv", "api_fields.jsonl", "coverage.jsonl"):
        p = tmp_path / n
        p.write_text((d / n).read_text(encoding="utf-8"), encoding="utf-8")
        out[n] = p
    return out


def run(files):
    return R.check(files["libcloud.sssom.tsv"], files["api_fields.jsonl"], files["coverage.jsonl"])


def test_published_files_resolve(files):
    rep = run(files)
    assert rep["ok"], rep["failures"][:5]
    assert rep["rows_by_evidence_state"].get("UNRESOLVED", 0) > 0


def test_unregistered_subject_fails(files):
    p = files["libcloud.sssom.tsv"]
    t = p.read_text(encoding="utf-8")
    p.write_text(t.replace("_to_node/element/instanceId\t", "_to_node/element/instanceIdX\t", 1), encoding="utf-8")
    assert any(f.startswith("S3") for f in run(files)["failures"])


def test_wrong_site_line_fails(files):
    p = files["api_fields.jsonl"]
    recs = [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines()]
    tgt = next(r for r in recs if r["subject_id"].endswith("_to_node/element/instanceId"))
    tgt["sites"] = [{"file": tgt["sites"][0]["file"], "line": 1}]
    p.write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in recs), encoding="utf-8")
    assert any(f.startswith("S3") and "segmento" in f for f in run(files)["failures"])


def test_missing_unresolved_row_fails(files):
    p = files["libcloud.sssom.tsv"]
    lines = p.read_text(encoding="utf-8").splitlines(keepends=True)
    drop = next(i for i, ln in enumerate(lines) if not ln.startswith("#") and "\tUNRESOLVED\t" in ln)
    p.write_text("".join(lines[:drop] + lines[drop + 1:]), encoding="utf-8")
    assert any(f.startswith("S5") for f in run(files)["failures"])


def test_object_outside_base_fails(files):
    p = files["libcloud.sssom.tsv"]
    t = p.read_text(encoding="utf-8")
    p.write_text(t.replace("\tlcm:compute.Node.id\t", "\tlcm:compute.Node.idx\t", 1), encoding="utf-8")
    assert any(f.startswith("S2") for f in run(files)["failures"])
