"""Testes do GOLD-CARTO. As conferências são independentes do caminho que gera (contagem direta no ast) e cada
gate é quebrado de propósito numa cópia (arranjo errado não pode ficar verde)."""
from __future__ import annotations

import ast
import copy
import json
import unittest
from pathlib import Path

from bo.contracts import rules as CR
from bo.contracts.sssom import read_tsv
from bo.gold_carto import PROVIDERS, TARBALL
from bo.gold_carto import build as B
from bo.gold_carto import convert as C
from bo.gold_carto import extract as X
from bo.gold_carto import resolve as R
from bo.semantics import composition as K
from bo.semantics.vocab import INVERSE_RELATION

TAR = B.download_dir() / TARBALL
DATA = "cartography/models/ontology/mapping/data/"


def _src():
    if not hasattr(_src, "v"):
        _src.v = X.Source(TAR)
    return _src.v


def _gen():
    if not hasattr(_gen, "v"):
        _gen.v = B.generate()
    return _gen.v


class Extracao(unittest.TestCase):
    def test_tarball_errado_reprova(self):
        p = Path(B.bo_data()) / "tmp" / "GOLD-CARTO" / TARBALL
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(TAR.read_bytes()[:-10] + b"0" * 10)
        try:
            with self.assertRaises(ValueError):
                X.Source(p)
        finally:
            p.unlink()

    def test_contagem_independente_por_arquivo_e_modulo(self):
        """Conta no ast, sem o avaliador: OntologyFieldMapping (e auxiliares) dentro de cada OntologyMapping
        de aws/gcp/azure. Tem de bater com o que o avaliador extraiu (nenhum mapeamento órfão ou perdido)."""
        src = _src()
        expect: dict[tuple, int] = {}
        for rel in src.py_files(DATA):
            tree = ast.parse(src.text(rel))
            helpers = {f.name for f in tree.body if isinstance(f, ast.FunctionDef)}
            lists = {t.id: st.value for st in tree.body if isinstance(st, ast.Assign)
                     for t in st.targets if isinstance(t, ast.Name) and isinstance(st.value, ast.List)}

            def n_fields(node) -> int:
                return sum(1 for m in ast.walk(node) if isinstance(m, ast.Call) and isinstance(m.func, ast.Name)
                           and (m.func.id == "OntologyFieldMapping" or m.func.id in helpers))

            for n in ast.walk(tree):
                if not (isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "OntologyMapping"):
                    continue
                mod = next((k.value.value for k in n.keywords if k.arg == "module_name"), None)
                if mod not in PROVIDERS:
                    continue
                self.assertFalse(any(isinstance(m, ast.ListComp) for m in ast.walk(n)), f"{rel}: compreensão")
                c = 0
                for nm in ast.walk(n):
                    if isinstance(nm, ast.Call) and isinstance(nm.func, ast.Name) and nm.func.id == "OntologyNodeMapping":
                        fk = next(k.value for k in nm.keywords if k.arg == "fields")
                        c += n_fields(lists[fk.id]) if isinstance(fk, ast.Name) else n_fields(fk)
                if c:
                    expect[(rel, mod)] = expect.get((rel, mod), 0) + c
        got: dict[tuple, int] = {}
        for r in X.field_mappings(src)["in_scope"]:
            got[(r["file"], r["module"])] = got.get((r["file"], r["module"]), 0) + 1
        self.assertEqual(expect, got)
        self.assertEqual(sum(got.values()), 327)

    def test_mapeamento_conhecido(self):
        rows = X.field_mappings(_src())["in_scope"]
        ebs = [r for r in rows if r["node_label"] == "AWSEBSVolume" and r["ontology_field"] == "size_gb"]
        self.assertEqual(len(ebs), 1)
        self.assertEqual((ebs[0]["node_field"], ebs[0]["category"], ebs[0]["ontology_label"]),
                         ("size", "blockstorage", "BlockStorage"))
        st = [r for r in rows if r["node_label"] == "AzureDisk" and r["ontology_field"] == "state"][0]
        self.assertEqual(st["special_handling"], "mapping")
        self.assertEqual(st["extra"]["map"]["Attached"], "in_use")

    def test_avaliador_recusa_forma_desconhecida(self):
        class Fake:
            files = {"cartography/models/ontology/mapping/data/x.py": b""}

            def text(self, rel):
                return ("from cartography.models.ontology.mapping.specs import OntologyFieldMapping\n"
                        "import os\nA = OntologyFieldMapping(ontology_field='a', node_field=os.getcwd())\n")

            def rel_of(self, dotted):
                return "cartography/models/ontology/mapping/data/x.py" if dotted.endswith(".x") else None

        ev = X.Evaluator(Fake())
        env = ev.module("cartography.models.ontology.mapping.data.x")
        with self.assertRaises(X.Unevaluable):
            env.get("A")


