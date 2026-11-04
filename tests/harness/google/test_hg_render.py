"""Renderizador: fixtures renderizam e passam no fmt; cada falta/defeito do plano reprova o caso com o código certo."""
import copy
import json
import re
import shutil
import subprocess

import pytest

from bo.harness.google import common as C
from bo.harness.google import render as R
from bo.harness.google.schema import is_settable
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


# Plano google do stub do C26 de antes da emenda 2 do CONTRACTS (3c2141f), guardado como fixture do harness: a
# emenda trocou o stub por um plano por provedor e o google passou a ser o LP-HG-BUCKET, que renderiza. O caso
# de obrigatório ausente (database_version) e campo fora do schema continua provado com o plano original.
PRE_EMENDA2 = C.templates() / "c26_stub_pre_emenda2"
STUB = C.repo() / "contracts" / "stubs" / "C26" / "lowering_plan.jsonl"


def test_stub_do_c26_por_provedor_so_o_google_renderiza(work):
    rc, rep = R.render_file(STUB, work / "out")
    st = {p["plan_id"]: p["status"] for p in rep["plans"]}
    provs = {p["plan_id"]: p["target_provider"] for p in C.read_jsonl(STUB)}
    assert rc == 0 and sorted(provs.values()) == ["aws", "azurerm", "google", "oci"]
    for pid, prov in provs.items():
        assert st[pid] == ("RENDERED" if prov == "google" else "WRONG_PROVIDER"), (pid, st[pid])
    other = [p for p in rep["plans"] if p["status"] != "RENDERED"]
    assert all([f["code"] for f in p["failures"]] == ["WRONG_PROVIDER"] for p in other)
    google = [pid for pid, prov in provs.items() if prov == "google"]
    assert sorted(x.name for x in (work / "out").iterdir()) == sorted(
        ["render_report.json", "versions.tf"] + [R.file_name(pid) for pid in google])


def test_stub_do_c26_falha_unknown_input_sem_hcl(work):
    rc, rep = R.render_file(PRE_EMENDA2 / "lowering_plan.jsonl", work / "out")
    assert [p["target_provider"] for p in C.read_jsonl(PRE_EMENDA2 / "lowering_plan.jsonl")] == ["google"]
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
    # perda + valor no mesmo campo deixou de ser conflito (achado do PILOT-STO-E2E); conflito é o mesmo campo duas vezes
    (lambda p: p["steps"][1]["values"].append(dict(p["steps"][1]["values"][1])), "CONFLICTING_VALUES"),
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


# ------------------------------------------------------------------ HI-GCP-01: rótulo bo-run da execução
def test_lista_do_rotulo_bate_com_a_tabela_do_safety():
    from bo.harness.google import run_label as RL
    assert (C.repo() / RL.SAFETY_TABLE).is_file(), "tabela de SKUs do SAFETY ausente"
    assert sorted(RL.types()) == RL.from_safety_table()
    # todo tipo da lista que o índice compacto conhece tem labels map(string) configurável
    for t in sorted(RL.types()):
        b = SCHEMA.block("resource", t)
        if b is not None:
            a = b["attributes"].get("labels")
            assert a is not None and a["type"] == ["map", "string"] and is_settable(a), t


@pytest.mark.parametrize("name", FIXTURES)
def test_rotulo_bo_run_so_nos_tipos_rastreados_por_rotulo(name):
    from bo.harness.google import run_label as RL
    plan, graph = load_fixture(name)
    r = render(plan, graph)
    assert r.status == "RENDERED", r.failures
    var = RL.var_name(C.slug(plan["plan_id"]))
    labeled = sorted(a for a in r.addresses.values() if not a.startswith("data.") and a.split(".")[0] in RL.types())
    got = sorted(x["address"] for x in r.ledger if x["path"] == "labels.bo-run")
    assert got == labeled
    assert all(x["origin"] == "harness_declared" and x["insertion_id"] == "HI-GCP-01"
               for x in r.ledger if x["path"] == "labels.bo-run")
    vs = [v for v in r.variables if v["kind"] == "run_label"]
    if labeled:
        assert [v["name"] for v in vs] == [var] and not vs[0]["sensitive"] and sorted(vs[0]["used_by"]) == labeled
        assert f"var.{var}" in r.hcl and f'variable "{var}"' in r.hcl
    else:
        assert vs == [] and "bo-run" not in r.hcl


