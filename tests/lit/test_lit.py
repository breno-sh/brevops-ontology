"""Testes do módulo LIT. Cada gate é quebrado de propósito numa cópia (arranjo errado não pode ficar verde)."""
from __future__ import annotations

import csv
import io
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from bo.lit import bib, build, cocoon_disambiguation, data, ids, matrix_check, verify

ROOT = Path(os.environ.get("BO_REPO") or Path(__file__).resolve().parents[2])
BIB = ROOT / "lit" / "related.bib"
CSV = ROOT / "lit" / "positioning_matrix.csv"
HTML = ROOT / "lit" / "RELATED_WORK.html"
LEDGER = ROOT / ids.LEDGER_REL
COCOON = ROOT / "results" / "LIT" / "cocoon_disambiguation.json"


def ledger():
    return json.loads(LEDGER.read_text(encoding="utf-8"))


class Work(unittest.TestCase):
    """Cópia dos artefatos numa pasta temporária (TMPDIR do runner = $BO_DATA/tmp/LIT)."""

    def setUp(self):
        self.d = Path(tempfile.mkdtemp(prefix="lit-test-"))
        for p in (BIB, CSV, HTML, LEDGER, COCOON):
            shutil.copy(p, self.d / p.name)

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def p(self, name):
        return self.d / name

    def mcheck(self):
        return matrix_check.check(self.p("positioning_matrix.csv"), self.p("related.bib"),
                                  self.p("RELATED_WORK.html"), self.p("id_resolution.json"))

    def ccheck(self):
        return cocoon_disambiguation.check(self.p("related.bib"), self.p("cocoon_disambiguation.json"),
                                           self.p("positioning_matrix.csv"), self.p("RELATED_WORK.html"),
                                           self.p("id_resolution.json"))[0]

    def edit_row(self, row_id, **kw):
        path = self.p("positioning_matrix.csv")
        with open(path, encoding="utf-8", newline="") as fh:
            rows = list(csv.DictReader(fh))
        out = []
        for r in rows:
            if r["row_id"] == row_id:
                if kw.get("_drop"):
                    continue
                r.update({k: v for k, v in kw.items() if not k.startswith("_")})
            out.append(r)
        buf = io.StringIO()
        w = csv.DictWriter(buf, fieldnames=data.COLUMNS, lineterminator="\n")
        w.writeheader()
        w.writerows(out)
        path.write_text(buf.getvalue(), encoding="utf-8")


class TestBibAndIds(unittest.TestCase):
    def test_roundtrip(self):
        parsed = bib.parse(bib.render(data.ENTRIES, data.EDITED_AT))
        self.assertEqual([e["key"] for e in parsed], [e["key"] for e in data.ENTRIES])
        for e, p in zip(data.ENTRIES, parsed):
            self.assertEqual(dict((k, " ".join(v.split())) for k, v in e["fields"]), p["fields"])

    def test_duplicate_key_rejected(self):
        with self.assertRaises(bib.BibError):
            bib.parse("@misc{a, title={x}}\n@misc{a, title={y}}")

    def test_isbn_checksum(self):
        self.assertTrue(ids.isbn13_ok("978-83-60810-22-4"))      # cabeçalho do artigo mOSAIC
        self.assertFalse(ids.isbn13_ok("978-83-60810-34-4"))     # índice dos anais: reprova
        self.assertTrue(ids.isbn13_ok("978-0-262-52781-1"))

    def test_formats(self):
        self.assertIsNone(ids.validate_format("commit", "github:a/b@" + "0" * 40))
        self.assertIsNotNone(ids.validate_format("commit", "github:a/b@2118338"))
        self.assertIsNotNone(ids.validate_format("wayback", "https://example.org/x"))


def entry(**fields):
    return {"key": "t", "type": "article", "fields": {"author": "Kalinin, N.", "title": "T", "year": "2026", **fields}}


