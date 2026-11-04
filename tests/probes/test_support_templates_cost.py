"""Suporte validado antes do sorteio, templates (avaliador HCL, schema fixado, controle = mesma configuração
desligada, plan_guard) e teto de custo."""

from __future__ import annotations

import copy
import json
import shutil

import pytest

from bo.probes import cells as C
from bo.probes import cost as K
from bo.probes import support_matrix as SM
from bo.probes import templates as T
from bo.probes.common import ProbeError
from bo.probes.tfschema import resource_block


@pytest.fixture(scope="module")
def built():
    return SM.build("2026-11-04T09:00:00-03:00")


@pytest.fixture(scope="module")
def inputs():
    from bo.safety import skus
    from bo.probes import protocol
    from bo.probes.tfschema import pins
    return protocol.load(), SM.load_service_evidence(), skus.load_table(), pins()


def cellmap(matrix):
    return {c["cell"]: c for c in matrix["cells"]}


def test_committed_outputs_match_regeneration():
    assert SM.main([]) == 0


def test_only_validated_cells_are_drawable(built):
    support, matrix, not_valid = built
    cm = cellmap(matrix)
    assert SM.invariants(support, matrix) == []
    assert set(matrix["drawable"]) == {c for c, v in cm.items() if v["status"] == "validated"}
    assert set(not_valid) == set(cm) - set(matrix["drawable"])
    assert set(SM.drawable()) == set(matrix["drawable"])
    for c in matrix["drawable"]:
        assert T.has_template(c) and all(k["ok"] for k in cm[c]["checks"])


def test_findings_against_the_hypothesis_are_kept(built):
    _, matrix, _ = built
    cm = cellmap(matrix)
    # janela de 96 h do PREREG passa da janela máxima de 72 h do SAFETY (D12): fora do sorteio em todo provedor
    assert cm["log_retention/aws"]["status"] == "unsupported" and "S5" in cm["log_retention/aws"]["failed"]
    # limite de taxa sem janela, chave, rajada e mecanismo declarados: nenhum provedor sorteável
    assert all("S3" in cm[f"rate_limit/{p}"]["failed"] for p in ("aws", "google", "azurerm", "oci"))
    # mínimo de 30 dias de log no Azure e no OCI: protocolo não suportado (demonstrado)
    assert cm["log_retention/azurerm"]["status"] == "unsupported"


def test_invariants_catch_tampering(built):
    support, matrix, _ = built
    s2 = copy.deepcopy(support)
    for t in s2["probe_types"]:
        if t["probe_type"] == "rate_limit":
            t["validated_support"][0]["status"] = "validated"
    assert any("sem suporte validado" in x or "drawable" in x for x in SM.invariants(s2, matrix))
    m2 = copy.deepcopy(matrix)
    m2["drawable"].append("log_retention/aws")
    assert SM.invariants(support, m2)


def test_service_evidence_unsupported_or_sku_out_of_table_blocks_draw(inputs):
    protos, se, table, pins = inputs
    cell = "object_versioning/aws"
    assert SM.evaluate_cell(cell, se[cell], protos, table, pins)["status"] == "validated"
    se2 = copy.deepcopy(se[cell])
    se2["status"] = "documented_unsupported"
    v = SM.evaluate_cell(cell, se2, protos, table, pins)
    assert v["status"] == "unsupported" and not v["drawable"]
    t2 = copy.deepcopy(table)
    del t2["providers"]["aws"]["types"]["aws_s3_bucket_versioning"]
    v = SM.evaluate_cell(cell, se[cell], protos, t2, pins)
    assert v["status"] != "validated" and {"S6", "S8"} <= set(v["failed"])
    p2 = copy.deepcopy(pins)
    p2["aws"] = {**p2["aws"], "version": "9.9.9"}
    assert "S7" in SM.evaluate_cell(cell, se[cell], protos, table, p2)["failed"]


def test_protocol_support_is_c22_and_keeps_published_evidence():
    support = json.loads(SM.support_path().read_text(encoding="utf-8"))
    assert SM.load_support()  # passa pelo validador oficial
    for t in support["probe_types"]:
        for v in t["validated_support"]:
            levels = [e["level"] for e in v["evidence"]]
            assert "derived" in levels
            if v["status"] == "validated":
                assert "published" in levels


# ------------------------------------------------------------------------------------- templates
def test_expression_subset():
    sc = T.Scope({"bo_names": {"a.b": "bo-x-0001"}, "r": "us-east-1"}, {"on": True, "l": [1]})
    assert T.eval_value('${lookup(var.bo_names, "a.b", "z")}', sc) == "bo-x-0001"
    assert T.eval_value('${lookup(var.bo_names, "c", "z")}', sc) == "z"
    assert T.eval_value("${local.on ? 1 : 0}", sc) == 1
    assert T.eval_value('"bo${substr(sha1("x"), 0, 4)}"', sc) == "bo11f6"
    assert T.eval_value("${aws_s3_bucket.probe.id}", sc) is T.UNKNOWN
    assert T.eval_value('"a-${var.r}"', sc) == "a-us-east-1"
    with pytest.raises(T.ExprError):
        T.eval_value("${file(\"/etc/passwd\")}", sc)
    with pytest.raises(T.ExprError):
        T.eval_value("${var.nao_existe}", sc)


@pytest.fixture
def tdir(work):
    def copy_cell(cell):
        d = work / cell.replace("/", "_")
        shutil.copytree(T.template_dir(cell), d)
        return d
    return copy_cell


def _plan(cell, side, d):
    v = T.synthetic_vars(cell, "b-test", {}, "us-east-1", C.IMPL[cell].runner_inputs)
    return T.synthetic_plan(cell, side, v, d)