class Conversao(unittest.TestCase):
    def setUp(self):
        self.out = _gen()
        self.recs = self.out["records"]
        self.pub = [r for r in self.recs if r["basis"] == "direct"]
        self.der = [r for r in self.recs if r["basis"] == "shared_concept"]

    def test_c09_valida_e_mutacao_reprova(self):
        meta, recs, cols = read_tsv(self.out["files"]["cartography.sssom.tsv"])
        self.assertEqual(CR.check_correspondences(recs, meta, cols), [])
        self.assertEqual(meta["license"], "https://www.apache.org/licenses/LICENSE-2.0")
        bad = copy.deepcopy(recs)
        bad[0]["predicate_id"] = "skos:broadMatch"
        self.assertTrue(CR.check_correspondences(bad, meta, cols))

    def test_regras_fixas(self):
        for r in self.pub:
            sh = json.loads(r["other"])["special_handling"]
            rel, fid, _ = C.RULES[sh]
            self.assertEqual((r["semantic_relation"], r["transport_fidelity"]), (rel, fid), r["claim_id"])
            if rel == "related":
                self.assertIsNone(r["translation_fn"], r["claim_id"])
            if rel == "close":
                self.assertTrue(r["loss_contract"], r["claim_id"])
            if sh == "static_value":
                self.assertEqual(r["fixed_default"]["kind"], "fixed")

    def test_derivada_segue_a_tabela(self):
        table = K.semantic_table()
        pub = {r["claim_id"]: r for r in self.pub}
        for d in self.der:
            a, b = (pub[x] for x in d["anchors"])
            self.assertEqual(a["object_id"], b["object_id"])
            self.assertNotEqual(C.pa_of(a), C.pa_of(b))
            self.assertLess(PROVIDERS.index(C.pa_of(a)), PROVIDERS.index(C.pa_of(b)))
            want = table[(a["semantic_relation"], INVERSE_RELATION[b["semantic_relation"]])]["result"] or "related"
            self.assertEqual(d["semantic_relation"], want, d["claim_id"])
            self.assertEqual((d["subject_id"], d["object_id"]), (a["subject_id"], b["subject_id"]))
            o = json.loads(d["other"])
            self.assertEqual(o["hub_outcome"]["outcome"], "UNPROVEN")

    def test_sem_promocao_de_evidencia(self):
        self.assertFalse({r["evidence_state"] for r in self.recs} - {"STRUCTURALLY_VALID", "UNRESOLVED"})

    def test_ids_unicos(self):
        for k in ("claim_id", "claim_version_id", "event_id"):
            v = [r[k] for r in self.recs]
            self.assertEqual(len(v), len(set(v)), k)


class Resolucao(unittest.TestCase):
    def setUp(self):
        out = _gen()
        _, self.recs, _ = read_tsv(out["files"]["cartography.sssom.tsv"])
        self.idx = R.Index([json.loads(l) for l in out["files"]["api_fields.jsonl"].splitlines()])

    def test_tudo_resolve_ou_esta_marcado(self):
        errs, counts = R.check(self.recs, self.idx)
        self.assertEqual(errs, [])
        self.assertGreater(counts.get("API_FIELD", 0), 0)

    def test_marcacao_errada_reprova(self):
        bad = copy.deepcopy(self.recs)
        i = next(i for i, r in enumerate(bad) if r["evidence_state"] == "UNRESOLVED")
        bad[i]["evidence_state"] = "STRUCTURALLY_VALID"
        errs, _ = R.check(bad, self.idx)
        self.assertTrue(any("devia ser UNRESOLVED" in e for e in errs))

    def test_status_forjado_reprova(self):
        bad = copy.deepcopy(self.recs)
        i = next(i for i, r in enumerate(bad) if json.loads(r["other"])["resolution"][0]["status"] == "KWARG_ONLY")
        o = json.loads(bad[i]["other"])
        o["resolution"][0]["status"] = "API_FIELD"
        bad[i]["other"] = json.dumps(o)
        errs, _ = R.check(bad, self.idx)
        self.assertTrue(errs)

    def test_campo_fora_do_esquema(self):
        self.assertEqual(self.idx.resolve("AWSEBSVolume", "size")["api_keys"], ["Size"])
        self.assertEqual(self.idx.resolve("AWSEBSVolume", "region")["status"], "KWARG_ONLY")
        self.assertEqual(self.idx.resolve("AWSEBSVolume", "nao_existe")["status"], "FIELD_NOT_IN_SCHEMA")
        self.assertEqual(self.idx.resolve("RotuloInexistente", "x")["status"], "NO_SCHEMA")


if __name__ == "__main__":
    unittest.main()
