"""G2-CHILD (0.1.7) com DADO REAL: a regra de rede filha do NSG (separada e embutida) é COMPONENT do NSG.

A identidade é relativa ao NSG (pai de composição marcado como segmento de caminho: o tipo de API da ponte,
networkSecurityGroups/securityRules, está aninhado no tipo do pai), o ciclo de vida de API publicado é próprio e a
regra é apagada em cascata pelo NSG. Sai COMPONENT do NSG com own_api_lifecycle e cascade_delete_by. Controles
negativos: o NSG continua ENTITY (G4-NS); facetas sem operações próprias continuam FACET; um filho sem ciclo de
vida próprio não passa pela G2-CHILD.
"""

import pytest

from bo.grain import battery as B
from bo.grain import fixtures as F
from bo.grain import realdata as RD
from bo.grain import relations as REL
from bo.grain import rules as R
from bo.grain import schema as S
from bo.grain.common import data_root

TOP, INL, SEP = ("azurerm_network_security_group", "azurerm_network_security_group.security_rule",
                 "azurerm_network_security_rule")


@pytest.fixture(scope="module")
def records():
    p = data_root() / "SERVICE-EVIDENCE" / "service_evidence.jsonl"
    assert p.is_file(), f"dado real ausente: {p}"
    return RD.load_evidence(p)


@pytest.fixture(scope="module")
def res(records):
    return RD.run(slice_types={"azurerm": [TOP, SEP]}, records=records)["providers"]["azurerm"]["_res"]


def test_g2child_real_standalone_and_embedded_same_grain(res):
    a, b = res.decisions[INL], res.decisions[SEP]
    for d in (a, b):
        assert d.grain == "COMPONENT" and d.rule == "GRAIN-G2-CHILD" and d.parent == TOP, (d.grain, d.rule, d.missing)
        assert d.own_api_lifecycle and TOP in d.cascade and d.lifecycle["kind"] == "self"
    assert S.signature(res, [TOP, INL]) == S.signature(res, [TOP, SEP])
    ra, ea = REL.relations(res, [TOP, INL])
    rb, eb = REL.relations(res, [TOP, SEP])
    assert not ea and not eb
    pick = lambda rels, lab: sorted((h.split(":")[0], y) for x, h, y in rels if x and x[-1] == lab)  # noqa: E731
    assert pick(ra, a.label) == pick(rb, b.label)
    assert ("cascade_delete_by", (res.decisions[TOP].label,)) in pick(ra, a.label)


def test_g2child_c19_records(res):
    units = {u["unit_id"]: u for u in S.to_c19(res)[0]}
    u = units[f"CU-azurerm-{SEP}"]
    refs = {e.get("ref") for e in u["evidence"]}
    assert "own_api_lifecycle=true" in refs and f"cascade_delete_by=CU-azurerm-{TOP}" in refs
    assert u["kind"] == "COMPONENT" and u["lifecycle_controller"]["kind"] == "self"


def test_g2child_negative_namespace_entity_stays_entity(res):
    d = res.decisions[TOP]
    assert d.grain == "ENTITY" and d.rule == "GRAIN-G4-NS"


def test_g2child_negative_facets_without_own_crud_stay_facet(records):
    rep = RD.run(slice_types={"aws": RD.STO_SLICE["aws"]}, records=records)
    top = rep["providers"]["aws"]["top_level"]
    for c in ("aws_s3_bucket_versioning", "aws_s3_bucket_policy", "aws_s3_bucket_acl"):
        assert top[c]["grain"] == "FACET" and top[c]["rule"] == "GRAIN-G3-FACET", (c, top[c])


def test_g2child_negative_child_without_own_lifecycle_is_plain_component():
    rs = R.load()
    child = F.ev_element("rule", "nm", "name", {}, via="set_id", ref_field="set_id", ref_target="z_set")
    child["field_map"]["set_id"]["path_parent"] = True
    w = {"provider": "provider_z", "schema": {"z_set": F.res(["name"]), "z_rule": F.res(["set_id", "name"])},
         "evidence": {"z_set": F.ev_entity("set", "set_name", "name", tag="s"), "z_rule": child}}
    d = B.run_schema(w, rs).decisions["z_rule"]
    assert d.grain == "COMPONENT" and d.rule == "GRAIN-G2-COMPONENT" and not d.own_api_lifecycle
    child["lifecycle_controller"] = [F.c(kind="self", tag="own")]
    d2 = B.run_schema(w, rs).decisions["z_rule"]
    assert d2.grain == "COMPONENT" and d2.rule == "GRAIN-G2-CHILD" and d2.own_api_lifecycle
    child["field_map"]["set_id"].pop("path_parent")
    d3 = B.run_schema(w, rs).decisions["z_rule"]
    assert d3.grain == "UNKNOWN"                                   # sem a marca de caminho: segue UNKNOWN