def test_rotulo_bo_run_na_fixture_bucket_e_no_kms_pubsub():
    b = render(*load_fixture("bucket"))
    assert any(x["path"] == "labels.bo-run" and x["address"] == "google_storage_bucket.lp_hg_bucket_r1"
               for x in b.ledger)
    assert re.search(r"\n +bo-run += var\.lp_hg_bucket_bo_run\n", b.hcl)
    # a tag de execução vem só da inserção HI-GCP-01: nenhum valor do plano é rótulo bo_* (C26-NOTAG)
    plan, _ = load_fixture("bucket")
    assert not any(v["field"].startswith("labels.bo") for s in plan["steps"] for v in s["values"])
    assert [x["origin"] for x in b.ledger if x["path"].startswith("labels.bo")] == ["harness_declared"]
    k = render(*load_fixture("kms_pubsub"))
    tipos = sorted(x["address"].split(".")[0] for x in k.ledger if x["path"] == "labels.bo-run")
    assert tipos == ["google_kms_crypto_key", "google_pubsub_subscription", "google_pubsub_topic"]
    assert not any(x["address"].startswith("data.") for x in k.ledger if x["path"] == "labels.bo-run")


def test_rotulo_bo_run_vindo_do_plano_e_conflito():
    plan, graph = load_fixture("bucket")
    plan["steps"][0]["values"].append({"field": "labels.bo-run", "marked": False, "origin": "carried",
                                       "term": {"datatype": "string", "kind": "literal", "value": "fixo"}})
    r = render(plan, graph)
    assert r.status == "CONFLICTING_VALUES" and r.hcl is None
    assert any("labels.bo-run" in f["detail"] for f in r.failures)


def test_rotulo_nao_altera_o_termo_do_plano():
    plan, graph = load_fixture("bucket")
    plan["steps"][0]["values"] = [v for v in plan["steps"][0]["values"] if not v["field"].startswith("labels.")]
    plan["steps"][0]["values"].append({"field": "labels", "marked": False, "origin": "carried",
                                       "term": {"datatype": "map", "kind": "literal", "value": {"env": "sandbox"}}})
    before = copy.deepcopy(plan)
    r = render(plan, graph)
    assert r.status == "RENDERED", r.failures
    assert plan == before and re.search(r'\n +env += "sandbox"\n +bo-run += var\.lp_hg_bucket_bo_run\n', r.hcl)


# ------------------------------------------------------------------ termo list (C00 3.1.0) e forma indexada (C26-LIST)
def _fw(name="net_list"):
    plan, graph = load_fixture(name)
    return plan, graph, next(st for st in plan["steps"] if st["resource_type"] == "google_compute_firewall")


def test_termo_list_de_literais_e_de_referencias():
    plan, graph, fw = _fw()
    r = render(plan, graph)
    assert r.status == "RENDERED", r.failures
    assert 'source_ranges           = ["10.0.0.0/8", "192.168.0.0/16"]' in r.hcl
    assert ("target_service_accounts = [google_service_account.lp_hg_netlist_r2.email, "
            "google_service_account.lp_hg_netlist_r3.email]") in r.hcl
    assert 'ports    = ["22", "443"]' in r.hcl and r.notes == []


def test_forma_indexada_antiga_monta_a_mesma_lista_com_nota():
    plan, graph, fw = _fw("net_list_indexed")
    r = render(plan, graph)
    assert r.status == "RENDERED", r.failures
    assert ("target_service_accounts = [google_service_account.lp_hg_netlistidx_r2.email, "
            "google_service_account.lp_hg_netlistidx_r3.email]") in r.hcl
    assert len(r.notes) == 3 and all("C26-LIST" in n for n in r.notes)


def test_forma_indexada_com_buraco_e_index_gap():
    plan, graph, fw = _fw("net_list_indexed")
    for v in fw["values"]:
        if v["field"] == "target_service_accounts.1":
            v["field"] = "target_service_accounts.2"
    r = render(plan, graph)
    assert r.status == "UNKNOWN_INPUT" and r.hcl is None and "INDEX_GAP" in codes(r)


def test_termo_list_e_indice_no_mesmo_atributo_e_conflito():
    plan, graph, fw = _fw()
    fw["values"].append({"field": "source_ranges.2", "marked": False, "origin": "carried",
                         "term": {"datatype": "string", "kind": "literal", "value": "172.16.0.0/12"}})
    r = render(plan, graph)
    assert r.hcl is None and "CONFLICTING_VALUES" in codes(r)


def test_termo_list_em_atributo_escalar_e_tipo_errado():
    plan, graph, fw = _fw()
    for v in fw["values"]:
        if v["field"] == "network":
            v["term"] = {"kind": "list", "items": [v["term"]]}
    r = render(plan, graph)
    assert r.hcl is None and "TYPE_MISMATCH" in codes(r)


