"""Unidades: versões, âncoras auditadas, registro do TRANSFORMS, CLI (C21 oficial, --frozen, --check-unproven),
congelamento, detector de importação e determinismo."""

import copy
import json
import os
from pathlib import Path

import pytest

from bo.arbiter import battery as B
from bo.arbiter import engine, freeze, no_llm, run
from bo.arbiter.common import load_jsonl
from bo.arbiter.inputs import Glossary, resolve_versions
from bo.contracts import sssom as CSSSOM

SHA = "0" * 64
DEC = "2026-11-03T00:00:00-03:00"
TMP = Path(os.environ["BO_TMP"])


def judge(claims, **kw):
    return engine.arbitrate(B.items_of(claims), decided_at=DEC, arbiter_sha256=SHA, **kw)


def v_of(res, cid):
    return [v for v in res["verdicts"] if v["claim_id"] == cid]


def base(cid="T-1", s="pa:t.n", o="pb:t.n"):
    return B.C(cid, s, "exact", o, B.INT(1, 9), B.INT(1, 9), B.IDN, "equal", "lossless",
               tests=[{"input": 1, "expected": 1}])


# ------------------------------------------------------------------------------------------------- versões
def test_versao_corrente_e_substituida():
    a = base()
    b = copy.deepcopy(a)
    b.update(claim_version_id="T-1@2", event_id="EV-T-1-2", supersedes="T-1@1")
    cur, sup, fails = resolve_versions(B.items_of([b, a]))
    assert [c["rec"]["claim_version_id"] for c in cur] == ["T-1@2"] and len(sup) == 1 and not fails
    res = judge([a, b])
    assert [v["claim_version_id"] for v in v_of(res, "T-1")] == ["T-1@2"]


def test_supersedes_de_outra_alegacao_refuta():
    a = base()
    b = copy.deepcopy(a)
    b.update(claim_version_id="T-1@2", event_id="EV-T-1-2", supersedes="T-9@1")
    res = judge([a, b])
    assert all(v["verdict"] == "REFUTED_BY_RULE" and "ARB-VERSION" in v["rules"] for v in v_of(res, "T-1"))


def test_um_veredito_por_versao_mesmo_com_colisao():
    a = base()
    res = judge([a, copy.deepcopy(a)])
    vs = v_of(res, "T-1")
    assert len(vs) == 1 and vs[0]["verdict"] == "REFUTED_BY_RULE"


# ------------------------------------------------------------------------------------------------- âncoras
def _shared(states):
    s, o = "pa:t.ret", "pb:t.ret"
    c = B.C("T-SH", s, "exact", o, B.DAYS(1, 30), B.DAYS(1, 30), B.IDN, "equal", "lossless",
            tests=[{"input": 2, "expected": 2}], basis="shared_concept", subject_concept="concept:backup_retention",
            object_concept="concept:backup_retention",
            anchors=[{"claim_id": "ANC-BAT-01", "evidence_state": "DOC_SUPPORTED"},
                     {"claim_id": "ANC-BAT-02", "evidence_state": "DOC_SUPPORTED"}])
    g = B.glossary_records({s: states[0], o: states[1]})
    return c, Glossary(g["claims"], g["audits"])


def test_ancora_auditada_prova_e_estado_declarado_nao():
    c, g = _shared(("DOC_SUPPORTED", "DOC_SUPPORTED"))
    assert v_of(judge([c], glossary=g), "T-SH")[0]["verdict"] == "OK"
    assert v_of(judge([c]), "T-SH")[0]["verdict"] == "UNPROVEN"
    c, g = _shared(("DOC_SUPPORTED", "UNRESOLVED"))
    v = v_of(judge([c], glossary=g), "T-SH")[0]
    assert v["verdict"] == "UNPROVEN" and "ARB-ANCHOR" in v["rules"]


def test_ancora_de_outro_atomo_refuta():
    c, g = _shared(("DOC_SUPPORTED", "DOC_SUPPORTED"))
    c["object_id"] = "pb:t.outro"
    v = v_of(judge([c], glossary=g), "T-SH")[0]
    assert v["verdict"] == "REFUTED_BY_RULE" and "ARB-ANCHOR" in v["rules"]


# ------------------------------------------------------------------------------------------- registro TRANSFORMS
def _reg(fn, tests):
    return B.C("T-REG", "pa:t.flag", "exact", "pb:t.flag", B.BOOL, B.ENUM("on", "off"), fn, "unknown", "partial",
               tests=tests)


