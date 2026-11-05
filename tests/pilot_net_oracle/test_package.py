"""Testes do pacote bo.pilot_net_oracle: regras de cobertura, selagem, regeneração e semente C11."""
import copy
import json
import os
import shutil
from pathlib import Path

import pytest

from bo.pilot_net_oracle import build, calib, coverage_lib, oracle_coverage, seal, spec

REPO = Path(os.environ.get("BO_REPO") or Path(__file__).resolve().parents[2])


def _counts():
    exp = json.loads((REPO / "pilot/net/expected_answers.json").read_text(encoding="utf-8"))
    idx = json.loads((REPO / "pilot/net/oracle/sealed_index.json").read_text(encoding="utf-8"))
    return exp["counts"]["calib"], idx["counts"]


def test_cobertura_atual_passa():
    cal, ret = _counts()
    assert coverage_lib.check(cal, ret) == []


def test_cobertura_reprova_polaridade_faltando():
    cal, ret = _counts()
    ret = copy.deepcopy(ret)
    ret["by_case"]["NET-C04"]["unknown"] = 0
    assert any("NET-C04: sem fixture unknown em retidas" in e for e in coverage_lib.check(cal, ret))


def test_cobertura_reprova_menos_de_30_por_cento():
    cal, ret = _counts()
    ret = copy.deepcopy(ret)
    ret["translations_total"] = 5
    assert any("translations_total" in e for e in coverage_lib.check(cal, ret))


def test_cobertura_reprova_direcao_sem_contraexemplo_retido():
    cal, ret = _counts()
    ret = copy.deepcopy(ret)
    ret["by_direction"]["aws->oci"]["negative"] = 0
    assert any("aws->oci: nenhum contraexemplo retido" in e for e in coverage_lib.check(cal, ret))


def test_envelope_confere_e_adulteracao_reprova(tmp_path, monkeypatch):
    assert seal.verify() == []
    fake = tmp_path / "PILOT-NET-ORACLE" / "sealed"
    fake.mkdir(parents=True)
    idx = json.loads((REPO / "pilot/net/oracle/sealed_index.json").read_text(encoding="utf-8"))
    src = seal.envelope_path(idx)
    for old in idx.get("retired_sets", []):
        shutil.copy(seal.envelope_path(old), fake / seal.envelope_path(old).name)
    data = src.read_text().splitlines()
    data[3] = data[3][:-4] + ("AAAA" if not data[3].endswith("AAAA") else "BBBB")
    (fake / src.name).write_text("\n".join(data) + "\n")
    monkeypatch.setenv("BO_DATA", str(tmp_path))
    errs = seal.verify()
    assert any("sha256 do envelope" in e for e in errs)


def test_envelope_fora_de_git_e_do_repositorio():
    sd = seal.sealed_dir().resolve()
    assert not oracle_coverage._inside_git(sd)
    assert not str(sd).startswith(str(REPO.resolve()))


def test_nenhuma_retida_no_repositorio():
    assert all(f["split"] == "calib" for f in calib.fixtures())
    assert all(t["split"] == "calib" for t in calib.translations())


def test_regeneracao_identica():
    g = build.generate(check_only=True)
    assert g["errors"] == []
    for p, content in g["files"].items():
        assert (REPO / p).read_text(encoding="utf-8") == content, p


def test_semente_c11_par_e_sentido():
    t = {"case_id": "NETC-T-OCI-AWS-P", "direction": "oci->aws"}
    s = build.c11_seed(t)
    assert s["stratum_partial"]["pair"] == "AWSOCI" and s["stratum_partial"]["direction"] == "inverse"
    s = build.c11_seed({"case_id": "X", "direction": "google->azurerm"})
    assert s["stratum_partial"]["pair"] == "GCPAZ" and s["stratum_partial"]["direction"] == "forward"


def test_catalogo_de_perdas_por_direcao():
    e = spec.direction_entry("google->aws")
    assert "LOSS-NET-EFFECT-DENY" in e["expected_losses"] and "REQ-T-EFFECTIVE-SET" in e["acceptable_target"]
    e = spec.direction_entry("oci->azurerm")
    assert {"LOSS-NET-STATE", "LOSS-NET-DEFAULT", "LOSS-NET-SRCPORT"} - set(e["expected_losses"]) == {"LOSS-NET-SRCPORT"}
    assert "REQ-T-CATCHALL" in e["acceptable_target"] and "REQ-T-AZ-PRIORITY" in e["acceptable_target"]


def test_conjunto_v1_aposentado_e_v2_ativo():
    idx = json.loads((REPO / "pilot/net/oracle/sealed_index.json").read_text(encoding="utf-8"))
    assert idx["set_version"] == 2 and idx["status"] == "ativo"
    old = idx["retired_sets"][0]
    assert old["set_version"] == 1 and old["status"] == "usado 2×, aposentado"
    assert idx["envelope_sha256"] != old["envelope_sha256"]
    ret = json.loads((REPO / "pilot/net/oracle/sealed_index_v1_retired.json").read_text(encoding="utf-8"))
    assert ret["status"] == "usado 2×, aposentado"
    assert idx["counts"]["fixtures_total"] >= ret["counts"]["fixtures_total"]
    assert idx["counts"]["translations_total"] >= ret["counts"]["translations_total"]
