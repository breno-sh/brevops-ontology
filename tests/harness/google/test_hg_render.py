"""Renderizador: fixtures renderizam e passam no fmt; cada falta/defeito do plano reprova o caso com o código certo."""
import copy
import json
import shutil
import subprocess

import pytest

from bo.harness.google import common as C
from bo.harness.google import render as R
from conftest import PLANS, load_fixture

SCHEMA = R.Schema.load()
FIXTURES = sorted(p.name for p in PLANS.iterdir() if p.is_dir())


def render(plan, graph):
    return R.render_plan(plan, graph, SCHEMA)


def codes(r):
    return [f["code"] for f in r.failures]


@pytest.mark.parametrize("name", FIXTURES)
def test_fixture_renderiza_e_passa_no_fmt(name, work):
    rc, rep = R.render_file(PLANS / name / "lowering_plan.jsonl", work / "out")
    assert rc == 0 and rep["counts"]["rendered"] == 1, rep["plans"][0]["failures"]
    p = subprocess.run([shutil.which("terraform"), f"-chdir={work / 'out'}", "fmt", "-check", "-diff"],
                       capture_output=True, text=True)
    assert p.returncode == 0, p.stdout
    text = (work / "out" / R.file_name(rep["plans"][0]["plan_id"])).read_text()
    assert "default" not in text


def test_render_deterministico(work):
    a = R.render_file(PLANS / "net_sql" / "lowering_plan.jsonl", work / "a")[1]
    b = R.render_file(PLANS / "net_sql" / "lowering_plan.jsonl", work / "b")[1]
    for f in a["files"]:
        assert (work / "a" / f).read_text() == (work / "b" / f).read_text()


def test_stub_do_c26_falha_unknown_input_sem_hcl(work):
    stub = C.repo() / "contracts" / "stubs" / "C26" / "lowering_plan.jsonl"
    rc, rep = R.render_file(stub, work / "out")
    p = rep["plans"][0]
    assert rc == 0 and p["status"] == "UNKNOWN_INPUT"
    assert set(codes(type("x", (), {"failures": p["failures"]}))) == {"FIELD_NOT_IN_SCHEMA", "UNKNOWN_INPUT"}
    assert any("database_version" in f["detail"] for f in p["failures"])
    assert sorted(x.name for x in (work / "out").iterdir()) == ["render_report.json", "versions.tf"]


def test_obrigatorio_ausente_e_unknown_input():
    plan, graph = load_fixture("net_sql")
    plan["steps"][1]["values"] = [v for v in plan["steps"][1]["values"] if v["field"] != "settings.tier"]
    r = render(plan, graph)
    assert r.status == "UNKNOWN_INPUT" and r.hcl is None
    assert any("settings.tier" in f["detail"] for f in r.failures)


def test_obrigatorio_de_bloco_so_conta_com_o_bloco():
    # backup_retention_settings.retained_backups é obrigatório só se o bloco existe
    plan, graph = load_fixture("net_sql")
    plan["steps"][2]["values"] = [plan["steps"][2]["values"][0]]
    assert render(plan, graph).status == R.RENDERED


def test_referencia_nao_e_inferida_do_grafo():
    plan, graph = load_fixture("net_fw")
    plan["steps"][1]["values"] = [v for v in plan["steps"][1]["values"] if v["field"] != "network"]
    r = render(plan, graph)
    assert r.status == "UNKNOWN_INPUT" and any("network" in f["detail"] for f in r.failures)


@pytest.mark.parametrize("mut,code", [
    (lambda p: p["steps"][1]["values"].append({"field": "connection_name", "origin": "carried", "marked": False,
                                              "term": {"kind": "literal", "datatype": "string", "value": "x"}}),
     "COMPUTED_ONLY"),
    (lambda p: p["steps"][1]["values"][1].update(term={"kind": "literal", "datatype": "number", "value": 7}),
     "TYPE_MISMATCH"),
    (lambda p: p["steps"][1]["values"][4].update(term={"kind": "literal", "datatype": "string", "value": "abcdefgh"}),
     "WITHHELD_LITERAL"),
    (lambda p: p["steps"][1]["values"].append({"field": "settings.user_labels", "origin": "carried", "marked": False,
                                              "term": {"kind": "expression", "op": "merge", "args": []}}),
     "UNSUPPORTED_TERM"),
    (lambda p: p["steps"][1]["typed_choices"][0].update(selected=None), "CHOICE_UNRESOLVED"),
    (lambda p: p["steps"][2]["losses"].append({"code": "X_LOSS", "field": "settings.backup_configuration.enabled"}),
     "CONFLICTING_VALUES"),
    (lambda p: p["steps"][1]["values"].append({"field": "settings.database_flags.name", "origin": "carried",
                                              "marked": False,
                                              "term": {"kind": "literal", "datatype": "string", "value": "x"}}),
     "AMBIGUOUS_BLOCK_INDEX"),
    (lambda p: p["steps"][1]["values"].append({"field": "settings.nao_existe", "origin": "carried", "marked": False,
                                              "term": {"kind": "literal", "datatype": "string", "value": "x"}}),
     "FIELD_NOT_IN_SCHEMA"),
    (lambda p: p["steps"][0].update(resource_type="google_compute_ha_vpn_gateway"), "UNSUPPORTED_TYPE"),
    (lambda p: p.update(target_provider="aws"), "WRONG_PROVIDER"),
    (lambda p: p.update(dependency_closure={"closed": False, "missing": ["r9"]}), "PLAN_NOT_CLOSED"),
])
def test_defeito_do_plano_reprova_com_codigo(mut, code):
    plan, graph = load_fixture("net_sql")
    mut(plan)
    r = render(plan, graph)
    assert r.status != R.RENDERED and r.hcl is None
    assert code in codes(r), r.failures
    assert all(R.FAIL_TO_BLOCK[c] for c in codes(r))


