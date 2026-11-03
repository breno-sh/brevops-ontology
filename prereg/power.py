#!/usr/bin/env python3
"""Cálculo de poder pré-registrado do BrevOps Ontology v3 (módulo PREREG).

  python -I prereg/power.py --write [power.json]   recalcula e grava power.json (C15 3.0.0, documento "result")
  python -I prereg/power.py --check power.json     recalcula e reprova (saída 1) se o arquivo diverge do cálculo,
                                                   se um contraste reivindicado não tem poder, se o modelo de
                                                   correlação não traz família E repositório, se uma hipótese
                                                   H1-H9 fica sem contraste ou se um contraste cita métrica
                                                   que não está em metrics_spec.yaml
  python -I prereg/power.py --report               tabela legível dos contrastes

Autocontido de propósito: só biblioteca padrão e PyYAML (versão do requirements.lock), para que a pasta
prereg/ possa ser depositada sozinha numa âncora externa (OSF) e rodada por quem não tem o repositório.
Lê só o metrics_spec.yaml ao lado (as métricas citadas pelos contrastes e a hora do conteúdo).

Nenhum número aqui vem de dado do estudo: não existe dado do estudo quando este arquivo é escrito. Os valores
de planejamento são hipóteses declaradas, escolhidas do lado conservador (mais perto do limiar, correlação
intracluster alta) e acompanhadas de uma grade de sensibilidade. A única reestimação permitida é a cega,
descrita em REESTIMATION: contagens estruturais da partição de teste (quantas decisões, repositórios e famílias,
nunca desfechos) e correlação intracluster estimada na partição de CALIBRAÇÃO; ela só pode rebaixar um
contraste a descritivo, nunca mudar teste, limiar, margem ou alfa.

Modelo de correlação (aninhado): decisão ⊂ grafo ⊂ repositório ⊂ família. Duas decisões do mesmo grafo
correlacionam rho_G; do mesmo repositório e grafos diferentes, rho_R; da mesma família e repositórios
diferentes, rho_F (rho_G >= rho_R >= rho_F). Efeito de desenho com m_G, m_R, m_F decisões por grafo, por
repositório e por família (numa direção):
    DE = 1 + (m_G - 1) rho_G + (m_R - m_G) rho_R + (m_F - m_R) rho_F
n_efetivo = n / DE. A reamostragem da análise é por família (o cluster de topo, que contém os outros);
repositório e grafo são leituras de sensibilidade.
"""

from __future__ import annotations

import argparse
import copy
import json
import math
import re
import sys
from pathlib import Path
from statistics import NormalDist

HERE = Path(__file__).resolve().parent
N01 = NormalDist()
ALPHA = 0.05
TARGET = 0.80
LEVEL = 0.95
SCHEMA_RESULT = "bo.result/1"

# ----------------------------------------------------------------------------------------------- modelo de cluster
CLUSTER = {
    "levels": ["decisão", "grafo", "repositório", "família"],
    "rho": {"graph": 0.30, "repository": 0.20, "family": 0.10},
    "m": {"graph": 3, "repository": 6, "family": 12},
    "resampling_primary": "família",
    "resampling_sensitivity": ["repositório", "grafo"],
    "source": ("hipótese conservadora declarada: não há dado do estudo; o C1 (COBERTURA_NEUTRA, bootstrap por "
               "stack) só dá ordem de grandeza e é medida circular (R3-M1). m por direção é hipótese de "
               "estrutura e é substituído pela contagem real da partição de teste na reestimação cega"),
}
# amostra de deploy: casos espalhados por muitas famílias (poucos por família), pesos desiguais entre estratos
DEPLOY_CLUSTER = {
    "rho": {"graph": 0.30, "repository": 0.20, "family": 0.10},
    "m": {"graph": 1, "repository": 1.5, "family": 2},
    "weights_cv": 0.5,
    "source": ("hipótese declarada: DEPSAMPLE sorteia poucos casos por família; pesos de estrato com coeficiente "
               "de variação 0,5 (efeito de desenho de Kish 1 + CV²)"),
}
SENS_RHO = [0.5, 1.0, 1.5]          # multiplicadores de todas as rho
SENS_M = [0.5, 1.0, 2.0]            # multiplicadores de m (tamanho de cluster)

REESTIMATION = (
    "Reestimação cega, uma vez, pelo STATS, antes do UNSEAL: (1) m_G, m_R, m_F e o número de famílias por "
    "direção vêm das CONTAGENS estruturais da partição de teste publicadas pelo SPLIT (nenhum desfecho); "
    "(2) rho_G, rho_R, rho_F vêm do tradutor rodado na partição de CALIBRAÇÃO (estimador ANOVA de componentes "
    "de variância, truncado em 0); (3) o poder é recalculado com estes valores e com os mesmos valores de "
    "planejamento de efeito; contraste 'claimed_conditional' cujo poder recalculado fica abaixo de 0,80 vira "
    "'descriptive' (relatado, não reivindicado). Em contraste replicado (direções, pares, braços), o poder é "
    "recalculado por unidade: as unidades sem poder saem descritivas e a regra se aplica às K' restantes com o "
    "limiar proporcional, arredondado para cima (todas as K' em H1; ceil(4·K'/6) em H2 e C-LOPO; ceil(10·K'/12) "
    "em H7), e a alegação é rotulada 'parcial, K' de K'. Nada mais muda: teste, limiar, margem, alfa e unidade "
    "ficam."
)


def z(p: float) -> float:
    return N01.inv_cdf(p)


def phi(x: float) -> float:
    return N01.cdf(x)


def design_effect(m: dict, rho: dict) -> float:
    mg, mr, mf = m["graph"], m["repository"], m["family"]
    if not (1 <= mg <= mr <= mf):
        raise ValueError(f"tamanhos de cluster fora de ordem: {m}")
    rg, rr, rf = rho["graph"], rho["repository"], rho["family"]
    if not (0 <= rf <= rr <= rg < 1):
        raise ValueError(f"correlações fora de ordem: {rho}")
    return 1 + (mg - 1) * rg + (mr - mg) * rr + (mf - mr) * rf


def scaled(cl: dict, rho_mult: float = 1.0, m_mult: float = 1.0) -> tuple[dict, dict]:
    rho = {k: min(0.95, v * rho_mult) for k, v in cl["rho"].items()}
    m = {k: max(1.0, v * m_mult) for k, v in cl["m"].items()}
    # mantém a ordem m_G <= m_R <= m_F depois da escala
    m["repository"] = max(m["repository"], m["graph"])
    m["family"] = max(m["family"], m["repository"])
    return m, rho


