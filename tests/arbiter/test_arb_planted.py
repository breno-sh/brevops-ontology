"""Conflitos plantados achados; 1:N, N:1, N:M, campo para vários conceitos e várias ocorrências, inclusive
cruzando facetas, NÃO viram CONTESTED. Cada regra de conflito é a que derruba (mutação: desligada, o caso passa)."""

import copy

import pytest

from bo.arbiter import battery as B
from bo.arbiter import engine

SHA = "0" * 64
DEC = "2026-11-03T00:00:00-03:00"


def judge(claims, **kw):
    return engine.arbitrate(B.items_of(claims), decided_at=DEC, arbiter_sha256=SHA, **kw)


@pytest.fixture(scope="module")
def world():
    claims, expect, cases = B.world()
    res = judge(claims)
    by = {}
    for v in res["verdicts"]:
        by.setdefault(v["claim_id"], []).append(v)
    return {"res": res, "by": by, "expect": expect, "cases": cases}


def _rule_of(case, cid):
    return (case.get("rules") or {}).get(cid) or case.get("rule")


def test_todo_veredito_plantado_no_mundo_inteiro(world):
    wrong = {cid: [v["verdict"] for v in world["by"][cid]] for cid, e in world["expect"].items()
             if {v["verdict"] for v in world["by"][cid]} != {e}}
    assert not wrong


@pytest.mark.parametrize("case", [c["case"] for c in B.conflict_cases()])
def test_conflito_plantado_achado_pela_regra_certa(world, case):
    c = next(x for x in world["cases"] if x["case"] == case)
    for cid, e in c["expect"].items():
        if e == "OK":
            continue
        vs = world["by"][cid]
        assert all(v["verdict"] == e for v in vs), (cid, vs)
        assert all(_rule_of(c, cid) in v["rules"] for v in vs), (cid, vs)


ESTRUTURAS = ("k4_exact_consistente", "k4_broad_consistente", "grupos_1N_N1_NM_ocorrencias", "campo_varios_conceitos",
              "alternativas_exclusivas", "close_nao_compoe", "mesmo_par_guardas_exclusivas", "fixo_e_duplicata")


@pytest.mark.parametrize("case", ESTRUTURAS)
def test_estrutura_valida_nao_vira_contested(world, case):
    c = next(x for x in world["cases"] if x["case"] == case)
    for cid in c["expect"]:
        for v in world["by"][cid]:
            assert v["verdict"] == "OK", (cid, v["verdict"], v["rules"], v["detail"])


def test_cardinalidades_e_facetas_presentes(world):
    g = {c["claim_id"]: c for c in next(x for x in world["cases"] if x["case"] == "grupos_1N_N1_NM_ocorrencias")["claims"]}
    assert g["G-1N"]["group"]["cardinality"] == "1:N"
    assert g["G-N1"]["group"]["cardinality"] == "N:1" and g["G-N1"]["group"]["joins"][0]["via"] == "facet_of"
    assert g["G-NM"]["group"]["cardinality"] == "N:M"
    assert all(p["occurrence"]["scope"] == "block" for p in g["G-NM"]["projection"])
    vs = world["res"]["report"]["valid_structure"]
    assert vs["groups_by_cardinality"]["1:N"] >= 1 and vs["groups_by_cardinality"]["N:M"] >= 1
    assert "G-N1" in vs["groups_crossing_occurrences"]
    assert any(f["field"] == "pa:mc.alarm.query" and len(f["concepts"]) >= 4 for f in vs["fields_with_several_concepts"])
    assert "pa:gnm.rule.from_port" in vs["block_occurrence_fields"]


