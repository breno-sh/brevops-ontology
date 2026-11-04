"""Os dois gates do UNITS reprovam o que devem (mutações) e passam no value_space gravado."""
import json
import os
from pathlib import Path

import pytest

from bo.units import qudt, qudt_iri_only, rate_window

GOOD = {"atom_id": "aws:aws_x:size", "datatype": {"kind": "scalar", "scalar": "decimal"},
        "quantity_kind": "quantitykind:AmountOfData", "unit_qudt": "unit:GibiBYTE", "rate_window": None,
        "byte_convention": "IEC", "evidence": [{"level": "derived", "ref": "UNITS-UNK-01"}]}


def mut(**kw):
    r = json.loads(json.dumps(GOOD))
    r.update(kw)
    return r


def test_qudt_files_pinned():
    assert qudt.verify_files() == []


def test_qudt_accepts_good_and_markers():
    assert qudt_iri_only.check_record(GOOD) == []
    na = mut(quantity_kind="NOT_APPLICABLE", unit_qudt="NOT_APPLICABLE", byte_convention="NOT_APPLICABLE")
    assert qudt_iri_only.check_record(na) == []
    assert qudt_iri_only.check_record(mut(quantity_kind="UNKNOWN", unit_qudt="UNKNOWN")) == []
    assert qudt_iri_only.check_record(mut(unit_qudt="UNKNOWN")) == []


@pytest.mark.parametrize("bad", [
    mut(unit_qudt="GiB"),                                    # texto livre
    mut(unit_qudt="gibibytes"),
    mut(quantity_kind="data size"),
    mut(unit_qudt="unit:GIGABYTE_FAKE"),                     # não existe no QUDT
    mut(quantity_kind="quantitykind:Time"),                  # QUDT não liga GibiBYTE a Time
    mut(quantity_kind="quantitykind:InformationEntropy"),    # QUDT 3.5.3 não liga BYTE a InformationEntropy
    mut(unit_qudt="unit:PER-SEC", quantity_kind="quantitykind:Frequency"),  # fora do registro do TRANSFORMS
    mut(quantity_kind="UNKNOWN"),                            # UNKNOWN de grandeza com unidade
    mut(quantity_kind="NOT_APPLICABLE"),                     # NA só de um lado
    mut(unit_qudt="unknown"),                                # marcador fora da forma exata
    mut(format="metros"),                                    # formato fora do vocabulário
])
def test_qudt_rejects(bad):
    assert qudt_iri_only.check_record(bad)


def test_rate_window_rejects_and_accepts():
    ok, _ = rate_window.check_record(mut(rate_window="PT1S", unit_qudt="unit:MebiBYTE"), {})
    assert ok == []
    named = mut(atom_id="aws:aws_x:throughput_mibps", unit_qudt="unit:MebiBYTE")
    errs, is_rate = rate_window.check_record(named, {})
    assert is_rate and errs
    sent = mut(evidence=[{"level": "published", "ref": "DF-1"}], unit_qudt="unit:MebiBYTE")
    errs, is_rate = rate_window.check_record(sent, {"DF-1": "Throughput in MiB/s."})
    assert is_rate and errs
    unk = mut(atom_id="aws:aws_x:throughput_mibps", quantity_kind="UNKNOWN", unit_qudt="UNKNOWN",
              byte_convention="NOT_APPLICABLE")
    errs, is_rate = rate_window.check_record(unk, {})
    assert is_rate and errs == []
    na = mut(atom_id="aws:aws_x:requests_per_second", quantity_kind="NOT_APPLICABLE",
             unit_qudt="NOT_APPLICABLE", byte_convention="NOT_APPLICABLE")
    assert rate_window.check_record(na, {})[0]


@pytest.mark.parametrize("bad", [
    mut(rate_window="P1M"),                                  # janela com mês não é fixa
    mut(rate_window="PT0S"),                                 # janela não positiva
    mut(quantity_kind="UNKNOWN", unit_qudt="UNKNOWN", byte_convention="NOT_APPLICABLE", rate_window="PT1S"),
    mut(byte_convention="SI"),                               # GibiBYTE é IEC
    mut(unit_qudt="unit:BYTE", byte_convention="IEC"),       # BYTE sem prefixo: UNITS-BYTE-00 grava SI
])
def test_rate_window_type_errors(bad):
    errs, _ = rate_window.check_record(bad, {})
    assert errs


def _value_space() -> Path:
    return Path(os.environ["BO_DATA"]) / "UNITS" / "value_space.jsonl"


@pytest.mark.skipif(not _value_space().exists(), reason="value_space ainda não gerado")
def test_one_record_per_schema_atom_and_markers_distinct():
    from bo.units.build import PROVIDERS, bo_data
    want = set()
    for P, _ in PROVIDERS:
        with open(bo_data() / f"SCHEMA-{P}" / "atoms.jsonl", encoding="utf-8") as f:
            for line in f:
                i = line.find('"atom_id": "')
                want.add(line[i + 12:line.index('"', i + 12)])
    got, na_numeric, unk_string = set(), 0, 0
    with open(_value_space(), encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            got.add(r["atom_id"])
            dt = r["datatype"]
            if dt.get("scalar") in ("string", "boolean", "enum") and r["quantity_kind"] == "UNKNOWN":
                unk_string += 1
    assert got == want
    assert unk_string == 0   # texto, booleano e enum nunca viram UNKNOWN (NOT_APPLICABLE ≠ UNKNOWN)


@pytest.mark.skipif(not _value_space().exists(), reason="value_space ainda não gerado")
def test_gates_pass_on_written_value_space():
    assert qudt_iri_only.main([str(_value_space())]) == 0
    assert rate_window.main([str(_value_space())]) == 0
