"""Guardas (gramática, satisfatibilidade, avaliação) e tipos de valor (domínios, normalização, N4)."""
from fractions import Fraction

import pytest

from bo.semantics import guards as G
from bo.semantics.valuetypes import (EnumDomain, NumDomain, OutOfDomain, TypeError_, ValueType, canonical,
                                     duration_seconds, relation)
from bo.semantics.vocab import ABSENT, NOT_READ

STD = {"term": "object.edition", "op": "edition_in", "value": ["standard"]}
PREM = {"term": "object.edition", "op": "edition_in", "value": ["premium"]}


@pytest.mark.parametrize("atom", [
    {"term": "object.edition", "op": "neq", "value": "x"},                       # operador fora da gramática
    {"term": "target.edition", "op": "edition_in", "value": ["x"]},              # papel inválido
    {"term": "object.region", "op": "edition_in", "value": ["x"]},               # edition_in sobre termo errado
    {"term": "object.provider_version", "op": "version_range", "value": {"min": "2", "max_exclusive": "1"}},
    {"term": "subject.engine", "op": "eq", "value": "a"},                        # vizinho sem tipo
    {"term": "subject.flag", "op": "present", "value": "yes"},
])
def test_guard_type_errors(atom):
    with pytest.raises(G.GuardTypeError):
        G.typecheck({"all": [atom]})


def test_guard_sat_unsat_unknown_and_witness():
    sat, w = G.satisfiable({"all": [STD, {"term": "object.edition", "op": "edition_in", "value": ["standard", "premium"]}]})
    assert sat == G.SAT and G.evaluate({"all": [STD]}, w)[0] == G.TRUE
    assert G.satisfiable({"all": [STD, PREM]})[0] == G.UNSAT
    v = {"term": "object.provider_version", "op": "version_range"}
    assert G.satisfiable({"all": [dict(v, value={"min": "5.0"}), dict(v, value={"max_exclusive": "5.0"})]})[0] == G.UNSAT
    assert G.satisfiable({"all": [dict(v, value={"min": "4.2"}), dict(v, value={"max_exclusive": "5.0"})]})[0] == G.SAT
    r = [{"term": "object.k", "op": "refers_to_kind", "value": "a"}, {"term": "object.k", "op": "refers_to_kind", "value": "b"}]
    assert G.satisfiable({"all": r})[0] == G.UNKNOWN
    assert G.satisfiable({"all": r, "kind_disjoint": [["a", "b"]]})[0] == G.UNSAT
    p = [{"term": "subject.x", "op": "present", "value": False},
         {"term": "subject.x", "op": "eq", "value": True}]
    assert G.satisfiable({"all": p, "term_types": {"subject.x": {"datatype": "boolean"}}})[0] == G.UNSAT


def test_guard_three_valued_evaluation():
    g = {"all": [STD]}
    assert G.evaluate(g, {"object.edition": "standard"})[0] == G.TRUE
    assert G.evaluate(g, {"object.edition": "premium"})[0] == G.FALSE
    assert G.evaluate(g, {})[0] == G.INDETERMINATE
    assert G.evaluate(g, {"object.edition": NOT_READ})[0] == G.INDETERMINATE
    pres = {"all": [{"term": "subject.lock", "op": "present", "value": False}]}
    assert G.evaluate(pres, {"subject.lock": ABSENT})[0] == G.TRUE
    # falso vence indeterminado numa conjunção
    two = {"all": [STD, {"term": "object.region", "op": "region_in", "value": ["r1"]}]}
    assert G.evaluate(two, {"object.edition": "premium"})[0] == G.FALSE


def test_guard_rename_project_flip():
    g = G.rename({"all": [STD]}, {"subject": "n0", "object": "n1"})
    assert g["all"][0]["term"] == "n1.edition"
    assert G.project(G.conj(g, {"all": [{"term": "n0.region", "op": "region_in", "value": ["r"]}]}, roles=("n0", "n1")),
                     {"n0"})["all"] == [{"term": "n0.region", "op": "region_in", "value": ["r"]}]
    assert G.flip({"all": [STD]})["all"][0]["term"] == "subject.edition"


def test_domain_relations_enum_and_lattice():
    assert relation(EnumDomain(frozenset("ab")), EnumDomain(frozenset("abc"))) == "subset"
    assert relation(EnumDomain(frozenset("abc")), EnumDomain(frozenset("ab"))) == "superset"
    assert relation(EnumDomain(frozenset("ab")), EnumDomain(frozenset("bc"))) == "overlap"
    assert relation(EnumDomain(frozenset("a")), EnumDomain(frozenset("b"))) == "disjoint"
    F = Fraction
    d35 = NumDomain(F(1), F(35), F(1), F(1))
    assert relation(d35, NumDomain(F(1), F(365), F(1), F(1))) == "subset"
    assert relation(NumDomain(F(0), F(100), F(2), F(0)), NumDomain(F(1), F(99), F(2), F(1))) == "disjoint"   # pares x ímpares
    assert relation(NumDomain(F(0), F(100), F(4), F(0)), NumDomain(F(0), F(100), F(2), F(0))) == "subset"
    assert relation(NumDomain(F(0), F(10), None), NumDomain(F(5), F(20), None)) == "overlap"
    assert relation(NumDomain(F(0), F(10), F(1)), NumDomain(F(0), F(10), None)) == "subset"


def test_types_n4():
    with pytest.raises(TypeError_):
        ValueType.from_dict({"datatype": "integer", "quantity_kind": "quantitykind:Time"})       # sem unidade
    with pytest.raises(TypeError_):
        ValueType.from_dict({"datatype": "integer", "quantity_kind": "quantitykind:Time", "unit": "unit:NUM"})
    with pytest.raises(TypeError_):
        ValueType.from_dict({"datatype": "integer", "quantity_kind": "quantitykind:AmountOfData",
                             "unit": "unit:GibiBYTE", "byte_convention": "SI"})
    na = ValueType.from_dict({"datatype": "enum", "enum": ["a"]})
    unk = ValueType.from_dict({"datatype": "integer", "quantity_kind": "UNKNOWN", "unit": "UNKNOWN"})
    assert not na.kind_unknown() and unk.kind_unknown()            # NOT_APPLICABLE != UNKNOWN
    gib = ValueType.from_dict({"datatype": "integer", "quantity_kind": "quantitykind:AmountOfData", "unit": "unit:GibiBYTE"})
    gb = ValueType.from_dict({"datatype": "integer", "quantity_kind": "quantitykind:AmountOfData", "unit": "unit:GigaBYTE"})
    assert canonical(gib, 1) != canonical(gb, 1) and gib.byte_convention == "IEC" and gb.byte_convention == "SI"
    rpm = ValueType.from_dict({"datatype": "decimal", "quantity_kind": "quantitykind:Count", "unit": "unit:NUM", "rate_window": "PT1M"})
    rps = ValueType.from_dict({"datatype": "decimal", "quantity_kind": "quantitykind:Count", "unit": "unit:NUM", "rate_window": "PT1S"})
    assert canonical(rpm, 60) == canonical(rps, 1)
    assert rpm.signature() != rps.signature()


def test_durations_month_needs_calendar():
    assert duration_seconds("P7D") == 604800 and duration_seconds("PT1H30M") == 5400
    with pytest.raises(OutOfDomain):
        duration_seconds("P1M")
    with pytest.raises(OutOfDomain):
        duration_seconds("P1Y")
    assert duration_seconds("P1M", {"seconds_per_month": 2629746}) == 2629746
