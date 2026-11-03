"""Fixtures dos testes offline do HARNESS-OCI (nenhum teste toca nuvem; terraform só em fmt/validate no sandbox)."""
import copy
import json
import os
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
os.environ.setdefault("BO_REPO", str(REPO))
os.environ.setdefault("BO_DATA", "/Users/breno/doutorado/brevops-data")
os.environ.setdefault("BO_TMP", os.path.join(os.environ["BO_DATA"], "tmp", "HARNESS-OCI"))

EX = REPO / "deploy" / "fixtures" / "oci" / "_templates" / "examples"
REC = HERE / "fixtures" / "recordings"


def load_jsonl(p):
    return [json.loads(x) for x in Path(p).read_text(encoding="utf-8").splitlines() if x.strip()]


@pytest.fixture
def tmp_out(request):
    """Pasta exclusiva do teste dentro de $BO_TMP (nunca /tmp)."""
    base = Path(os.environ["BO_TMP"]) / "pytest" / request.node.name.replace("[", "_").replace("]", "_")
    if base.exists():
        import shutil
        shutil.rmtree(base)
    base.mkdir(parents=True)
    return base


@pytest.fixture
def example_plans():
    return {p["plan_id"]: p for p in load_jsonl(EX / "lowering_plan.jsonl")}


def write_plan(d: Path, plans, bindings=None, graph=True):
    d.mkdir(parents=True, exist_ok=True)
    (d / "lowering_plan.jsonl").write_text("".join(json.dumps(p) + "\n" for p in plans), encoding="utf-8")
    if graph:
        (d / "graph_ir.jsonl").write_text((EX / "graph_ir.jsonl").read_text(encoding="utf-8"), encoding="utf-8")
    b = None
    if bindings is not False:
        b = d / "bindings.json"
        src = json.loads((EX / "bindings.json").read_text(encoding="utf-8"))
        if isinstance(bindings, dict):
            src["bindings"] = [{"symbol_id": k, "key": v} for k, v in bindings.items()]
        b.write_text(json.dumps(src), encoding="utf-8")
    return d / "lowering_plan.jsonl", b


def make_case(cid, plan_id, graph_id, comparator=None, domain="NET"):
    return {"case_id": cid, "group_id": "G-" + cid[5:], "claim_id": "CLM-OCI-EX-01",
            "claim_version_id": "CLM-OCI-EX-01@1", "comparator": comparator or {"name": "exact"},
            "cost_class": "free",
            "frame_ref": {"path": "$BO_DATA/DEPSAMPLE/frame.jsonl", "sha256": "0" * 64},
            "lowering_plan": {"plan_id": plan_id, "graph_id": graph_id}, "origin": "sample", "side": "object",
            "stratum": {"cardinality": "1:1", "direction": "forward", "domain": domain, "pair": "AWSOCI",
                        "relation": "exact"},
            "values": [{"var": "?x", "term": {"kind": "literal", "datatype": "number", "value": 1}}], "weight": 1}


def mutate(plan, order, fn):
    p = copy.deepcopy(plan)
    fn(next(s for s in p["steps"] if s["order"] == order))
    return p
