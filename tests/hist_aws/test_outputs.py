"""Saídas reais do HIST-AWS em $BO_DATA/HIST-AWS (sem rede, sem binário): contrato, cobertura da lista do PINS,
binários apagados e coerência com o pin."""
import json

from bo.contracts import validate as V
from bo.hist_aws import check, common


def _ext():
    return json.loads((common.out_dir() / "extraction.json").read_text(encoding="utf-8"))["versions"]


def test_versions_json_confere_c13():
    res = V.validate("versions", common.out_dir() / "versions.json")
    assert res.ok, res.errors[:5]


def test_toda_versao_listada_extraida_ou_com_motivo_e_datas_monotonas():
    assert check.check() == []


def test_cobre_a_lista_inteira_do_pins():
    hist = common.read_history()
    vd = json.loads((common.out_dir() / "versions.json").read_text(encoding="utf-8"))
    assert [v["version"] for v in vd["versions"]] == [it.version for it in hist.versions]
    assert len(hist.versions) == 26
    assert set(_ext()) == {it.version for it in hist.versions}


def test_binarios_apagados_fica_so_schema_e_hashes():
    dl = common.bo_data() / "downloads" / "hist-aws"
    assert not list(dl.rglob("*.zip")), "zip do provider ficou em downloads/hist-aws"
    assert not list(dl.rglob("*.part"))
    assert not (common.bo_tmp() / "plugin-cache").exists() or not any((common.bo_tmp() / "plugin-cache").iterdir())
    assert not list(common.out_dir().rglob("terraform-provider-*"))
    for d in (common.out_dir() / "schemas").iterdir():
        assert sorted(p.name for p in d.iterdir()) == ["SOURCE.txt", "receipt.json", "schema.json.gz",
                                                       "schema.json.sha256", "trust.json"]


def test_pin_igual_ao_pins_json_e_ao_schema_aws():
    pins = common.read_pins()
    r = _ext()[pins.version]
    assert r["status"] == "EXTRACTED" and r["schema_sha256"] == pins.schema_sha256
    other = common.bo_data() / "downloads" / "tfschema" / f"aws-{pins.version}" / "schema.json.sha256"
    if other.is_file():   # extração independente do SCHEMA-AWS, mesmo terraform: mesmos bytes
        assert other.read_text().split()[0] == r["schema_sha256"]


def test_extraidas_com_assinatura_da_ancora_e_binario_do_zip():
    for v, r in _ext().items():
        if r["status"] != "EXTRACTED":
            continue
        t = json.loads((common.schema_dir(v) / "trust.json").read_text(encoding="utf-8"))
        assert t["gpg"]["primary_fpr"] == common.HASHICORP_FPR
        assert t["binary"]["sha256"] == t["unpacked"]["files"][t["binary"]["file"]]["sha256"]
        assert t["zip"]["sha256"] == r["zip_sha256"]
        assert r["terraform"] == common.read_pins().terraform_version