# ----------------------------------------------------------------------------------------------- fórmulas
# A análise julga com IC de Wald (bootstrap por família ou erro robusto por cluster, crítico t com gl pelo
# número de famílias). O poder é calculado do mesmo jeito: erro-padrão sob a ALTERNATIVA (não a variância sob
# H0 da fórmula de Fleiss, que subestimava o n quando p1 está mais perto de 0,5 que p0) e a aproximação da t
# não central  P(T'(gl, ncp) > t_c) ≈ Phi((ncp - t_c) / sqrt(1 + t_c²/(2 gl))). Conferido por simulação em
# tests/prereg (beta-binomial por família, três tamanhos de amostra).
def crit(alpha: float, sides: int, k: int, df: float | None) -> float:
    """Crítico de um teste com alfa/(sides·k) em cada cauda: normal (df None) ou t(df)."""
    q = alpha / (sides * k)
    return z(1 - q) if df is None else t_ppf(1 - q, df)


def wald_power(delta: float, v1: float, n_eff: float, tc: float, df: float | None, sides: int) -> float:
    """Poder de um teste de Wald da diferença delta (variância por unidade v1, n efetivo n_eff)."""
    ncp = abs(delta) / math.sqrt(v1 / n_eff)
    den = 1.0 if df is None else math.sqrt(1 + tc * tc / (2 * df))
    p = phi((ncp - tc) / den)
    if sides == 2:
        p += phi((-ncp - tc) / den)
    return p


def power_asym(delta: float, p_mean: float, n_eff: float, tc: float, df: float | None, min_abs: float) -> float:
    """Critério de H2 num par: |estimativa| >= min_abs E IC bilateral exclui zero, para diferença verdadeira
    delta entre duas direções independentes de mesmo n efetivo. Os dois eventos quase coincidem; o poder é o
    do mais exigente."""
    p1, p2 = p_mean + delta / 2, p_mean - delta / 2
    v1 = p1 * (1 - p1) + p2 * (1 - p2)
    se = math.sqrt(v1 / n_eff)
    p_min = phi((abs(delta) - min_abs) / se)
    p_ci = wald_power(delta, v1, n_eff, tc, df, 2)
    return min(p_min, p_ci)


def paired_moments(cells: dict, ratio: float) -> tuple[float, float]:
    """Média e variância de D = Y_a - ratio * Y_b por unidade, dado o par (Y_a, Y_b) com probabilidades
    cells = {"11","10","01","00"} (primeiro dígito = Y_a)."""
    vals = {"11": 1 - ratio, "10": 1.0, "01": -ratio, "00": 0.0}
    tot = sum(cells.values())
    if abs(tot - 1) > 1e-9:
        raise ValueError(f"células não somam 1: {cells}")
    mu = sum(cells[k] * vals[k] for k in vals)
    var = sum(cells[k] * vals[k] ** 2 for k in vals) - mu ** 2
    return mu, var


def _betacf(a: float, b: float, x: float) -> float:
    """Fração contínua da beta incompleta (Lentz modificado)."""
    tiny, qab, qap, qam = 1e-300, a + b, a + 1, a - 1
    c, d = 1.0, 1 - qab * x / qap
    d = 1 / (d if abs(d) > tiny else tiny)
    h = d
    for m in range(1, 400):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1 + aa * d
        d = 1 / (d if abs(d) > tiny else tiny)
        c = 1 + aa / c if abs(1 + aa / c) > tiny else tiny
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1 + aa * d
        d = 1 / (d if abs(d) > tiny else tiny)
        c = 1 + aa / c if abs(1 + aa / c) > tiny else tiny
        dl = d * c
        h *= dl
        if abs(dl - 1) < 1e-14:
            break
    return h


def betainc(a: float, b: float, x: float) -> float:
    """Beta incompleta regularizada I_x(a, b)."""
    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0
    lbt = math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b) + a * math.log(x) + b * math.log(1 - x)
    if x < (a + 1) / (a + b + 2):
        return math.exp(lbt) * _betacf(a, b, x) / a
    return 1 - math.exp(lbt) * _betacf(b, a, 1 - x) / b


def t_cdf(t: float, df: float) -> float:
    x = df / (df + t * t)
    tail = 0.5 * betainc(df / 2, 0.5, x)
    return 1 - tail if t >= 0 else tail


def t_ppf(p: float, df: float) -> float:
    """Quantil da t de Student por bisseção (p em (0,5; 1))."""
    lo, hi = 0.0, 1000.0
    for _ in range(200):
        mid = (lo + hi) / 2
        if t_cdf(mid, df) < p:
            lo = mid
        else:
            hi = mid
    return hi


def binom_pmf(k: int, n: int, p: float) -> float:
    return math.comb(n, k) * p ** k * (1 - p) ** (n - k)


def sign_crit(d: int, alpha: float) -> int | None:
    """Menor b com P(Bin(d, 1/2) >= b) <= alpha (teste exato de McNemar unilateral); None se não há."""
    tail = 0.0
    for b in range(d, -1, -1):
        tail += math.comb(d, b) / 2 ** d
        if tail > alpha + 1e-15:
            return b + 1 if b + 1 <= d else None
    return 0


def power_sign_exact(n: int, p10: float, p01: float, alpha: float) -> float:
    """Poder exato do McNemar unilateral (c3 certo e controle errado = p10; o contrário = p01) com n casos."""
    pd = p10 + p01
    q = p10 / pd
    tot = 0.0
    for d in range(n + 1):
        crit = sign_crit(d, alpha)
        if crit is None:
            continue
        pdd = binom_pmf(d, n, pd)
        tot += pdd * sum(binom_pmf(b, d, q) for b in range(crit, d + 1))
    return tot


def at_least(k: int, probs: list[float]) -> float:
    """P(pelo menos k sucessos) com sucessos independentes de probabilidades probs (Poisson-binomial)."""
    dist = [1.0]
    for p in probs:
        nd = [0.0] * (len(dist) + 1)
        for i, v in enumerate(dist):
            nd[i] += v * (1 - p)
            nd[i + 1] += v * p
        dist = nd
    return sum(dist[k:])


