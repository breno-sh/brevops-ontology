"""Renderizador: HCL = plano + declarados; falta de valor bloqueia (UNKNOWN_INPUT e afins), nunca default."""
import json

import hcl2
import pytest
from azh_helpers import FIX, REF, RG_REF, SYM, lit, plan_with, rg_step, step, val, write_plan

from bo.harness.azurerm import render as R
from bo.harness.azurerm import tf
from bo.harness.azurerm._common import HarnessError, repo


def rend(work, steps, **kw):
    plan, graph = plan_with(steps, **kw)
    p = write_plan(work, plan, graph)
    rep = R.render_file(p, work / "out")
    return rep["plans"][0], work / "out"


def codes(row):
    return sorted({(i["code"], i["field"]) for i in row["issues"]})


def sa_values(*drop):
    vals = [val("resource_group_name", RG_REF), val("location", lit("string", "brazilsouth")),
            val("account_tier", lit("string", "Standard")), val("account_replication_type", lit("string", "LRS"))]
    return [v for v in vals if v["field"] not in drop]


# ------------------------------------------------------------------------------------------------ referência
def test_reference_set_status_and_golden(work):
    rep = R.render_file(REF / "lowering_plan.jsonl", work / "out")
    st = {p["plan_id"]: p["status"] for p in rep["plans"]}
    assert st == {"LP-AZREF-0001": "RENDERED", "LP-AZREF-0002": "RENDERED", "LP-AZREF-0003": "BLOCKED"}
    assert rep["layout"] == "per_plan"
    for pid in ("LP-AZREF-0001", "LP-AZREF-0002"):
        got = (work / "out" / pid / "main.tf").read_text()
        assert got == (FIX / "golden" / f"{pid}.main.tf").read_text(), pid
    assert not (work / "out" / "LP-AZREF-0003").exists()


def test_reference_modules_pass_terraform_fmt(work):
    R.render_file(REF / "lowering_plan.jsonl", work / "out")
    ok, out = tf.fmt_check(work / "out")
    assert ok, out


def test_single_plan_layout_is_module_root(work):
    row, out = rend(work, [rg_step()])
    assert row["status"] == "RENDERED"
    assert sorted(p.name for p in out.iterdir()) == ["main.tf", "render_manifest.json", "render_report.json",
                                                    "versions.tf"]
    ok, msg = tf.fmt_check(out)
    assert ok, msg


# ------------------------------------------------------------------------------------------------ bloqueios
def test_missing_required_attribute_blocks_unknown_input(work):
    row, out = rend(work, [rg_step(), step(2, "r2", "azurerm_storage_account", sa_values("account_replication_type"),
                                           deps=[1], name="bo{t1}st")])
    assert row["status"] == "BLOCKED"
    assert ("UNKNOWN_INPUT", "account_replication_type") in codes(row)
    assert not list(out.rglob("*.tf"))


def test_rg_without_location_blocks(work):
    row, _ = rend(work, [step(1, "r1", "azurerm_resource_group", [], name="bo-{t1}-rg")])
    assert codes(row) == [("UNKNOWN_INPUT", "location")]


def test_missing_name_is_unknown_input_not_invented(work):
    row, _ = rend(work, [step(1, "r1", "azurerm_resource_group", [val("location", lit("string", "x"))])])
    assert codes(row) == [("UNKNOWN_INPUT", "name")]


def test_missing_required_block(work):
    vm = [val("resource_group_name", RG_REF), val("location", lit("string", "brazilsouth")),
          val("size", lit("string", "Standard_B1s")), val("admin_username", lit("string", "bo")),
          val("network_interface_ids", lit("list", []))]
    row, _ = rend(work, [rg_step(), step(2, "r2", "azurerm_linux_virtual_machine", vm, deps=[1], name="bo-{t1}-vm")])
    assert row["status"] == "BLOCKED"
    assert ("UNKNOWN_INPUT", "os_disk") in codes(row)


def test_required_attribute_inside_present_block(work):
    vals = sa_values() + [val("blob_properties.cors_rule", lit("list", [{"allowed_methods": ["GET"]}]))]
    row, _ = rend(work, [rg_step(), step(2, "r2", "azurerm_storage_account", vals, deps=[1], name="bo{t1}st")])
    got = codes(row)
    assert ("UNKNOWN_INPUT", "blob_properties[0].cors_rule[0].allowed_origins") in got
    assert ("UNKNOWN_INPUT", "blob_properties[0].cors_rule[0].max_age_in_seconds") in got


def test_symbol_in_value_position(work):
    vals = sa_values("account_tier") + [val("account_tier", SYM)]
    row, _ = rend(work, [rg_step(), step(2, "r2", "azurerm_storage_account", vals, deps=[1], name="bo{t1}st")])
    assert codes(row) == [("UNKNOWN_SYMBOLIC_INPUT", "account_tier")]


def test_withheld_non_secret_is_unknown_input(work):
    vals = [val("location", lit("string", "x")), val("tags", {"kind": "withheld", "reason": "environment"})]
    row, _ = rend(work, [step(1, "r1", "azurerm_resource_group", vals, name="bo-{t1}-rg")])
    assert codes(row) == [("UNKNOWN_INPUT", "tags")]


