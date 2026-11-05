"""Regras como dados (vocabulário fechado), lint de higiene, gates de prioridade e de UNKNOWN, adaptador C25."""

import copy
import json
import os
import subprocess
import sys

import pytest
import yaml

from bo.grain import battery as B
from bo.grain import lint as L
from bo.grain import priority, unknown_exit
from bo.grain import rules as R
from bo.grain.common import rules_path
from bo.grain.evidence import C25Adapter, FixtureAdapter

RAW = yaml.safe_load(rules_path().read_text(encoding="utf-8"))


def test_rules_load_and_order():
    rs = R.load()
    assert [r.id for r in rs.rules] == ["GRAIN-G0-IDENTITY", "GRAIN-G1-BINDING", "GRAIN-G1b-REFERENCE", "GRAIN-G2-COMPONENT",
                                        "GRAIN-G2-CHILD",
                                        "GRAIN-G3-FACET", "GRAIN-G4-ENTITY", "GRAIN-G4-NS", "GRAIN-G0-NOMATCH"]
    assert rs.status == "PROVISIONAL"


@pytest.mark.parametrize("mut", ["unknown_predicate", "no_g0", "bad_class", "dup_priority", "bad_needs"])
def test_rules_parse_rejects(mut):
    raw = copy.deepcopy(RAW)
    rules = raw["rules"]
    if mut == "unknown_predicate":
        rules[3]["guard"]["name_suffix"] = ["x"]
    elif mut == "no_g0":
        raw["rules"] = [r for r in rules if r["id"] != "GRAIN-G0-IDENTITY"]
    elif mut == "bad_class":
        rules[4]["match"]["identity_class_in"] = ["LOOKS_LIKE_ENTITY"]
    elif mut == "dup_priority":
        rules[2]["priority"] = rules[1]["priority"]
    elif mut == "bad_needs":
        rules[1]["needs"] = ["resource_type"]
    with pytest.raises(R.RulesError):
        R.parse(raw)


def test_lint_clean_and_mutants():
    text = rules_path().read_text(encoding="utf-8")
    assert L.lint_text(text) == []
    assert L.selftest(text) == []


def test_priority_gate():
    rep = priority.run()
    assert rep["ok"], rep["checks"]


def test_unknown_exit_gate_and_control():
    rep = unknown_exit.run()
    assert rep["ok"], rep["violations"][:5]
    assert rep["stats"]["became_unknown"] > 100
    ctl = unknown_exit.run(unknown_exit.broken_rules(R.load()))
    assert not ctl["ok"] and any(v.startswith(("A ", "E ")) for v in ctl["violations"])


def test_decision_independent_of_node_order():
    rs = R.load()
    w = B.all_worlds()["nic"]
    from bo.grain import schema as S
    from bo.grain.engine import decide_graph
    res = B.run_schema(w, rs)
    nodes = list(res.nodes.values())
    a = {k: (d.grain, d.rule) for k, d in decide_graph(nodes, rs).items()}
    b = {k: (d.grain, d.rule) for k, d in decide_graph(list(reversed(nodes)), rs).items()}
    assert a == b


def _c25(eid, rt, fact, value=None, status="stated", level="derived", derived_from=None, reason=None):
    r = {"evidence_id": eid, "provider": "provider_b", "pin": {"provider_version": "1.0.0"},
         "api_resource": {"service": "compute", "resource": "InterfaceAttachment"},
         "terraform_resource_type": rt, "fact_kind": fact, "status": status, "level": level}
    if status == "stated":
        r["value"] = value
    else:
        r["unknown_reason"] = reason
    if level == "derived":
        r["derived_from"] = derived_from or ["SE-root"]
    if level == "published":
        r["citation"] = {"uri": "https://docs.example.org/provider-b/attachments", "retrieved_at":
                         "2026-11-03T02:00:00-03:00", "sentence": "frase sintética: a anexação liga instância e interface"}
    return r


def test_c25_adapter_matches_fixture_adapter(tmp_path):
    """O mesmo fato expresso em C25 dá a mesma decisão que a evidência neutra da fixture."""
    w = B.all_worlds()["nic"]
    recs = [
        _c25("SE-root", "b_nic_attachment", "identity", {"status": "present", "scope": "independent",
                                                          "key_fields": ["id"], "surrogate": True,
                                                          "api_status": "resource",
                                                          "label": "interface attachment"}, level="published"),
        _c25("SE-2", "b_nic_attachment", "import_key", {"status": "present", "fields": ["instance", "interface"]}),
        _c25("SE-3", "b_nic_attachment", "lifecycle_controller", "self"),
        _c25("SE-4", "b_nic_attachment", "owner", "self"),
        _c25("SE-5", "b_nic_attachment", "effective_scope", "self"),
    ]
    p = tmp_path / "service_evidence.jsonl"
    p.write_text("".join(json.dumps(r) + "\n" for r in recs))
    v = subprocess.run([sys.executable, "-I", "-m", "bo.contracts.validate", "C25", str(p)], capture_output=True,
                       text=True, env=dict(os.environ))
    assert v.returncode == 0, v.stdout + v.stderr
    extra = {cid: w["evidence"][cid] for cid in w["evidence"] if cid != "b_nic_attachment"}
    extra["b_nic_attachment"] = {k: w["evidence"]["b_nic_attachment"][k] for k in ("field_map", "references")}
    ad = C25Adapter(recs, extra=extra)
    from bo.grain import schema as S
    rs = R.load()
    res_c25 = S.decompose_schema(S.candidates_from_tf_schema(w["provider"], w["schema"]), ad, rs)
    res_fx = S.decompose_schema(S.candidates_from_tf_schema(w["provider"], w["schema"]),
                                FixtureAdapter(w["evidence"]), rs)
    assert S.signature(res_c25) == S.signature(res_fx)
    # fato desconhecido por contradição no C25 vira UNKNOWN
    recs2 = recs[:2] + [_c25("SE-3", "b_nic_attachment", "lifecycle_controller", status="unknown",
                             reason="contradictory")] + recs[3:]
    res2 = S.decompose_schema(S.candidates_from_tf_schema(w["provider"], w["schema"]), C25Adapter(recs2, extra),
                              rs)
    d = res2.decisions["b_nic_attachment"]
    assert d.grain == "UNKNOWN" and "lifecycle_controller" in d.missing