def solve_unit_power(k: int, n_true: int, n_null: int, null_rate: float, target: float) -> float:
    """Poder por unidade (par ou direção) que dá P(>= k de n_true + n_null) = target, por bisseção."""
    lo, hi = 0.0, 1.0
    for _ in range(80):
        mid = (lo + hi) / 2
        if at_least(k, [mid] * n_true + [null_rate] * n_null) >= target:
            hi = mid
        else:
            lo = mid
    return hi


def bisect_n(fn_power, target: float, lo: float = 2.0, hi: float = 1e7) -> float:
    """Menor n efetivo (contínuo) com fn_power(n) >= target; fn_power monótona crescente."""
    if fn_power(hi) < target:
        raise ValueError("poder alvo inalcançável")
    for _ in range(200):
        mid = (lo + hi) / 2
        if fn_power(mid) >= target:
            hi = mid
        else:
            lo = mid
    return hi


# ----------------------------------------------------------------------------------------------- contrastes
# Cada contraste: o que se afirma, sobre que métrica, com que teste e com que valores de planejamento.
# status: claimed (limite de viabilidade conhecido agora e o poder nele >= 0,80) | claimed_conditional (n
# necessário calculado; reivindicado só se a contagem real alcançar, conferida pelo STATS antes do UNSEAL) |
# descriptive (sem inferência; motivo declarado). priority: P0 | P1 | suplementar.
CONTRASTS = [
    {
        "contrast_id": "C-H1", "hypothesis": "H1", "rq": "RQ1", "priority": "P0",
        "claim": ("Cobertura operacional por decisão, no limite superior, abaixo de 0,70 em cada uma das 12 "
                  "direções."),
        "metrics": ["M-OPCOV-DEC"], "bound": "upper",
        "replication": {"over": "direção A→B", "k": 12, "rule": "teste de interseção-união: H1 só vale se as "
                        "12 direções rejeitarem; cada direção é relatada"},
        "test": "unilateral: limite superior de confiança 95% (bootstrap por família) do limite superior < 0,70",
        "alpha": ALPHA, "sides": 1,
        "multiplicity": "interseção-união (exige todas): sem ajuste de alfa; o poder conjunto é que é exigido",
        "fixed_effects": ["direção"],
        "model": "one_prop", "planning": {"p0": 0.70, "p1": 0.60},
        "planning_source": ("C1 (COBERTURA_NEUTRA): 40–62% dos valores AWS sem contrapartida e 68–85% de "
                            "acerto do pipeline nos que têm; produto ≈ 0,3–0,5. Planejamento em 0,60, mais "
                            "perto do limiar (conservador)."),
        "power_rule": {"kind": "all_of", "k": 12},
        "feasibility": {"kind": "census", "cap": None,
                        "rule": "n = decisões configuradas em A na partição de teste, por direção (SPLIT)"},
        "status": "claimed_conditional",
    },
    {
        "contrast_id": "C-H2", "hypothesis": "H2", "rq": "RQ2", "priority": "P0",
        "claim": ("Em pelo menos 4 dos 6 pares, |cobertura(A→B) − cobertura(B→A)| ≥ 0,05 por decisão, com IC "
                  "95% (bootstrap por família e repositório) que exclui zero, nas leituras de limite inferior "
                  "e superior."),
        "metrics": ["M-OPCOV-DEC"], "bound": "both",
        "replication": {"over": "par", "k": 6, "rule": "contagem: pelo menos 4 de 6 pares"},
        "test": "bilateral por par: IC 95% da diferença exclui 0 e |estimativa| >= 0,05; mesmo sinal nos dois limites",
        "alpha": ALPHA, "sides": 2,
        "multiplicity": "regra de contagem 4 de 6; sob nulidade global P(>= 4 falsos) < 1e-4",
        "fixed_effects": ["par", "direção"],
        "model": "asym", "planning": {"delta": 0.10, "p_mean": 0.50, "min_abs": 0.05},
        "planning_source": ("efeito de planejamento = o dobro do mínimo de interesse (0,05) da hipótese; "
                            "p médio 0,50 maximiza a variância (conservador); sem desconhecidos no "
                            "planejamento: com eles, exigir o mesmo sinal nos dois limites só torna o critério "
                            "mais severo"),
        "power_rule": {"kind": "at_least", "k": 4, "n_true": 4, "n_null": 2},
        "feasibility": {"kind": "census", "cap": None,
                        "rule": "n por direção = decisões configuradas na origem na partição de teste (SPLIT)"},
        "status": "claimed_conditional",
    },
    {
        "contrast_id": "C-H3", "hypothesis": "H3", "rq": "RQ3", "priority": "P0",
        "claim": ("Autorização e borda (CDN/WAF) atravessam menos que dimensionamento de compute e storage: razão "
                  "de chances < 1 no modelo por decisão com efeitos fixos de par e de direção."),
        "metrics": ["M-OPCOV-DEC"], "bound": "both",
        "replication": {"over": "modelo único", "k": 1, "rule": "um coeficiente; leituras de limite inferior e superior"},
        "test": ("unilateral: regressão logística por decisão, efeitos fixos de par e direção, erro-padrão "
                 "robusto por família; IC 95% superior da razão de chances < 1 nos dois limites"),
        "alpha": ALPHA, "sides": 1,
        "multiplicity": "contraste único; o tipo de perda NÃO entra como preditor (recodifica o desfecho)",
        "fixed_effects": ["par", "direção", "domínio", "tipo de grão", "papel", "cardinalidade"],
        "model": "two_prop", "planning": {"p1": 0.55, "p2": 0.35},
        "planning_source": ("dimensionamento 0,55 contra autorização/borda 0,35 (razão de chances ≈ 0,44); "
                            "os efeitos fixos de par reduzem a variância e os dois grupos vêm em parte das "
                            "mesmas famílias (comparação dentro da família): os dois ignorados aqui, como "
                            "grupos independentes (conservador)"),
        "power_rule": {"kind": "single"},
        "feasibility": {"kind": "census", "cap": None,
                        "rule": "n por grupo = decisões de autorização+borda e de dimensionamento no teste, 12 direções juntas"},
        "status": "claimed_conditional",
    },
    {
        "contrast_id": "C-H4", "hypothesis": "H4", "rq": "RQ1", "priority": "P0",
        "claim": ("A tipagem por evidência superestima a persistência: precisão de persistência combinada "
                  "(pesos do frame) ≤ 0,90 no limite superior."),
        "metrics": ["M-PERS-DEC"], "bound": "upper",
        "replication": {"over": "leitura combinada", "k": 1, "rule": "um teste; estratos par×domínio×"
                        "cardinalidade×relação×direção são descritivos"},
        "test": "unilateral: limite superior de confiança 95% (bootstrap por família, recurso e repositório) < 0,90",
        "alpha": ALPHA, "sides": 1,
        "multiplicity": "contraste único; estratos sem inferência",
        "fixed_effects": [],
        "model": "one_prop_deploy", "planning": {"p0": 0.90, "p1": 0.80},
        "planning_source": "planejamento 0,80, a 10 pontos do limiar (C1 não mediu persistência)",
        "power_rule": {"kind": "single"},
        "feasibility": {"kind": "cap", "cap": 720,
                        "rule": "casos carregados a deploy limitados pelo orçamento D3 (DEPSAMPLE)"},
        "status": "claimed",
    },
    {
        "contrast_id": "C-H5", "hypothesis": "H5", "rq": "RQ4", "priority": "P1",
        "claim": "Mediana do atraso de disponibilidade no provider Terraform > 6 meses.",
        "metrics": [], "estimands": ["E-DRIFT-LAG"], "bound": "na",
        "replication": {"over": "modelo único", "k": 1, "rule": "um teste"},
        "test": ("unilateral: Turnbull (censura intervalar, truncamento à esquerda); limite inferior de "
                 "confiança 95% da mediana > 6 meses"),
        "alpha": ALPHA, "sides": 1,
        "multiplicity": "suplementar (P1); nenhum P0 depende dele",
        "fixed_effects": ["provedor de origem", "provedor de destino"],
        "model": "survival_median", "planning": {"m0": 6.0, "m1": 9.0, "censor_inflation": 1.5},
        "planning_source": ("mediana de planejamento 9 meses; variância do log da mediana ≈ 1/eventos "
                            "(exponencial) inflada 1,5× pela censura intervalar trimestral"),
        "power_rule": {"kind": "single"},
        "feasibility": {"kind": "census", "cap": None, "rule": "eventos = pares conceito×provedor com chegada observada"},
        "status": "claimed_conditional",
    },
    {
        "contrast_id": "C-H6-COV", "hypothesis": "H6", "rq": "RQ1", "priority": "P0",
        "claim": ("Semente simétrica e grão canônico não baixam a cobertura operacional frente a semente só AWS "
                  "com tipos crus: não inferioridade com margem 0,02 por decisão."),
        "metrics": ["M-OPCOV-DEC", "M-ABL-AWSRAW-DEC"], "bound": "both",
        "replication": {"over": "12 direções juntas", "k": 1, "rule": "média das 12 direções com pesos iguais"},
        "test": "unilateral pareado por decisão: limite inferior 95% de (completo − ablado) > −0,02, nos dois limites",
        "alpha": ALPHA, "sides": 1,
        "multiplicity": "contraste único; a parte de Gini de H6 é descritiva (C-H6-GINI)",
        "fixed_effects": ["direção"],
        "model": "paired_noninf",
        "planning": {"cells": {"11": 0.50, "10": 0.05, "01": 0.05, "00": 0.40}, "ratio": 1.0, "margin": -0.02},
        "planning_source": "sem diferença verdadeira; discordância de 5% em cada sentido (hipótese conservadora)",
        "power_rule": {"kind": "single"},
        "feasibility": {"kind": "census", "cap": None, "rule": "decisões do teste, 12 direções"},
        "status": "claimed_conditional",
    },
    {
        "contrast_id": "C-H6-GINI", "hypothesis": "H6", "rq": "RQ1", "priority": "P0",
        "claim": ("Equilíbrio de contagens entre provedores (Gini das classes realizadas por provedor) menor com "
                  "semente simétrica e grão canônico do que com semente só AWS e tipos crus."),
        "metrics": [], "estimands": ["E-GINI-BALANCE"], "bound": "na",
        "replication": {"over": "artefato", "k": 1, "rule": "comparação de dois artefatos"},
        "test": "nenhum: descritivo",
        "alpha": None, "sides": None,
        "multiplicity": "não se aplica",
        "fixed_effects": [],
        "model": "descriptive", "planning": {},
        "planning_source": ("o Gini é propriedade do artefato construído (4 contagens), não estimativa amostral; "
                            "rotulado 'equilíbrio de contagens', nunca 'neutralidade'"),
        "power_rule": {"kind": "none"},
        "feasibility": {"kind": "none", "cap": None, "rule": "não se aplica"},
        "status": "descriptive",
    },
    {
        "contrast_id": "C-H7", "hypothesis": "H7", "rq": "RQ1", "priority": "P0",
        "claim": ("Perda do hub pequena: cobertura pela ontologia ≥ 0,95 × cobertura do caminho direto em pelo "
                  "menos 10 das 12 direções, sob o mesmo oráculo e lowering."),
        "metrics": ["M-OPCOV-DEC", "M-OPCOV-DEC-DIRECT"], "bound": "both",
        "replication": {"over": "direção A→B", "k": 12, "rule": "contagem: pelo menos 10 de 12 direções"},
        "test": ("unilateral pareado por decisão: limite inferior 95% de (Y_ont − 0,95·Y_dir) > 0, nos dois "
                 "limites; falha é resultado contra o hub"),
        "alpha": ALPHA, "sides": 1,
        "multiplicity": "regra de contagem 10 de 12",
        "fixed_effects": ["direção"],
        "model": "paired_ratio",
        "planning": {"cells": {"11": 0.52, "10": 0.03, "01": 0.03, "00": 0.42}, "ratio": 0.95, "margin": 0.0},
        "planning_source": "razão verdadeira 1 (sem perda), cobertura direta 0,55, discordância 3% em cada sentido",
        "power_rule": {"kind": "at_least", "k": 10, "n_true": 12, "n_null": 0},
        "feasibility": {"kind": "census", "cap": None, "rule": "decisões do teste por direção"},
        "status": "claimed_conditional",
    },
    {
        "contrast_id": "C-H8", "hypothesis": "H8", "rq": "RQ1", "priority": "P0",
        "claim": ("Correspondências complexas (grupo sobre subgrafo, 1:N, condicionais) respondem por ≥ 10% da "
                  "cobertura primária por decisão."),
        "metrics": ["M-OPCOV-DEC-COMPLEX"], "bound": "lower",
        "replication": {"over": "12 direções juntas", "k": 1, "rule": "fração entre as decisões carregadas no limite inferior"},
        "test": "unilateral: limite inferior de confiança 95% da fração >= 0,10",
        "alpha": ALPHA, "sides": 1,
        "multiplicity": "contraste único",
        "fixed_effects": ["direção"],
        "model": "one_prop", "planning": {"p0": 0.10, "p1": 0.15},
        "planning_source": "fração de planejamento 0,15 (meio caminho entre o limiar e o dobro dele)",
        "power_rule": {"kind": "single"},
        "feasibility": {"kind": "census", "cap": None, "rule": "decisões carregadas (limite inferior) no teste"},
        "status": "claimed_conditional",
    },
    {
        "contrast_id": "C-H9", "hypothesis": "H9", "rq": "RQ1", "priority": "P0",
        "claim": ("Fora da calibração, a axiomatização completa (c3) obtém, em pelo menos uma família de "
                  "consequências, consequências corretas e justificadas que nem a tabela (c1) nem a "
                  "taxonomia+realizações (c2) obtêm."),
        "metrics": ["M-OPCOV-DEC-C1", "M-OPCOV-DEC-C2", "M-OPCOV-DEC"], "bound": "na",
        "replication": {"over": "família de consequências", "k": 7, "rule": "pelo menos 1 de 7 famílias"},
        "test": ("por família: dois McNemar exatos unilaterais pareados por caso (c3×c2 e c3×c1), os dois com "
                 "p <= 0,05/7; resposta esperada independente (REQUIREMENTS, CQs congeladas) e justificativa"),
        "alpha": ALPHA, "sides": 1,
        "multiplicity": "Bonferroni nas 7 famílias; interseção-união nos 2 controles",
        "fixed_effects": [],
        "model": "sign_exact",
        "planning": {"p10": 0.30, "p01": 0.02, "families": 7, "fixture_scale_n": 12},
        "planning_source": ("efeito só numa família (cenário menos favorável que ainda torna H9 verdadeira); "
                            "c2 é o controle que liga (mais perto de c3); n = 12 é a escala das fixtures por família"),
        "power_rule": {"kind": "single"},
        "feasibility": {"kind": "census", "cap": None,
                        "rule": ("casos fora da calibração com resposta esperada independente por família "
                                 "(REASONING-PROOF); abaixo do n necessário H9 sai 'inconclusivo', nunca 'nulo'")},
        "status": "claimed_conditional",
    },
    {
        "contrast_id": "C-LOPO", "hypothesis": "LOPO", "rq": "RQ1", "priority": "P0",
        "claim": ("Leave-one-provider-out (OCI): a ontologia induzida sem OCI acomoda a OCI com cobertura ≥ "
                  "0,90 × a da ontologia de 4 provedores em pelo menos 4 das 6 direções com OCI."),
        "metrics": ["M-LOPO-OPCOV-DEC", "M-OPCOV-DEC"], "bound": "both",
        "replication": {"over": "direção com OCI", "k": 6, "rule": "contagem: pelo menos 4 de 6"},
        "test": "unilateral pareado por decisão: limite inferior 95% de (Y_3 − 0,90·Y_4) > 0, nos dois limites",
        "alpha": ALPHA, "sides": 1,
        "multiplicity": "regra de contagem 4 de 6; contaminação do glossário declarada (favorece a acomodação)",
        "fixed_effects": ["direção"],
        "model": "paired_ratio",
        "planning": {"cells": {"11": 0.45, "10": 0.05, "01": 0.05, "00": 0.45}, "ratio": 0.90, "margin": 0.0},
        "planning_source": "razão verdadeira 1, cobertura 0,50, discordância 5% em cada sentido",
        "power_rule": {"kind": "at_least", "k": 4, "n_true": 6, "n_null": 0},
        "feasibility": {"kind": "census", "cap": None, "rule": "decisões OCI do teste por direção (raras no TerraDS)"},
        "status": "claimed_conditional",
    },
    {
        "contrast_id": "C-ABL", "hypothesis": "ABL", "rq": "RQ1", "priority": "P0",
        "claim": ("Ablações (evidência principal, R4-W2): cada braço — semente só AWS, limiar alternativo de "
                  "admissão (2 braços), tipos crus, sem guardas e transformações, c1 e c2 — muda a cobertura "
                  "operacional por decisão frente ao pipeline completo; sem efeito e com equivalência ±0,03 o "
                  "componente é relatado como higiene."),
        "metrics": ["M-OPCOV-DEC", "M-ABL-SEEDAWS-DEC", "M-ABL-THR-ALT1-DEC", "M-ABL-THR-ALT2-DEC",
                    "M-ABL-RAWTYPES-DEC", "M-ABL-NOGUARD-DEC", "M-OPCOV-DEC-C1", "M-OPCOV-DEC-C2"],
        "bound": "both",
        "replication": {"over": "braço", "k": 7, "rule": "cada braço decide: efeito, equivalência (higiene) ou inconclusivo"},
        "test": ("bilateral pareado por decisão (12 direções juntas): IC da diferença exclui 0 (efeito); TOST "
                 "com margem ±0,03 (equivalência); nenhum dos dois = inconclusivo"),
        "alpha": ALPHA, "sides": 2,
        "multiplicity": "Holm nos 7 braços (poder calculado no alfa mais severo, 0,05/7)",
        "fixed_effects": ["direção"],
        "model": "paired_diff_holm",
        "planning": {"cells": {"11": 0.47, "10": 0.06, "01": 0.03, "00": 0.44}, "ratio": 1.0, "margin": 0.0,
                     "arms": 7},
        "planning_source": "diferença verdadeira 0,03 (discordância 6% contra 3%)",
        "power_rule": {"kind": "single"},
        "feasibility": {"kind": "census", "cap": None, "rule": "decisões do teste, conjunto selado"},
        "status": "claimed_conditional",
    },
    {
        "contrast_id": "C-RQ5-TRANS", "hypothesis": "RQ5", "rq": "RQ5", "priority": "P0",
        "claim": ("Eixo de tradução com orçamento igual: diferença de cobertura operacional por decisão entre "
                  "o tradutor pela ontologia e o pacote de tradução de cada comparador com artefato (Kalinin: "
                  "contra a melhor variante da família, por direção)."),
        "metrics": ["M-OPCOV-DEC", "M-H2H-TRANS-DEC"], "bound": "both",
        "replication": {"over": "comparador com eixo de tradução", "k": 12,
                        "rule": "cada comparador relatado; sem artefato = NOT_APPLICABLE, nunca 0"},
        "test": "bilateral pareado por decisão: IC da diferença exclui 0",
        "alpha": ALPHA, "sides": 2,
        "multiplicity": "Holm nos comparadores com artefato de tradução (poder no alfa mais severo, 0,05/12)",
        "fixed_effects": ["direção"],
        "model": "paired_diff_holm",
        "planning": {"cells": {"11": 0.40, "10": 0.10, "01": 0.05, "00": 0.45}, "ratio": 1.0, "margin": 0.0,
                     "arms": 12},
        "planning_source": "diferença 0,05 (discordância 10% contra 5%); escolher a melhor variante Kalinin favorece o baseline",
        "power_rule": {"kind": "single"},
        "feasibility": {"kind": "census", "cap": None, "rule": "decisões do teste"},
        "status": "claimed_conditional",
    },
    {
        "contrast_id": "C-TOOL", "hypothesis": "TOOL", "rq": "RQ1", "priority": "suplementar",
        "claim": ("Acerto por ferramenta: tradutor pela ontologia × par-a-par × LLM com prompt congelado, por "
                  "decisão, sob o mesmo oráculo (suplementar)."),
        "metrics": ["M-OPCOV-DEC", "M-OPCOV-DEC-DIRECT", "M-TOOL-LLM-DEC"], "bound": "both",
        "replication": {"over": "par de ferramentas", "k": 3, "rule": "três diferenças pareadas"},
        "test": "bilateral pareado por decisão, reamostragem por família e repositório (McNemar por valor saiu)",
        "alpha": ALPHA, "sides": 2,
        "multiplicity": "Holm nas 3 diferenças",
        "fixed_effects": ["direção"],
        "model": "paired_diff_holm",
        "planning": {"cells": {"11": 0.40, "10": 0.10, "01": 0.05, "00": 0.45}, "ratio": 1.0, "margin": 0.0,
                     "arms": 3},
        "planning_source": "diferença 0,05 (discordância 10% contra 5%)",
        "power_rule": {"kind": "single"},
        "feasibility": {"kind": "cap", "cap": 2400,
                        "rule": "amostra de teste traduzida pelo LLM limitada a 200 decisões por direção (custo)"},
        "status": "claimed",
    },
    {
        "contrast_id": "C-BEHAV", "hypothesis": "BEHAV", "rq": "RQ1", "priority": "P0",
        "claim": ("Comportamento: fração de pares de sonda com OBSERVATIONS_MATCH_UNDER_PROTOCOL, por tipo de "
                  "sonda, com IC de Wilson do tamanho real; vale só para os casos sondados."),
        "metrics": ["M-BEHAV-DEC"], "bound": "both",
        "replication": {"over": "tipo de sonda", "k": 6, "rule": "relatado por tipo"},
        "test": "nenhum: descritivo (Wilson; 10 em 10 dão limite inferior ≈ 0,72)",
        "alpha": None, "sides": None,
        "multiplicity": "não se aplica",
        "fixed_effects": [],
        "model": "descriptive", "planning": {"n_per_type": 10},
        "planning_source": "amostra de sondas pequena por custo e janela; nunca extrapolada",
        "power_rule": {"kind": "none"},
        "feasibility": {"kind": "cap", "cap": 60, "rule": "≈10 pares por tipo de sonda com suporte validado"},
        "status": "descriptive",
    },
]

