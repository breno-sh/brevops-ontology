"""Testes unitários das ferramentas do REPO (rodados por gates/REPO.sh e make test)."""

import os
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.dont_write_bytecode = True

from bo.repo import catalog, commits, core, fixtures, lane, privacy, smoke  # noqa: E402


class Catalogo(unittest.TestCase):
    def test_strip_comment_respeita_aspas(self):
        self.assertEqual(catalog.strip_comment("python -I x.py  # comentário"), ("python -I x.py", "comentário"))
        self.assertEqual(catalog.strip_comment("bash -lc 'echo # não é comentário'")[0],
                         "bash -lc 'echo # não é comentário'")
        self.assertEqual(catalog.strip_comment("echo a#b")[0], "echo a#b")

    def test_auto_referencia(self):
        self.assertTrue(catalog.is_self_gate("make -C $BO_REPO gate ID=REPO", "REPO"))
        self.assertFalse(catalog.is_self_gate("make -C $BO_REPO gate ID=LIT", "REPO"))
        self.assertFalse(catalog.is_self_gate("make -C $BO_REPO integration", "REPO"))

    def test_casamento_de_caminhos(self):
        self.assertTrue(catalog.matches("/r/src/bo/x/a.py", "/r/src/bo/x/"))
        self.assertFalse(catalog.matches("/r/src/bo/xy/a.py", "/r/src/bo/x/"))
        self.assertTrue(catalog.matches("/d/CORPUS-AWS/usage.jsonl", "/d/CORPUS-*/usage.jsonl"))
        self.assertFalse(catalog.matches("/d/CORPUS-AWS/sub/usage.jsonl", "/d/CORPUS-*/usage.jsonl"))
        self.assertTrue(catalog.overlaps("/d/GOLD-*/", "/d/GOLD-CARTO/gold.jsonl"))
        self.assertFalse(catalog.overlaps("/d/A/x.txt", "/d/A/y.txt"))

    def test_expansao_de_index_sets(self):
        cat = catalog.Catalog({"index_sets": {"provider": ["aws", "oci"]}, "modules": []}, Path("x.json"))
        got = cat.expand("$BO_DATA/S/{provider}/a.json", "S")
        self.assertEqual([Path(g).parent.name for g in got], ["aws", "oci"])

    def test_modulo_inexistente_da_erro_claro(self):
        cat = catalog.Catalog({"modules": [{"stable_id": "REPO"}]}, Path("x.json"))
        with self.assertRaises(core.BoError) as e:
            cat.get("repo")
        self.assertIn("quis dizer REPO", str(e.exception))
        self.assertEqual(e.exception.code, 2)


class Privacidade(unittest.TestCase):
    def test_doze_digitos_dentro_de_hash_nao_conta(self):
        d12 = "".join(str(i % 10) for i in range(1, 13))
        self.assertEqual(privacy.twelve_digit_hits("sha " + d12 + "ab" * 20), [])
        self.assertEqual(len(privacy.twelve_digit_hits("conta " + d12 + " fim")), 1)
        self.assertEqual(privacy.twelve_digit_hits("x " + d12 + "3 y"), [])  # 13 dígitos

    def test_mascara_nao_expoe_valor(self):
        self.assertNotIn("segredo", privacy.mask("segredo-muito-longo"))


class Commits(unittest.TestCase):
    def test_portugues(self):
        self.assertGreater(*commits.language_score("cria o runner de gates e a trava"))
        pt, en = commits.language_score("add the gate runner for the repo")
        self.assertGreaterEqual(en, pt)

    def test_proibidos(self):
        self.assertTrue(commits.lint_message("[REPO] cria o gate\n\nCo-authored-by: x <x@example.org>"))
        self.assertFalse(commits.lint_message("[REPO] cria o gate de posse"))


class Smoke(unittest.TestCase):
    def test_divide_comandos(self):
        parts = smoke.split_simple("a x && b y || c ; d | e")
        self.assertEqual([p[0] for p in parts], ["a", "b", "c", "d", "e"])

    def test_expande_variaveis(self):
        self.assertEqual(smoke.expand("$BO_REPO/t/${X}", {"BO_REPO": "/r", "X": "y"}), "/r/t/y")
        self.assertEqual(smoke.expand("$NADA/x", {}), "$NADA/x")


class Sandbox(unittest.TestCase):
    def test_regra_absoluta(self):
        rx = lane.rule_regex("Read(//Users/u/a b/**)")
        self.assertTrue(rx.match("/Users/u/a b/c/d"))
        self.assertTrue(rx.match("/Users/u/a b"))
        self.assertFalse(rx.match("/Users/u/a bc"))

    def test_complemento_nega_irmaos(self):
        base = Path(fixtures.scratch_root()) / f"compl-{os.getpid()}"
        try:
            (base / "a" / "keep").mkdir(parents=True)
            (base / "a" / "other").mkdir()
            (base / "b").mkdir()
            deny = lane.complement([base / "a" / "keep"], root=base)
            self.assertEqual(sorted(p.name for p in deny), ["b", "other"])
        finally:
            import shutil
            shutil.rmtree(base, ignore_errors=True)

    def test_papel_padrao(self):
        self.assertEqual(lane.norm_role(None, "MAP-AWSGCP-NET"), "mapper")
        self.assertEqual(lane.norm_role(None, "PILOT-STO-GLOSS"), "glossarist")
        self.assertEqual(lane.norm_role(None, "GLOSSARY-AUDIT"), "auditor")
        self.assertEqual(lane.norm_role(None, "REPO"), "builder")
        self.assertEqual(lane.norm_role("mapeador", "X"), "mapper")


class GateRunner(unittest.TestCase):
    def test_smoke_bloqueia_execucao_e_pula_auto_referencia(self):
        mods = [fixtures.module("RUIM", gates=["python -I -m bo.nao_existe.x && touch $BO_DATA/MARCA"]),
                fixtures.module("BOM", gates=["make -C $BO_REPO gate ID=BOM", "touch $BO_DATA/RODOU"])]
        with fixtures.sandbox(mods) as root:
            repo, data = root / "repo", root / "data"
            fixtures.commit_files(repo, "[REPO] copia o Makefile", {
                "Makefile": (ROOT / "Makefile").read_text(encoding="utf-8"),
                "gates/RUIM.sh": "#!/bin/sh\ntrue\n", "gates/BOM.sh": "#!/bin/sh\ntouch $BO_DATA/SH\n"})
            for n in ("RUIM", "BOM"):
                os.chmod(repo / "gates" / f"{n}.sh", 0o755)
            run = [sys.executable, "-I", "-B", "-c",
                   f"import sys; sys.path.insert(0, {str(ROOT / 'src')!r}); from bo.repo.gate_runner import main; "
                   "from bo.repo import core; core.run_main(lambda: main(sys.argv[1:]))"]
            r = subprocess.run(run + ["RUIM"], capture_output=True, text=True)
            self.assertEqual(r.returncode, 3, r.stdout + r.stderr)
            self.assertFalse((data / "MARCA").exists())
            r = subprocess.run(run + ["BOM"], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("SKIP", r.stdout)
            self.assertTrue((data / "RODOU").exists() and (data / "SH").exists())
            self.assertTrue((data / "BOM" / "gate_report.json").exists())
            r = subprocess.run(run + ["NAO-EXISTE"], capture_output=True, text=True)
            self.assertEqual(r.returncode, 2)
            self.assertIn("não existe", r.stderr)


if __name__ == "__main__":
    unittest.main()
