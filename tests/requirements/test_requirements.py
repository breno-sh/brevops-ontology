"""Testes do REQUIREMENTS: validador, gates e determinismo. Cada gate é testado também no sentido de reprovar
(arranjo quebrado de propósito), para que um verde não prove outra coisa.

Rodar: python -I -B -m unittest discover -s tests/requirements -q   (temporário em $BO_TMP, nunca /tmp)
"""

import copy
import json
import os
import shutil
import sys
import unittest
import uuid
from pathlib import Path

REPO = Path(os.environ.get("BO_REPO") or Path(__file__).resolve().parents[2])
sys.path.insert(0, str(REPO / "src"))

from bo.requirements import beyond_cis, build, common, coverage, model, validate, vocab_independent  # noqa: E402


def tmpdir() -> Path:
    base = Path(os.environ.get("BO_TMP") or "/Users/breno/doutorado/brevops-data/tmp/REQUIREMENTS")
    d = base / f"t_{uuid.uuid4().hex[:10]}"
    d.mkdir(parents=True)
    return d


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.reqs, cls.cmts, cls.cqs = common.collect()

    def setUp(self):
        self.d = tmpdir()

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def write(self, reqs=None, cmts=None, cqs=None):
        for kind, recs in (("requirements", reqs or self.reqs), ("commitments", cmts or self.cmts),
                           ("cq_spec", cqs or self.cqs)):
            (self.d / common.KIND_FILE[kind]).write_text(common.dump_jsonl(recs), encoding="utf-8")
        return self.d


class TestContent(Base):
    def test_conteudo_valido(self):
        self.assertEqual(build.schemas_and_rules(self.reqs, self.cmts, self.cqs), [])

    def test_publicado_igual_ao_conteudo(self):
        self.assertEqual(build.main(["--check"]), 0)

    def test_build_deterministico(self):
        self.assertEqual(build.produce(), build.produce())

    def test_fixture_ids_unicos_globalmente(self):
        ids = [f["fixture_id"] for c in self.cmts for f in c["fixtures"]] + \
              [q["fixtures"][r]["fixture"]["fixture_id"] for q in self.cqs for r in ("conforming", "nonconforming", "incomplete")]
        self.assertEqual(len(ids), len(set(ids)))

    def test_seis_casos_tres_polaridades(self):
        for case in model.ADVERSARIAL_CASES:
            pols = {c["polarity"] for c in self.cmts if c["case"] == case}
            self.assertEqual(pols, set(model.POLARITIES), case)

    def test_vm_com_duas_nics_tres_individuos(self):
        c = next(c for c in self.cmts if c["commitment_id"] == "CMT-NIC-P01")
        f = c["fixtures"][0]
        n = sum(e["kind"] in ("compute_instance", "network_interface") for e in f["entities"])
        self.assertEqual(n, c["expected_answer"]["value"])
        c1 = next(c for c in self.cmts if c["commitment_id"] == "CMT-NIC-P02")
        n1 = sum(e["kind"] in ("compute_instance", "network_interface") for e in c1["fixtures"][0]["entities"])
        self.assertEqual(n1, c1["expected_answer"]["value"])

    def test_deny_nao_vira_allow_presente(self):
        neg = [c for c in self.cmts if c["polarity"] == "negative" and c["layer"] == "translation"]
        self.assertTrue(any("deny" in json.dumps(c["fixtures"]) for c in neg))


