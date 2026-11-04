"""Camada de instância com as regras 0.1.5–0.1.9 (PILOT-EXIT 1/2): contêiner externo, faceta implícita, ligação
por atributo-lista e seleção (T58), namespace herdado pelo bloco (T52b), identidade por endereço do recurso de topo
de id opaco (T59), fora do domínio (T45)."""

from bo.grain import fixtures as F
from bo.grain import instance as I
from bo.grain import rules as R
from bo.grain.evidence import FixtureAdapter

RS = R.load()


def _world():
    ev = {"v_set": F.ev_entity("Set", "set_name", "name", tag="s"),
          "v_host": F.ev_entity("Host", "host_name", "name", tag="h"),
          "v_set.rule": F.ev_element("Rule", "rule_id", "id", {"days": ("days", "int")}, tag="r")}
    ev["v_host"]["links"] = {"set_ids": {"kind": "reference", "target": "v_set", "source": F.src("lk")},
                             "tags": {"kind": "selection", "target": None, "source": F.src("sel")}}
    ev["v_set.rule"]["implicit_facet"] = {"facet": "rules", "label": "RuleSet", "operation": "PutRules",
                                          "member": "Rules", "source": F.src("imp")}
    return ev


def _cfg(order=(0, 1), with_set=True):
    rs = []
    if with_set:
        rs.append({"type": "v_set", "name": "a", "values": {"name": "set-a", "rule": [
            {"id": "r1", "days": 1}, {"id": "r2", "days": 2}][order[0]:] + ([{"id": "r1", "days": 1}] if order[0] else [])}})
    rs.append({"type": "v_host", "name": "h", "values": {"name": "host-1", "set_ids": [{"$ref": "v_set.a"}],
                                                        "tags": ["web", "db"][::1 if order == (0, 1) else -1]}})
    return {"provider": "provider_v", "resources": rs}


def occs(cfg):
    blocks = {"v_set": {"rule"}}
    return I.decompose_config(cfg, FixtureAdapter(_world()), blocks, RS)


def test_implicit_facet_in_instance_layer():
    oc = occs(_cfg())
    fac = [o for o in oc if o.label == "RuleSet"]
    assert len(fac) == 1 and fac[0].grain == "FACET"
    rules = [o for o in oc if o.label == "Rule"]
    assert len(rules) == 2 and all(o.parent == fac[0].occ_id for o in rules)


def test_list_attribute_link_and_selection_occurrences():
    oc = occs(_cfg())
    links = [o for o in oc if any(":set_ids#" in n for n in o.tf)]
    sels = [o for o in oc if any(":tags#" in n for n in o.tf)]
    assert len(links) == 1 and len(sels) == 2
    # sem ciclo de vida, dono e alcance da ligação: UNKNOWN com o que falta (não força BINDING)
    assert all(o.grain == "UNKNOWN" and set(o.missing) >= {"lifecycle_controller", "owner"} for o in links + sels)


def test_link_decides_binding_with_link_facts():
    ev = _world()
    ad = FixtureAdapter(dict(ev, **{"v_host:set_ids": {
        "lifecycle_controller": [F.c(kind="self", tag="l")], "owner": [F.c(kind="self", tag="l")],
        "effective_scope": [F.c(kind="self", tag="l")]}}))
    oc = I.decompose_config(_cfg(), ad, {"v_set": {"rule"}}, RS)
    link = [o for o in oc if any(":set_ids#" in n for n in o.tf)]
    assert link and link[0].grain == "BINDING" and set(link[0].endpoints) == {"holder", "target"}


def test_external_reference_and_address_identity():
    oc = occs(_cfg(with_set=False))                  # o conjunto referenciado não está na configuração
    link = [o for o in oc if any(":set_ids#" in n for n in o.tf)]
    assert link and "identity" not in link[0].missing   # o alvo externo resolve a identidade da ligação


def test_reorder_invariance_with_new_layers():
    a = I.canonical_rows(occs(_cfg((0, 1))))
    b = I.canonical_rows(occs(_cfg((1, 0))))
    assert a == b