HYPOTHESES = ["H1", "H2", "H3", "H4", "H5", "H6", "H7", "H8", "H9"]


def _de(model: str, cl_mult=(1.0, 1.0)) -> float:
    if model == "one_prop_deploy":
        m, rho = scaled(DEPLOY_CLUSTER, *cl_mult)
        return design_effect(m, rho) * (1 + DEPLOY_CLUSTER["weights_cv"] ** 2)
    m, rho = scaled(CLUSTER, *cl_mult)
    return design_effect(m, rho)


def unit_target(c: dict) -> float:
    pr = c["power_rule"]
    if pr["kind"] == "all_of":
        return TARGET ** (1 / pr["k"])
    if pr["kind"] == "at_least":
        null_rate = c["alpha"] / c["sides"]
        return solve_unit_power(pr["k"], pr["n_true"], pr["n_null"], null_rate, TARGET)
    return TARGET


def unit_power_fn(c: dict, df: float | None = None):
    """Função n_efetivo -> poder por unidade (direção, par, família ou braço). df = gl da análise (crítico t);
    None = crítico normal."""
    p, a, s = c["planning"], c["alpha"], c["sides"]
    mdl = c["model"]
    if mdl in ("one_prop", "one_prop_deploy"):
        tc = crit(a, 1, 1, df)
        return lambda n: wald_power(p["p1"] - p["p0"], p["p1"] * (1 - p["p1"]), n, tc, df, 1)
    if mdl == "two_prop":
        tc = crit(a, s, 1, df)
        v1 = p["p1"] * (1 - p["p1"]) + p["p2"] * (1 - p["p2"])
        return lambda n: wald_power(p["p1"] - p["p2"], v1, n, tc, df, s)
    if mdl == "asym":
        tc = crit(a, 2, 1, df)
        return lambda n: power_asym(p["delta"], p["p_mean"], n, tc, df, p["min_abs"])
    if mdl in ("paired_noninf", "paired_ratio"):
        mu, var = paired_moments(p["cells"], p["ratio"])
        tc = crit(a, 1, 1, df)
        return lambda n: wald_power(mu - p["margin"], var, n, tc, df, 1)
    if mdl == "paired_diff_holm":
        mu, var = paired_moments(p["cells"], p["ratio"])
        tc = crit(a, 2, p["arms"], df)
        return lambda n: wald_power(mu, var, n, tc, df, 2)
    if mdl == "survival_median":
        eff = abs(math.log(p["m1"] / p["m0"]))
        return lambda d: phi(eff * math.sqrt(d / p["censor_inflation"]) - z(1 - a))
    raise ValueError(mdl)


