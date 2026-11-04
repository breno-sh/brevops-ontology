"""Fixtures e traduções de calibração: o avaliador e o juiz reproduzem as respostas escritas à mão."""
import pytest

import net_oracle as no
from conftest import NETDIR, load
from net_oracle.decomposing import compare, invariant

FX = {d["fixture_id"]: d for d in (load(p) for p in sorted((NETDIR / "fixtures_calib").glob("*.json")))}
TR = [load(p) for p in sorted((NETDIR / "fixtures_calib/translations").glob("*.json"))]


@pytest.mark.parametrize("fid", sorted(FX))
def test_decisoes(fid):
    f = FX[fid]
    r = no.evaluate_fixture(f)
    for k, e in f["expected"]["decisions"].items():
        assert r["decisions"][k]["value"] == e["value"], (k, e["why"])
        if e["value"] == "UNKNOWN":
            assert r["decisions"][k]["code"] == e["code"], k
    assert r["validity"]["value"] == f["expected"]["validity"]["value"]


@pytest.mark.parametrize("t", TR, ids=[t["case_id"] for t in TR])
def test_traducoes(t):
    src = FX[t["source_fixture"]]
    j = no.judge(src, t["target"], t["declared_losses"], t["direction"])
    assert j["verdict"] == t["expected"]["verdict"], t["expected"]["why"]
    for k in ("negatives_carried", "silent_losses", "covered", "undetermined"):
        if k in t["expected"]:
            assert sorted(j[k]) == sorted(t["expected"][k])


def test_doze_direcoes_com_tres_polaridades():
    seen = {}
    for t in TR:
        seen.setdefault(t["direction"], set()).add(t["polarity"])
    assert len(seen) == 12 and all(v == {"positive", "negative", "unknown"} for v in seen.values())


def test_contraexemplo_negado_nunca_aceito():
    for t in TR:
        if t["polarity"] == "negative":
            j = no.judge(FX[t["source_fixture"]], t["target"], t["declared_losses"], t["direction"])
            assert j["verdict"] == "REJECT" and (j["negatives_carried"] or j["silent_losses"])


@pytest.mark.parametrize("fid", sorted(k for k, v in FX.items() if v["expected"].get("decomposition_invariant_with")))
def test_invariancia_de_embalagem(fid):
    f = FX[fid]
    g = FX[f["expected"]["decomposition_invariant_with"]]
    assert invariant(f["expected"]["decomposition"], g["expected"]["decomposition"])


def test_compare_aponta_tipo_errado_e_falta():
    exp = FX["NETC-C01-AWS-INLINE"]["expected"]["decomposition"]
    act = [dict(u) for u in exp]
    act[1]["kind"] = "ENTITY"
    r = compare(exp, act[:-1])
    assert not r["equal"] and r["wrong_kind"] and r["missing"]
    assert compare(exp, FX["NETC-C01-AWS-SEP"]["expected"]["decomposition"])["equal"]


def test_disputa_spec_doc_vira_unknown_na_regra_de_nsg_oci():
    from net_oracle.decomposing import apply_disputes, disputes
    assert "oci_core_network_security_group_security_rule" in disputes()
    units = apply_disputes(FX["NETC-C03-OCI-NSG-REV"]["expected"]["decomposition"])
    rules = [u for u in units if u["tf"]["resource_type"] == "oci_core_network_security_group_security_rule"]
    assert rules and all(u["kind"] == "UNKNOWN" and u["dispute"] and u["kind_without_dispute"] == "COMPONENT" for u in rules)
    raw = FX["NETC-C03-OCI-NSG-REV"]["expected"]["decomposition"]
    assert not compare(raw, raw)["equal"]  # quem afirma COMPONENT na regra disputada erra o tipo
    assert compare(raw, units)["equal"]
