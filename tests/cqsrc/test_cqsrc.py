"""Testes do CQSRC: leitor de HCL, extrator, regra de direção SKOS e o gate src_check. Cada gate é testado
também no sentido de reprovar (arranjo quebrado de propósito), para que um verde não prove outra coisa.

Rodar: python -I -B -m unittest discover -s tests/cqsrc -q   (temporário em $BO_TMP, nunca /tmp)
"""

import csv
import io
import os
import shutil
import sys
import tarfile
import unittest
import uuid
from pathlib import Path

REPO = Path(os.environ.get("BO_REPO") or Path(__file__).resolve().parents[2])
sys.path.insert(0, str(REPO / "src"))

from bo.cqsrc import align, build, concepts, extract, hcl_lite, src_check  # noqa: E402


def tmpdir() -> Path:
    base = Path(os.environ.get("BO_TMP") or "/Users/breno/doutorado/brevops-data/tmp/CQSRC")
    d = base / f"t_{uuid.uuid4().hex[:10]}"
    d.mkdir(parents=True)
    return d


SECTION = '''
locals {
  cis_v100_common_tags = merge(local.x_common_tags, {
    cis         = "true"
    cis_version = "v1.0.0"
  })
}
# comentário
benchmark "cis_v100" {
  title    = "X CIS v1.0.0"
  children = [benchmark.cis_v100_1]
  tags = merge(local.cis_v100_common_tags, { type = "Benchmark" })
}
locals {
  cis_v100_1_common_tags = merge(local.cis_v100_common_tags, {
    cis_section_id = "1"
  })
}
benchmark "cis_v100_1" {
  title = "1 Identity"
  children = [
    control.cis_v100_1_1,
    benchmark.cis_v100_1_2,
  ]
  tags = merge(local.cis_v100_1_common_tags, { type = "Benchmark" })
}
control "cis_v100_1_1" {
  title       = "1.1 Ensure \\"root\\" has MFA"
  description = <<-EOT
    texto livre { com chaves } e "aspas"
  EOT
  query       = query.root_mfa
  tags = merge(local.cis_v100_1_common_tags, {
    cis_item_id = "1.1"
    cis_level   = "1"
    cis_type    = "automated"
    service     = "X/IAM"
  })
}
benchmark "cis_v100_1_2" {
  title    = "1.2 Item feito de checagens externas"
  children = [control.ext_a, control.ext_b]
  tags = merge(local.cis_v100_1_common_tags, {
    cis_item_id = "1.2"
    cis_level   = "2"
    cis_type    = "automated"
  })
}
'''


class HclLite(unittest.TestCase):
    def test_blocks_attrs_strings_heredoc(self):
        bs = hcl_lite.parse(SECTION, "s.pp")
        kinds = [(b.type, tuple(b.labels)) for b in bs]
        self.assertIn(("control", ("cis_v100_1_1",)), kinds)
        c = [b for b in bs if b.labels == ["cis_v100_1_1"]][0]
        self.assertEqual(c.attrs["title"].value, '1.1 Ensure "root" has MFA')
        self.assertIn("{ com chaves }", c.attrs["description"].value)
        self.assertEqual(c.attrs["query"].value, "query.root_mfa")

    def test_rejects_garbage(self):
        for bad in ['control "x" {', 'x = "a" + "b"', 'control "x" { title = "sem fim }', 'a = 1\n']:
            with self.assertRaises(hcl_lite.HclError):
                hcl_lite.parse(bad, "bad.pp")

    def test_duplicate_attribute_rejected(self):
        with self.assertRaises(hcl_lite.HclError):
            hcl_lite.parse('control "x" {\n title = "a"\n title = "b"\n}\n', "d.pp")


