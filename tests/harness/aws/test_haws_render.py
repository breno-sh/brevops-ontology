"""Renderizador: estados tipados, nada inventado, HCL canônico (terraform fmt), modelos presos ao pins.json."""
import json
import shutil
import subprocess

import pytest

from bo.harness.aws import hcl, pins, render

from conftest import PLANS


def by_id(man):
    return {e["plan_id"]: e for e in man["plans"]}


def test_status_of_each_fixture_plan(rendered):
    _, man = rendered
    st = {k: e["status"] for k, e in by_id(man).items()}
    assert st == {"LP-AWS-NET-01": "RENDERED", "LP-AWS-STO-01": "RENDERED", "LP-AWS-DB-01": "UNKNOWN_INPUT",
                  "LP-AWS-DB-02": "RENDERED", "LP-AWS-SEC-01": "UNKNOWN_INPUT", "LP-AWS-SEC-02": "RENDERED",
                  "LP-AWS-MSG-01": "UNKNOWN_INPUT", "LP-AWS-BAD-01": "INVALID_PLAN",
                  "LP-AWS-NET-02": "RENDERED", "LP-AWS-NET-03": "RENDERED"}
    assert man["other_provider"] == [{"plan_id": "LP-AWS-OTH-01", "status": "OTHER_PROVIDER",
                                      "target_provider": "google"}]


def test_missing_required_field_is_unknown_input_and_not_invented(rendered):
    out, man = rendered
    e = by_id(man)["LP-AWS-DB-01"]
    assert {m["field"] for m in e["missing"]} == {"instance_class"}
    text = (out / "LP-AWS-DB-01.tf").read_text()
    assert "instance_class" not in text.split("BO-STATUS")[1].split("\n\n", 1)[1]
    assert "NÃO APLICÁVEL" in text


def test_unknown_input_reasons_are_typed(rendered):
    _, man = rendered
    reasons = " | ".join(m["reason"] for e in man["plans"] for m in e["missing"])
    for frag in ("escolha CH-SEC-01 sem seleção", "documento com 1 símbolo", "expressão '*' sem redução",
                 "dependência fora do plano: chave KMS"):
        assert frag in reasons


def test_invalid_plan_writes_no_hcl(rendered):
    out, man = rendered
    e = by_id(man)["LP-AWS-BAD-01"]
    assert e["file"] is None and not (out / "LP-AWS-BAD-01.tf").exists()
    assert any("não existe no schema fixado" in p["reason"] for p in e["problems"])
    assert any("aws_tipo_que_nao_existe" in p["reason"] for p in e["problems"])


def test_reference_resolved_to_earlier_step_and_depends_on(rendered):
    out, _ = rendered
    t = (out / "LP-AWS-NET-01.tf").read_text()
    assert "vpc_id     = aws_vpc.lp_aws_net_01_r1.id" in t
    assert "depends_on = [aws_vpc.lp_aws_net_01_r1]" in t


def test_symbol_and_secret_become_variables_without_default(rendered):
    out, man = rendered
    sto = (out / "LP-AWS-STO-01.tf").read_text()
    db = (out / "LP-AWS-DB-02.tf").read_text()
    assert "var.lp_aws_sto_01_sym_b2c3d4e5f6071829" in sto and "default" not in sto
    assert "password                = var.lp_aws_db_02_secret_1" in db and "sensitive = true" in db
    assert "default" not in db


def test_template_escape_of_literal_interpolation(rendered):
    out, _ = rendered
    assert 'bo-nota = "a$${b}"' in (out / "LP-AWS-STO-01.tf").read_text()


def test_output_is_terraform_fmt_canonical(rendered):
    out, _ = rendered
    tf = shutil.which("terraform")
    for f in sorted(out.glob("*.tf")):
        r = subprocess.run([tf, "fmt", "-"], input=f.read_text(), capture_output=True, text=True)
        assert r.returncode == 0 and r.stdout == f.read_text(), f.name


