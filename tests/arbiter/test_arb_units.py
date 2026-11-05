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


# ------------------------------------------------------------------------------------- ids de regra (CC-2)
def test_todo_id_de_regra_publicado_casa_com_o_c21():
    import re
    from bo.arbiter.rules import RULE_ID_PATTERN, all_rules
    pat = re.compile(RULE_ID_PATTERN)
    assert all(pat.match(r) for r in all_rules())


def test_vereditos_da_bateria_sem_prova_passam_no_c21_oficial():
    """Sem prova cobre EVIDENCE e SENTINEL do SEMANTICS (ids de uma palavra): saem com o id conforme."""
    from bo.arbiter.unproven import _gloss
    vs = []
    for c in B.unproven_cases():
        r = engine.arbitrate(B.items_of([c["claim"]]), glossary=_gloss(c.get("glossary_case")), decided_at=DEC,
                             arbiter_sha256=SHA)
        vs += r["verdicts"]
    s = B.C("T-SN", "pa:t.ret", "exact", "pb:t.ret",
            B.T("integer", quantity_kind="quantitykind:Time", unit="unit:DAY", range={"min": 1, "max": 30},
                sentinels={"0": "nunca expira"}), B.SECS(86400, 2592000), B.UC("unit:DAY", "unit:SEC"), "subset",
            "lossless", tests=[{"input": 1, "expected": 86400}])
    vs += judge([s])["verdicts"]
    rules = {r for v in vs for r in v["rules"]}
    assert {"EVIDENCE-DOC", "SENTINEL-MAP"} <= rules and not ({"EVIDENCE", "SENTINEL"} & rules)
    p = TMP / "c21_unproven" / "verdicts.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("".join(json.dumps(v, ensure_ascii=False, sort_keys=True) + "\n" for v in vs), encoding="utf-8")
    assert not run.validate_c21(p)


def test_alias_antigo_desliga_a_regra():
    r = base()
    r["evidence_state"] = "STRUCTURALLY_VALID"
    assert "EVIDENCE-DOC" in v_of(judge([r]), "T-1")[0]["rules"]
    for alias in ("EVIDENCE", "EVIDENCE-DOC"):
        assert v_of(judge([r], disabled=frozenset({alias})), "T-1")[0]["verdict"] == "OK"


# ------------------------------------------------------------------- ausência tipada (CC-7 do PILOT-STO-MAP)
def _absence(cid, kind, side="subject", evidence=True, **kw):
    atom = "pa:t.only_here"
    r = {"claim_id": cid, "claim_version_id": f"{cid}@1", "event_id": f"EV-{cid}",
         "subject_id": atom if side == "subject" else "sssom:NoTermFound",
         "object_id": "sssom:NoTermFound" if side == "subject" else atom,
         "predicate_id": "skos:relatedMatch", "mapping_justification": "semapv:UnspecifiedMatching",
         "semantic_relation": "related", "value_domain_relation": {"relation": "unknown", "orientation": "subject_to_object"},
         "transport_fidelity": "none", "guard": {"all": []}, "evidence_state": "STRUCTURALLY_VALID", "basis": "direct",
         "proof": {"type": "absence", "evidence": [], "tests": []},
         "subject_concept": "bo:UNGLOSSED", "object_concept": "bo:UNGLOSSED",
         "absence": {"kind": kind, "searched": ["átomos do outro provedor no pacote: 0"]}}
    if side != "subject":
        r["absence"]["side"] = side
    if evidence:
        r["absence"]["evidence"] = [{"source": "fixture:doc-sintetica", "sentence": "o outro provedor não tem o atributo",
                                     "date": "2026-11-04"}]
    r.update(kw)
    return r


@pytest.mark.parametrize("rec,verdict,rule", [
    (_absence("T-AB-OK", "ABSENCE_DEMONSTRATED"), "OK", None),
    (_absence("T-AB-OBJ", "OUT_OF_PIN", side="object"), "OK", None),
    (_absence("T-AB-UNRES", "UNRESOLVED"), "UNPROVEN", "ARB-ABSENCE-KIND"),
    (_absence("T-AB-NOEV", "ABSENCE_DEMONSTRATED", evidence=False), "UNPROVEN", "ARB-ABSENCE-EV"),
    (_absence("T-AB-SIDE", "ABSENCE_DEMONSTRATED", side="object", subject_id="pa:t.only_here",
              object_id="sssom:NoTermFound"), "REFUTED_BY_RULE", "ARB-ABSENCE-WF"),
])
def test_ausencia_tem_veredito_proprio_e_nao_e_related(rec, verdict, rule):
    res = judge([rec])
    v = v_of(res, rec["claim_id"])[0]
    assert v["verdict"] == verdict and (rule is None or rule in v["rules"]), v
    assert "ARB-RELATED-EV" not in v["rules"]
    rep = res["report"]
    assert rep["n_absences"] == 1 and rep["n_current"] == 0 and rep["verdicts"] == {}
    assert rep["verdicts_absences"] == {verdict: 1}


def test_ausencia_nao_entra_no_conjunto_nem_no_k4():
    claims, _, _ = B.world()
    base_ = judge(claims)
    more = judge(claims + [_absence("T-AB-W1", "ABSENCE_DEMONSTRATED", subject_id="pa:k4.retention"),
                           _absence("T-AB-W2", "UNRESOLVED", subject_id="pb:k4.retention",
                                    claim_version_id="T-AB-W2@1", event_id="EV-T-AB-W2")])
    vm = engine.verdict_map(base_["verdicts"])
    assert all(engine.verdict_map(more["verdicts"])[k] == v for k, v in vm.items())


