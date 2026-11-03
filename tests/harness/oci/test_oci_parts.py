"""Tabela de schema, escritor de HCL, redator e o gate no_silent_insert (inclusive quebrado de propósito)."""
import json
import shutil

import pytest
from conftest import EX, REPO

from bo.harness.oci import PROVIDER_VERSION, SCHEMA_SHA256, build_table, hcl, raw_schema_path
from bo.harness.oci import no_silent_insert as NSI
from bo.harness.oci import render as R
from bo.harness.oci import sandbox as SB
from bo.harness.oci import schema as S
from bo.harness.oci.redact import Redactor, RedactionError, is_withheld_leaf
from bo.harness.oci.runners import fake_ocid


# ------------------------------------------------------------------------------------------- schema
def test_table_is_the_pinned_provider():
    t = S.table()
    assert t.header["version"] == PROVIDER_VERSION and t.header["schema_sha256"] == SCHEMA_SHA256
    assert t.header["counts"]["resource"] == len(t.types("resource")) > 900
    pins = REPO / "universe" / "pins.json"
    if pins.exists():
        oci = next(p for p in json.loads(pins.read_text())["providers"] if p["provider"] == "oci")
        assert (oci["version"], oci["schema_sha256"]) == (PROVIDER_VERSION, SCHEMA_SHA256)


@pytest.mark.skipif(not raw_schema_path().exists(), reason="dump bruto do D1 ausente nesta máquina")
def test_table_regenerates_identically():
    assert build_table.main(["--check"]) == 0


def test_resolve_paths():
    b = S.table().block("resource", "oci_core_security_list")
    toks, a = S.resolve(b, "ingress_security_rules.1.tcp_options.min")
    assert [(t.kind, t.name, t.index) for t in toks] == [("block", "ingress_security_rules", 1),
                                                          ("block", "tcp_options", 0), ("attr", "min", 0)]
    toks, a = S.resolve(b, "freeform_tags.k1")
    assert [t.kind for t in toks] == ["attr", "key"] and S.leaf_type(a, toks) == "string"
    for path, code in [("ingress_security_rules", "PATH_ENDS_AT_BLOCK"), ("nope", "FIELD_NOT_IN_SCHEMA"),
                       ("state", "FIELD_NOT_CONFIGURABLE"), ("display_name.x", "KEY_NOT_ALLOWED")]:
        with pytest.raises(S.PathError) as e:
            S.resolve(b, path)
        assert e.value.code == code
    v = S.table().block("resource", "oci_core_vcn")
    with pytest.raises(S.PathError) as e:
        S.resolve(v, "timeouts.0.create")          # bloco single não tem ocorrências
    assert e.value.code == "INDEX_NOT_ALLOWED"
    assert v.attrs["compartment_id"].required and v.blocks["timeouts"].mode == "single"


# ------------------------------------------------------------------------------------------- hcl
def test_hcl_escapes_and_literals():
    assert hcl.string('a"b\\c\n${x}%{y}') == '"a\\"b\\\\c\\n$${x}%%{y}"'
    assert hcl.literal({"b": [1, 2.5, True, None], "a": {}}) == '{ "a" = {}, "b" = [1, 2.5, true, null] }'
    assert hcl.literal(3.0) == "3"
    with pytest.raises(hcl.HclError):
        hcl.literal(float("nan"))
    with pytest.raises(hcl.HclError):
        hcl.traversal("var", "a-b c")


def test_hcl_writer_matches_terraform_fmt(tmp_out):
    b = hcl.Block("resource", ["oci_core_vcn", "r1"])
    b.attr("a", '"x"').attr("long_name", hcl.literal({"k": "v"})).attr("bb", hcl.literal(["1"]))
    inner = b.block(hcl.Block("nested"))
    inner.attr("x", "1").attr("yyyy", "true")
    (tmp_out / "x.tf").write_text(hcl.write_file([b, hcl.Block("terraform")], ["cabeçalho"]))
    r = SB.fmt_check(tmp_out)
    assert r.rc == 0, r.out


def test_sandbox_refuses_cloud_commands(tmp_out):
    for cmd in (["apply"], ["plan"], ["destroy"], ["import"], ["init"]):
        with pytest.raises(SB.SandboxError):
            SB.run(cmd, tmp_out)
    assert SB.version_ok()
    assert "HOME" in SB.env(tmp_out) and not any(k.startswith(("OCI_", "AWS_", "TF_VAR_")) for k in SB.env(tmp_out))


# ------------------------------------------------------------------------------------------- redator
def test_redactor_rules():
    comp = fake_ocid("oci_identity_compartment", 1)
    vcn = fake_ocid("oci_core_vcn", 7)
    other = fake_ocid("oci_kms_key", 3)
    r = Redactor({"compartment_id": comp, "objectstorage_namespace": "nsabc123"}, ["Sup3rSecretValue"])
    r.index_state([{"type": "oci_core_vcn", "name": "r1", "values": {"id": vcn}}])
    assert r.value(comp) == ("ok", "bind:compartment_id")
    assert r.value(vcn) == ("ok", "ref:oci_core_vcn.r1")
    assert r.value(other) == ("withheld", "REDACT-OCID-01")
    assert r.value("https://x.example.invalid/n/nsabc123/b") == ("withheld", "REDACT-CTX-01")
    assert r.value(["a", "xxSup3rSecretValuexx"]) == ("withheld", "REDACT-SECRET-01")
    assert r.value({"a": 1, "b": "c"}) == ("ok", {"a": 1, "b": "c"})
    with pytest.raises(RedactionError):
        r.guard_text('{"v": "' + other + '"}', "t")
    with pytest.raises(RedactionError):
        r.guard_text("nsabc123", "t")
    with pytest.raises(RedactionError):
        r.guard_text("conta " + "".join(str(i % 10) for i in range(1, 13)), "t")
    r.guard_text('{"ok": "bind:compartment_id"}', "t")