class TestValidatorRejeita(Base):
    def errs_c(self, mut):
        cm = copy.deepcopy(self.cmts)
        mut(cm)
        return model.validate_commitments(cm, {r["req_id"] for r in self.reqs}) + validate.schema_errors("commitments", cm)

    def errs_q(self, mut):
        qs = copy.deepcopy(self.cqs)
        mut(qs)
        return model.validate_cq_spec(qs, {r["req_id"] for r in self.reqs}, {c["commitment_id"] for c in self.cmts}) \
            + validate.schema_errors("cq_spec", qs)

    def test_positivo_com_unknown(self):
        def m(cm):
            c = next(c for c in cm if c["polarity"] == "positive" and c["check"]["kind"] == "entails")
            c["expected_answer"]["value"] = "UNKNOWN"
        self.assertTrue(self.errs_c(m))

    def test_polaridade_x_checagem(self):
        def m(cm):
            next(c for c in cm if c["polarity"] == "negative")["check"]["kind"] = "entails"
        self.assertTrue(self.errs_c(m))

    def test_unknown_com_leitura_completa(self):
        def m(cm):
            c = next(c for c in cm if c["polarity"] == "unknown")
            for f in c["fixtures"]:
                f["read"] = {"completeness": "complete", "not_read": [], "withheld": []}
        self.assertTrue(any("leitura parcial" in e for e in self.errs_c(m)))

    def test_termo_nao_declarado(self):
        def m(cm):
            cm[0]["fixtures"][0]["entities"][0]["kind"] = "vm_of_some_cloud"
        self.assertTrue(any("não declarado" in e for e in self.errs_c(m)))

    def test_relacao_para_id_inexistente(self):
        def m(cm):
            c = next(c for c in cm if c["fixtures"][0]["relations"])
            c["fixtures"][0]["relations"][0]["to"] = "fantasma"
        self.assertTrue(any("inexistente" in e for e in self.errs_c(m)))

    def test_requisito_inexistente(self):
        def m(cm):
            cm[0]["requirement_ids"] = ["REQ-XXX-99"]
        self.assertTrue(any("requisito inexistente" in e for e in self.errs_c(m)))

    def test_id_repetido(self):
        def m(cm):
            cm[1]["commitment_id"] = cm[0]["commitment_id"]
        self.assertTrue(any("repetido" in e for e in self.errs_c(m)))

    def test_cq_incompleta_sem_unknown(self):
        def m(qs):
            qs[0]["fixtures"]["incomplete"]["expected"]["value"] = False
        self.assertTrue(self.errs_q(m))

    def test_cq_sem_nao_conforme(self):
        def m(qs):
            del qs[0]["fixtures"]["nonconforming"]
        self.assertTrue(self.errs_q(m))

    def test_cq_conforme_igual_nao_conforme(self):
        def m(qs):
            qs[0]["fixtures"]["nonconforming"]["expected"]["value"] = qs[0]["fixtures"]["conforming"]["expected"]["value"]
        self.assertTrue(any("mesma resposta" in e for e in self.errs_q(m)))

    def test_cq_conforme_com_leitura_parcial(self):
        def m(qs):
            f = qs[0]["fixtures"]["conforming"]["fixture"]
            f["read"] = {"completeness": "partial", "not_read": [{"of": f["entities"][0]["id"], "what": "setting"}],
                         "withheld": []}
        self.assertTrue(any("leitura completa" in e for e in self.errs_q(m)))


class TestGatesReprovam(Base):
    def test_coverage_ok_no_publicado(self):
        errs, _ = coverage.check(self.write())
        self.assertEqual(errs, [])

    def test_coverage_reprova_caso_sem_unknown(self):
        cm = [c for c in self.cmts if not (c["case"] == "LB" and c["polarity"] == "unknown")]
        errs, _ = coverage.check(self.write(cmts=cm))
        self.assertTrue(any("caso LB: nenhum compromisso unknown" in e for e in errs))

    def test_coverage_reprova_caso_sem_aterramento(self):
        cm = copy.deepcopy(self.cmts)
        for c in cm:
            if c["case"] == "DB":
                c["provider_grounding"] = [g for g in c["provider_grounding"] if g["provider"] != "oci"]
        errs, _ = coverage.check(self.write(cmts=cm))
        self.assertTrue(any("caso DB: sem aterramento em oci" in e for e in errs))

    def test_coverage_reprova_requisito_orfao(self):
        rq = copy.deepcopy(self.reqs) + [model.req("REQ-ORF-01", "entity", "requisito sem verificação nenhuma aqui",
                                                    "teste de reprovação do gate de cobertura", ["F1"])]
        errs, _ = coverage.check(self.write(reqs=rq))
        self.assertTrue(any("REQ-ORF-01 sem compromisso nem CQ" in e for e in errs))

    def test_beyond_cis_reprova_familia_ausente(self):
        qs = [q for q in self.cqs if q["family"] != "loss"]
        errs, _ = beyond_cis.check(self.write(cqs=qs))
        self.assertTrue(any("'loss'" in e for e in errs))

    def test_beyond_cis_ok(self):
        errs, cnt = beyond_cis.check(self.write())
        self.assertEqual(errs, [])
        self.assertTrue(all(cnt[f] >= 1 for f in model.FAMILIES_BEYOND_CIS))

    def test_vocab_reprova_termo_na_cq(self):
        qs = copy.deepcopy(self.cqs)
        qs[3]["question"] = "O security group da VPC permite o fluxo?"
        errs, _ = vocab_independent.check(self.write(cqs=qs))
        self.assertTrue(any("security group" in e.lower() for e in errs))
        self.assertTrue(any("vpc" in e.lower() for e in errs))

    def test_vocab_reprova_iri(self):
        qs = copy.deepcopy(self.cqs)
        qs[0]["criterion"] = "conforme = bo:Resource persiste"
        errs, _ = vocab_independent.check(self.write(cqs=qs))
        self.assertTrue(any("IRI" in e for e in errs))

    def test_vocab_ignora_aterramento(self):
        errs, _ = vocab_independent.check(self.write())
        self.assertEqual(errs, [])
        self.assertTrue(any("aws_" in g["note"] for c in self.cmts for g in c["provider_grounding"]))

    def test_vocab_selftest(self):
        self.assertEqual(vocab_independent.selftest(), 0)


if __name__ == "__main__":
    unittest.main()
