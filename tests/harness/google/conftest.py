"""Fixtures do HARNESS-GCP: BO_TMP exclusivo do módulo (nunca /tmp), caso C11 sintético e plano da fixture."""
import os
from pathlib import Path

os.environ.setdefault("BO_DATA", "/Users/breno/doutorado/brevops-data")
os.environ["BO_TMP"] = str(Path(os.environ["BO_DATA"]) / "tmp" / "HARNESS-GCP")
os.environ["TMPDIR"] = os.environ["BO_TMP"]
Path(os.environ["BO_TMP"]).mkdir(parents=True, exist_ok=True)

import json  # noqa: E402
import shutil  # noqa: E402
import uuid  # noqa: E402

import pytest  # noqa: E402

from bo.harness.google import common as C  # noqa: E402

HERE = Path(__file__).resolve().parent
PLANS = C.templates() / "plans"


def load_fixture(name):
    return C.read_jsonl(PLANS / name / "lowering_plan.jsonl")[0], C.read_jsonl(PLANS / name / "graph_ir.jsonl")[0]


def recorded(name):
    return json.loads((C.templates() / "recorded" / name).read_text(encoding="utf-8"))


def case_for(plan, comparator=None):
    return {"case_id": "CASE-" + plan["plan_id"].removeprefix("LP-"), "group_id": "G-HG-0001",
            "claim_id": "CLM-EX-01", "claim_version_id": "CLM-EX-01@2", "comparator": comparator or {"name": "exact"},
            "cost_class": "low", "frame_ref": {"path": "$BO_DATA/DEPSAMPLE/frame.jsonl", "sha256": "0" * 64},
            "lowering_plan": {"plan_id": plan["plan_id"], "graph_id": plan["graph_id"]}, "origin": "sample",
            "side": "object", "stratum": {"cardinality": "1:1", "direction": "forward", "domain": "DB",
                                          "pair": "AWSGCP", "relation": "exact"},
            "values": [{"term": {"datatype": "number", "kind": "literal", "value": 7}, "var": "pa:x"}],
            "weight": 1.0}


@pytest.fixture
def work():
    d = C.tmp() / "pytest" / uuid.uuid4().hex[:12]
    d.mkdir(parents=True)
    yield d
    shutil.rmtree(d, ignore_errors=True)