def test_withheld_leaves_by_type():
    ud = "user" + "_data"
    assert is_withheld_leaf("oci_core_instance", f"metadata.{ud}")
    assert is_withheld_leaf("oci_objectstorage_object", "content")
    assert not is_withheld_leaf("oci_core_security_list", "ingress_security_rules.0.source")
    assert is_withheld_leaf("oci_functions_function", "config")


# ------------------------------------------------------------------------------------------- no_silent_insert
def test_gate_passes_on_default_corpus(tmp_out):
    assert NSI.main(["--report", str(tmp_out / "nsi.json")]) == 0
    rep = json.loads((tmp_out / "nsi.json").read_text())
    assert rep["rendered_checked"] >= 2 and rep["mutations"]["as_expected"] == rep["mutations"]["total"] > 10


def _rendered(tmp_out):
    out = tmp_out / "o"
    rr = R.render(EX / "lowering_plan.jsonl", out, bindings_path=EX / "bindings.json")
    plans = {p["plan_id"]: p for p in R.load_jsonl(EX / "lowering_plan.jsonl")}
    pr = next(p for p in rr.report["plans"] if p["plan_id"] == "LP-OCI-STO-0001")
    return out, plans["LP-OCI-STO-0001"], pr, R.load_bindings(EX / "bindings.json"), R.Templates.load()


def test_checker_catches_inserted_attribute(tmp_out):
    out, plan, pr, b, tpl = _rendered(tmp_out)
    assert NSI.check_rendered(out, plan, pr, b, tpl) == []
    f = out / "lp_oci_sto_0001" / "main.tf"
    f.write_text(f.read_text().replace('  versioning     = "Enabled"\n',
                                       '  versioning     = "Enabled"\n  storage_tier   = "Standard"\n'))
    v = NSI.check_rendered(out, plan, pr, b, tpl)
    assert any("storage_tier" in x and "INSERÇÃO" in x for x in v)


def test_checker_catches_dropped_and_changed_values(tmp_out):
    out, plan, pr, b, tpl = _rendered(tmp_out)
    f = out / "lp_oci_sto_0001" / "main.tf"
    f.write_text(f.read_text().replace('  access_type    = "NoPublicAccess"\n', "")
                 .replace('"Enabled"', '"Disabled"'))
    v = NSI.check_rendered(out, plan, pr, b, tpl)
    assert any("access_type" in x and "PERDA" in x for x in v)
    assert any("versioning" in x and "difere" in x for x in v)


def test_checker_catches_defaulted_variable_and_extra_provider_attr(tmp_out):
    out, plan, pr, b, tpl = _rendered(tmp_out)
    f = out / "lp_oci_sto_0001" / "main.tf"
    f.write_text(f.read_text().replace('variable "bo_ctx_run_tag" {\n  type = string\n}',
                                       'variable "bo_ctx_run_tag" {\n  type    = string\n  default = "x"\n}'))
    assert any("default" in x for x in NSI.check_rendered(out, plan, pr, b, tpl))
    root = out / "main.tf"
    root.write_text(root.read_text().replace("  region = var.bo_region\n",
                                             "  region = var.bo_region\n  auth   = \"InstancePrincipal\"\n"))
    rep = json.loads((out / R.REPORT_NAME).read_text())
    assert any("provider" in x for x in NSI.check_root(out, rep["plans"], tpl))


def test_renderer_that_inserts_a_default_fails_the_gate(tmp_out, monkeypatch):
    orig = R._emit

    def emit_with_default(node, hb):
        orig(node, hb)
        if hb.type == "resource" and hb.labels[0] == "oci_objectstorage_bucket":
            hb.attr("storage_tier", '"Standard"')     # default inventado pelo renderizador
    monkeypatch.setattr(R, "_emit", emit_with_default)
    rep = NSI.run_corpus([(EX / "lowering_plan.jsonl", EX / "bindings.json")], tmp_out / "w")
    assert any("storage_tier" in x and "INSERÇÃO" in x for x in rep["violations"])


def test_renderer_that_fills_missing_required_fails_mutations(tmp_out, monkeypatch):
    monkeypatch.setattr(R, "_check_required", lambda *a, **k: None)
    rep = NSI.run_corpus([(EX / "lowering_plan.jsonl", EX / "bindings.json")], tmp_out / "w")
    assert rep["mutations"]["failed"] and all("esperado UNKNOWN_INPUT" in x or "esperado INVALID_PLAN" in x
                                              for x in rep["mutations"]["failed"])


def test_gate_is_not_vacuous(tmp_out):
    stub = REPO / "contracts" / "stubs" / "C26" / "lowering_plan.jsonl"
    d = tmp_out / "only_stub"
    d.mkdir()
    shutil.copy(stub, d / "lowering_plan.jsonl")
    assert NSI.main([str(d / "lowering_plan.jsonl"), "--report", str(tmp_out / "r.json")]) == 1
    assert json.loads((tmp_out / "r.json").read_text())["vacuous"] is True
