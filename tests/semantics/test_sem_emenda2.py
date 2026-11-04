"""Emenda 2 (2026-11-04): coleções com tipo do elemento (CC-6) e grandeza de dado = AmountOfData (CC-5)."""
import copy
from pathlib import Path

import pytest

from bo.semantics import common
from bo.semantics.content import examples as E
from bo.semantics.obligations import assess
from bo.semantics.transport import transport
from bo.semantics.valuetypes import INFO, UNITS, TypeError_, ValueType


def test_collection_types():
    lt = ValueType.from_dict({"datatype": "list", "item_type": {"datatype": "string"}})
    assert lt.admits(["a", "b"]) and not lt.admits("a") and not lt.kind_unknown()
    st = ValueType.from_dict({"datatype": "set", "item_type": {"datatype": "string"}})
    assert st.admits(["a", "b"]) and not st.admits(["a", "a"])
    mt = ValueType.from_dict({"datatype": "map", "key_type": "string", "item_type": {"datatype": "boolean"}})
    assert mt.admits({"k": True}) and not mt.admits({"k": "x"})
    for bad in ({"datatype": "list"}, {"datatype": "map", "item_type": {"datatype": "string"}},
                {"datatype": "string", "item_type": {"datatype": "string"}},
                {"datatype": "list", "quantity_kind": "quantitykind:Time", "unit": "unit:DAY",
                 "item_type": {"datatype": "string"}}):
        with pytest.raises(TypeError_):
            ValueType.from_dict(bad)
    unk = ValueType.from_dict({"datatype": "list", "item_type": {"datatype": "integer", "quantity_kind": "UNKNOWN",
                                                                "unit": "UNKNOWN"}})
    assert unk.kind_unknown()        # a grandeza é a do elemento


def test_typed_list_claims_are_not_kind_unknown():
    for c in (E.PREFIX_LIST, E.DAYS_LIST):
        a = assess(c)
        assert a.verdict == "OK" and "KIND-UNKNOWN" not in a.rules
    untyped = copy.deepcopy(E.PREFIX_LIST)
    untyped["subject_value_type"] = None
    assert "KIND-UNKNOWN" in assess(untyped).rules


def test_elementwise_transport_with_per_element_loss():
    assert transport(E.DAYS_LIST, [1, 30])["value"] == [86400, 2592000]
    sat = copy.deepcopy(E.DAYS_LIST)
    sat["object_value_type"]["item_type"]["range"]["max"] = 864000
    sat["loss_contract"] = [{"kind": "saturation", "min": 0, "max": 864000}]
    sat["value_domain_relation"]["relation"], sat["transport_fidelity"] = "overlap", "declared_loss"
    o = transport(sat, [1, 30])
    assert o["value"] == [86400, 864000] and o["losses"] == [{"kind": "saturation", "from": 2592000, "to": 864000,
                                                               "element": 1}]
    assert transport(E.PREFIX_LIST, ["a/"], direction="inverse")["value"] == ["a/"]


def test_set_to_list_allowed_list_to_set_needs_declared_loss():
    s2l = copy.deepcopy(E.PREFIX_LIST)
    s2l["subject_value_type"] = {"datatype": "set", "item_type": {"datatype": "string"}}
    assert "KIND-COLL" not in assess(s2l).rules
    l2s = copy.deepcopy(E.PREFIX_LIST)
    l2s["object_value_type"] = {"datatype": "set", "item_type": {"datatype": "string"}}
    assert "KIND-COLL" in assess(l2s).rules
    l2s["loss_contract"] = [{"kind": "semantic", "what": "ordem e repetição dos prefixos"}]
    l2s["transport_fidelity"] = "declared_loss"
    assert "KIND-COLL" not in assess(l2s).rules


def test_data_quantity_kind_is_amount_of_data():
    assert INFO == "quantitykind:AmountOfData"
    for u in ("unit:BYTE", "unit:BIT", "unit:GigaBYTE", "unit:GibiBYTE", "unit:TeraBYTE", "unit:KiloBIT"):
        assert UNITS[u][0] == INFO
    t = ValueType.from_dict({"datatype": "integer", "quantity_kind": "quantitykind:AmountOfData", "unit": "unit:BYTE"})
    assert not t.kind_unknown()
    with pytest.raises(TypeError_):        # o par antigo agora é erro de tipo, não grandeza alternativa
        ValueType.from_dict({"datatype": "integer", "quantity_kind": "quantitykind:InformationEntropy",
                             "unit": "unit:BYTE"})


def test_kernel_units_agree_with_units_module():
    R = pytest.importorskip("bo.units.rules")
    shared = set(UNITS) & set(R.UNIT_KIND)
    assert {"unit:BYTE", "unit:GibiBYTE", "unit:SEC", "unit:NUM"} <= shared
    assert {u: UNITS[u][0] for u in shared} == {u: R.UNIT_KIND[u] for u in shared}


def test_kernel_data_units_agree_with_qudt_353():
    p = common.data_root() / "downloads" / "qudt-3.5.3" / "VOCAB_QUDT-UNITS-ALL.ttl"
    if not p.is_file():
        pytest.skip("QUDT 3.5.3 não baixado")
    import rdflib
    g = rdflib.Graph()
    g.parse(str(p), format="turtle")
    Q = rdflib.Namespace("http://qudt.org/schema/qudt/")
    for u, (kind, _, _) in UNITS.items():
        if kind != INFO:
            continue
        iri = rdflib.URIRef("http://qudt.org/vocab/unit/" + u.split(":", 1)[1])
        kinds = {str(o).rsplit("/", 1)[-1] for o in g.objects(iri, Q.unitForQuantityKind)} | \
                {str(o).rsplit("/", 1)[-1] for o in g.objects(iri, Q.hasQuantityKind)}
        assert "AmountOfData" in kinds, (u, kinds)
