"""Regra R-CTRL sobre casos SINTÉTICOS: cada linha sai quando a condição dela vale, e só ela."""
from bo.pilot_exit import controls as K

N = 41  # n_cases_per_family do prereg/power.json (C-H9)


def mk(n, fam="F1", c1="absent", c2="absent", c3="correct", pol="positive", start=0, **kw):
    return [dict({"case_id": f"{fam}-{start + i}", "family": fam, "polarity": pol, "c1": c1, "c2": c2, "c3": c3}, **kw)
            for i in range(n)]


def test_n_pequeno_e_inconclusivo_nunca_nulo():
    r = K.r_ctrl(mk(12) + mk(12, c3="absent", start=100), N)
    assert r["main"] == "R-CTRL-4" and "não elegível" in r["why"]


def test_efeito_grande_com_n_suficiente_e_r_ctrl_1():
    r = K.r_ctrl(mk(30) + mk(15, c1="correct", c2="correct", start=50), N)
    assert r["main"] == "R-CTRL-1"


def test_c2_explica_tudo_e_r_ctrl_2():
    r = K.r_ctrl(mk(30, c2="correct") + mk(15, c1="correct", c2="correct", start=50), N)
    assert r["main"] == "R-CTRL-2"


def test_nenhuma_diferenca_e_r_ctrl_3():
    r = K.r_ctrl(mk(45, c1="correct", c2="correct"), N)
    assert r["main"] == "R-CTRL-3"


def test_regressao_e_deteccao_sao_linhas_proprias():
    cs = mk(5, c1="correct", c2="correct", c3="incorrect") + mk(3, pol="negative", start=9, c3_rejects=True,
                                                                  c1_rejects=False, c2_rejects=False)
    r = K.r_ctrl(cs, N)
    ids = {x["id"]: x["cases"] for x in r["extra"]}
    assert ids == {"R-CTRL-5": 5, "R-CTRL-6": 3} and r["main"] == "R-CTRL-4"


def test_contagens_por_controle_e_polaridade():
    c = K.counts(mk(2) + mk(1, pol="negative", c3="incorrect", start=5))
    assert c["c3"]["positive"]["correct"] == 2 and c["c3"]["negative"]["incorrect"] == 1
    assert c["c1"]["positive"]["absent"] == 2


def test_justificativa_c23_sep():
    ok = {"result": "carried", "justifying_axioms": ["ax1"], "consulted_metadata": ["m1"]}
    sobrepoe = {"result": "carried", "justifying_axioms": ["m1"], "consulted_metadata": ["m1"]}
    vazio = {"result": "carried", "justifying_axioms": [], "consulted_metadata": ["codec"]}
    bloqueado = {"result": "blocked", "justifying_axioms": [], "consulted_metadata": []}
    cons = [{"kind": "x", "axioms": ["AX-1"]}, {"kind": "y", "axioms": []}]
    j = K.justified([ok, sobrepoe, vazio, bloqueado], cons)
    assert j["c3_carried"] == 3 and j["c3_sep_violations"] == 1          # codec sem axioma não é violação
    assert j["c3_consequences_without_axioms"] == 1 and j["c3_bad_justification"] == 2
