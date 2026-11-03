"""Verificador de não inserção: aceita o render honesto, pega cada tipo de inserção, troca e perda."""
import shutil

from azh_helpers import REF

from bo.harness.azurerm import no_silent_insert as N
from bo.harness.azurerm import render as R
from bo.harness.azurerm import schema as S
from bo.harness.azurerm._common import read_jsonl


def _module(work, pid="LP-AZREF-0001"):
    R.render_file(REF / "lowering_plan.jsonl", work / "out", plan_id=pid)
    plan = next(p for p in read_jsonl(REF / "lowering_plan.jsonl") if p["plan_id"] == pid)
    graph = R.load_graphs(REF / "lowering_plan.jsonl", None)[plan["graph_id"]]
    return work / "out", plan, graph


def _check(d, plan, graph):
    return N.check_module(d, plan, graph, S.load(), S.templates_manifest(), {})


def test_honest_render_passes(work):
    for pid in ("LP-AZREF-0001", "LP-AZREF-0002"):
        d, plan, graph = _module(work / pid, pid)
        assert _check(d, plan, graph) == [], pid


def _mutate(d, work, fn, fname="main.tf"):
    m = work / "mut"
    if m.exists():
        shutil.rmtree(m)
    shutil.copytree(d, m)
    (m / fname).write_text(fn((m / fname).read_text()))
    return m


def test_each_mutation_is_caught_with_the_right_message(work):
    d, plan, graph = _module(work)
    cases = {
        "folha inserida": lambda t: t.replace('  account_tier             = "Standard"\n',
                                              '  account_tier             = "Standard"\n  access_tier = "Hot"\n'),
        "≠ plano": lambda t: t.replace('"TLS1_2"', '"TLS1_0"'),
        "sumiu do HCL": lambda t: t.replace('  min_tls_version          = "TLS1_2"\n', ""),
        "sem passo no plano": lambda t: t + '\nresource "azurerm_resource_group" "zz" {\n  name = "x"\n}\n',
        "variável sem entrada": lambda t: t + '\nvariable "extra" {\n  type = string\n}\n',
        "meta-argumento proibido": lambda t: t.replace('resource "azurerm_subnet" "r4" {\n',
                                                       'resource "azurerm_subnet" "r4" {\n  count = 2\n'),
        "depends_on": lambda t: t.replace("depends_on = [azurerm_resource_group.r1, azurerm_virtual_network.r3]",
                                          "depends_on = [azurerm_resource_group.r1]"),
    }
    for want, fn in cases.items():
        errs = _check(_mutate(d, work, fn), plan, graph)
        assert any(want in e for e in errs), (want, errs)


def test_provider_and_template_changes_are_caught(work):
    d, plan, graph = _module(work)
    m = _mutate(d, work, N.provider_mutant, "versions.tf")
    errs = _check(m, plan, graph)
    assert any("versions.tf difere" in e for e in errs)
    assert any("resource_provider_registrations" in e for e in errs)
    m = _mutate(d, work, lambda t: t.replace('"= 5.12.0"', '">= 5.0"'), "versions.tf")
    assert _check(m, plan, graph)
    (m / "extra.tf").write_text('locals {\n  a = 1\n}\n')
    errs = _check(m, plan, graph)
    assert any("arquivos .tf inesperados" in e for e in errs)


def test_gate_run_default_inputs_is_not_vacuous(work):
    rep = N.run(N.default_inputs(), work / "nsi")
    assert rep["ok"], rep["errors"]
    assert rep["modules_checked"] == 3  # 2 da referência + o plano azurerm do stub C26 (emenda 2)
    assert rep["mutants"] == rep["mutants_caught"] >= 21
    statuses = sorted(p["status"] for f in rep["files"] for p in f["plans"])
    assert statuses == ["BLOCKED", "RENDERED", "RENDERED", "RENDERED", "WRONG_PROVIDER", "WRONG_PROVIDER",
                        "WRONG_PROVIDER"]


def test_gate_fails_when_nothing_renders(work):
    from azh_helpers import plan_with, step, write_plan
    plan, graph = plan_with([step(1, "r1", "google_compute_network", [])], provider="google")
    rep = N.run([write_plan(work, plan, graph)], work / "nsi")
    assert not rep["ok"]
    assert any("vacuidade" in e for e in rep["errors"])


def test_dotted_path_into_map_attribute(work):
    from azh_helpers import lit, plan_with, step, val, write_plan
    vals = [val("location", lit("string", "x")), val("tags.env", lit("string", "t")),
            val("tags.team", lit("string", "bo"))]
    plan, graph = plan_with([step(1, "r1", "azurerm_resource_group", vals, name="bo-{t1}-rg")])
    p = write_plan(work, plan, graph)
    R.render_file(p, work / "out")
    assert "tags = {\n    env  = \"t\"\n    team = \"bo\"\n  }" in (work / "out" / "main.tf").read_text()
    assert _check(work / "out", plan, graph) == []
    m = _mutate(work / "out", work, lambda t: t.replace('    team = "bo"\n', '    team = "bo"\n    extra = "z"\n'))
    errs = _check(m, plan, graph)
    assert any("tags.extra" in e for e in errs), errs
    m = _mutate(work / "out", work, lambda t: t.replace('"bo"\n  }', '"xx"\n  }'))
    assert any("tags.team" in e for e in _check(m, plan, graph))
