"""Testes do CQFIX: emissor HCL, especificação CIS, regras estruturais e mutações que as guardas têm de pegar."""
import copy
import json
import shutil

import pytest
import yaml

from bo.cqfix import PROVIDERS, VARIANTS, build, cis_spec, fixture_check, fixtures_dir, fxlint, hcl
from bo.cqfix import plan_guard_offline, schema_index, spec, tmp_root
from bo.cqfix.model import NA, schema_type_absent
from bo.cqfix.realize.base import Ctx


def test_hcl_escapa_interpolacao_em_literal():
    assert hcl.value("a${b}") == '"a$${b}"'
    assert hcl.value(hcl.Tpl("${var.x}-y")) == '"${var.x}-y"'
    assert hcl.value(hcl.Ref("aws_vpc.v.id")) == "aws_vpc.v.id"
    r = hcl.Res("aws_vpc", "fx_a", {"cidr_block": "10.0.0.0/16"})
    assert hcl.resource(r).startswith('resource "aws_vpc" "fx_a" {')


def test_cis_tem_8_conceitos_e_passa_no_validador_c24():
    from bo.requirements.model import validate_cq_spec
    assert len(cis_spec.records()) == 8
    assert set(cis_spec.cis_controls()) == set(cis_spec.CONCEPT_CQ)
    assert validate_cq_spec(cis_spec.records()) == []


def test_catalogo_37_cqs():
    cat = spec.catalog()
    assert len(cat) == 37 and len({q["cq_id"] for q in cat}) == 37


def test_toda_realizacao_passa_no_lint():
    res = build.realize_all()
    errs = []
    for p in PROVIDERS:
        for q in spec.catalog():
            for v in VARIANTS:
                r, fid = res[p][q["cq_id"]][v]
                errs += fxlint.lint(q, v, fid, r)
    assert errs == []


def test_lint_pega_entidade_sem_mapa_e_incompletude_faltando():
    q = spec.by_id()["CQ-CMP-02"]
    from bo.cqfix.realize import aws
    c = Ctx("aws", q, "incomplete")
    r = aws.REALIZERS["CQ-CMP-02"]("incomplete", c)
    r.entity_map.pop("nic2")
    r.incompleteness.clear()
    errs = fxlint.lint(q, "incomplete", c.fid, r)
    assert any("entity_map" in e for e in errs) and any("not_read" in e for e in errs)


def test_evidencia_falsa_de_ausencia_reprova():
    assert schema_index.check_evidence(schema_type_absent("aws", r"^aws_s3_bucket$", "x")) is not None
    assert schema_index.check_evidence(schema_type_absent("aws", r"^aws_nao_existe_x$", "x")) is None


@pytest.fixture()
def copia():
    d = tmp_root() / "test_copy"
    if d.exists():
        shutil.rmtree(d)
    shutil.copytree(fixtures_dir(), d)
    yield d
    shutil.rmtree(d)


def test_guarda_aprova_as_fixtures_gravadas():
    assert plan_guard_offline.check(fixtures_dir())["ok"]


def test_guarda_reprova_sku_caro(copia):
    f = copia / "aws" / "main.tf"
    f.write_text(f.read_text().replace('"t4g.nano"', '"m5.24xlarge"', 1))
    rep = plan_guard_offline.check(copia)
    assert not rep["ok"] and any(x["rule"] == "SKU fora da lista" for x in rep["findings"])


def test_guarda_reprova_classe_c_e_tipo_fora_da_lista(copia):
    f = copia / "aws" / "main.tf"
    t = f.read_text()
    t = t.replace('resource "aws_sqs_queue" "fx_idl_02_c_c1"', 'resource "aws_redshift_cluster" "fx_idl_02_c_c1"')
    f.write_text(t)
    pr = yaml.safe_load((copia / "probes.yaml").read_text())
    for p in pr["probes"]:
        p["slice"] = [a.replace("aws_sqs_queue.fx_idl_02_c_c1", "aws_redshift_cluster.fx_idl_02_c_c1")
                      for a in p["slice"]]
    (copia / "probes.yaml").write_text(yaml.safe_dump(pr, allow_unicode=True, sort_keys=False))
    rep = plan_guard_offline.check(copia)
    assert not rep["ok"] and any("fora da allowlist" in x["rule"] for x in rep["findings"])


def test_guarda_reprova_credencial_no_provider(copia):
    f = copia / "aws" / "main.tf"
    f.write_text(f.read_text().replace("region = var.location_1\n  default_tags",
                                       'region = var.location_1\n  access_key = "x"\n  default_tags', 1))
    assert not plan_guard_offline.check(copia)["ok"]


def test_fixture_check_aprova_e_reprova_resposta_alterada(copia):
    assert fixture_check.check(fixtures_dir())["ok"]
    ea = json.loads((copia / "expected_answers.json").read_text())
    x = ea["cqs"][0]["providers"]["aws"]["variants"]["conforming"]
    x["expected"] = dict(x["expected"], value=not x["expected"]["value"])
    (copia / "expected_answers.json").write_text(json.dumps(ea, ensure_ascii=False))
    rep = fixture_check.check(copia)
    assert not rep["ok"] and any("resposta esperada difere" in e for e in rep["errors"])


def test_fixture_check_reprova_bloco_sem_fixture(copia):
    f = copia / "oci" / "main.tf"
    f.write_text(f.read_text() + '\nresource "oci_core_vcn" "solto" {\n  compartment_id = var.compartment_ocid\n}\n')
    rep = fixture_check.check(copia)
    assert not rep["ok"] and any("não pertence a nenhuma fixture" in e for e in rep["errors"])


def test_fixture_check_reprova_na_trocado_para_realizado(copia):
    ea = json.loads((copia / "expected_answers.json").read_text())
    for q in ea["cqs"]:
        for p, pe in q["providers"].items():
            for v, x in pe["variants"].items():
                if x["status"] == "NOT_APPLICABLE":
                    x["evidence"] = [schema_type_absent(p, r"^.*$", "tudo casa")]
                    (copia / "expected_answers.json").write_text(json.dumps(ea, ensure_ascii=False))
                    rep = fixture_check.check(copia)
                    assert not rep["ok"] and any("evidência não confere" in e for e in rep["errors"])
                    return
    pytest.fail("nenhum NOT_APPLICABLE para testar")