# ----------------------------------------------------- domínio de função do registro (CC-9 do PILOT-STO-MAP)
def _e2b(vdr, fid, table_out=None):
    return B.C("T-E2B", "pa:t.status", "exact", "pb:t.enabled", B.ENUM("Enabled", "Disabled"), B.BOOL,
               {"name": "enum_to_bool", "params": table_out or {"true": ["Enabled"], "false": ["Disabled"]}}, vdr, fid,
               tests=[{"input": "Enabled", "expected": True}])


def test_e3_bijecao_do_registro_nao_sai_ok_onde_a_semantica_nao_prova():
    """Regressão do E3 (PILOT-EXIT 2/2): CLM-AWSAZ-STO-0006 e CLM-AWSOCI-STO-0005 têm esta forma (enum_to_bool
    Enabled/Disabled -> booleano, exact, sem perda, equal). A semântica congelada dá UNPROVEN (VDR-UNKNOWN); o domínio
    calculado pelo registro não pode tirar essa falha."""
    from bo.semantics.obligations import assess
    for cid in ("CLM-AWSAZ-STO-0006", "CLM-AWSOCI-STO-0005"):
        r = _e2b("equal", "lossless")
        r.update(claim_id=cid, claim_version_id=f"{cid}@1", event_id=f"EV-{cid}")
        assert assess(r).verdict == "UNPROVEN"
        v = v_of(judge([r]), cid)[0]
        assert v["verdict"] == "UNPROVEN" and "VDR-UNKNOWN" in v["rules"], v


def test_dominio_do_registro_declarado_errado_refuta():
    v = v_of(judge([_e2b("subset", "lossless")]), "T-E2B")[0]
    assert v["verdict"] == "REFUTED_BY_RULE" and "VDR-COMPUTED" in v["rules"], v


# --------------------------------------------- --check-unproven sem --out não grava em $BO_DATA (CC-MAP-NET-4)
def test_check_unproven_sem_out_grava_em_bo_tmp(tsv, monkeypatch):
    p, d = tsv
    from bo.arbiter.common import data_root
    mid = "ARBITERLIB-TESTE-SAIDA"
    monkeypatch.setenv("BO_ID", mid)
    monkeypatch.setenv("BO_TMP", str(d / "bo_tmp"))
    assert run.main(["--check-unproven", "--in", str(p), "--decided-at", DEC]) == 0
    assert (d / "bo_tmp" / "arbiter" / "verdicts.jsonl").exists()
    assert not (data_root() / mid).exists()


# ------------------------------------------ domínio de wrap_list / unwrap_single (CC-13 do PILOT-STO-MAP)
def _coll(cid, fn, st, ot, vdr, fid, test):
    return B.C(cid, "pa:t.prefix", "exact", "pb:t.prefixes", st, ot, {"name": fn, "params": {}}, vdr, fid, tests=[test])


def _L(it):
    return {"datatype": "list", "item_type": it}


@pytest.mark.parametrize("fn,st,ot,vdr,fid,test", [
    ("wrap_list", B.ENUM("logs/", "tmp/"), _L(B.ENUM("logs/", "tmp/", "data/")), "subset", "lossless",
     {"input": "logs/", "expected": ["logs/"]}),
    ("wrap_list", B.STR, _L(B.STR), "subset", "lossless", {"input": "logs/", "expected": ["logs/"]}),
    ("unwrap_single", _L(B.ENUM("a", "b")), B.ENUM("a", "b"), "superset", "partial", {"input": ["a"], "expected": "a"}),
])
def test_colecao_segue_a_semantica_congelada(fn, st, ot, vdr, fid, test):
    """wrap_list/unwrap_single (CC-13): o veredito nunca é mais permissivo que o da semântica congelada."""
    from bo.semantics.obligations import assess
    from bo.arbiter.rules import PRECEDENCE
    c = _coll("T-COLL", fn, st, ot, vdr, fid, test)
    a = assess(c).verdict
    v = v_of(judge([c]), "T-COLL")[0]["verdict"]
    assert PRECEDENCE.index(v) <= PRECEDENCE.index(a), (v, a)


def test_dominio_da_colecao_calculado_so_acrescenta_refutacao():
    c = _coll("T-WRAP", "wrap_list", B.ENUM("logs/"), _L(B.ENUM("logs/")), "equal", "lossless",
              {"input": "logs/", "expected": ["logs/"]})
    v = v_of(judge([c]), "T-WRAP")[0]
    assert v["verdict"] == "REFUTED_BY_RULE" and "VDR-COMPUTED" in v["rules"]


# ----------------------------------------------- piso semântico geral (E3 do PILOT-EXIT 2/2)
CALIBRATED = [Path(os.environ.get("BO_DATA", "/Users/breno/doutorado/brevops-data")) / m / "mapping.sssom.tsv"
              for m in ("PILOT-STO-MAP", "PILOT-NET-MAP")]


def test_todo_ok_da_bateria_tem_a_semantica_de_acordo():
    from bo.arbiter import semcheck
    claims, _, _ = B.world()
    r = semcheck.check(B.items_of(claims))
    assert r["ok_claims"] > 20 and r["pass"], r


@pytest.mark.parametrize("path", CALIBRATED, ids=["sto", "net"])
def test_todo_ok_dos_mapeamentos_calibrados_tem_a_semantica_de_acordo(path):
    from bo.arbiter import semcheck
    from bo.arbiter.inputs import load
    if not path.exists():
        pytest.skip(f"mapeamento calibrado ausente: {path}")
    r = semcheck.check(load([str(path)]))
    assert r["ok_claims"] > 0 and r["pass"], r