def test_relatorio_separa_conflito_de_estrutura(world):
    rep = world["res"]["report"]
    contested = {cid for x in rep["genuine_conflicts"] for cid in x["claims"]}
    valid = {cid for c in world["cases"] if c["case"] in ESTRUTURAS for cid in c["expect"]}
    assert contested and not (contested & valid)
    assert {"SKOS-DISJ", "ARB-K4-VALUE", "ARB-K4-REL", "ARB-ATOM-TYPE", "ARB-PAIR-VALUE", "ARB-PAIR-REL"} <= \
        {x["rule"] for x in rep["genuine_conflicts"]}
    assert rep["duplicates"] and rep["duplicates"][0]["claims"] == ["DUP-1", "DUP-2"]


def test_ciclo_contestado_cita_a_composicao(world):
    v = world["by"]["X2-AC"][0]
    assert v["composition_used"] and len(v["composition_used"]) >= 2
    comp = [x for x in world["res"]["verdicts"] if "∘" in x["claim_id"] and set(x["composition_used"]) &
            {"X2-AB", "X2-BC", "X2-AC", "X2-AB~inv", "X2-BC~inv", "X2-AC~inv"}]
    assert comp and all(x["verdict"] == "CONTESTED" for x in comp)


def test_close_close_nao_compoe(world):
    cc = [x for x in world["res"]["verdicts"] if x["claim_id"] in ("CC-AB∘CC-BC", "CC-BC~inv∘CC-AB~inv")]
    assert cc and all(x["verdict"] == "UNPROVEN" and x["rules"] == ["K-TABLE"] for x in cc)


def test_k4_exact_compoe_e_confere(world):
    ok = [x for x in world["res"]["verdicts"] if "∘" in x["claim_id"] and x["claim_id"].startswith("K4-")]
    assert len(ok) >= 12 and all(x["verdict"] == "OK" for x in ok)
    checked = [c for c in world["res"]["cycles"] if c.get("composite_id", "").startswith("K4-") and c.get("checked_against")]
    assert checked


@pytest.mark.parametrize("case", [c["case"] for c in B.conflict_cases()])
def test_caso_isolado_igual_ao_mundo(world, case):
    c = next(x for x in world["cases"] if x["case"] == case)
    res = judge(copy.deepcopy(c["claims"]))
    for cid, e in c["expect"].items():
        assert {v["verdict"] for v in res["verdicts"] if v["claim_id"] == cid} == {e}


MUT = [("skos_disj", "SKOS-DISJ"), ("k4_valor", "ARB-K4-VALUE"), ("k4_relacao", "ARB-K4-REL"),
       ("tipo_do_atomo", "ARB-ATOM-TYPE"), ("dominio_do_atomo", "ARB-ATOM-TYPE"), ("mesmo_par_valor", "ARB-PAIR-VALUE"),
       ("sobreposicao_nao_declarada", "P-OVERLAP"), ("varios_conceitos_sem_projecao", "ARB-PROJ-DECL"),
       ("realizacoes_ambiguas", "ARB-REAL-MULTI"), ("alternativa_nao_mutua", "ARB-ALT-MUTUAL"),
       ("grupo_inconsistente", "ARB-G-CONSIST"), ("ocorrencia_nao_identificada", "ARB-OCC-ID"),
       ("versao_bifurcada", "ARB-VERSION")]


@pytest.mark.parametrize("case,rule", MUT)
def test_mutacao_regra_desligada_deixa_passar(case, rule):
    c = next(x for x in B.conflict_cases() if x["case"] == case)
    res = judge(copy.deepcopy(c["claims"]), disabled=frozenset({rule}))
    for cid, e in c["expect"].items():
        if e == "OK":
            continue
        for v in (v for v in res["verdicts"] if v["claim_id"] == cid):
            assert rule not in v["rules"]
            assert v["verdict"] != e or v["rules"], (cid, v)


def test_mutacao_k4_relacao_vira_ok():
    c = next(x for x in B.conflict_cases() if x["case"] == "k4_relacao")
    res = judge(copy.deepcopy(c["claims"]), disabled=frozenset({"ARB-K4-REL"}))
    assert all(v["verdict"] == "OK" for v in res["verdicts"] if v["claim_id"] in c["expect"])