def test_open_dependency_closure_blocks(work):
    row, _ = rend(work, [rg_step()], closed=False, missing=["azurerm_virtual_network"])
    assert row["status"] == "BLOCKED"
    assert row["issues"][0]["code"] == "UNKNOWN_INPUT"


def test_unselected_typed_choice_is_ambiguous(work):
    ch = {"choice_id": "CH-T-1", "options": ["a", "b"], "selected": None, "reason": "edição desconhecida"}
    s = rg_step()
    s["typed_choices"] = [ch]
    row, _ = rend(work, [s])
    assert codes(row) == [("AMBIGUOUS_TARGET", None)]


def test_reference_without_dependency_and_ambiguous(work):
    row, _ = rend(work, [rg_step(), step(2, "r2", "azurerm_storage_account", sa_values(), deps=[], name="bo{t1}st")])
    assert ("UNKNOWN_INPUT", "resource_group_name") in codes(row)
    two = [rg_step(), step(2, "r9", "azurerm_resource_group", [val("location", lit("string", "x"))], name="bo-{t1}-b"),
           step(3, "r2", "azurerm_storage_account", sa_values(), deps=[1, 2], name="bo{t1}st")]
    row, _ = rend(work, two)
    assert ("AMBIGUOUS_TARGET", "resource_group_name") in codes(row)


# ------------------------------------------------------------------------------------------------ inválidos
@pytest.mark.parametrize("field,term,code", [
    ("nao_existe", lit("string", "x"), "FIELD_NOT_IN_SCHEMA"),
    ("primary_blob_endpoint", lit("string", "x"), "FIELD_NOT_CONFIGURABLE"),
    ("account_tier", lit("number", "Standard"), "TERM_DATATYPE"),
    ("blob_properties", lit("string", "x"), "BLOCK_VALUE_SHAPE"),
])
def test_plan_contradicting_schema_is_invalid(work, field, term, code):
    vals = sa_values("account_tier" if field == "account_tier" else "") + [val(field, term)]
    row, out = rend(work, [rg_step(), step(2, "r2", "azurerm_storage_account", vals, deps=[1], name="bo{t1}st")])
    assert row["status"] == "INVALID_PLAN"
    assert code in {c for c, _ in codes(row)}
    assert not list(out.rglob("*.tf"))


def test_unknown_type_and_wrong_provider(work):
    row, _ = rend(work, [step(1, "r1", "azurerm_nao_existe", [])])
    assert row["status"] == "INVALID_PLAN" and codes(row) == [("TYPE_NOT_IN_SCHEMA", None)]
    row, _ = rend(work, [step(1, "r1", "google_compute_network", [])], provider="google")
    assert row["status"] == "WRONG_PROVIDER"


def test_name_conflict_with_derived_name(work):
    s = rg_step()
    s["values"].append(val("name", lit("string", "outro")))
    row, _ = rend(work, [s])
    assert ("NAME_CONFLICT", "name") in codes(row)


# ------------------------------------------------------------------------------------------------ forma do HCL
def test_no_optional_attribute_is_added(work):
    row, out = rend(work, [rg_step(), step(2, "r2", "azurerm_storage_account", sa_values(), deps=[1], name="bo{t1}st")])
    doc = hcl2.loads((out / "main.tf").read_text())
    body = doc["resource"][1]['"azurerm_storage_account"']['"r2"']
    keys = {k for k in body if k != "__is_block__"}
    assert keys == {"name", "resource_group_name", "location", "account_tier", "account_replication_type",
                    "depends_on"}


def test_strings_never_become_interpolation(work):
    tricky = 'a"b\\c ${var.x} %{if} \n fim'
    vals = [val("location", lit("string", "x")), val("tags", lit("map", {"k": tricky, "k 2": "v"}))]
    row, out = rend(work, [step(1, "r1", "azurerm_resource_group", vals, name="bo-{t1}-rg")])
    assert row["status"] == "RENDERED"
    text = (out / "main.tf").read_text()
    assert "${var.x}" not in text.replace("$${var.x}", "")
    ok, msg = tf.fmt_check(out)
    assert ok, msg


def test_ownership_tags_are_declared_and_merged(work):
    vals = [val("location", lit("string", "x")), val("tags", lit("map", {"env": "t"}))]
    plan, graph = plan_with([step(1, "r1", "azurerm_resource_group", vals, name="bo-{t1}-rg")])
    p = write_plan(work, plan, graph)
    R.render_file(p, work / "out", ownership_tags={"bo-run": "RUN-1", "bo-case": "CASE-T-0001"})
    m = json.loads((work / "out" / "render_manifest.json").read_text())
    tag_entries = sorted(e["field"] for e in m["entries"] if e["origin"] == "harness.ownership_tag")
    assert tag_entries == ["tags.bo-case", "tags.bo-run"]
    doc = hcl2.loads((work / "out" / "main.tf").read_text())
    tags = doc["resource"][0]['"azurerm_resource_group"']['"r1"']["tags"]
    assert {k.strip('"'): v.strip('"') for k, v in tags.items()} == {"env": "t", "bo-run": "RUN-1",
                                                                     "bo-case": "CASE-T-0001"}
    with pytest.raises(HarnessError):
        R.render_file(p, work / "out2", ownership_tags={"Bad": "x"})


