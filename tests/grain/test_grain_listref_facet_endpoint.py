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


def _rec(eid, kind, value, bp="items"):
    return {"evidence_id": eid, "provider": "oci", "pin": {"provider_version": "0.0.1"},
            "api_resource": {"service": "core", "resource": "X"}, "terraform_resource_type": "t_x", "block_path": bp,
            "fact_kind": kind, "status": "stated", "level": "derived", "derived_from": ["SE-controle"],
            "value": dict(value, block_path=bp)}


def test_t62_list_item_bridge_is_not_an_aspect():
    """T62: ponte para campo-lista de itens (item_model + list[...]) não vira aspecto pela T49; sem identidade do
    item, api_resource fica UNKNOWN com o motivo. Controle: ponte para submodelo único segue aspecto (T49)."""
    from bo.grain.evidence import C25Adapter
    life = {"kind": "parent", "layer": "api", "rule": "R-OWN-SPEC-BLOCK", "configured_by": "update do pai"}

    def bridge(ft):
        return {"aspect": "api_resource_bridge", "field_type": ft, "item_model": "Item", "resource": "x.items",
                "rule": "R-BRIDGE-SPEC-BLOCK", "service": "core"}
    lst = C25Adapter([_rec("SE-c-1", "api_bridge", bridge("list[Item]")), _rec("SE-c-2", "lifecycle_controller", life)])
    f = lst.evidence("t_x.items").fact("api_resource")
    assert not f.known
    one = C25Adapter([_rec("SE-c-1", "api_bridge", bridge("Item")), _rec("SE-c-2", "lifecycle_controller", life)])
    g = one.evidence("t_x.items").fact("api_resource")
    assert g.known and g.value["status"] == "aspect"


def _att(eid, binds_to, level="interpreted"):
    r = _rec(eid, "identity", {"aspect": "attachment_attribute", "attribute": "items.ids", "binds_to": binds_to,
                               "rule": "R-ATTACH-SPEC", "spec_field": "F.ids", "spec_operation": "Op"})
    r["level"] = level
    if level == "interpreted":
        r["model_id"] = "modelo-x"
    return r


def _ref(eid, target):
    return _rec(eid, "identity", {"aspect": "reference_target", "attribute": "items.ids", "resolved": target,
                                  "target_types": [target], "references": {"items.ids": target},
                                  "rule": "R-REF-TARGET"})


def test_t63_attachment_attribute_is_typed_link_kept_interpreted():
    from bo.grain.evidence import C25Adapter
    lk = C25Adapter([_att("SE-a-1", "t_set")]).evidence("t_x.items").links["ids"]
    assert lk["target"] == "t_set" and lk["kind"] == "reference"
    assert lk["source"]["level"] == "interpreted" and lk["source"]["model_id"] == "modelo-x"   # não promovido
    assert "R-GRAIN-T63" in lk["source"]["note"]


def test_t63_divergent_typed_target_is_untyped_in_any_order():
    from bo.grain.evidence import C25Adapter
    for recs in ([_att("SE-a-1", "t_set"), _ref("SE-a-2", "t_other")],
                 [_ref("SE-a-2", "t_other"), _att("SE-a-1", "t_set")]):
        assert C25Adapter(recs).evidence("t_x.items").links["ids"]["target"] is None
    for recs in ([_att("SE-a-1", "t_set"), _ref("SE-a-2", "t_set")],
                 [_ref("SE-a-2", "t_set"), _att("SE-a-1", "t_set")]):
        assert C25Adapter(recs).evidence("t_x.items").links["ids"]["target"] == "t_set"
