"""E6 (ledger de pedidos) e E7 (esforço e cronograma) com textos e grafos SINTÉTICOS."""
from bo.pilot_exit import amendments as A, reestimate as R

TXT = """CONTRACT_CHANGE — PILOT-X
ATUALIZAÇÃO: os itens 1 e 2 foram adotados pela emenda 5 do CONTRACTS (79d04b7).
  CC-1 RESOLVIDO na interface (GRAIN d8ada03 lê o C25). CC-2 e CC-3 RESOLVIDOS (briefs 1.2.0).
  CC-4 RESOLVIDO (sem versão nenhuma citada).
1. primeiro pedido
2. segundo pedido
3. terceiro, aberto
CC-1 (BLOQUEANTE) x
CC-2 (x) y
CC-3 (x) z
CC-4 (x) w
CC-5 (achado) aberto
  0 raiz(es) não é item
"""


def test_parse_itens_e_resolvidos():
    p = A.parse(TXT)
    assert p["items"] == ["1", "2", "3", "CC-1", "CC-2", "CC-3", "CC-4", "CC-5"]
    assert sorted(p["resolved"]) == ["1", "2", "CC-1", "CC-2", "CC-3"]   # CC-4 sem versão fica aberto


def test_horas_por_unidade():
    assert R._hours({"seconds": 7200}) == 2.0
    assert R._hours({"minutes": 30}) == 0.5
    assert R._hours({"hours": 1.5}) == 1.5
    assert R._hours({"elapsed_s": 3600}) == 1.0
    assert R._hours({"name": "x"}) is None
    assert R._hours({"hours": True}) is None


def test_classe_de_escala():
    assert R.scale_class("MAP-AWSGCP-NET") == "MAP"
    assert R.scale_class("GLOSSARY-STO") == "GLOSS" and R.scale_class("GLOSSARY-AUDIT") is None
    assert R.scale_class("TRANSLATOR") == "E2E" and R.scale_class("DEP-AWS-A") is None


def mods():
    m = lambda i, d=(), e=1.0, lock=None: (i, {"stable_id": i, "deps": list(d), "effort_h": e, "wall_h": 0, "lock": lock})
    return dict([m("A", e=2), m("B", ["A"], 3), m("C", ["A"], 1), m("D", ["B", "C"], 1),
                 m("L1", e=2, lock="cloud-x"), m("L2", e=2, lock="cloud-x")])


def test_cronograma_teto_e_trava():
    ms = mods()
    eff = {k: v["effort_h"] for k, v in ms.items()}
    s = R.schedule(ms, eff, set(), cap=12)
    assert s["critical_path_h"] == 6.0 and s["critical_path"] == ["A", "B", "D"]
    assert s["makespan_h"] == 6.0            # L1 e L2 em série pela trava (4 h) cabem nas 6 h
    s1 = R.schedule(ms, eff, set(), cap=1)
    assert s1["makespan_h"] == 11.0          # um agente: soma de tudo
    s2 = R.schedule(ms, eff, {"A", "B"}, cap=12)
    assert s2["critical_path"][0] in ("C", "L1", "L2") and s2["makespan_h"] == 4.0