def test_withheld_nao_segredo_e_unknown_input():
    plan, graph = load_fixture("net_sql")
    plan["steps"][1]["values"][4]["term"] = {"kind": "withheld", "reason": "environment"}
    r = render(plan, graph)
    assert r.status == "UNKNOWN_INPUT"


def test_guarda_falsa_e_guarda_adiada():
    plan, graph = load_fixture("net_sql")
    g2 = copy.deepcopy(graph)
    g2["contexts"][1]["value"] = "enterprise_plus"
    assert "CONDITION_FALSE" in codes(render(plan, g2))
    plan2, graph2 = load_fixture("kms_pubsub")
    r = render(plan2, graph2)
    assert r.status == R.RENDERED and len(r.deferred_guards) == 1 and r.deferred_guards[0]["terms"] == ["object.region"]


def test_nome_derivado_sem_atributo_name():
    plan, graph = load_fixture("net_fw")
    plan["steps"][2] = {**plan["steps"][2], "resource_type": "google_project_iam_member",
                        "values": [], "depends_on": []}
    r = render(plan, graph)
    assert "DERIVED_NAME_NO_FIELD" in codes(r)


def test_endereco_duplicado():
    plan, graph = load_fixture("kms_pubsub")
    plan["steps"][4]["node_id"] = "r1"
    plan["steps"][4]["action"] = "create"
    plan["steps"][4]["resource_type"] = "google_kms_key_ring"
    assert "CONFLICTING_VALUES" in codes(render(plan, graph))


def test_variaveis_sem_default_e_segredo_sensivel():
    plan, graph = load_fixture("net_sql")
    r = render(plan, graph)
    kinds = {v["name"]: v for v in r.variables}
    sec = [v for v in kinds.values() if v["kind"] == "runtime_secret"]
    assert len(sec) == 1 and sec[0]["sensitive"] and "sensitive   = true" in r.hcl
    assert "default" not in r.hcl


def test_entrada_invalida_no_c26_nao_escreve_nada(work):
    plan, graph = load_fixture("net_sql")
    plan["steps"][0]["values"][0]["marked"] = False
    C.write_jsonl(work / "lowering_plan.jsonl", [plan])
    C.write_jsonl(work / "graph_ir.jsonl", [graph])
    rc, rep = R.render_file(work / "lowering_plan.jsonl", work / "out")
    assert rc == 1 and rep["errors"] and not (work / "out").exists()


def test_saida_fora_do_bo_tmp_e_recusada():
    with pytest.raises(SystemExit):
        R.prepare_out(C.repo() / "results" / "HARNESS-GCP" / "render")


def test_saida_com_arquivo_alheio_e_recusada(work):
    (work / "out").mkdir()
    (work / "out" / "alheio.tf").write_text("# outro\n")
    with pytest.raises(SystemExit):
        R.prepare_out(work / "out")
    assert (work / "out" / "alheio.tf").exists()


def test_relatorio_lista_sintetizados_marcados(work):
    rc, rep = R.render_file(PLANS / "net_sql" / "lowering_plan.jsonl", work / "out")
    syn = rep["plans"][0]["synthesized"]
    assert {(s["field"], s["origin"]) for s in syn} == {("auto_create_subnetworks", "synthesized"),
                                                         ("deletion_protection", "synthesized"),
                                                         ("settings.ip_configuration.ipv4_enabled", "default_declared")}
    assert all(s["marked"] for s in syn)
    assert json.loads((work / "out" / "render_report.json").read_text())["counts"]["failed"] == 0
