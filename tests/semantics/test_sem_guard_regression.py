"""Regressão do defeito achado pelo TRANSFORMS: guardas insatisfazíveis que saíam SAT/UNKNOWN.
(a) version_range sobre termo de universo fechado (enum, booleano); (b) refers_to_kind com valor escalar no mesmo termo.
Além dos 39 casos, um oráculo de força bruta próprio (sobre o evaluate deste módulo) confere guardas aleatórias."""
import itertools
import json
import random
from pathlib import Path

import pytest

from bo.semantics import guards as G
from bo.semantics.vocab import ABSENT

CASES = json.loads((Path(__file__).parent / "data" / "guard_regression_39.json").read_text(encoding="utf-8"))["casos"]


@pytest.mark.parametrize("case", CASES, ids=[f"{i:02d}-{c['class']}" for i, c in enumerate(CASES)])
def test_regression_case(case):
    assert G.satisfiable(case["guard"])[0] == case["expected"] == "UNSAT"


def test_regression_counts():
    assert len(CASES) == 39
    assert {c["class"] for c in CASES} == {"kind_with_scalar_value", "version_range_over_closed_universe"}


def _brute(g):
    """Testa candidatos por termo no evaluate: constantes, valor novo, ABSENT, referências, universo fechado."""
    by = {}
    for a in g["all"]:
        by.setdefault(a["term"], []).append(a)
    tt = g.get("term_types") or {}
    res = "SAT"
    for term, atoms in by.items():
        kinds = sorted({a["value"] for a in atoms if a["op"] == "refers_to_kind"})
        ty = tt.get(term) or {}
        if ty.get("datatype") == "boolean":
            cands = [True, False]
        elif ty.get("enum") is not None:
            cands = list(ty["enum"])
        else:
            cands = ["__novo__", "0", 7]
            for a in atoms:
                v = a["value"]
                cands += [v] if a["op"] == "eq" else list(v) if a["op"] in ("in", "region_in", "edition_in") else \
                    list(v.values()) if a["op"] == "version_range" else []
            cands += [{"$kind": k} for k in kinds]
        cands.append(ABSENT)
        sub = {"all": [a for a in atoms if a["op"] != "refers_to_kind" or not kinds or a["value"] == kinds[0]],
               **({"term_types": tt} if tt else {})}
        if not any(G.evaluate(sub, {term: c})[0] == G.TRUE for c in cands):
            return "UNSAT"
        if len(kinds) > 1:
            if any(frozenset(p) in {frozenset(x) for x in g.get("kind_disjoint") or []}
                   for p in itertools.combinations(kinds, 2)):
                return "UNSAT"
            res = "UNKNOWN"
    return res


def _rand(rng):
    terms = ["object.edition", "object.provider_version", "object.tier", "object.flag", "object.ref", "subject.region"]
    g = {"all": [], "term_types": {"object.tier": {"datatype": "enum", "enum": ["t1", "t2", "t3"]},
                                   "object.flag": {"datatype": "boolean"}, "object.ref": {"datatype": "string"}}}
    vers = ["1.0", "2.0", "3.0", "4.0"]
    for _ in range(rng.randint(1, 4)):
        t = rng.choice(terms)
        if t == "object.edition":
            g["all"].append({"term": t, "op": "edition_in", "value": rng.sample(["std", "prem", "ent"], rng.randint(1, 2))})
        elif t == "object.provider_version":
            lo, hi = sorted(rng.sample(vers, 2))
            g["all"].append({"term": t, "op": "version_range", "value": rng.choice([{"min": lo}, {"max_exclusive": hi},
                                                                                     {"min": lo, "max_exclusive": hi}])})
        elif t in ("object.tier", "object.flag"):
            op = rng.choice(["eq", "version_range", "refers_to_kind", "present"])
            v = {"eq": rng.choice(["t1", "t2"]) if t == "object.tier" else rng.random() < .5,
                 "version_range": {"min": rng.choice(vers)}, "refers_to_kind": rng.choice(["ka", "kb"]),
                 "present": rng.random() < .5}[op]
            g["all"].append({"term": t, "op": op, "value": v})
        elif t == "object.ref":
            op = rng.choice(["eq", "refers_to_kind", "refers_to_kind", "present"])
            v = {"eq": "ref-a", "refers_to_kind": rng.choice(["ka", "kb"]), "present": rng.random() < .5}[op]
            g["all"].append({"term": t, "op": op, "value": v})
        else:
            g["all"].append({"term": t, "op": "region_in", "value": rng.sample(["r1", "r2"], 1)})
    if rng.random() < .3:
        g["kind_disjoint"] = [["ka", "kb"]]
    return g


def test_random_guards_match_own_brute_force_and_witnesses_hold():
    rng = random.Random(20261103)
    n = 0
    for _ in range(3000):
        g = _rand(rng)
        try:
            G.typecheck(g)
        except G.GuardTypeError:
            continue
        n += 1
        st, w = G.satisfiable(g)
        assert st == _brute(g), g
        if st == "SAT":
            assert G.evaluate(g, w)[0] == G.TRUE, (g, w)
    assert n > 2000
