"""Emenda 1.3.0 (STO-MAP CC-5): grandeza e convenção das unidades do registro conferem com bo.units.rules."""
import pytest

from bo.transforms import registry as R
from bo.transforms import units as U

UR = pytest.importorskip("bo.units.rules")


def test_byte_and_bit_are_amount_of_data():
    assert U.INFO == UR.DATA == "quantitykind:AmountOfData"
    for iri in ("unit:BIT", "unit:BYTE", "unit:GigaBYTE", "unit:GibiBYTE", "unit:MegaBIT"):
        assert U.UNITS[iri].kind == "quantitykind:AmountOfData"
    assert all(u.kind != "quantitykind:InformationEntropy" for u in U.UNITS.values())


def test_kinds_equal_units_rules():
    assert set(U.UNITS) == set(UR.UNIT_KIND)
    assert {i: u.kind for i, u in U.UNITS.items()} == UR.UNIT_KIND


def test_byte_convention_matches_except_vacuous_unprefixed():
    for iri, conv in UR.BYTE_CONV.items():
        mine = U.UNITS[iri].byte_convention
        if iri in ("unit:BYTE", "unit:BIT"):
            assert mine is None and conv == "SI"      # UNITS-BYTE-00: convenção vácua (fator 1 nas duas)
        else:
            assert mine == conv, iri


def test_registry_declares_amount_of_data():
    for s in R.SCALARS:
        if s.name.endswith("_information"):
            assert s.domain["quantity_kind"] == s.codomain["quantity_kind"] == "quantitykind:AmountOfData"
    t = U.UnitType.of({"unit": "unit:GibiBYTE", "quantity_kind": "quantitykind:AmountOfData"})
    assert t.byte_convention == "IEC"