def test_item_de_lista_com_tipo_errado_e_item_nao_suportado():
    plan, graph, fw = _fw()
    for v in fw["values"]:
        if v["field"] == "source_ranges":
            v["term"]["items"].append({"datatype": "number", "kind": "literal", "value": 7})
    assert "TYPE_MISMATCH" in codes(render(plan, graph))
    plan, graph, fw = _fw()
    for v in fw["values"]:
        if v["field"] == "source_ranges":
            v["term"]["items"].append({"kind": "withheld", "reason": "secret"})
    assert "UNSUPPORTED_TERM" in codes(render(plan, graph))


def test_lista_vazia_vira_colchetes():
    plan, graph, fw = _fw()
    for v in fw["values"]:
        if v["field"] == "source_ranges":
            v["term"]["items"] = []
    r = render(plan, graph)
    assert r.status == "RENDERED" and "source_ranges           = []" in r.hcl


# ------------------------------------------------------------------ achados do PILOT-STO-E2E (controls.json)
def test_referencia_por_target_node_a_conteiner_com_nome_literal():
    plan, graph, fw = _fw()
    r = render(plan, graph)
    # r2 e r3 não têm nome derivado: só o target_node acha o alvo
    assert not any("derived_name" in st for st in plan["steps"] if st["node_id"] in ("r2", "r3"))
    assert "google_service_account.lp_hg_netlist_r3.email" in r.hcl
    for v in fw["values"]:
        if v["field"] == "target_service_accounts":
            for it in v["term"]["items"]:
                del it["target_node"]
    r = render(plan, graph)
    assert r.hcl is None and "UNKNOWN_INPUT" in codes(r)


def test_target_node_de_outro_tipo_nao_resolve():
    plan, graph, fw = _fw()
    for v in fw["values"]:
        if v["field"] == "target_service_accounts":
            v["term"]["items"][0]["target_node"] = "r1"      # r1 é a rede, não a conta de serviço
    r = render(plan, graph)
    assert r.hcl is None and any("0 alvo(s)" in f["detail"] for f in r.failures)


def test_perda_declarada_em_campo_com_valor_renderiza_e_fica_no_relatorio():
    plan, graph, fw = _fw()
    assert [x["field"] for x in fw["losses"]] == ["source_ranges"]
    r = render(plan, graph)
    assert r.status == "RENDERED" and "source_ranges" in r.hcl
    assert [(x["field"], x["address"]) for x in r.losses] == [("source_ranges",
                                                              "google_compute_firewall.lp_hg_netlist_r4")]


def test_validate_offline_das_fixtures_de_lista(work):
    from bo.harness.google import tf_validate as TV
    outs = []
    for n in ("net_list", "net_list_indexed"):
        rc, rep = R.render_file(PLANS / n / "lowering_plan.jsonl", work / n)
        assert rc == 0 and rep["counts"]["failed"] == 0
        outs.append(work / n)
    assert all(TV.validate_dir(d)["ok"] for d in outs)
    # quebra de propósito: lista de referências num atributo escalar do HCL tem de reprovar no validate
    f = outs[0] / "lp_hg_netlist.tf"
    f.write_text(f.read_text().replace("network                 = google_compute_network.lp_hg_netlist_r1.id",
                                       "network                 = [google_compute_network.lp_hg_netlist_r1.id]"))
    assert TV.validate_dir(outs[0])["ok"] is False


def test_readback_de_lista_com_referencias():
    from bo.harness.google import readback as RB
    plan, graph, fw = _fw()
    leaves = [lf for lf in RB.plan_leaves(plan, graph, SCHEMA) if lf["path"] == "target_service_accounts"]
    assert len(leaves) == 1 and leaves[0]["set_attr"]
    lf = leaves[0]
    st = {"google_service_account.lp_hg_netlist_r2": {"values": {"email": "a@x"}},
          "google_service_account.lp_hg_netlist_r3": {"values": {"email": "b@x"}}}
    f = lambda v: {"state": "read", "value": v}
    cmp = {"name": "exact"}
    assert RB.judge_leaf(lf, f(["b@x", "a@x"]), cmp, st) == "match"          # set: sem ordem
    assert RB.judge_leaf(lf, f(["a@x"]), cmp, st) == "mismatch"
    assert RB.judge_leaf(lf, f(["a@x", "c@x"]), cmp, st) == "mismatch"
    assert RB.judge_leaf(lf, f(["a@x", "b@x"]), cmp, {}) == "symbolic"