def df_of(c: dict, n_fam: float) -> float:
    """Graus de liberdade da análise: famílias - 1 (uma amostra ou pareado); 2·(famílias - 1) com dois grupos
    independentes de famílias (H3 por grupo, H2 por direção)."""
    two = c["model"] in ("two_prop", "asym")
    return max(1.0, (2 * (n_fam - 1)) if two else (n_fam - 1))


def power_t(c: dict, n_fam: float, m_f: float, de: float) -> float:
    """Poder por unidade com n_fam famílias de m_f decisões, efeito de desenho de e crítico t da análise."""
    return unit_power_fn(c, df_of(c, n_fam))(n_fam * m_f / de)


def sign_required(c: dict, target: float) -> tuple[int, float]:
    p = c["planning"]
    a = c["alpha"] / p["families"]
    for n in range(2, 2001):
        pw = power_sign_exact(n, p["p10"], p["p01"], a)
        if pw >= target:
            # o poder do teste exato não é monótono em n; exige que os 5 n seguintes também alcancem
            if all(power_sign_exact(n + k, p["p10"], p["p01"], a) >= target for k in range(1, 6)):
                return n, pw
    raise ValueError("n exato não encontrado até 2000")


def compute(c: dict, cl_mult=(1.0, 1.0)) -> dict:
    """Resultado do contraste: alvo por unidade, n efetivo, efeito de desenho, n de unidades e de famílias."""
    mdl = c["model"]
    if mdl == "descriptive":
        return {"kind": "descriptive"}
    target = unit_target(c)
    if mdl == "sign_exact":
        n, pw = sign_required(c, target)
        p = c["planning"]
        fx = power_sign_exact(p["fixture_scale_n"], p["p10"], p["p01"], c["alpha"] / p["families"])
        return {"kind": "exact", "unit_power_target": round(target, 4), "alpha_per_test": round(c["alpha"] / p["families"], 6),
                "n_cases_per_family": n, "unit_power_at_n": round(pw, 4),
                "power_at_fixture_scale": round(fx, 4), "fixture_scale_n": p["fixture_scale_n"],
                "overall_power": round(pw, 4)}
    fn = unit_power_fn(c)
    n_eff = bisect_n(fn, target)
    if mdl == "survival_median":
        d = math.ceil(n_eff)
        return {"kind": "events", "unit_power_target": round(target, 4), "events": d,
                "unit_power_at_n": round(fn(d), 4), "overall_power": round(fn(d), 4)}
    de = _de(mdl, cl_mult)
    if mdl == "one_prop_deploy":
        m_f = scaled(DEPLOY_CLUSTER, *cl_mult)[0]["family"]
    else:
        m_f = scaled(CLUSTER, *cl_mult)[0]["family"]
    n_fam_z = math.ceil(n_eff * de / m_f)
    n_fam = n_fam_z
    while power_t(c, n_fam, m_f, de) < target:   # crítico t com gl pelo número de famílias
        n_fam += 1
    n_units = math.ceil(n_fam * m_f)
    pw_unit = power_t(c, n_fam, m_f, de)
    out = {"kind": "normal", "unit_power_target": round(target, 4), "n_effective": math.ceil(n_eff),
           "design_effect": round(de, 4), "n_units": n_units, "n_families": n_fam,
           "families_added_by_t": n_fam - n_fam_z, "unit_power_at_n": round(pw_unit, 4)}
    if mdl == "two_prop":
        out["per_group"] = True
    pr = c["power_rule"]
    if pr["kind"] == "all_of":
        out["overall_power"] = round(pw_unit ** pr["k"], 4)
    elif pr["kind"] == "at_least":
        out["overall_power"] = round(at_least(pr["k"], [pw_unit] * pr["n_true"] + [c["alpha"] / c["sides"]] * pr["n_null"]), 4)
    else:
        out["overall_power"] = round(pw_unit, 4)
    cap = c["feasibility"].get("cap")
    if cap is not None:
        out["cap_units"] = cap
        pw_cap = power_t(c, cap / m_f, m_f, de)
        out["unit_power_at_cap"] = round(pw_cap, 4)
        out["overall_power_at_cap"] = round(pw_cap, 4) if pr["kind"] == "single" else None
    return out


