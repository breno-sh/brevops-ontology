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


def test_estado_do_nsg_azure_nao_assumido(se_rows):
    # desde o CC-14 o SG AWS e o firewall GCP têm estado publicado; o NSG Azure segue sem evidência
    assert se_rows["SE-azurerm-x6ikfm2ljwnl4tca"]["status"] == "unknown"
    assert not semantics.param("azurerm", "state.default").known
    for prov, ev in (("aws", "SE-aws-p272pgtmcwbrjsvb"), ("google", "SE-google-egw54c4ruinm6cgl")):
        assert se_rows[ev]["level"] == "published" and se_rows[ev]["value"]["stateful"] is True
        assert semantics.param(prov, "state.default", "strict").value == "stateful"


def test_regras_implicitas_do_gcp_publicadas_valem_na_strict():
    f = load(NETDIR / "fixtures_calib/NETC-C09-GCP-NOMATCH.json")
    for rd in ("strict", "default", "lenient"):
        d = no.evaluate_fixture(f, rd)["decisions"]
        assert (d["f2"]["value"], d["f4"]["value"]) == ("DENY", "ALLOW"), rd


def test_estado_da_regra_de_nsg_oci_publicado_vale_na_strict():
    f = load(NETDIR / "fixtures_calib/NETC-C03-OCI-NSG-SYM.json")
    f["config"]["resources"][1]["values"].pop("stateless")
    assert no.evaluate_fixture(f, "default")["decisions"]["f1r"]["value"] == "ALLOW"
    # desde 83953b9 o estado da regra de NSG é publicado: a strict não o tira; o que cai na strict é o efeito
    # 'só permissão' (oracle_derived) e o padrão sem regra, por isso o retorno fica UNKNOWN lá pelo outro motivo
    assert semantics.param("oci", "state.nsg_rule", "strict").known
    # desde o CC-14 o efeito 'só permissão' e o 'sem regra, nada passa' da OCI são publicados: a strict decide
    f2 = load(NETDIR / "fixtures_calib/NETC-C02-OCI-STATEFUL.json")
    d = no.evaluate_fixture(f2, "strict")["decisions"]
    assert d["f1"]["value"] == "ALLOW" and d["f1r"]["value"] == "ALLOW"
