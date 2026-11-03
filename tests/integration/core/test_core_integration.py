"""Integração cruzada do núcleo (dono: REPO). Roda a cada merge via make integration.

Cobre a fiação do catálogo (S9), a posse disjunta (S10), os comprovantes e manifestos (S11) e
verifica que os testes cruzados entre domínios (IAM em NET/SEC; chaves em STO/SEC/OPS) existem
quando o DOMAIN-CONTRACTS já foi mergeado. O que depende de domínio ainda ausente sai SKIP com
motivo explícito, registrado pelo tools/integration.py.
"""

import os
import re
import sys
import unittest
from pathlib import Path

REPO = Path(os.environ.get("BO_REPO") or Path(__file__).resolve().parents[3])
sys.path.insert(0, str(REPO / "src"))
sys.dont_write_bytecode = True

from bo.repo import catalog, core, receipts, state  # noqa: E402

CROSS = {  # teste cruzado exigido -> domínios que ele amarra
    "iam_net": ("IAM", "NET"), "iam_sec": ("IAM", "SEC"),
    "keys_sto": ("KEYS", "STO"), "keys_sec": ("KEYS", "SEC"), "keys_ops": ("KEYS", "OPS"),
}


def load_cat():
    return catalog.load(REPO)


class CatalogWiring(unittest.TestCase):
    """O gerador do plano afirma isto; aqui é conferido a cada merge."""

    @classmethod
    def setUpClass(cls):
        cls.cat = load_cat()

    def test_posses_disjuntas(self):
        owns = [(m.id, p) for m in self.cat.modules.values() for o in m.owns for p in self.cat.expand(o, m.id)]
        bad = [(a, p, b, q) for i, (a, p) in enumerate(owns) for (b, q) in owns[i + 1:]
               if a != b and catalog.overlaps(p, q)]
        self.assertEqual(bad, [], f"{len(bad)} sobreposição(ões) de posse")

    def test_saidas_dentro_da_posse(self):
        bad = []
        for m in self.cat.modules.values():
            owns = [p for o in m.owns for p in self.cat.expand(o, m.id)]
            for out in m.outputs:
                for x in self.cat.expand(out, m.id):
                    if not any(catalog.matches(x, o) or catalog.overlaps(x, o) and o.endswith("/") for o in owns):
                        bad.append(f"{m.id}: {out}")
        self.assertEqual(bad, [], "saídas fora de owns: " + "; ".join(bad[:10]))

    def test_entradas_internas_tem_produtor_nas_deps(self):
        bad = []
        for m in self.cat.modules.values():
            reach = set(self.cat.deps_closure(m.id)) | {m.id}
            for inp in m.inputs:
                if not inp.startswith("$BO_"):
                    continue
                prods = set()
                for x in self.cat.expand(inp, m.id):
                    prods |= self.cat.producers_of(x)
                if not prods & reach:
                    bad.append(f"{m.id}: {inp} (produtores: {sorted(prods) or 'nenhum'})")
        self.assertEqual(bad, [], "entradas sem produtor nas deps: " + "; ".join(bad[:10]))

    def test_deps_existem_e_sem_ciclo(self):
        ids = set(self.cat.modules)
        missing = [(m.id, d) for m in self.cat.modules.values() for d in m.deps if d not in ids]
        self.assertEqual(missing, [])
        for m in self.cat.modules.values():
            self.assertNotIn(m.id, self.cat.deps_closure(m.id), f"ciclo passando por {m.id}")

    def test_branch_e_worktree_seguem_stable_id(self):
        bad = [m.id for m in self.cat.modules.values()
               if m.branch != "bo/" + m.id.lower() or not m.worktree.endswith("/bo-" + m.id.lower())]
        self.assertEqual(bad, [])


class RepoState(unittest.TestCase):
    def test_state_json_valido(self):
        p = state.path(REPO)
        if not p.exists():
            self.skipTest("modules/state.json ainda não existe neste checkout")
        st = core.read_json(p)
        cat = load_cat()
        unknown = sorted(set(st["modules"]) - set(cat.modules))
        self.assertEqual(unknown, [], "módulos no state.json fora do catálogo")
        bad = {k: v.get("status") for k, v in st["modules"].items() if v.get("status") not in state.STATUSES}
        self.assertEqual(bad, {})

    def test_comprovantes_integros(self):
        recs = receipts.list_receipts(REPO)
        probs = {r.parent.name: receipts.verify(r, REPO) for r in recs}
        probs = {k: v for k, v in probs.items() if v}
        self.assertEqual(probs, {}, "comprovante divergente: rode tools/invalidate.py check --apply")

    def test_manifestos_dos_mergeados(self):
        cat = load_cat()
        merged = catalog.merged_modules(REPO)
        probs = []
        for mid in sorted(merged & set(cat.modules)):
            for mf in receipts.manifest_paths(cat, mid, REPO):
                probs += [f"{mid}: {p['path']} {p['problem']}" for p in receipts.verify_manifest(mf, REPO)]
        self.assertEqual(probs, [], "; ".join(probs[:10]))


class CrossDomain(unittest.TestCase):
    """IAM aparece em NET e SEC; chaves em STO, SEC e OPS (S10). Os testes de verdade são do DOMAIN-CONTRACTS."""

    def _domains_ready(self):
        dc = REPO / "domain" / "domain_contracts.yaml"
        if not dc.exists():
            self.skipTest("DOMAIN-CONTRACTS ainda não mergeado: domain/domain_contracts.yaml ausente")
        d = REPO / "tests" / "integration" / "domains"
        self.assertTrue(d.is_dir(), "domain_contracts.yaml existe mas tests/integration/domains/ não")
        return d

    def _assert_cross(self, key):
        d = self._domains_ready()
        text = "\n".join(p.read_text(encoding="utf-8", errors="replace") for p in sorted(d.rglob("test*.py")))
        self.assertRegex(text, rf"def test\w*{key}\w*\(", f"falta teste cruzado {key} {CROSS[key]} em {d}")

    def test_iam_em_net(self):
        self._assert_cross("iam_net")

    def test_iam_em_sec(self):
        self._assert_cross("iam_sec")

    def test_chaves_em_sto(self):
        self._assert_cross("keys_sto")

    def test_chaves_em_sec(self):
        self._assert_cross("keys_sec")

    def test_chaves_em_ops(self):
        self._assert_cross("keys_ops")

    def test_fragmentos_compartilhados_coerentes(self):
        frag = REPO / "domain" / "fragments"
        if not frag.is_dir():
            self.skipTest("DOMAIN-CONTRACTS ainda não mergeado: domain/fragments/ ausente")
        names = {}
        for p in sorted(frag.rglob("*")):
            if p.is_file():
                names.setdefault(p.name, []).append(core.sha256_file(p))
        dup = {n: h for n, h in names.items() if len(set(h)) > 1 and re.search(r"(iam|key|kms)", n, re.I)}
        self.assertEqual(dup, {}, "fragmento de IAM/chaves com o mesmo nome e conteúdo diferente entre domínios")


if __name__ == "__main__":
    unittest.main()
