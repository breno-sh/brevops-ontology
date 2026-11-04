"""O perfil semântico só cita evidência que existe no SERVICE-EVIDENCE, com o nível declarado; e as leituras mudam o que devem."""
import json

import pytest

import net_oracle as no
from conftest import DATA, NETDIR, load
from net_oracle import semantics

SE = DATA / "SERVICE-EVIDENCE/service_evidence.jsonl"


@pytest.fixture(scope="module")
def se_rows():
    ids = set(semantics.evidence_ids())
    out = {}
    with SE.open(encoding="utf-8") as fh:
        for line in fh:
            if '"evidence_id"' in line:
                d = json.loads(line)
                if d["evidence_id"] in ids:
                    out[d["evidence_id"]] = d
    return out


def test_evidencia_existe(se_rows):
    assert set(semantics.evidence_ids()) == set(se_rows)


def test_nivel_publicado_so_com_linha_publicada(se_rows):
    for prov, params in semantics.profile()["params"].items():
        for name, p in params.items():
            if isinstance(p, dict) and p.get("level") == "published":
                se = [e for e in p["evidence"] if e.startswith("SE-")]
                assert not se or any(se_rows[e]["level"] == "published" and se_rows[e]["status"] == "stated" for e in se), (prov, name)
            if isinstance(p, dict) and p.get("level") == "unknown":
                assert p.get("value") is None and p.get("values"), (prov, name)


def test_estado_aws_gcp_azure_nao_assumido(se_rows):
    for prov, ev in (("aws", "SE-aws-ys4irutgmpm2h6os"), ("google", "SE-google-zpvpswcdzblhsngy"),
                     ("azurerm", "SE-azurerm-x6ikfm2ljwnl4tca")):
        assert se_rows[ev]["status"] == "unknown"
        assert not semantics.param(prov, "state.default").known


def test_leitura_lenient_usa_regras_implicitas_interpretadas():
    f = load(NETDIR / "fixtures_calib/NETC-C09-GCP-NOMATCH.json")
    d = no.evaluate_fixture(f, "lenient")["decisions"]
    assert (d["f2"]["value"], d["f4"]["value"]) == ("DENY", "ALLOW")
    d = no.evaluate_fixture(f, "default")["decisions"]
    assert d["f2"]["value"] == d["f4"]["value"] == "UNKNOWN"


def test_leitura_strict_tira_o_estado_derivado_do_nsg_oci():
    f = load(NETDIR / "fixtures_calib/NETC-C03-OCI-NSG-SYM.json")
    f["config"]["resources"][1]["values"].pop("stateless")
    assert no.evaluate_fixture(f, "default")["decisions"]["f1r"]["value"] == "ALLOW"
    assert no.evaluate_fixture(f, "strict")["decisions"]["f1r"]["value"] == "UNKNOWN"
    # na strict também cai o efeito 'só permissão' (derivado deste oráculo): até o fluxo novo fica UNKNOWN
    f2 = load(NETDIR / "fixtures_calib/NETC-C02-OCI-STATEFUL.json")
    d = no.evaluate_fixture(f2, "strict")["decisions"]
    assert d["f1"]["value"] == "UNKNOWN" and d["f1r"]["value"] == "UNKNOWN"
    assert no.evaluate_fixture(f2, "default")["decisions"]["f1r"]["value"] == "ALLOW"
