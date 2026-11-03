"""Testes do PINS: regras puras (SemVer, corte, trimestres, majors) e o gate contra mutações plantadas."""

from __future__ import annotations

import datetime as dt
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from bo.pins import build as B
from bo.pins import check as C
from bo.pins import config, semver
from bo.pins import select as S

UTC = dt.timezone.utc


def rel(v, ts, plats=("darwin_arm64",)):
    return S.Release(v, dt.datetime.fromisoformat(ts).replace(tzinfo=UTC), ("5.0",), plats)


class TestSemver(unittest.TestCase):
    def test_order_numeric_not_lexical(self):
        vs = ["4.9.0", "4.10.0", "4.100.0", "4.67.3", "10.0.0"]
        self.assertEqual(sorted(vs, key=semver.key), ["4.9.0", "4.10.0", "4.67.3", "4.100.0", "10.0.0"])

    def test_prerelease_before_release(self):
        self.assertLess(semver.key("6.0.0-beta1"), semver.key("6.0.0"))
        self.assertLess(semver.key("6.0.0-beta1"), semver.key("6.0.0-beta2"))
        self.assertLess(semver.key("6.0.0-alpha.9"), semver.key("6.0.0-alpha.10"))
        self.assertTrue(semver.is_prerelease("6.0.0-rc1"))
        self.assertFalse(semver.is_prerelease("6.0.0"))

    def test_rejects_non_semver(self):
        with self.assertRaises(semver.SemverError):
            semver.parse("v6.0")


class TestSelect(unittest.TestCase):
    def test_stable_is_max_semver_not_latest_date(self):
        rels = [rel("8.0.0", "2026-08-26T17:00:00"), rel("7.46.2", "2026-10-23T19:49:04"),
                rel("8.1.0", "2026-09-01T00:00:00"), rel("9.0.0-beta1", "2026-10-30T00:00:00")]
        end = dt.datetime(2026, 11, 3, tzinfo=config.TZ)
        self.assertEqual(S.stable_before(rels, end).version, "8.1.0")

    def test_cutoff_day_is_recife_inclusive(self):
        # 02:59Z do dia 3 ainda é dia 2 em Recife (UTC-3); 03:00Z já é dia 3
        rels = [rel("1.0.0", "2026-11-01T00:00:00"), rel("1.1.0", "2026-11-03T02:59:59"),
                rel("1.2.0", "2026-11-03T03:00:00")]
        end = dt.datetime(2026, 11, 3, tzinfo=config.TZ)
        self.assertEqual(S.stable_before(rels, end).version, "1.1.0")
        self.assertEqual(rels[1].date_recife, "2026-11-02")

    def test_quarters_complete_only(self):
        end = dt.datetime(2026, 11, 3, tzinfo=config.TZ)
        qs = S.quarters(dt.date(2021, 1, 1), end)
        self.assertEqual(qs[0][0], "2021Q1")
        self.assertEqual(qs[-1][0], "2026Q3")
        self.assertEqual(len(qs), 23)
        self.assertEqual(qs[0][1], dt.datetime(2021, 4, 1, tzinfo=config.TZ))

    def test_quarter_boundary_in_recife(self):
        # publicado 01/04 01:00Z = 31/03 22:00 em Recife: pertence ao 1º trimestre
        rels = [rel("3.0.0", "2021-01-10T00:00:00"), rel("3.1.0", "2021-04-01T01:00:00")]
        nxt = dict(S.quarters(dt.date(2021, 1, 1), dt.datetime(2021, 7, 1, tzinfo=config.TZ)))["2021Q1"]
        self.assertEqual(S.stable_before(rels, nxt).version, "3.1.0")

    def test_major_first_vs_index_first(self):
        rels = [rel("4.67.3", "2022-03-14T19:33:16"), rel("4.68.0", "2022-03-20T00:00:00"),
                rel("5.0.0-beta", "2023-05-01T00:00:00"), rel("5.0.0", "2023-06-06T00:00:00"),
                rel("2.0.0", "2019-01-01T00:00:00")]
        out = S.first_of_each_major(rels, dt.datetime(2021, 1, 1, tzinfo=config.TZ),
                                    dt.datetime(2026, 11, 3, tzinfo=config.TZ))
        self.assertEqual([(r.version, w) for r, w in out], [("4.67.3", "index_first"), ("5.0.0", "major_first:5")])

    def test_history_merges_reasons_and_ends_at_pin(self):
        rels = [rel("3.0.0", "2020-06-01T00:00:00"), rel("3.5.0", "2021-03-01T00:00:00"),
                rel("4.0.0", "2026-06-20T00:00:00"), rel("4.1.0", "2026-10-30T00:00:00")]
        pin, picks, det = S.history(rels)
        self.assertEqual(pin.version, "4.1.0")
        self.assertEqual(picks[-1].release.version, "4.1.0")
        by = {p.release.version: p.reasons for p in picks}
        self.assertIn("major_first:4", by["4.0.0"])
        self.assertIn("quarter_end:2026Q2", by["4.0.0"])
        self.assertIn("quarter_end:2021Q1", by["3.5.0"])
        self.assertEqual(det["left_truncation"]["version_in_force"], "3.0.0")

    def test_v1_v2_divergence_is_reported(self):
        v1 = {"versions": [{"version": "1.0.0", "protocols": ["5.0"], "platforms": []},
                           {"version": "1.1.0", "protocols": ["5.0"], "platforms": []}]}
        v2 = {"included": [{"type": "provider-versions",
                            "attributes": {"version": "1.0.0", "published-at": "2021-01-01T00:00:00Z"}}]}
        rels, issues = S.releases_from_registry(v1, v2)
        self.assertEqual([r.version for r in rels], ["1.0.0"])
        self.assertTrue(issues and "só no v1" in issues[0])


