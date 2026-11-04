"""O avaliador reproduz a resposta esperada de toda fixture e de toda entrada de direção da calibração, e as
propriedades que o PILOT-EXIT vai cobrar nas retidas (invariância à embalagem e a renomeação, perda declarada)."""
import copy
import json
import os
from pathlib import Path

import pytest

import sto_oracle as o

STO = Path(__file__).resolve().parents[1]
REPO = STO.parents[1]
EA = json.loads((STO / "expected_answers.json").read_text(encoding="utf-8"))
FIX = sorted(EA["fixtures"].items())
DIRS = sorted(EA["directions"].items())


def _load(rel):
    return json.loads((REPO / rel).read_text(encoding="utf-8"))


def test_oracle_sha_matches_expected_answers():
    import hashlib
    assert hashlib.sha256((STO / "oracle" / "sto_oracle.py").read_bytes()).hexdigest() == EA["oracle_sha256"]


@pytest.mark.parametrize("fid,meta", FIX, ids=[f for f, _ in FIX])
def test_fixture_checks(fid, meta):
    fx = _load(meta["file"])
    assert fx["fixture_id"] == fid and fx["provider"] == meta["provider"]
    for chk in meta["checks"]:
        ok, got = o.evaluate_check(fx, chk)
        assert ok, (chk, got)
    assert o.polarity_consistent(meta["polarity"], meta["checks"]), meta["polarity"]


@pytest.mark.parametrize("eid,meta", DIRS, ids=[e for e, _ in DIRS])
def test_direction_entries(eid, meta):
    doc = _load(meta["file"])
    entry = dict(doc, expect=meta["expect"])
    ok, j = o.evaluate_entry(entry)
    assert ok, j
    if meta["variant"] == "acceptable":
        assert j["verdict"] == "ACCEPT" and not j["divergences"]
    if meta["variant"] == "acceptable_declared":
        assert j["verdict"] == "ACCEPT_WITH_DECLARED_LOSS" and not j["spurious_declared"]


def test_invariant_groups_have_same_neutral_decomposition():
    groups = {}
    for fid, meta in FIX:
        if meta.get("invariant_group"):
            groups.setdefault(meta["invariant_group"], []).append(o.neutral_decomposition(o.decompose(_load(meta["file"]))))
    assert groups
    for g, decs in groups.items():
        assert len(decs) >= 2 and all(d == decs[0] for d in decs), g


def _rename(fx, old, new):
    s = json.dumps(fx).replace(f".{old}.", f".{new}.").replace(f'"{old}":', f'"{new}":').replace(f".{old}\"", f".{new}\"")
    return json.loads(s)


@pytest.mark.parametrize("fid,meta", [x for x in FIX if x[1]["case"] in ("MC-LC-CUR", "MC-PUB-LEVEL")][:12])
def test_renaming_local_names_does_not_change_state(fid, meta):
    fx = _load(meta["file"])
    c = o.containers(fx)[0]
    old = c.split(".", 1)[1]
    fx2 = _rename(fx, old, "renamed_x")
    c2 = c.split(".", 1)[0] + ".renamed_x"
    a = o.effective_state(fx)["containers"][c]
    b = o.effective_state(fx2)["containers"][c2]
    assert a["versioning"] == b["versioning"]
    assert a["public_access"]["axes"] == b["public_access"]["axes"]
    if fx.get("timeline"):
        sa, sb = o.simulate(fx), o.simulate(fx2)
        assert (o.is_unk(sa) and o.is_unk(sb)) or sa["versions"] == sb["versions"]


def test_resource_order_does_not_change_state():
    for fid, meta in FIX[:40]:
        fx = _load(meta["file"])
        rev = copy.deepcopy(fx)
        rev["terraform"]["resource"] = dict(reversed(list(rev["terraform"]["resource"].items())))
        assert o.effective_state(fx) == o.effective_state(rev), fid


def test_every_direction_has_all_polarities_in_calibration():
    seen = {}
    for _, m in DIRS:
        seen.setdefault(m["direction"], set()).add(m["polarity"])
    assert len(seen) == 12
    assert all(v == {"positive", "negative", "unknown"} for v in seen.values()), seen