def test_funcao_so_do_registro_testada_pelo_registro():
    fn = {"name": "bool_to_enum", "params": {"true": "on", "false": "off"}}
    assert v_of(judge([_reg(fn, [{"input": True, "expected": "on"}])]), "T-REG")[0]["verdict"] == "OK"
    v = v_of(judge([_reg(fn, [{"input": True, "expected": "off"}])]), "T-REG")[0]
    assert v["verdict"] == "REFUTED_BY_RULE" and "EXACT-TESTS" in v["rules"]


@pytest.mark.parametrize("name", ["nao_existe", "compare_exact"])
def test_fora_do_registro_ou_comparador_refuta(name):
    v = v_of(judge([_reg({"name": name, "params": {}}, [{"input": True, "expected": "on"}])]), "T-REG")[0]
    assert v["verdict"] == "REFUTED_BY_RULE" and "ARB-FN-REG" in v["rules"]


def test_esquema_c09_refuta_linha_fora_do_contrato():
    c = base()
    c["predicate_id"] = "owl:sameAs"
    v = v_of(judge([c]), "T-1")[0]
    assert v["verdict"] == "REFUTED_BY_RULE" and "ARB-C09-SCHEMA" in v["rules"]


# ------------------------------------------------------------------------------------------------------- CLI
@pytest.fixture(scope="module")
def tsv():
    claims, _, _ = B.world()
    ok = [c for c in claims if c["claim_id"].startswith(("K4-", "MC-", "G-", "X2-", "X1-"))]
    d = TMP / "test_run"
    d.mkdir(parents=True, exist_ok=True)
    p = d / "mapping.sssom.tsv"
    p.write_text(CSSSOM.write_tsv(ok, "https://example.org/mapping-set/arbiter-test"), encoding="utf-8")
    return p, d


def test_cli_tsv_frozen_check_unproven_e_c21_oficial(tsv):
    p, d = tsv
    rc = run.main(["--frozen", "--check-unproven", "--in", str(p), "--out", str(d / "out"), "--decided-at", DEC])
    assert rc == 0
    vs = load_jsonl(d / "out" / "verdicts.jsonl")
    assert not run.validate_c21(d / "out" / "verdicts.jsonl")
    got = {v["claim_id"]: v["verdict"] for v in vs}
    assert got["K4-AB"] == "OK" and got["X2-AC"] == "CONTESTED" and got["G-NM"] == "OK" and got["MC-METRIC"] == "OK"
    assert all(v["arbiter_sha256"] == freeze.arbiter_sha() for v in vs)
    rep = json.loads((d / "out" / "arbiter_report.json").read_text(encoding="utf-8"))
    assert rep["frozen_checked"] and (d / "out" / "run_record.json").exists()


def test_check_unproven_pega_ok_sem_prova():
    r = base()
    r["proof"]["evidence"] = []
    assert "evidência" in run.minimal_proof_gaps(r, False)
    r = base()
    r["basis"] = "shared_concept"
    assert "âncoras auditadas" in run.minimal_proof_gaps(r, False)
    assert run.minimal_proof_gaps(base(), False) == []


def test_ciclo_seguinte_com_previous(tsv):
    p, d = tsv
    prev = d / "out" / "verdicts.jsonl"
    assert run.main(["--in", str(p), "--out", str(d / "out2"), "--previous", str(prev), "--decided-at", DEC]) == 0
    assert {v["cycle"] for v in load_jsonl(d / "out2" / "verdicts.jsonl")} == {2}


# ------------------------------------------------------------------------------------------- congelamento e higiene
def test_manifesto_cobre_o_fecho_de_importacao():
    listed = {ln.split("  ", 1)[1] for ln in freeze.manifest_path().read_text(encoding="utf-8").splitlines() if ln}
    for f in ("src/bo/arbiter/engine.py", "src/bo/semantics/obligations.py", "src/bo/semantics/composition.py",
              "src/bo/semantics/guards.py", "src/bo/transforms/registry.py", "semantics/composition_table.json",
              "arbiter/RULES.html"):
        assert f in listed
    assert not freeze.verify()


def test_detector_de_importacao_nao_e_vazio():
    hits = no_llm.scan_source(no_llm.CONTROL, "<c>")
    assert {h["root"] for h in hits} >= {"openai", "langchain", "anthropic", "requests"}
    assert not no_llm.scan_source("import json\nfrom bo.semantics import guards\n", "<ok>")


def test_determinismo_no_mundo():
    claims, _, _ = B.world()
    a = judge(claims)
    b = judge(list(reversed(claims)))
    assert engine.verdict_map(a["verdicts"]) == engine.verdict_map(b["verdicts"])
    assert [v["claim_version_id"] for v in a["verdicts"]] == [v["claim_version_id"] for v in b["verdicts"]]