def test_secret_becomes_sensitive_variable_without_value(work):
    rep = R.render_file(REF / "lowering_plan.jsonl", work / "out", plan_id="LP-AZREF-0002")
    assert rep["plans"][0]["status"] == "RENDERED"
    m = json.loads((work / "out" / "render_manifest.json").read_text())
    kinds = {i["variable"]: i["kind"] for i in m["inputs"]}
    assert kinds == {"secret_r2_administrator_password": "secret_at_run", "sym_a1b2c3d4e5f60718": "name_symbol"}
    assert "variable \"secret_r2_administrator_password\" {\n  type      = string\n  sensitive = true\n}" in \
        (work / "out" / "main.tf").read_text()


def test_writer_matches_terraform_fmt_on_stress_body(work):
    from bo.harness.azurerm import hclwrite as H
    b = H.Block("resource", ("azurerm_x", "r1"), [
        H.Attr("a", H.Lit("x")), H.Attr("long_name_here", H.Lit(1.5)), H.Attr("lst", H.Lit([1, "2", True, None])),
        H.Attr("m", H.Lit({"k": [1, {"z": "w"}], "bo-x": {}})), H.Attr("e", H.Lit({})),
        H.Attr("f", H.Call("jsonencode", (H.Lit({"Statement": [{"Effect": "Allow"}]}),))),
        H.Attr("o", H.BinOp("+", H.Lit(1), H.Ref("var.x"))), H.Attr("t", H.Tmpl(("p-", H.Ref("var.x"), "-s"))),
        H.Block("blk", (), [H.Attr("q", H.Lit(True)), H.Block("inner", (), [])]), H.Block("blk", (), []),
        H.Attr("depends_on", H.ListE((H.Ref("azurerm_y.r2"),)))])
    text = H.file_text([b])
    assert tf.fmt_text(text, work / "fmt") == text


# ------------------------------------------------------------------------------------------------ CLI e E/S
def test_cli_exit_codes(work):
    stub = repo() / "contracts" / "stubs" / "C26" / "lowering_plan.jsonl"
    assert R.main([str(stub), "--out", str(work / "a")]) == 4
    plan, graph = plan_with([step(1, "r1", "azurerm_resource_group", [], name="bo-{t1}-rg")])
    assert R.main([write_plan(work, plan, graph).as_posix(), "--out", str(work / "b")]) == 5
    assert R.main([str(REF / "lowering_plan.jsonl"), "--out", str(work / "c"), "HARNESS-AZURE"]) == 0
    assert R.main([str(work / "nao_existe.jsonl"), "--out", str(work / "d")]) == 2


def test_contract_invalid_plan_is_rejected(work):
    plan, graph = plan_with([rg_step()])
    plan["steps"][0]["order"] = 2
    p = write_plan(work, plan, graph)
    with pytest.raises(HarnessError, match="C26"):
        R.render_file(p, work / "out")


def test_out_dir_foreign_content_is_not_wiped(work):
    (work / "out").mkdir()
    (work / "out" / "alheio.txt").write_text("x")
    plan, graph = plan_with([rg_step()])
    with pytest.raises(HarnessError, match="não está vazio"):
        R.render_file(write_plan(work, plan, graph), work / "out")
    assert (work / "out" / "alheio.txt").exists()


def test_tf_wrapper_refuses_cloud_subcommands(work):
    for sub in ("apply", "plan", "init", "destroy", "import"):
        with pytest.raises(HarnessError):
            tf.run(sub, [], work)
    env = tf.sandbox_env()
    assert not any(k.startswith(("ARM_", "AZURE_", "AWS_", "GOOGLE_")) for k in env)
    assert env["HOME"].startswith(str(work.parents[1]))


def test_reference_modules_pass_offline_validate_with_pinned_provider(work):
    from bo.harness.azurerm._common import templates_dir
    if not (tf.plugin_dir() / "registry.terraform.io" / "hashicorp" / "azurerm" / "5.12.0").is_dir():
        pytest.skip("provider azurerm 5.12.0 fora do cache local (validate offline impossível sem ele)")
    lock = templates_dir() / "terraform.lock.hcl"
    R.render_file(REF / "lowering_plan.jsonl", work / "out")
    for pid in ("LP-AZREF-0001", "LP-AZREF-0002"):
        ok, msg = tf.validate_offline(work / "out" / pid, lock)
        assert ok, (pid, msg)
    # controle negativo: o validate de verdade reprova atributo que o provider não tem
    bad = work / "bad"
    bad.mkdir()
    for f in ("versions.tf", "main.tf"):
        (bad / f).write_text((work / "out" / "LP-AZREF-0001" / f).read_text())
    t = (bad / "main.tf").read_text().replace("min_tls_version", "min_tls_versao")
    (bad / "main.tf").write_text(t)
    ok, msg = tf.validate_offline(bad, lock)
    assert not ok and "min_tls_versao" in msg