def test_render_is_deterministic(rendered, work):
    out, _ = rendered
    man2 = render.render_file(PLANS, work / "r2")
    for f in sorted(out.glob("*.tf")):
        assert (work / "r2" / f.name).read_text() == f.read_text()
    assert [e["status"] for e in man2["plans"]] == [e["status"] for e in json.loads(
        (out / "render_manifest.json").read_text())["plans"]]


def test_cli_current_stub_renders_aws_plan_and_passes_fmt(work):
    stub = pins.repo_root() / "contracts" / "stubs" / "C26" / "lowering_plan.jsonl"
    assert render.main([str(stub), "--out", str(work / "o")]) == 0
    man = json.loads((work / "o" / "render_manifest.json").read_text())
    assert man["plans"] and all(e["status"] == "RENDERED" for e in man["plans"])
    assert all((work / "o" / e["file"]).exists() for e in man["plans"])
    r = subprocess.run([shutil.which("terraform"), f"-chdir={work / 'o'}", "fmt", "-check"],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


def test_cli_synthetic_stub_without_aws_plan_exits_2(work):
    rows = [json.loads(x) for x in PLANS.read_text().splitlines()]
    graphs = [json.loads(x) for x in PLANS.with_name("graph_ir.jsonl").read_text().splitlines()]
    other = [r for r in rows if r["target_provider"] != "aws"]
    assert other
    (work / "lowering_plan.jsonl").write_text("".join(json.dumps(r) + "\n" for r in other))
    gids = {r["graph_id"] for r in other}
    (work / "graph_ir.jsonl").write_text("".join(json.dumps(g) + "\n" for g in graphs if g["graph_id"] in gids))
    assert render.main([str(work / "lowering_plan.jsonl"), "--out", str(work / "o")]) == 2


def test_cli_missing_input_exits_2(work):
    assert render.main([str(work / "nao_existe.jsonl"), "--out", str(work / "o")]) == 2


def test_cli_strict_fails_when_not_all_rendered(work):
    assert render.main([str(PLANS), "--out", str(work / "o")]) == 0
    assert render.main([str(PLANS), "--out", str(work / "o"), "--strict"]) == 1
    assert render.main([str(PLANS), "--out", str(work / "o"), "--strict", "--plan-id", "LP-AWS-NET-01"]) == 0


def test_contract_violation_is_rejected(work):
    bad = work / "lowering_plan.jsonl"
    rows = [json.loads(x) for x in PLANS.read_text().splitlines()]
    rows[0]["steps"][1]["depends_on"] = [2]           # C26-ORDER: depende de passo não anterior
    bad.write_text("".join(json.dumps(r) + "\n" for r in rows))
    shutil.copyfile(PLANS.with_name("graph_ir.jsonl"), work / "graph_ir.jsonl")
    with pytest.raises(ValueError, match="C26"):
        render.render_file(bad, work / "o")


def test_templates_follow_pins(work):
    pin = pins.load_pin()
    assert render.check_templates(render.templates_dir(), pin) == []
    fake = pins.Pin("9.9.9", pin.provider_version, pin.schema_sha256, pin.pins_path)
    assert render.check_templates(render.templates_dir(), fake)


def test_hcl_literals_and_keys():
    assert hcl.quote('a"b\n${x}%{y}') == '"a\\"b\\n$${x}%%{y}"'
    assert hcl.key("bo-run") == "bo-run" and hcl.key("null") == '"null"' and hcl.key("a b") == '"a b"'
    assert hcl.lit(1.0) == "1" and hcl.lit(1.5) == "1.5" and hcl.lit(True) == "true" and hcl.lit(None) == "null"
    with pytest.raises(ValueError):
        hcl.Ref("aws_vpc.x.id + 1")
    with pytest.raises(ValueError):
        hcl.lit(float("nan"))