class TestGateAgainstSnapshot(unittest.TestCase):
    """Usa o instantâneo real ($BO_DATA/PINS/registry_index/); sem ele o teste reprova (nada passa vazio)."""

    @classmethod
    def setUpClass(cls):
        cls.repo = config.bo_repo()
        if not (config.index_dir() / "snapshot.json").exists():
            raise AssertionError(f"instantâneo ausente em {config.index_dir()}")

    def test_build_is_deterministic(self):
        a, b = B.build(), B.build()
        self.assertEqual(a, b)

    def _with_repo_copy(self, mutate):
        tmp = Path(tempfile.mkdtemp(prefix="pins-test-", dir=config.bo_tmp()))
        old = os.environ.get("BO_REPO")
        try:
            for rel_ in ["universe/pins.json", "universe/history_versions.json"] + B.MANIFEST_FILES[2:] + [
                    "results/PINS/MANIFEST.sha256"]:
                src = self.repo / rel_
                if src.exists():
                    (tmp / rel_).parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src, tmp / rel_)
            (tmp / "contracts").symlink_to(self.repo / "contracts")  # o validador lê os schemas de $BO_REPO
            mutate(tmp)
            os.environ["BO_REPO"] = str(tmp)
            return C.run()
        finally:
            if old is None:
                os.environ.pop("BO_REPO", None)
            else:
                os.environ["BO_REPO"] = old
            shutil.rmtree(tmp, ignore_errors=True)

    def _edit(self, tmp, rel_, fn):
        p = tmp / rel_
        d = json.loads(p.read_text(encoding="utf-8"))
        fn(d)
        p.write_text(json.dumps(d, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")

    def test_control_copy_passes(self):
        r = self._with_repo_copy(lambda t: None)
        self.assertEqual(r.errors, [])

    def test_wrong_pin_version_fails(self):
        def m(t):
            self._edit(t, "universe/pins.json", lambda d: d["providers"][0].update(version="6.70.0"))
        r = self._with_repo_copy(m)
        self.assertTrue(any("estável no corte" in e for e in r.errors), r.errors)

    def test_missing_provider_fails(self):
        def m(t):
            self._edit(t, "universe/pins.json", lambda d: d["providers"].pop())
        r = self._with_repo_copy(m)
        self.assertTrue(any("providers esperados" in e for e in r.errors), r.errors)

    def test_index_sha_tamper_fails(self):
        def m(t):
            def f(d):
                d["providers"][1]["selection"][3]["index_sha256"] = "0" * 64
            self._edit(t, "universe/history_versions.json", f)
        r = self._with_repo_copy(m)
        self.assertTrue(any("sem sha do índice" in e for e in r.errors), r.errors)

    def test_date_tamper_fails(self):
        def m(t):
            def f(d):
                s = d["providers"][2]["selection"][5]
                s["released_at"] = "2020-01-01"
                d["providers"][2]["versions_doc"]["versions"][5]["released_at"] = "2020-01-01"
            self._edit(t, "universe/history_versions.json", f)
        r = self._with_repo_copy(m)
        self.assertTrue(any("data ≠ índice" in e for e in r.errors), r.errors)

    def test_dropped_quarter_fails(self):
        def m(t):
            def f(d):
                p = d["providers"][0]
                i = next(k for k, s in enumerate(p["selection"]) if s["reasons"] == ["quarter_end:2023Q3"])
                del p["selection"][i]
                del p["versions_doc"]["versions"][i]
            self._edit(t, "universe/history_versions.json", f)
        r = self._with_repo_copy(m)
        self.assertTrue(any("trimestres" in e for e in r.errors), r.errors)

    def test_different_cutoff_fails(self):
        def m(t):
            self._edit(t, "universe/history_versions.json", lambda d: d["cutoff"].update(date="2026-10-01"))
        r = self._with_repo_copy(m)
        self.assertTrue(any("data de corte diverge" in e for e in r.errors), r.errors)


if __name__ == "__main__":
    unittest.main()
