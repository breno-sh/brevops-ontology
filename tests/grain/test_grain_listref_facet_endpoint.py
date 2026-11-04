"""Rodada final antes do PILOT-EXIT 2/2 (0.1.10): R-GRAIN-LISTREF (T61) e ponta FACET do vínculo (A13).

T61: atributo-lista de escalares do dono, sem fato do SERVICE-EVIDENCE sobre ele, cujos elementos são referências
a recursos na configuração: cada elemento vira ligação (T58) com citação do átomo do schema. Elemento literal ou
simbólico não cria ligação; fato do SE no atributo prevalece; sem o átomo citável, nada.
A13: a faceta não tem identidade própria; como ponta do vínculo ela é lida como a unidade dona da faceta."""

from bo.grain import fixtures as F
from bo.grain import instance as I
from bo.grain import rules as R
from bo.grain import schema as S
from bo.grain.evidence import FixtureAdapter

RS = R.load()
PROV = "provider_v"
ATOM = f"{PROV}:v_host:set_ids"


def _world(se_link=False, nic_facet=False):
    ev = {"v_set": F.ev_entity("Set", "set_name", "name", tag="s"),
          "v_host": F.ev_entity("Host", "host_name", "name", tag="h")}
    if se_link:
        ev["v_host"]["links"] = {"set_ids": {"kind": "reference", "target": "v_set", "source": F.src("lk")}}
    if nic_facet:
        ev["v_host.nic"] = F.ev_aspect("NicConfig", {"mode": ("mode", "str")}, tag="nic")
        ev["v_host.nic"]["links"] = {"set_ids": {"kind": "reference", "target": "v_set", "source": F.src("lk2")}}
    return ev


def _cfg(elements, in_nic=False):
    host = {"name": "host-1"}
    if in_nic:
        host["nic"] = {"mode": "a", "set_ids": elements}
    else:
        host["set_ids"] = elements
    return {"provider": PROV, "resources": [
        {"type": "v_set", "name": "a", "values": {"name": "set-a"}},
        {"type": "v_host", "name": "h", "values": host}]}


def _run(cfg, ev, atoms=True):
    saved = dict(S.ATOM_TYPES)
    S.ATOM_TYPES[PROV] = {ATOM: ["set", "string"]} if atoms else {}
    try:
        return I.decompose_config(cfg, FixtureAdapter(ev), {"v_host": {"nic"}}, RS)
    finally:
        S.ATOM_TYPES.clear()
        S.ATOM_TYPES.update(saved)


def _links(oc, attr="set_ids"):
    return [o for o in oc if any(f":{attr}#" in n for n in o.tf)]


def test_listref_reference_in_config_creates_binding_with_atom_citation():
    oc = _run(_cfg([{"$ref": "v_set.a"}]), _world())
    lk = _links(oc)
    assert len(lk) == 1 and lk[0].grain == "BINDING" and set(lk[0].endpoints) == {"holder", "target"}
    link = S.listref_link(ATOM)
    assert link["source"]["level"] == "derived" and link["source"]["ref"] == ATOM
    assert "R-GRAIN-LISTREF" in link["source"]["note"]


def test_listref_symbolic_or_literal_element_creates_no_link():
    for els in ([{"$unknown": "var.sg"}], ["sg-literal"], []):
        assert _links(_run(_cfg(els), _world())) == []


def test_listref_needs_citable_schema_atom():
    assert _links(_run(_cfg([{"$ref": "v_set.a"}]), _world(), atoms=False)) == []


def test_listref_yields_to_service_evidence_fact_on_attribute():
    nodes = I.build_nodes(_cfg([{"$ref": "v_set.a"}]), FixtureAdapter(_world(se_link=True)), {})[0]
    lk = [n for n in nodes.values() if ":set_ids#" in n.nid]
    assert lk and lk[0].ev.claims["identity"][0]["source"]["ref"].endswith("-lk")   # fonte = fato do SE, não T61


def test_listref_switch_off_for_sensitivity():
    S.LISTREF_ENABLED = False
    try:
        assert _links(_run(_cfg([{"$ref": "v_set.a"}]), _world())) == []
    finally:
        S.LISTREF_ENABLED = True


def test_listref_holder_unknown_keeps_link_unknown():
    ev = _world()
    ev["v_host"].pop("lifecycle_controller")                 # dono sem ciclo de vida: o vínculo não é decidido
    lk = _links(_run(_cfg([{"$ref": "v_set.a"}]), ev))
    assert len(lk) == 1 and lk[0].grain == "UNKNOWN" and lk[0].missing


def test_facet_endpoint_is_read_as_owning_unit():
    oc = _run(_cfg([{"$ref": "v_set.a"}], in_nic=True), _world(nic_facet=True))
    nic = [o for o in oc if o.label == "NicConfig"]
    host = [o for o in oc if o.label == "Host"]
    lk = _links(oc)
    assert nic and nic[0].grain == "FACET"
    assert len(lk) == 1 and lk[0].grain == "BINDING"
    assert lk[0].endpoints["holder"] == host[0].occ_id                  # a ponta é o dono da faceta, não a faceta


def test_component_endpoint_is_not_lifted():
    """Controle negativo: bloco COMPONENT (identidade própria) continua ponta de si mesmo."""
    ev = _world(nic_facet=True)
    ev["v_host.nic"] = F.ev_element("Nic", "nic_name", "mode", {}, tag="nicc")
    ev["v_host.nic"]["links"] = {"set_ids": {"kind": "reference", "target": "v_set", "source": F.src("lk2")}}
    oc = _run(_cfg([{"$ref": "v_set.a"}], in_nic=True), ev)
    nic = [o for o in oc if o.label == "Nic"]
    lk = _links(oc)
    assert nic and nic[0].grain == "COMPONENT"
    assert len(lk) == 1 and lk[0].grain == "BINDING" and lk[0].endpoints["holder"] == nic[0].occ_id
