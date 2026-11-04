"""Módulo OWL: regeneração idêntica, tabelas C14 válidas, sem punning; pipeline independente do oráculo."""
import re
from pathlib import Path

from bo.contracts import validate as V

from bo.pilot.sto import common as C
from bo.pilot.sto import owl as O

PIPELINE = ("claims", "evidence", "lift", "abox", "owl", "tbox", "translate", "lower", "policy", "pipeline", "atoms",
            "canary", "render")


def test_module_regenerates_identically(syn, tmp_path):
    a = O.build_module(syn, {}, tmp_path / "a")
    b = O.build_module(syn, {}, tmp_path / "b")
    for f in ("sto-c3_full.ttl", "sto-c2_taxonomy.ttl", "sto-c1_table.ttl", "classes.jsonl", "properties.jsonl",
              "realizations.jsonl"):
        assert (tmp_path / "a" / f).read_bytes() == (tmp_path / "b" / f).read_bytes(), f
    for f, kind in (("classes.jsonl", "classes"), ("properties.jsonl", "properties"), ("realizations.jsonl", "realizations"),
                    ("sto-c3_full.ttl", "ttl"), ("sto-c2_taxonomy.ttl", "ttl")):
        r = V.validate(kind, tmp_path / "a" / f)
        assert r.ok, (f, r.errors[:3])
    assert a["ok_claims"] == len(syn.ok_claims())


def test_c1_table_has_no_axioms(syn, tmp_path):
    O.build_module(syn, {}, tmp_path)
    t = (tmp_path / "sto-c1_table.ttl").read_text(encoding="utf-8")
    assert "subClassOf" not in t and "owl:Class" not in t and "propertyChainAxiom" not in t


def test_pipeline_does_not_import_oracle():
    base = Path(C.__file__).parent
    for m in PIPELINE:
        src = (base / f"{m}.py").read_text(encoding="utf-8")
        assert not re.search(r"^\s*(from|import)\s+.*(oracle_io|sto_oracle)", src, re.M), m
