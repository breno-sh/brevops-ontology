"""bo.schema_oci.atoms: a biblioteca gera, esta passada só acrescenta write_only (C01 2.1.0)."""
import gzip
import json

import pytest
from conftest import schema_doc

from bo.contracts import validate as V
from bo.schema import build as libbuild
from bo.schema import core
from bo.schema_oci import atoms


def _gz(path, doc):
    with gzip.open(path, "wb") as f:
        f.write(json.dumps(doc).encode())
    return path


def _lines(p):
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines()]


def test_sem_write_only_sai_igual_a_biblioteca(work):
    gz = _gz(work / "s.json.gz", schema_doc())
    libbuild.build(gz, "oci", "9.99.0", work / "lib_a.jsonl", work / "lib_t.jsonl")
    r = atoms.make(gz, "9.99.0", work / "a.jsonl", work / "t.jsonl")
    assert (work / "a.jsonl").read_bytes() == (work / "lib_a.jsonl").read_bytes()
    assert (work / "t.jsonl").read_bytes() == (work / "lib_t.jsonl").read_bytes()
    assert r["write_only"] == 0 and r["atoms"] == 4 == r["schema_attributes"] and r["types"] == 1
    assert r["data_sources"] == 1


def test_write_only_marcado_no_atomo_certo_e_valida_c01(work):
    gz = _gz(work / "s.json.gz", schema_doc({"regra.dias": {"write_only": True}}))
    r = atoms.make(gz, "9.99.0", work / "a.jsonl", work / "t.jsonl")
    got = {a["atom_id"]: a.get("write_only") for a in _lines(work / "a.jsonl")}
    assert r["write_only"] == 1
    assert got == {"oci:oci_exemplo_bucket:id": None, "oci:oci_exemplo_bucket:name": None,
                   "oci:oci_exemplo_bucket:segredo": None, "oci:oci_exemplo_bucket:regra.dias": True}
    assert V.validate("C01_atoms", work / "a.jsonl").ok


def test_write_only_com_computed_reprova(work):
    doc = schema_doc({"segredo": {"write_only": True, "computed": True}})
    gz = _gz(work / "s.json.gz", doc)
    with pytest.raises(core.SchemaError, match="C01-WRITEONLY"):
        atoms.make(gz, "9.99.0", work / "a.jsonl", work / "t.jsonl")


def test_contagem_independente_de_atributos():
    ps = schema_doc()["provider_schemas"]["registry.terraform.io/oracle/oci"]
    assert atoms.count_schema_attributes(ps) == 4


def test_flag_totals(work):
    gz = _gz(work / "s.json.gz", schema_doc())
    atoms.make(gz, "9.99.0", work / "a.jsonl", work / "t.jsonl")
    t = atoms.flag_totals(work / "a.jsonl")
    assert t["required"] == 1 and t["optional"] == 3 and t["computed"] == 1 and t["sensitive"] == 1
    assert t["configurable"] == 4 and t["dentro_de_bloco"] == 1 and t["write_only"] == 0
