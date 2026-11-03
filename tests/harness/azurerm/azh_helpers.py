"""Ajudantes dos testes do HARNESS-AZURE: tudo em $BO_TMP do módulo (nunca /tmp), planos montados em Python e validados
pelo validador único (C26) antes de renderizar; respostas gravadas em fixtures/recorded/ (sintéticas)."""
import copy
import json
import os
import shutil
from pathlib import Path

import pytest

os.environ.setdefault("BO_DATA", "/Users/breno/doutorado/brevops-data")
os.environ.setdefault("BO_TMP", str(Path(os.environ["BO_DATA"]) / "tmp" / "HARNESS-AZURE"))
os.environ.setdefault("TMPDIR", os.environ["BO_TMP"])
Path(os.environ["BO_TMP"]).mkdir(parents=True, exist_ok=True)

HERE = Path(__file__).resolve().parent
FIX = HERE / "fixtures"
REPO = HERE.parents[2]
REF = REPO / "deploy" / "fixtures" / "azurerm" / "_templates" / "reference"
SYM = {"kind": "symbol", "symbol_id": "SYM-a1b2c3d4e5f60718", "name_class": "variable", "scope": "repo"}
RG_REF = {"kind": "reference", "target_type": "azurerm_resource_group", "target_address":
          "azurerm_resource_group.SYM-0000aaaa1111bbbb", "attribute": "name"}


@pytest.fixture
def work(request):
    p = Path(os.environ["BO_TMP"]) / "pytest" / request.node.name.replace("[", "_").replace("]", "")
    if p.exists():
        shutil.rmtree(p)
    p.mkdir(parents=True)
    return p


def lit(dt, v):
    return {"kind": "literal", "datatype": dt, "value": v}


def val(field, term, origin="carried"):
    return {"field": field, "term": term, "origin": origin, "marked": origin != "carried"}


def step(order, node, rtype, values, deps=(), name=None, action="create", choices=()):
    s = {"order": order, "action": action, "node_id": node, "resource_type": rtype, "values": values,
         "depends_on": list(deps), "losses": [], "symbolic_unknowns": [], "typed_choices": list(choices)}
    if name:
        s["derived_name"] = {"template": name, "from_terms": ["t1"]}
    return s


def rg_step():
    return step(1, "r1", "azurerm_resource_group", [val("location", lit("string", "brazilsouth"), "synthesized")],
                name="bo-{t1}-rg")


def plan_with(steps, plan_id="LP-T-0001", closed=True, missing=(), provider="azurerm"):
    nodes = sorted({s["node_id"] for s in steps}, key=lambda n: int(n[1:]))
    graph = {"graph_id": "GIR-T-0001", "case_id": "CASE-T-0001", "source_provider": "aws",
             "terms": [{"term_id": "t1", "term": SYM}],
             "resources": [{"node_id": n, "class_iri": "x:Thing"} for n in nodes if n.startswith("r")],
             "components": [], "references": [], "preconditions": [], "contexts": []}
    plan = {"plan_id": plan_id, "graph_id": "GIR-T-0001", "target_provider": provider,
            "dependency_closure": {"closed": closed, "missing": list(missing)}, "steps": copy.deepcopy(steps)}
    return plan, graph


def write_plan(work: Path, plan, graph) -> Path:
    (work / "graph_ir.jsonl").write_text(json.dumps(graph) + "\n", encoding="utf-8")
    p = work / "lowering_plan.jsonl"
    p.write_text(json.dumps(plan) + "\n", encoding="utf-8")
    return p


def recording(name):
    return json.loads((FIX / "recorded" / name).read_text(encoding="utf-8"))