def sensitivity(c: dict) -> list[dict]:
    if c["model"] in ("descriptive", "sign_exact", "survival_median"):
        return []
    rows = []
    for rm in SENS_RHO:
        for mm in SENS_M:
            r = compute(c, (rm, mm))
            rows.append({"rho_mult": rm, "m_mult": mm, "design_effect": r["design_effect"],
                         "n_units": r["n_units"], "n_families": r["n_families"]})
    return rows


# ----------------------------------------------------------------------------------------------- documento C15
INC_RE = re.compile(r"^([A-Z][A-Z0-9]*(?:-[A-Z0-9]+)+): (.{5,})$", re.S)


def load_spec(path: Path) -> dict:
    import yaml  # PyYAML do requirements.lock
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def spec_metric_to_result(m: dict, correlated: list[str]) -> dict:
    mo = INC_RE.match(m["inclusion"])
    if not mo:
        raise ValueError(f"{m['metric_id']}: inclusion sem 'REGRA-ID: texto'")
    ju = {"method": m["uncertainty"], "level": LEVEL}
    if correlated:
        ju["correlated_with"] = correlated
    return {
        "metric_id": m["metric_id"],
        "name": m["definition"].split(" | ")[0].removeprefix("Definição: ")[:160],
        "reading": m["reading"], "axis": m["axis"], "quantifier": m["quantifier"],
        "operational_coverage": {"lower": 0.0, "upper": 1.0, "est": None, "n": 0},
        "frame": {"description": m["frame"]},
        "inclusion": {"rule_id": mo.group(1), "text": mo.group(2)},
        "weights": {"scheme": m["weights"]},
        "joint_uncertainty": ju,
    }