def test_schema_check_catches_bad_attribute_and_missing_required(tdir):
    cell = "object_versioning/aws"
    d = tdir(cell)
    txt = (d / "main.tf").read_text()
    (d / "main.tf").write_text(txt.replace("force_destroy = true", "force_destroy = true\n  versioning_x = 1")
                               .replace("  bucket = aws_s3_bucket.probe.id\n  versioning_configuration",
                                        "  versioning_configuration"))
    _, insts = _plan(cell, "case", d)
    f = T.schema_findings(insts, lambda t: resource_block("aws", t))
    assert any("versioning_x" in x for x in f) and any("bucket: obrigatório ausente" in x for x in f)


def test_control_must_differ_only_in_probe_attributes(tdir, inputs):
    _, se, _, _ = inputs
    cell = "object_versioning/google"
    d = tdir(cell)
    (d / "side_control.tf").write_text('locals {\n  bo_side = "control"\n  bo_versioning_enabled = true\n}\n')
    _, a = _plan(cell, "case", d)
    _, b = _plan(cell, "control", d)
    f = T.diff_findings(T.side_diff(a, b), se[cell]["terraform_resource_type"], se[cell]["attributes"], {})
    assert any("idênticos" in x for x in f)
    txt = (d / "main.tf").read_text().replace('storage_class               = "STANDARD"',
                                             'storage_class = local.bo_side == "case" ? "STANDARD" : "NEARLINE"')
    (d / "side_control.tf").write_text('locals {\n  bo_side = "control"\n  bo_versioning_enabled = false\n}\n')
    (d / "main.tf").write_text(txt)
    with pytest.raises(T.ExprError):  # "==" está fora do subconjunto: recusa em vez de adivinhar
        _plan(cell, "case", d)


def test_plan_guard_catches_missing_run_tag(tdir, protos):
    from bo.safety import plan_check, skus
    cell = "queue_retention/aws"
    d = tdir(cell)
    (d / "main.tf").write_text((d / "main.tf").read_text().replace('"bo-run" = var.bo_run_id', '"x" = "y"'))
    plan, _ = _plan(cell, "case", d)
    rep = plan_check.check_plan(plan, {"provider": "aws", "batch_id": "b-test", "ttl_hours": 1, "window_hours": 1,
                                       "region": "us-east-1"}, skus.load_table())
    assert any(f["code"] == "PG-TAG" for f in rep["findings"])


def test_ttl_in_plan_matches_kit(inputs):
    for cell, impl in C.IMPL.items():
        _, insts = _plan(cell, "case", T.template_dir(cell))
        assert SM.ttl_findings(cell, impl, insts) == [], cell
    impl = C.IMPL["queue_retention/aws"]
    _, insts = _plan("queue_retention/aws", "control", T.template_dir("queue_retention/aws"))
    assert SM.ttl_findings("queue_retention/aws", impl, insts)  # o controle tem retenção de 14 dias


def test_run_dir_has_one_side(work):
    d = T.render_run_dir("item_ttl/aws", "control", work / "run")
    assert sorted(p.name for p in d.iterdir()) == ["main.tf", "side.tf"]
    assert "bo_ttl_attributes = []" in (d / "side.tf").read_text()


# ------------------------------------------------------------------------------------- custo
def test_cost_cap_passes_and_counts_storage_traffic_requests():
    from bo.probes import cost_cap
    assert cost_cap.main([]) == 0
    doc = json.loads((SM.results_dir() / "cost_estimate.json").read_text())
    assert doc["n_templates"] == len(C.IMPL)
    for r in doc["templates"]:
        assert set(K.CATEGORIES) <= set(r["by_category"]) and r["within_limit"] and r["plan_guard_ok"]
        assert r["sides"]["case"]["cost"]["includes"][:4] == ["compute", "storage", "traffic", "requests"]


def test_cost_over_limit_is_caught(protos):
    from dataclasses import replace
    from bo.safety import skus
    p = replace(protos["object_versioning"], cost_limit_usd=1e-6)
    e = K.estimate("object_versioning/aws", p, skus.load_table())
    assert not e["within_limit"]
    u = K.usage_for("object_versioning/aws", protos["object_versioning"], e["_insts"]["case"])
    req = u["aws_s3_bucket.probe"]["requests_millions"] * 1e6
    # 3 repetições × (3 gravações + 30 leituras de 60 s até 30 min) × 3 tentativas no pior caso
    assert req == 3 * (3 + 30) * 3 and K.n_ticks(protos["object_versioning"]) == 30


def test_unestimable_template_fails_cost_cap(work, monkeypatch):
    from bo.probes import cost_cap
    fake = work / "deploy" / "probes" / "rate_limit" / "aws" / "_templates"
    fake.mkdir(parents=True)
    for f in T.TEMPLATE_FILES:
        (fake / f).write_text("")
    monkeypatch.setattr(cost_cap, "deploy_dir", lambda: work / "deploy" / "probes")
    _, probs = cost_cap.build()
    assert any("sem implementação" in p for p in probs)


def test_unsupported_cell_has_no_template_and_says_why():
    for c in C.all_cells():
        nv = T.template_dir(c) / SM.NOT_VALIDATED
        if c in C.IMPL:
            assert T.has_template(c) and not nv.exists()
        else:
            d = json.loads(nv.read_text())
            assert d["join_outcome_if_drawn"] == "PROTOCOL_UNSUPPORTED" and d["reasons"]
            assert not (T.template_dir(c) / "main.tf").exists()


def test_probe_error_code():
    with pytest.raises(ProbeError):
        T.load_doc(T.template_dir("item_ttl/aws"), "lado-errado")
