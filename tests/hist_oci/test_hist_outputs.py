"""Saídas reais do HIST-OCI em $BO_DATA/HIST-OCI: contrato, cobertura da lista, truncamento e binários apagados."""
import json

import pytest

from bo.contracts import validate as V
from bo.hist_oci import check, common, manifest

OUT = common.out_dir()


@pytest.fixture(scope="module")
def ext():
    p = OUT / "extraction.json"
    assert p.is_file(), "rode python -I -m bo.hist_oci.pipeline antes"
    return json.loads(p.read_text(encoding="utf-8"))


def test_versions_json_c13():
    r = V.validate("versions", OUT / "versions.json")
    assert r.ok, r.errors[:5]


def test_check_do_gate_passa():
    probs, counts = check.check(common.read_history(), OUT)
    assert probs == [], probs[:10]
    assert counts["extracted"] + counts["not_extracted"] == counts["listed"] == 25


def test_todo_not_extracted_tem_motivo_verificavel(ext):
    for r in ext["versions"]:
        if r["status"] == "not_extracted":
            assert "HTTP" in r["motivo"] or "Error" in r["motivo"], r


def test_pin_igual_a_lista_e_ao_pins():
    h = common.read_history()
    pin = common.read_pin()
    v = {e["version"]: e for e in json.loads((OUT / "versions.json").read_text())["versions"]}
    assert v[h.pin]["schema_sha256"] == h.versions[-1].schema_sha256 == pin["schema_sha256"]


def test_truncamento_declarado(ext):
    lt = ext["left_truncation"]
    assert lt["index_first_version"] == "4.67.3" and "Truncamento à esquerda" in lt["declarado"]


def test_nenhum_binario_sobrou():
    root = common.downloads()
    for sub in ("zip", "plugin-cache"):
        d = root / sub
        assert not d.exists() or not any(p.is_file() for p in d.rglob("*")), sub


def test_manifesto_sem_log_volatil():
    listed = (OUT / "MANIFEST.sha256").read_text(encoding="utf-8")
    for bad in ("gate_report.json", "consume_ledger.json", "integration/", ".log"):
        assert bad not in listed
    assert not manifest.verify()