def build(spec_path: Path) -> dict:
    spec = load_spec(spec_path)
    by_id = {m["metric_id"]: m for m in spec["metrics"]}
    cited: list[str] = []
    for c in CONTRASTS:
        for mid in c["metrics"]:
            if mid not in by_id:
                raise ValueError(f"{c['contrast_id']}: métrica {mid} não está em {spec_path.name}")
            if mid not in cited:
                cited.append(mid)
    # incerteza conjunta: métricas que entram no mesmo contraste são reamostradas juntas (mesmas famílias)
    corr: dict[str, list[str]] = {m: [] for m in cited}
    for c in CONTRASTS:
        for a in c["metrics"]:
            for b in c["metrics"]:
                if a != b and b not in corr[a]:
                    corr[a].append(b)
    metrics = [spec_metric_to_result(by_id[m], sorted(corr[m])) for m in cited]
    contrasts = []
    for c in CONTRASTS:
        cc = copy.deepcopy(c)
        cc["result"] = compute(c)
        cc["sensitivity"] = sensitivity(c)
        contrasts.append(cc)
    return {
        "schema": SCHEMA_RESULT, "contract": "C15", "contract_version": "3.0.0", "module": "PREREG",
        "generated_at": spec["generated_at"],
        "metrics": metrics,
        "notes": ("Documento de PLANEJAMENTO: nenhum dado do estudo existe; por isso toda métrica traz n = 0, "
                  "est nulo e limites 0..1. O bloco data guarda o modelo de poder, os contrastes "
                  "pré-registrados e a grade de sensibilidade. Gerado por prereg/power.py --write."),
        "data": {
            "alpha": ALPHA, "target_power": TARGET, "confidence_level": LEVEL,
            "cluster_model": CLUSTER, "deploy_cluster_model": DEPLOY_CLUSTER,
            "design_effect_formula": "DE = 1 + (m_G-1)·rho_G + (m_R-m_G)·rho_R + (m_F-m_R)·rho_F",
            "design_effect_census": round(_de("one_prop"), 4),
            "design_effect_deploy": round(_de("one_prop_deploy"), 4),
            "sensitivity_grid": {"rho_mult": SENS_RHO, "m_mult": SENS_M},
            "reestimation": REESTIMATION,
            "status_semantics": {
                "claimed": "limite de viabilidade conhecido agora e poder nele >= 0,80",
                "claimed_conditional": ("n necessário calculado; reivindicado só se a contagem real (SPLIT, "
                                        "DEPSAMPLE, REASONING-PROOF) alcançar, conferido pelo STATS antes do UNSEAL"),
                "descriptive": "sem inferência; motivo declarado em planning_source",
            },
            "hypotheses": HYPOTHESES,
            "contrasts": contrasts,
        },
    }


