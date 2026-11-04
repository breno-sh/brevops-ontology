"""UNITS-QK-01 (STO-MAP CC-5): grandeza única por unidade, decidida pelo QUDT fixado, com citação conferida."""
from bo.units import crosscheck, qudt


def test_citation_lines_are_in_the_pinned_file():
    lines = (qudt.qudt_dir() / "VOCAB_QUDT-UNITS-ALL.ttl").read_text(encoding="utf-8").splitlines()
    for st in crosscheck.CITATION["statements"]:
        text = lines[st["line"] - 1].strip()
        if "subject" in st:
            assert text == st["subject"]
        else:
            _, pred, obj = st["triple"].split()
            assert text.rstrip(" ;.") == f"{pred} {obj}"


def test_qudt_never_links_bytes_to_information_entropy():
    idx = qudt.index()
    for u in ("BYTE", "BIT", "GibiBYTE", "MegaBIT"):
        assert "InformationEntropy" not in idx["units"][u]["kinds"]
        assert "AmountOfData" in idx["units"][u]["kinds"]


def test_decision_is_supported_by_qudt_for_every_unit():
    d = crosscheck.decision()
    assert d["resolves"] == ["PILOT-STO-MAP CC-5"]
    assert all(r["qudt_supports"] for r in d["units"])
    assert {r["quantity_kind"] for r in d["units"] if "BYTE" in r["unit"] or "BIT" in r["unit"]} == {
        "quantitykind:AmountOfData"}


def test_compare_flags_a_divergent_core(monkeypatch):
    monkeypatch.setattr(crosscheck, "semantics_units", lambda: {"unit:BYTE": "quantitykind:InformationEntropy"})
    monkeypatch.setattr(crosscheck, "transforms_units", lambda: {"unit:SEC": "quantitykind:Time"})
    assert crosscheck.compare() == ["SEMANTICS: unit:BYTE em quantitykind:InformationEntropy; o QUDT 3.5.3 dá "
                                    "quantitykind:AmountOfData"]
    monkeypatch.setattr(crosscheck, "semantics_units", lambda: {"unit:BYTE": "quantitykind:AmountOfData"})
    assert crosscheck.compare() == []


def test_written_decision_matches_regenerated():
    assert crosscheck.main(["--check"]) == 0
