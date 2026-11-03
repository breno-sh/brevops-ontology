"""Ligação pré-registro x biblioteca: 28 métricas, 15 contrastes, política do desconhecido, sementes, nomes."""
import html
import json
import re

import pytest

from bo.metrics import contrasts as CT
from bo.metrics import policy as P
from bo.metrics import spec as S
from conftest import ROOT


def _prereg_text():
    t = (ROOT / "prereg" / "PREREG.html").read_text(encoding="utf-8")
    t = re.sub(r"<style.*?</style>", "", t, flags=re.S)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", t)))


def test_spec_frozen_and_bound():
    doc = S.load_spec()
    assert len(doc["metrics"]) == 28
    assert S.check_spec(doc) == []
    assert set(S.BINDINGS) == {m["metric_id"] for m in doc["metrics"]}


def test_spec_with_other_sha_is_refused(tmp_path):
    p = tmp_path / "metrics_spec.yaml"
    p.write_text(S.spec_path().read_text(encoding="utf-8") + "\n# emenda\n", encoding="utf-8")
    with pytest.raises(S.SpecError):
        S.load_spec(p)


def test_check_spec_catches_drift():
    doc = S.load_spec()
    doc["metrics"][0]["axis"] = "operational"
    cl = doc["metrics"][4]["definition"].replace("INFRA_ERROR contam", "contam")
    doc["metrics"][4]["definition"] = cl.replace("CONDITION_INDETERMINATE e INFRA_ERROR", "CONDITION_INDETERMINATE")
    errs = S.check_spec(doc)
    assert any("M-REPR-DEC: axis" in e for e in errs)
    assert any(e.startswith("M-OPCOV-DEC: desconhecidos") for e in errs)


def test_names_match_prereg():
    text = _prereg_text()
    for mid, b in S.BINDINGS.items():
        assert f"{mid} " in text and b.name in text, mid


def test_seeds_match_seeds_file():
    rows = [l.split("\t") for l in (ROOT / "prereg" / "SEEDS.txt").read_text(encoding="utf-8").splitlines()
            if l and not l.startswith("#") and not l.startswith("name\t")]
    seeds = {r[0]: int(r[1]) for r in rows}
    for name, val in seeds.items():
        assert S.seed(name) == val
    assert S.SEED_BOOT == seeds["SEED-BOOT"] and S.SEED_PERM == seeds["SEED-PERM"]
    assert (S.N_BOOT, S.N_PERM) == (4000, 10000)


def test_contrasts_match_power_json():
    assert CT.check_power() == []
    doc = json.loads((ROOT / "prereg" / "power.json").read_text(encoding="utf-8"))
    assert len(doc["data"]["contrasts"]) == 15 == len(CT.REGISTRY)
    assert len(CT.ESTIMANDS) == 6


def test_outcome_classes_match_prereg_table():
    text = _prereg_text()
    rows = re.findall(r"(trace_result|block_code|outcome_persistence|outcome_behavior) (\w+) (success|failure|bounded)",
                      text)
    assert len(rows) >= 2 + 15 + 6 + 6
    op, pe, be = P.operational_table(), P.persistence_table(), P.behavior_table()
    for enum, val, cls in rows:
        table = {"trace_result": op, "block_code": op, "outcome_persistence": pe, "outcome_behavior": be}[enum]
        assert table[val] == cls, (enum, val)


def test_enumerations_match_contracts():
    c00 = json.loads((ROOT / "contracts" / "C00_conventions.schema.json").read_text(encoding="utf-8"))
    assert tuple(c00["$defs"]["block_code"]["enum"]) == P.BLOCK_CODES
    c23 = json.loads((ROOT / "contracts" / "C23_translation_trace.schema.json").read_text(encoding="utf-8"))
    assert tuple(c23["$defs"]["trace"]["properties"]["result"]["enum"]) == P.TRACE_RESULTS


def test_every_metric_table_is_total_over_its_enumeration():
    for mid, b in S.BINDINGS.items():
        if b.kind == "product":
            continue
        assert set(b.table.values()) <= set(P.CLASSES)
        assert {c for c, k in b.table.items() if k == P.BOUNDED} == set(b.unknown), mid
    for mid in ("M-OPCOV-DEC", "M-OPCOV-FIELD", "M-OPCOV-GRAPH", "M-OPCOV-UNIT"):
        t = S.BINDINGS[mid].table
        assert set(P.BLOCK_CODES) <= set(t) and "carried" in t and "omitted" in t
    assert S.BINDINGS["M-OPCOV-UNIT"].table["UNKNOWN_INPUT"] == P.FAILURE
    assert S.BINDINGS["M-OPCOV-DEC"].table["UNKNOWN_INPUT"] == P.BOUNDED


def test_no_old_term_anywhere_in_library():
    for p in (ROOT / "src" / "bo" / "metrics").glob("*.py"):
        assert not re.search(r"(?i)ceiling|\bteto\b", p.read_text(encoding="utf-8")), p.name