def dumps(doc: dict) -> str:
    return json.dumps(doc, ensure_ascii=False, indent=1, sort_keys=False) + "\n"


def check(doc_path: Path, spec_path: Path) -> list[str]:
    errs: list[str] = []
    try:
        expected = dumps(build(spec_path))
    except Exception as e:  # noqa: BLE001 - o motivo vai na mensagem
        return [f"recalcular falhou: {e}"]
    got = doc_path.read_text(encoding="utf-8")
    if got != expected:
        errs.append(f"{doc_path.name} difere do recalculado (rode --write e revise o diff)")
    spec_ids = {m["metric_id"] for m in load_spec(spec_path)["metrics"]}
    return errs + semantic(json.loads(got), spec_ids)


def semantic(doc: dict, spec_ids: set) -> list[str]:
    """Regras de conteúdo de power.json, independentes da igualdade com o recalculado."""
    errs: list[str] = []
    data = doc.get("data", {})
    cm = data.get("cluster_model", {})
    rho = cm.get("rho", {})
    if not (rho.get("family", 0) > 0 and rho.get("repository", 0) > 0):
        errs.append("modelo de cluster sem correlação por família E por repositório")
    if not (data.get("design_effect_census", 1) > 1 and data.get("design_effect_deploy", 1) > 1):
        errs.append("efeito de desenho <= 1: a correlação não entrou no cálculo")
    seen_h = {c["hypothesis"] for c in data.get("contrasts", [])}
    for h in HYPOTHESES:
        if h not in seen_h:
            errs.append(f"hipótese {h} sem contraste")
    for c in data.get("contrasts", []):
        cid, st, r = c["contrast_id"], c["status"], c["result"]
        for mid in c["metrics"]:
            if mid not in spec_ids:
                errs.append(f"{cid}: métrica {mid} fora do metrics_spec.yaml")
        if st == "descriptive":
            if c["model"] != "descriptive" or c["alpha"] is not None:
                errs.append(f"{cid}: descritivo não pode trazer teste")
            if len(c.get("planning_source", "")) < 20:
                errs.append(f"{cid}: descritivo sem motivo declarado")
            continue
        if st not in ("claimed", "claimed_conditional"):
            errs.append(f"{cid}: status desconhecido {st}")
            continue
        if r.get("overall_power") is None or r["overall_power"] < TARGET - 1e-9:
            errs.append(f"{cid}: poder conjunto {r.get('overall_power')} < {TARGET} no n declarado")
        if r.get("kind") == "normal":
            if not r.get("design_effect", 1) > 1:
                errs.append(f"{cid}: n sem efeito de desenho (correlação por família e repositório)")
            if not c.get("sensitivity"):
                errs.append(f"{cid}: sem grade de sensibilidade")
        if st == "claimed":
            cap = c["feasibility"].get("cap")
            if cap is None:
                errs.append(f"{cid}: 'claimed' exige limite de viabilidade conhecido")
            elif r.get("unit_power_at_cap", 0) < r["unit_power_target"] - 1e-9:
                errs.append(f"{cid}: poder no limite de viabilidade ({r.get('unit_power_at_cap')}) abaixo do alvo")
        if c["feasibility"].get("cap") is not None and r.get("n_units", 0) > c["feasibility"]["cap"]:
            errs.append(f"{cid}: n necessário {r['n_units']} acima do limite {c['feasibility']['cap']}: tem de ser descritivo")
        if c["alpha"] is None or c["sides"] not in (1, 2):
            errs.append(f"{cid}: reivindicado sem alfa ou lateralidade")
    return errs


def report(doc: dict) -> str:
    lines = [f"{'contraste':<13} {'status':<20} {'poder':>6} {'n unid.':>8} {'famílias':>9}  alvo/unid."]
    for c in doc["data"]["contrasts"]:
        r = c["result"]
        n = r.get("n_units", r.get("n_cases_per_family", r.get("events", "")))
        lines.append(f"{c['contrast_id']:<13} {c['status']:<20} {str(r.get('overall_power', '-')):>6} "
                     f"{str(n):>8} {str(r.get('n_families', '-')):>9}  {r.get('unit_power_target', '-')}")
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--write", nargs="?", const=str(HERE / "power.json"))
    g.add_argument("--check")
    g.add_argument("--report", action="store_true")
    ap.add_argument("--spec", default=str(HERE / "metrics_spec.yaml"))
    a = ap.parse_args(argv)
    spec = Path(a.spec)
    if a.write:
        Path(a.write).write_text(dumps(build(spec)), encoding="utf-8")
        print(f"power.json gravado: {a.write}")
        return 0
    if a.report:
        print(report(build(spec)))
        return 0
    errs = check(Path(a.check), spec)
    for e in errs:
        print("FAIL", e)
    if errs:
        print(f"RESULTADO: REPROVADO ({len(errs)})")
        return 1
    doc = json.loads(Path(a.check).read_text(encoding="utf-8"))
    print(report(doc))
    print(f"RESULTADO: OK ({len(doc['data']['contrasts'])} contrastes; reivindicados com poder >= {TARGET})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
