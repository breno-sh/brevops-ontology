"""Saídas reais do DRIFT em $BO_DATA/DRIFT e results/DRIFT: coerência interna, intervalos entre versões
observadas consecutivas, lacunas declaradas e casos conhecidos dos guias dos providers."""
import gzip
import json
from functools import lru_cache

from bo.contracts import validate as V
from bo.drift import common


@lru_cache(maxsize=1)
def churn():
    return json.loads((common.results_dir() / "churn.json").read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def events():
    with open(common.out_dir() / "events.jsonl", encoding="utf-8") as f:
        return [json.loads(l) for l in f]


def test_churn_confere_c15_e_aponta_os_arquivos_certos():
    res = V.validate("results", common.results_dir() / "churn.json")
    assert res.ok, res.errors[:5]
    for k, ref in churn()["data"]["files"].items():
        p = common.bo_data() / ref["path"].removeprefix("$BO_DATA/")
        assert common.sha256_file(p) == ref["sha256"], k


def test_sem_staging_nem_partes_esquecidas():
    assert not common.staging_dir().exists()
    assert not (common.out_dir() / ".parts").exists()


def test_intervalo_entre_versoes_observadas_consecutivas():
    obs = {p: [v["version"] for v in s["versions"] if v["observed"]]
           for p, s in churn()["data"]["providers"].items()}
    pairs = {p: set(zip(vs, vs[1:])) for p, vs in obs.items()}
    ids = set()
    for e in events():
        iv = e["version_interval"]
        assert (iv["after"], iv["until"]) in pairs[e["provider"]], e["event_id"]
        ids.add(e["event_id"])
    assert len(ids) == len(events()) == churn()["data"]["totals"]["events"]


def test_lacunas_declaradas_e_nunca_estado():
    prov = churn()["data"]["providers"]
    assert [g["version"] for g in prov["google"]["gaps"]] == ["3.62.0"]
    assert [g["version"] for g in prov["oci"]["gaps"]] == ["4.67.3"]
    assert prov["aws"]["gaps"] == [] and prov["azurerm"]["gaps"] == []
    assert prov["google"]["left_truncation"]["first_observed"] == "3.74.0"
    assert prov["oci"]["left_truncation"]["first_observed"] == "4.69.0"
    gap = {"google": '"version":"3.62.0"', "oci": '"version":"4.67.3"'}
    n = 0
    with open(common.out_dir() / "atom_history.jsonl", encoding="utf-8") as f:
        for line in f:                         # varredura completa por texto (JSON canônico, sem espaços)
            for p, needle in gap.items():
                if f'"provider":"{p}"' in line:
                    n += 1
                    assert needle not in line, line[:120]
    assert n == prov["google"]["atoms_union"] + prov["oci"]["atoms_union"]


def test_renome_conhecido_aws_db_instance_name_para_db_name():
    r = [e for e in events() if e["event_type"] == "rename"
         and e["from_atom"] == "aws:aws_db_instance:name" and e["to_atom"] == "aws:aws_db_instance:db_name"]
    assert len(r) == 1
    assert r[0]["version_interval"] == {"after": "4.61.0", "until": "5.0.0"}
    assert any(x["level"] == "published" and x["doc"]["file"].endswith("version-5-upgrade.html.markdown")
               for x in r[0]["evidence"])


def test_renome_publicado_azurerm_exige_pista_de_renome_ou_nomes_relacionados():
    # substituição por atributo de outro significado (nome -> id) não pode virar renome
    bad = [e for e in events() if e["event_type"] == "rename" and e["provider"] == "azurerm"
           and e["from_atom"].endswith("storage_account_name") and e["to_atom"].endswith("storage_account_id")]
    assert bad == []


def test_remocoes_da_aws_6_0_0_batem_com_os_atomos_do_hist():
    d = common.bo_data() / "HIST-AWS"
    ids = [{json.loads(l)["atom_id"] for l in gzip.open(d / f"atoms_{v}.jsonl.gz", "rt")}
           for v in ("5.93.0", "6.0.0")]
    gone = ids[0] - ids[1]
    ev = [e for e in events() if e["provider"] == "aws" and e["version_interval"]["until"] == "6.0.0"
          and e["event_type"] in ("removal", "rename")]
    got = {e.get("atom_id") or e["from_atom"] for e in ev}
    assert got == gone and len(gone) == 886
