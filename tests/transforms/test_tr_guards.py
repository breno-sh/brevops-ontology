"""Gramática de guarda: tipagem, satisfatibilidade com testemunha, avaliação, interseção e composição."""
import json
import random
from pathlib import Path

import pytest

from bo.transforms import grammar as GR
from bo.transforms import guards as M
from bo.transforms.guard_sat import _rand_guard, classify

ROOT = Path(__file__).resolve().parents[2]
A, G = GR.A, GR.G


@pytest.mark.parametrize("tid,g,exp", GR.SAT_TESTS, ids=[t[0] for t in GR.SAT_TESTS])
def test_sat_tests(tid, g, exp):
    st, w = M.satisfiable(g)
    assert st == exp == M.brute_force(g)
    if st == "SAT":
        assert M.check_witness(g, w)


def test_sat_tests_published_and_semantics_agree():
    from bo.semantics import guards as S
    doc = json.loads((ROOT / "transforms/conditions.grammar.json").read_text(encoding="utf-8"))
    assert doc == GR.document()
    for t in doc["sat_tests"]:
        assert S.satisfiable(t["guard"])[0] == t["expected"], t["test_id"]
    assert set(doc["operators"]) == set(M.OPS)


@pytest.mark.parametrize("pid,g1,g2", GR.INCOMPATIBLE_PAIRS, ids=[p[0] for p in GR.INCOMPATIBLE_PAIRS])
def test_incompatible_intersection_is_empty(pid, g1, g2):
    assert M.satisfiable(g1)[0] == "SAT" and M.satisfiable(g2)[0] == "SAT"
    st, why = M.intersection_satisfiable(g1, g2)
    assert st == "UNSAT" and why["why"]


@pytest.mark.parametrize("pid,g1,g2", GR.COMPATIBLE_PAIRS, ids=[p[0] for p in GR.COMPATIBLE_PAIRS])
def test_compatible_intersection(pid, g1, g2):
    st, w = M.intersection_satisfiable(g1, g2)
    assert st == "SAT" and M.check_witness(M.intersect(g1, g2), w)


@pytest.mark.parametrize("kid,g1,g2,exp", GR.COMPOSITIONS, ids=[k[0] for k in GR.COMPOSITIONS])
def test_composition(kid, g1, g2, exp):
    st, g13, _ = M.compose(g1, g2)
    assert st == exp
    M.typecheck(g13)
    assert all(not a["term"].startswith("n1.") for a in g13["all"])


@pytest.mark.parametrize("bad", [
    {"all": [A("object.x", "eq", 1)]},                                           # sem term_types
    {"all": [A("object.x", "eq", "a")], "term_types": {"object.x": {"datatype": "integer"}}},
    {"all": [A("object.tier", "eq", "gold")], "term_types": {"object.tier": GR.TIER}},
    {"all": [A("object.name", "region_in", ["r-a"])]},                           # region_in fora de .region
    {"all": [A("object.provider_version", "version_range", {"min": "6", "max_exclusive": "5"})]},
    {"all": [A("object.provider_version", "version_range", {"min": "v5"})]},
    {"all": [A("object.provider_version", "version_range", {})]},
    {"all": [A("object.region", "region_in", [])]},
    {"all": [A("object.k", "present", "yes")]},
    {"all": [A("object.k", "not_in", ["a"])]},                                   # operador fora da gramática
    {"all": [A("other.k", "present", True)]},                                    # papel inválido
    {"all": [{"term": "object.k", "op": "present"}]},
    {"all": [], "any": []},
    {"all": [], "kind_disjoint": [["a"]]},
])
def test_typecheck_rejects(bad):
    from bo.semantics import guards as S
    with pytest.raises(M.GuardTypeError):
        M.typecheck(bad)
    with pytest.raises(S.GuardTypeError):
        S.typecheck(bad)


def test_evaluate_three_valued():
    g = G(A("object.region", "region_in", ["r-a"]), A("object.kms_key", "present", True))
    assert M.evaluate(g, {"object.region": "r-a", "object.kms_key": "k"})[0] == "TRUE"
    assert M.evaluate(g, {"object.region": "r-b", "object.kms_key": "k"})[0] == "FALSE"
    assert M.evaluate(g, {"object.region": "r-a"})[0] == "INDETERMINATE"
    assert M.evaluate(g, {"object.region": "r-a", "object.kms_key": {"$not_read": True}})[0] == "INDETERMINATE"
    assert M.evaluate(g, {"object.region": "r-b", "object.kms_key": {"$symbolic": True}})[0] == "FALSE"
    assert M.evaluate(g, {"object.region": "r-a", "object.kms_key": {"$absent": True}})[0] == "FALSE"


def test_intersect_type_conflict():
    g1 = G(A("object.x", "eq", "a"), term_types={"object.x": GR.STR})
    g2 = G(A("object.x", "eq", 1), term_types={"object.x": GR.INT})
    with pytest.raises(M.GuardTypeError):
        M.intersect(g1, g2)


def test_former_divergences_now_agree():
    """As duas classes em que bo.semantics.guards dizia SAT (corrigidas em f48865f): nenhum valor torna TRUE."""
    from bo.semantics import guards as S
    g_a = G(A("object.provider_version", "version_range", {"min": "6"}),
            term_types={"object.provider_version": {"datatype": "enum", "enum": ["4.9", "5.0"]}})
    g_b = G(A("object.target", "refers_to_kind", "subnet"), A("object.target", "eq", "ref-a"),
            term_types={"object.target": GR.STR})
    for g, cls in ((g_a, "version_range_over_closed_universe"), (g_b, "kind_with_scalar_value")):
        assert S.satisfiable(g)[0] == M.satisfiable(g)[0] == "UNSAT" == M.brute_force(g)
        assert classify(g) == cls
    for v in ("4.9", "5.0", {"$absent": True}):
        assert M.evaluate(g_a, {"object.provider_version": v})[0] == "FALSE"


def test_random_agreement_with_oracle():
    rng = random.Random(11)
    n = 0
    for _ in range(800):
        g = _rand_guard(rng)
        try:
            M.typecheck(g)
        except M.GuardTypeError:
            continue
        n += 1
        st, w = M.satisfiable(g)
        assert st == M.brute_force(g), json.dumps(g)
        if st == "SAT":
            assert M.check_witness(g, w), json.dumps(g)
    assert n > 700
