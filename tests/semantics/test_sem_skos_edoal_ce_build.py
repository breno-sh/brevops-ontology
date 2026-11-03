"""SKOS ida e volta, EDOAL, contraexemplos (com mutação), compromissos do REQUIREMENTS e regeneração idêntica."""
import copy
import json

import pytest

from bo.semantics import build, common, edoal, owl_theory as O, sssom_io as S
from bo.semantics import vocab
from bo.semantics.content import counterexamples as CEC
from bo.semantics.content import examples as E
from bo.semantics.counterexamples import verify
from bo.semantics.fixtures import suite
from bo.semantics.rules import RULES
from bo.semantics.skos_roundtrip import checks as rt_checks


def test_skos_roundtrip_all_checks():
    res = rt_checks()
    assert all(c["ok"] for c in res), [c for c in res if not c["ok"]]


def test_broken_direction_is_caught(monkeypatch):
    """Quebrar de propósito: com a tabela da v2 (subconjunto invertido), o ida e volta tem de reprovar."""
    monkeypatch.setitem(vocab.SUBSET_SIDE, "broad", "object")
    monkeypatch.setitem(vocab.SUBSET_SIDE, "narrow", "subject")
    res = {c["check"]: c["ok"] for c in rt_checks()}
    assert not res["claim_assessed_ok"]


def test_sssom_py_findings_are_real():
    tsv = S.write_tsv([E.BROAD_ARCHIVE], "https://example.org/ms/t")
    v = S.sssom_py_view(tsv, common.tmp_dir())
    assert v["columns"] == ["subject_id", "predicate_id", "object_id", "mapping_justification"]   # extensões descartadas
    bad = tsv.replace("subject_value_type", "subject_type")
    assert S.sssom_py_view(bad, common.tmp_dir())["rows"] == []   # colisão com slot padrão: linha some


def test_owl_closure_semantics():
    g = O.closure([E.BROAD_ARCHIVE])
    assert O.has(g, "pb:storage_class", "skos:narrowMatch", "pa:archive_class")
    assert not O.has(g, "pb:storage_class", "skos:broadMatch", "pa:archive_class")
    g2 = O.closure([E.EXACT_DAYS_HOURS, E.EXACT_HOURS_SECS])
    assert O.has(g2, "pa:log_retention_days", "skos:exactMatch", "pc:log_retention_seconds")   # transitiva
    assert O.has(g2, "pc:log_retention_seconds", "skos:exactMatch", "pa:log_retention_days")   # simétrica


def test_edoal_roundtrip_and_direction():
    recs = sorted(E.all_examples().values(), key=lambda r: r["claim_id"])
    r = edoal.roundtrip(recs)
    assert r["same"] and {x["claim_id"] for x in r["skipped"]} == {"CLM-CL-01", "CLM-CL-02", "CLM-RE-01", "CLM-TI-01"}
    g, _ = edoal.export([E.BROAD_ARCHIVE])
    assert {str(o) for o in g.objects(None, edoal.ALIGN.relation)} == {"<"}   # broad: entity1 ⊑ entity2
    g, _ = edoal.export([E.NARROW_TLS])
    assert {str(o) for o in g.objects(None, edoal.ALIGN.relation)} == {">"}


def test_every_rule_has_counterexample_and_all_verify():
    ces = CEC.records()
    assert {c["rule_id"] for c in ces} == set(RULES)
    res = [verify(c) for c in ces]
    assert all(r["ok"] for r in res), [r["ce_id"] for r in res if not r["ok"]]
    strict = [r for r in res if r["mutation"] == "strict"]
    assert len(strict) >= 0.8 * len(res)
    assert all(c.get("note") for c in ces if c["mutation"] == "rule_only")   # rule_only sempre diz quem segura


def test_counterexample_detects_rule_removal():
    """Arranjo que prova a coisa certa: se a regra some, o contraexemplo dela deixa de ser rejeitado por ela."""
    for c in CEC.records():
        off = verify(c)["rule_disabled"]
        assert c["rule_id"] not in off["rules"]


def test_requirements_commitments_and_cqs_reproduce():
    s = suite()
    assert s["n"] == 17 and s["n_reproduces"] == 17, [r["id"] for r in s["rows"] if not r["reproduces"]]


def test_build_regenerates_identically():
    root = common.repo()
    files = build.all_files(root)
    diff = [p for p, b in files.items() if not (root / p).is_file() or (root / p).read_bytes() != b]
    assert not diff, diff


def test_published_counterexamples_equal_content():
    pub = common.load_jsonl(common.semantics_dir() / "counterexamples.jsonl")
    assert pub == json.loads(json.dumps(CEC.records()))