class TestVerify(unittest.TestCase):
    def setUp(self):
        self.led = ledger()

    def test_real_bib_all_pass(self):
        vs = verify.check_all(bib.parse(BIB.read_text(encoding="utf-8")), self.led)
        self.assertTrue(all(v.ok for v in vs), [(v.key, v.problems) for v in vs if not v.ok])

    def test_doi_without_ledger_record_fails(self):
        v = verify.check_entry(entry(doi="10.9999/nao.existe"), self.led)
        self.assertFalse(v.ok)

    def test_no_identifier_fails(self):
        self.assertFalse(verify.check_entry(entry(), self.led).ok)

    def test_title_mismatch_fails(self):
        v = verify.check_entry(entry(doi="10.1134/S1054661826700367", title="Outra coisa qualquer"), self.led)
        self.assertFalse(v.ok)

    def test_undeclared_author_mismatch_fails(self):
        k = next(x for x in bib.parse(BIB.read_text(encoding="utf-8")) if x["key"] == "zhang2012cocoon")
        f = dict(k["fields"])
        f.pop("crossref_mismatch")
        self.assertFalse(verify.check_entry({"key": "z", "type": "inproceedings", "fields": f}, self.led).ok)
        self.assertTrue(verify.check_entry(k, self.led).ok)

    def test_std_without_wayback_fails(self):
        led = {"records": {"std:DMTF DSP0263 2.0.0": {"status": "ok"}}}
        self.assertFalse(verify.check_entry(entry(altid="std:DMTF DSP0263 2.0.0"), led).ok)

    def test_non_crossref_doi_needs_altid(self):
        led = {"records": {"doi:10.48550/arxiv.2007.02135": {"status": "not_crossref", "ra": "DataCite"}}}
        self.assertFalse(verify.check_entry(entry(doi="10.48550/arXiv.2007.02135"), led).ok)
        led["records"]["arxiv:2007.02135"] = {"status": "ok"}
        v = verify.check_entry(entry(doi="10.48550/arXiv.2007.02135", altid="arxiv:2007.02135"), led)
        self.assertTrue(v.ok, v.problems)
        self.assertEqual(v.basis, "altid")

    def test_failed_altid_fails_entry(self):
        led = ledger()
        k = "commit:github:someengineering/fixinventory@211833381fdd07690bc789d30ffc2bd84a67744e"
        led["records"][k] = dict(led["records"][k], status="fail")
        e = next(x for x in bib.parse(BIB.read_text(encoding="utf-8")) if x["key"] == "fixinventory2025")
        self.assertFalse(verify.check_entry(e, led).ok)


class TestMatrix(Work):
    def test_real_files_pass(self):
        self.assertEqual(self.mcheck(), [])

    def test_kalinin_artifact_available_fails(self):
        self.edit_row("kalinin2026", artifact_status="disponivel")
        self.assertTrue(any("Kalinin" in e for e in self.mcheck()))

    def test_kalinin_unpublished_fails(self):
        self.edit_row("kalinin2026", article_status="nao_se_aplica")
        self.assertTrue(any("article_status" in e for e in self.mcheck()))

    def test_kalinin_forbidden_phrase_fails(self):
        p = self.p("RELATED_WORK.html")
        p.write_text(p.read_text(encoding="utf-8").replace("O artigo está publicado", "O artigo não publicado"),
                     encoding="utf-8")
        self.assertTrue(any("proibida" in e for e in self.mcheck()))

    def test_kalinin_missing_hermit_fails(self):
        r = next(x for x in data.ROWS if x["row_id"] == "kalinin2026")
        self.edit_row("kalinin2026", what_it_does=r["what_it_does"].replace("HermiT", "um raciocinador"))
        self.assertTrue(any("HermiT" in e for e in self.mcheck()))

    def test_kalinin_providers_fail(self):
        self.edit_row("kalinin2026", providers="AWS;Azure;GCP;OCI")
        self.assertTrue(any("provedores" in e for e in self.mcheck()))

    def test_source_not_of_row_fails(self):
        self.edit_row("zodiac", source="doi:10.1134/S1054661826700367")
        self.assertTrue(any("zodiac" in e and "source" in e for e in self.mcheck()))

    def test_empty_source_fails(self):
        self.edit_row("cimi", source="")
        self.assertTrue(any("cimi" in e for e in self.mcheck()))

    def test_required_work_missing_fails(self):
        self.edit_row("terramod", _drop=True)
        self.assertTrue(any("TerraMod" in e for e in self.mcheck()))

    def test_webmedia_first_person_fails(self):
        self.edit_row("webmedia2025", what_it_does="Nosso trabalho anterior usa ontologias OWL.")
        self.assertTrue(any("primeira pessoa" in e for e in self.mcheck()))

    def test_bad_enum_fails(self):
        self.edit_row("fix", threat_to_novelty="enorme")
        self.assertTrue(any("threat_to_novelty" in e for e in self.mcheck()))


class TestCocoon(Work):
    def test_real_files_pass(self):
        self.assertEqual(self.ccheck(), [])

    def test_one_entry_missing_fails(self):
        p = self.p("related.bib")
        t = p.read_text(encoding="utf-8")
        i = t.index("@inproceedings{zhang2019cocoon")
        j = t.index("\n}\n", i) + 3
        p.write_text(t[:i] + t[j:], encoding="utf-8")
        self.assertTrue(self.ccheck())

    def test_registry_wrong_year_fails(self):
        p = self.p("cocoon_disambiguation.json")
        js = json.loads(p.read_text(encoding="utf-8"))
        js["entries"][1]["year"] = "2012"
        p.write_text(json.dumps(js), encoding="utf-8")
        self.assertTrue(any("diverge" in e for e in self.ccheck()))


class TestBuild(unittest.TestCase):
    def test_regeneration_identical(self):
        out = build.render_all(ROOT)
        for rel, text in out.items():
            self.assertEqual((ROOT / rel).read_text(encoding="utf-8"), text, rel)


if __name__ == "__main__":
    unittest.main()