class Extract(unittest.TestCase):
    def test_tree_tags_and_benchmark_item(self):
        cs = extract.extract_version("aws", "cis_v100", {"cis_v100/section_1.pp": SECTION})
        by = {c.cis_item_id: c for c in cs}
        self.assertEqual(set(by), {"1.1", "1.2"})
        c = by["1.1"]
        self.assertEqual((c.section_id, c.section_title, c.cis_version), ("1", "Identity", "v1.0.0"))
        self.assertEqual((c.cis_level, c.cis_type, c.service, c.query), ("1", "automated", "X/IAM", "root_mfa"))
        self.assertEqual(c.title, 'Ensure "root" has MFA')
        self.assertEqual(c.source_file, "cis_v100/section_1.pp")
        self.assertGreater(c.source_line, 1)
        self.assertEqual(by["1.2"].query, "ext_a+ext_b")
        self.assertIn("benchmark", by["1.2"].anomaly)

    def test_item_conflict_recorded_not_fixed(self):
        s = SECTION.replace('cis_item_id = "1.1"', 'cis_item_id = "1.9"')
        c = [x for x in extract.extract_version("aws", "cis_v100", {"cis_v100/s.pp": s}) if x.control_id ==
             "cis_v100_1_1"][0]
        self.assertEqual(c.cis_item_id, "1.9")
        self.assertEqual(c.title_item_id, "1.1")
        self.assertIn("difere", c.anomaly)

    def test_undefined_and_orphan_controls_fail(self):
        with self.assertRaises(extract.ExtractError):
            extract.extract_version("aws", "cis_v100", {"cis_v100/s.pp": SECTION.replace(
                "control.cis_v100_1_1,", "control.cis_v100_1_1, control.nao_existe,")})
        with self.assertRaises(extract.ExtractError):
            extract.extract_version("aws", "cis_v100", {"cis_v100/s.pp": SECTION + '\ncontrol "solto" {\n'
                                                                                  ' title = "9.9 x"\n}\n'})
        with self.assertRaises(extract.ExtractError):
            extract.extract_version("aws", "cis_v100", {"cis_v100/s.pp": SECTION.replace('"v1.0.0"', '"v9.0.0"')})

    def test_read_mod_from_tarball_without_extracting(self):
        d = tmpdir()
        try:
            arc = d / "m.tar.gz"
            with tarfile.open(arc, "w:gz") as tf:
                for name, text in {"raiz/cis_v100/section_1.pp": SECTION, "raiz/cis_v100/docs/x.md": "# x",
                                   "raiz/cis_controls_v8_ig1/a.pp": "", "raiz/outro/a.pp": ""}.items():
                    b = text.encode()
                    ti = tarfile.TarInfo(name)
                    ti.size = len(b)
                    tf.addfile(ti, io.BytesIO(b))
            dirs, skipped = extract.read_mod(arc)
            self.assertEqual(list(dirs), ["cis_v100"])
            self.assertEqual(list(dirs["cis_v100"]), ["cis_v100/section_1.pp"])
            self.assertEqual(skipped, ["cis_controls_v8_ig1"])
            self.assertEqual(sorted(p.name for p in d.iterdir()), ["m.tar.gz"])
            bad = d / "bad.tar.gz"
            with tarfile.open(bad, "w:gz") as tf:
                ti = tarfile.TarInfo("raiz/../fora.pp")
                ti.size = 0
                tf.addfile(ti, io.BytesIO(b""))
            with self.assertRaises(extract.ExtractError):
                extract.read_mod(bad)
        finally:
            shutil.rmtree(d)


class Direction(unittest.TestCase):
    def test_skos_direction_from_params(self):
        c = align.compare
        self.assertEqual(c({}, {})[0], "skos:closeMatch")
        self.assertEqual(c({"d": ("max", 90)}, {"d": ("max", 90)})[0], "skos:closeMatch")
        # a mais exigente (90 <= 365) -> a mais estreito -> "a broadMatch b" (b mais amplo)
        self.assertEqual(c({"d": ("max", 90)}, {"d": ("max", 365)})[0], "skos:broadMatch")
        self.assertEqual(c({"d": ("max", 365)}, {"d": ("max", 90)})[0], "skos:narrowMatch")
        self.assertEqual(c({}, {"d": ("max", 90)})[0], "skos:narrowMatch")  # ausente = sem limite
        self.assertEqual(c({"n": ("min", 14)}, {"n": ("min", 8)})[0], "skos:broadMatch")
        self.assertEqual(c({"p": ("forbid", (22, 3389))}, {"p": ("forbid", (22,))})[0], "skos:broadMatch")
        self.assertEqual(c({"e": ("allow", ())}, {"e": ("allow", ("icmp",))})[0], "skos:broadMatch")
        self.assertEqual(c({"p": ("forbid", (22,))}, {"p": ("forbid", (3389,))})[0], "skos:relatedMatch")
        self.assertEqual(c({"k": ("eq", "a")}, {"k": ("eq", "b")})[0], "skos:relatedMatch")
        self.assertEqual(c({"k": ("eq", "a")}, {})[0], "skos:relatedMatch")  # categoria ausente = incomparável
        self.assertEqual(c({"p": ("forbid", (22, 3389)), "s": ("forbid", ("v4",))},
                           {"p": ("forbid", (22,)), "s": ("forbid", ("v4", "v6"))})[0], "skos:relatedMatch")

    def test_mixed_operators_rejected(self):
        with self.assertRaises(align.AlignError):
            align.compare({"d": ("max", 1)}, {"d": ("min", 1)})


def _published() -> tuple[Path, Path]:
    return REPO / "cq" / "cis_controls.csv", REPO / "cq" / "cis_cross_provider.csv"


