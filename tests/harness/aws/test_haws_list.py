"""Termo list (C00 3.1.0) e forma indexada antiga (C26 1.3.0, C26-LIST) no renderizador e no no_silent_insert."""
import copy
import json

import pytest

from bo.harness.aws import no_silent_insert as nsi
from bo.harness.aws import render

from conftest import PLANS


def _plans():
    return {p["plan_id"]: p for p in render.read_jsonl(PLANS)}


def _graphs():
    return {g["graph_id"]: g for g in render.read_jsonl(PLANS.with_name("graph_ir.jsonl"))}


def _render(plan, schema):
    return render.render_plan(plan, _graphs().get(plan["graph_id"]), schema)


def _lb(plan):
    return next(s for s in plan["steps"] if s["resource_type"] == "aws_lb")


def _set(plan, field, term):
    st = _lb(plan)
    st["values"] = [v for v in st["values"] if v["field"] != field and not v["field"].startswith(field + ".")]
    st["values"].append({"field": field, "marked": False, "origin": "carried", "term": term})
    return plan


@pytest.fixture
def schema():
    from bo.harness.aws import schema as sch
    return sch.load(None)


def test_lista_de_referencias_vira_lista_hcl_na_ordem(schema):
    pr = _render(_plans()["LP-AWS-NET-02"], schema)
    assert pr.status == "RENDERED", pr.problems + pr.missing
    assert "subnets            = [aws_subnet.lp_aws_net_02_r2.id, aws_subnet.lp_aws_net_02_r3.id]" in pr.text
    assert "security_groups    = [aws_security_group.lp_aws_net_02_r4.id]" in pr.text
    refs = [r for r in pr.record["references"] if r["field"].startswith("subnets")]
    assert [r["to_step"] for r in refs] == [2, 3]


def test_forma_indexada_antiga_rende_o_mesmo_hcl_com_nota(schema):
    a = _render(_plans()["LP-AWS-NET-02"], schema).text.replace("net_02", "X")
    pr = _render(_plans()["LP-AWS-NET-03"], schema)
    assert pr.status == "RENDERED"
    assert pr.text.replace("net_03", "X").split("\n", 2)[2] == a.split("\n", 2)[2]
    assert any(n.startswith("C26-LIST:") and "subnets" in n for n in pr.record["notes"])
    assert {x["field"] for x in pr.provenance} >= {"subnets.0", "subnets.1", "security_groups.0"}


def test_lista_de_literais_e_lista_vazia(schema):
    p = _set(copy.deepcopy(_plans()["LP-AWS-NET-02"]), "subnets",
             {"kind": "list", "items": [{"kind": "literal", "datatype": "string", "value": "subnet-sintetica-a"}]})
    pr = _render(p, schema)
    assert pr.status == "RENDERED" and 'subnets            = ["subnet-sintetica-a"]' in pr.text
    p = _set(copy.deepcopy(_plans()["LP-AWS-NET-02"]), "subnets", {"kind": "list", "items": []})
    pr = _render(p, schema)
    assert pr.status == "RENDERED" and "subnets            = []" in pr.text


def test_lista_de_simbolos_vira_variavel(schema):
    p = _set(copy.deepcopy(_plans()["LP-AWS-NET-02"]), "subnets", {"kind": "list", "items": [
        {"kind": "symbol", "symbol_id": "SYM-b1c2d3e4f5a6ffff", "name_class": "variable", "scope": "repo"}]})
    pr = _render(p, schema)
    assert pr.status == "RENDERED" and "[var.lp_aws_net_02_sym_b1c2d3e4f5a6ffff]" in pr.text
    assert any(v["symbol_id"] == "SYM-b1c2d3e4f5a6ffff" for v in pr.variables)


@pytest.mark.parametrize("fields,why", [
    ({"subnets.0": 2, "subnets.2": 3}, "índices"),                 # buraco
    ({"subnets.1": 2}, "índices"),                                 # não começa em 0
])
def test_lista_indexada_com_buraco_e_recusada(schema, fields, why):
    p = copy.deepcopy(_plans()["LP-AWS-NET-03"])
    st = _lb(p)
    syms = {2: "SYM-b1c2d3e4f5a60002", 3: "SYM-b1c2d3e4f5a60003"}
    st["values"] = [v for v in st["values"] if not v["field"].startswith("subnets.")]
    for f, o in fields.items():
        st["values"].append({"field": f, "marked": False, "origin": "carried", "term": {
            "kind": "reference", "target_type": "aws_subnet", "target_address": f"aws_subnet.{syms[o]}",
            "attribute": "id"}})
    pr = _render(p, schema)
    assert pr.status == "INVALID_PLAN" and any(why in x["reason"] for x in pr.problems)
    assert "subnets" not in pr.text


def test_mistura_de_termo_list_e_indice_e_recusada(schema):
    p = copy.deepcopy(_plans()["LP-AWS-NET-02"])
    _lb(p)["values"].append({"field": "subnets.0", "marked": False, "origin": "carried", "term": {
        "kind": "reference", "target_type": "aws_subnet", "target_address": "aws_subnet.SYM-b1c2d3e4f5a60002",
        "attribute": "id"}})
    pr = _render(p, schema)
    assert pr.status == "INVALID_PLAN" and any("duas vezes" in x["reason"] for x in pr.problems)


def test_list_em_atributo_que_nao_e_lista_e_recusado(schema):
    p = _set(copy.deepcopy(_plans()["LP-AWS-NET-02"]), "load_balancer_type",
             {"kind": "list", "items": [{"kind": "literal", "datatype": "string", "value": "application"}]})
    pr = _render(p, schema)
    assert pr.status == "INVALID_PLAN" and any("não é atributo lista" in x["reason"] for x in pr.problems)


def test_item_literal_de_outro_tipo_e_recusado(schema):
    p = _set(copy.deepcopy(_plans()["LP-AWS-NET-02"]), "subnets",
             {"kind": "list", "items": [{"kind": "literal", "datatype": "number", "value": 7}]})
    pr = _render(p, schema)
    assert pr.status == "INVALID_PLAN" and any("elemento do schema é string" in x["reason"] for x in pr.problems)


@pytest.mark.parametrize("item", [
    {"kind": "withheld", "reason": "secret"},
    {"kind": "document", "format": "json", "tree": {"a": 1}, "symbolized": []},
    {"kind": "list", "items": []},
])
def test_item_nao_suportado_em_lista_e_recusado(schema, item):
    p = _set(copy.deepcopy(_plans()["LP-AWS-NET-02"]), "subnets", {"kind": "list", "items": [item]})
    pr = _render(p, schema)
    assert pr.status == "INVALID_PLAN" and any("dentro de lista" in x["reason"] for x in pr.problems)
    assert not any(v["kind"] == "secret" for v in pr.variables)


def test_no_silent_insert_confere_o_alvo_de_cada_item(rendered, work):
    out, _ = rendered
    rep = nsi.check_render(out)
    assert rep["findings"] == []
    import shutil
    d = work / "m"
    shutil.copytree(out, d)
    nsi._edit(d / "LP-AWS-NET-02.tf", "[aws_subnet.lp_aws_net_02_r2.id, aws_subnet.lp_aws_net_02_r3.id]",
              "[aws_subnet.lp_aws_net_02_r3.id, aws_subnet.lp_aws_net_02_r2.id]")
    f = nsi.check_render(d)["findings"]
    assert [x["path"] for x in f] == ["aws_lb.lp_aws_net_02_r5.subnets"] and "item 0" in f[0]["detail"]