def _rewrite(src: Path, dst: Path, fn):
    with open(src, encoding="utf-8", newline="") as f:
        rows = list(csv.reader(f))
    rows = fn(rows)
    with open(dst, "w", encoding="utf-8", newline="") as f:
        csv.writer(f, lineterminator="\n").writerows(rows)


class SrcCheck(unittest.TestCase):
    def setUp(self):
        self.d = tmpdir()
        self.ctl, self.cross = _published()

    def tearDown(self):
        shutil.rmtree(self.d)

    def run_check(self, ctl, cross):
        return src_check.main(["--controls", str(ctl), "--cross", str(cross), "--no-sources"])

    def test_published_passes(self):
        self.assertEqual(src_check.main([]), 0)
        self.assertEqual(src_check.main(["CQSRC"]), 0)  # o despachante bo.cq.src_check pode repassar o ID

    def _break_controls(self, col, value, row=1):
        def fn(rows):
            i = rows[0].index(col)
            rows[row][i] = value
            return rows
        out = self.d / "c.csv"
        _rewrite(self.ctl, out, fn)
        return out

    def test_missing_section_title_source_fail(self):
        for col in ("section_id", "title", "source_uri", "provider"):
            with self.subTest(col=col):
                self.assertEqual(self.run_check(self._break_controls(col, ""), self.cross), 1)

    def test_wrong_source_line_or_provider_fail(self):
        self.assertEqual(self.run_check(self._break_controls("source_line", "999999"), self.cross), 1)
        self.assertEqual(self.run_check(self._break_controls("provider", "gcp"), self.cross), 1)
        self.assertEqual(self.run_check(self._break_controls("cis_item_id", "77.1"), self.cross), 1)

    def test_source_line_checked_against_tarball(self):
        bad = self._break_controls("source_line", "3")
        # a URL coerente com a linha errada passa no formato, mas não no tarball
        def fix_uri(rows):
            h = rows[0]
            r = rows[1]
            r[h.index("source_uri")] = r[h.index("source_uri")].rsplit("#L", 1)[0] + "#L3"
            return rows
        out = self.d / "line.csv"
        _rewrite(bad, out, fix_uri)
        self.assertEqual(self.run_check(out, self.cross), 0)
        self.assertEqual(src_check.main(["--controls", str(out), "--cross", str(self.cross)]), 1)

    def test_cross_must_cite_existing_latest_controls(self):
        def bad_id(rows):
            rows[1][rows[0].index("object_control_id")] = "cis_v999_1_1"
            return rows

        def bad_pred(rows):
            rows[1][rows[0].index("predicate")] = "skos:exactMatch"
            return rows

        def proven(rows):
            rows[1][rows[0].index("proof_status")] = "PROVEN"
            return rows

        def swapped(rows):
            h = rows[0]
            r = rows[1]
            r[h.index("subject_provider")], r[h.index("object_provider")] = (r[h.index("object_provider")],
                                                                              r[h.index("subject_provider")])
            return rows

        for fn in (bad_id, bad_pred, proven, swapped):
            with self.subTest(fn=fn.__name__):
                out = self.d / f"{fn.__name__}.csv"
                _rewrite(self.cross, out, fn)
                self.assertEqual(self.run_check(self.ctl, out), 1)

    def test_old_version_control_not_accepted_in_alignment(self):
        with open(self.ctl, encoding="utf-8", newline="") as f:
            old = next(r for r in csv.DictReader(f) if r["is_latest"] == "false" and r["provider"] == "aws")

        def fn(rows):
            h = rows[0]
            rows[1][h.index("subject_control_id")] = old["control_id"]
            return rows
        out = self.d / "old.csv"
        _rewrite(self.cross, out, fn)
        self.assertEqual(self.run_check(self.ctl, out), 1)


class Catalog(unittest.TestCase):
    def test_guards_and_reviews_cover_audit(self):
        controls, report = build.load_all()
        latest = build.latest_of(controls, report)
        rows = align.align(latest)
        audit = align.lexical_audit(latest, rows)
        self.assertEqual(audit["unreviewed"], 0)
        for k in concepts.REVIEWED_NON_MATCHES:
            pa, ia, pb, ib = k
            self.assertTrue(any(c.cis_item_id == ia for c in latest[pa]) and any(c.cis_item_id == ib
                                                                                 for c in latest[pb]), k)

    def test_broken_guard_fails_regeneration(self):
        con = concepts.CONCEPTS[0]
        saved = con["members"][0]["guard"]
        try:
            con["members"][0]["guard"] = r"isto nao aparece em titulo nenhum"
            controls, report = build.load_all()
            with self.assertRaises(align.AlignError):
                align.align(build.latest_of(controls, report))
        finally:
            con["members"][0]["guard"] = saved

    def test_regeneration_identical(self):
        self.assertEqual(build.main(["--check"]), 0)


if __name__ == "__main__":
    unittest.main()
