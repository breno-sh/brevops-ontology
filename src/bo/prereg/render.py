"""Renderiza prereg/PREREG.html a partir do conteúdo e dos arquivos irmãos já gerados."""

from __future__ import annotations

import html

from . import content as C

CSS = """
:root{--bg:#fbfaf7;--fg:#1d1d1b;--muted:#5d5b55;--line:#dcd8cf;--card:#ffffff;--accent:#9a4a12;--ok:#2f6b3a;
--warn:#8a5a00;--code:#f2efe8}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){--bg:#161614;--fg:#ecebe6;--muted:#a9a69d;
--line:#3a3833;--card:#1f1e1b;--accent:#e39a5c;--ok:#7cc48a;--warn:#e0b45c;--code:#2a2925}}
:root[data-theme="dark"]{--bg:#161614;--fg:#ecebe6;--muted:#a9a69d;--line:#3a3833;--card:#1f1e1b;--accent:#e39a5c;
--ok:#7cc48a;--warn:#e0b45c;--code:#2a2925}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.55 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:1180px;margin:0 auto;padding:24px 16px 64px}
h1{font-size:1.7rem;margin:.2rem 0 .4rem}h2{font-size:1.25rem;margin:2.2rem 0 .6rem;border-bottom:1px solid var(--line);
padding-bottom:.3rem}h3{font-size:1.05rem;margin:1.4rem 0 .4rem}
p,li{max-width:80ch}.muted{color:var(--muted)}a{color:var(--accent)}
code{background:var(--code);padding:0 .25em;border-radius:3px;font-size:.92em;word-break:break-word}
.wrap{overflow-x:auto;margin:.6rem 0 1rem;border:1px solid var(--line);border-radius:6px;background:var(--card)}
table{border-collapse:collapse;width:100%;font-size:.88rem}
th,td{border-bottom:1px solid var(--line);padding:.42rem .55rem;text-align:left;vertical-align:top}
th{background:var(--code);font-weight:600;position:sticky;top:0}
.tag{display:inline-block;padding:0 .4em;border-radius:3px;border:1px solid var(--line);font-size:.8em;white-space:nowrap}
.claimed{color:var(--ok);border-color:var(--ok)}.cond{color:var(--warn);border-color:var(--warn)}
.note{border-left:3px solid var(--accent);background:var(--card);padding:.6rem .9rem;margin:1rem 0}
nav ul{columns:3;max-width:none;padding-left:1.1rem}@media (max-width:720px){nav ul{columns:1}}
.kv{display:grid;grid-template-columns:max-content 1fr;gap:.2rem 1rem}
"""


def e(s) -> str:
    return html.escape(str(s), quote=True)


def table(head: list[str], rows: list[list], raw_cols: set[int] | None = None) -> str:
    raw_cols = raw_cols or set()
    out = ['<div class="wrap"><table><thead><tr>' + "".join(f"<th>{e(h)}</th>" for h in head) + "</tr></thead><tbody>"]
    for r in rows:
        out.append("<tr>" + "".join(f"<td>{c if i in raw_cols else e(c)}</td>" for i, c in enumerate(r)) + "</tr>")
    out.append("</tbody></table></div>")
    return "\n".join(out)


def pt(x) -> str:
    """Número no formato brasileiro (vírgula decimal)."""
    if x is None:
        return "—"
    if isinstance(x, float):
        s = f"{x:.4f}".rstrip("0").rstrip(".")
        return s.replace(".", ",")
    return str(x)


def status_tag(st: str) -> str:
    cls = {"claimed": "claimed", "claimed_conditional": "cond"}.get(st, "")
    return f'<span class="tag {cls}">{e(st)}</span>'


def render(ctx: dict) -> str:
    power = ctx["power"]
    d = power["data"]
    S = []
    S.append(f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(C.TITLE)}</title><style>{CSS}</style></head><body><main>
<p class="muted">BrevOps Ontology · módulo PREREG · versão {e(C.VERSION)} · conteúdo escrito em {e(C.AUTHORED_AT)}
(America/Recife) · gerado por <code>python -I -m bo.prereg.build</code></p>
<h1>Pré-registro v3: estimandos, unidades, contrastes, poder, pilotos e congelamentos</h1>
<p>Este documento fixa, antes de qualquer dado do estudo, o que será medido, sobre que unidade, com que
denominador, como o desconhecido entra, que contrastes serão reivindicados e com que poder, como os pilotos
saem, como o resultado dos três controles de raciocínio será lido, o desenho de leave-one-provider-out, os
pontos de congelamento e as regras de emenda e de invalidação. Quando ele é escrito não existe partição de
teste, universo, mapeamento nem deploy. Venue fica fora.</p>
<div class="note"><b>Âncora externa.</b> Registro OSF: <b>{e(ctx['osf'])}</b> (D4, feito pelo Breno; o ID vai em
<code>results/PREREG/OSF_ID.txt</code>). Este arquivo e os irmãos entram no FREEZE0 com carimbo OpenTimestamps.</div>
""")
    S.append("<h3>Arquivos irmãos (sha256 na geração)</h3>")
    S.append(table(["arquivo", "contrato", "sha256"], [[k, v[0], v[1]] for k, v in ctx["hashes"].items()]))
    nav = [("nota-renomeacao", "Nota de renomeação"), ("escada", "1. Escada de eixos"),
           ("metricas", "2. Métricas e estimandos"), ("leituras", "3. Leituras, denominador e quantificador"),
           ("desconhecido", "4. Política do desconhecido"), ("unidades", "5. Unidades e reamostragem"),
           ("contrastes", "6. Hipóteses e contrastes"), ("poder", "7. Poder"), ("pilotos", "8. Pilotos e controles"),
           ("lopo", "9. Leave-one-provider-out e hold-outs"), ("sondas", "10. Sondas"),
           ("comparacao", "11. Comparação justa"), ("sementes", "12. Sementes"),
           ("congelamentos", "13. Congelamentos"), ("emendas", "14. Emendas e invalidação"),
           ("objecoes", "15. Objeções respondidas")]
    S.append("<nav><ul>" + "".join(f'<li><a href="#{a}">{e(t)}</a></li>' for a, t in nav) + "</ul></nav>")

    # nota de renomeação (único lugar do termo antigo)
    S.append(f'<section id="nota-renomeacao"><h2>Nota de renomeação</h2><p>{e(C.RENAMING_NOTE)}</p></section>')

    S.append('<h2 id="escada">1. Escada de eixos</h2><p>Cinco eixos medidos separadamente; nenhum é inferido do '
             'outro. A cobertura operacional é a medida principal; persistência e comportamento são eixos '
             'próprios, nunca promovidos a "mesmo significado".</p>')
    S.append(table(["eixo (C15)", "nome", "o que mede"], [[a, n, t] for a, n, t in C.LADDER]))

    S.append('<h2 id="metricas">2. Métricas e estimandos</h2><p>Texto normativo em <code>prereg/metrics_spec.yaml'
             '</code> (C15 3.0.0). A definição de cada métrica carrega as seis cláusulas do estimando; o gate '
             '<code>python -I -m bo.prereg.estimands</code> confere todas. A principal é <b>M-OPCOV-DEC</b>.</p>')
    rows = []
    for m in C.METRICS:
        rows.append([f"<b>{e(m['metric_id'])}</b>" + (" <span class=\"tag claimed\">principal</span>" if m["primary"] else ""),
                     e(m["name"]), e(f"{m['axis']} · {m['reading']} · {m['quantifier']}"), e(m["population"]),
                     e(m["direction"]), e(m["denominator"]), e(m["unknown"]),
                     e(f"{m['weights']} · {m['uncertainty']} · {m['priority']}")])
    S.append(table(["métrica", "nome", "eixo · leitura · quantificador", "população", "direção", "denominador",
                    "desconhecido", "pesos · incerteza · prioridade"], rows, raw_cols=set(range(8))))
    S.append("<h3>Estimandos que não são métrica do C15</h3>")
    S.append(table(["estimando", "definição", "população", "direção", "unidade", "denominador", "desconhecido",
                    "contraste"],
                   [[x["estimand_id"], x["definition"], x["population"], x["direction"], x["unit"],
                     x["denominator"], x["unknown"], x["contrast"] or "auditoria"] for x in C.OTHER_ESTIMANDS]))

    S.append('<h2 id="leituras">3. Leituras, denominador invariante e quantificador</h2>')
    S.append("<p>Quatro leituras da cobertura operacional, todas calculadas rodando o tradutor: por campo, por "
             "decisão (principal), por grafo e por unidade implantável completa. NAME e TAG têm leitura própria "
             "(M-OPCOV-NAMETAG) e saem das outras. O denominador é fixado no lado de origem, pela regra de "
             "inclusão, antes de rodar o tradutor: o desfecho nunca o altera. Um documento JSON de política conta "
             "por decisão, não por linha (uma decisão por declaração normalizada efeito, principal, ação, "
             "recurso, condição); reserializar, reordenar chaves ou partir listas não muda o número, e o "
             "METRICSLIB testa isso.</p>")
    S.append(table(["unidade", "leitura C15", "definição"], [[a, b, c] for a, b, c in C.UNITS[:4]]))
    S.append("<h3>Quantificador declarado para broad/narrow</h3>")
    S.append(table(["quantificador", "regra"], [[a, b] for a, b in C.QUANTIFIER_RULES]))

    S.append('<h2 id="desconhecido">4. Política de NOT_READABLE, INFRA_ERROR e UNKNOWN</h2>')
    S.append("<p>Todo valor de toda enumeração que decide desfecho cai em exatamente uma classe; o gate confere "
             "esta tabela contra o C00. Limite inferior: todo desconhecido como falha; limite superior: como "
             "sucesso.</p>")
    S.append(table(["classe", "efeito"], [[k, v] for k, v in C.BOUND_CLASSES.items()]))
    rows = []
    for enum, mp in C.BOUND_POLICY.items():
        for code, cls in mp.items():
            rows.append([enum, code, cls])
    S.append(table(["enumeração", "valor", "classe"], rows))
    S.append(table(["caso", "regra"], [[a, b] for a, b in C.UNKNOWN_RULES]))

    S.append('<h2 id="unidades">5. Unidades de análise, reamostragem e efeitos fixos</h2>')
    S.append(table(["unidade", "nome interno", "definição"], [[a, b, c] for a, b, c in C.UNITS]))
    S.append("<ul>" + "".join(f"<li>{e(x)}</li>" for x in C.RESAMPLING) + "</ul>")

    S.append('<h2 id="contrastes">6. Hipóteses e contrastes pré-registrados</h2>')
    S.append("<p>Só estes contrastes são confirmatórios; qualquer outro é exploratório e rotulado assim. Cada "
             "hipótese é uma alegação separada, com a própria regra de multiplicidade; não há ajuste entre "
             "hipóteses.</p>")
    rows = []
    for c in d["contrasts"]:
        r = c["result"]
        n = r.get("n_units", r.get("n_cases_per_family", r.get("events", "—")))
        rows.append([f"<b>{e(c['contrast_id'])}</b>", e(c["hypothesis"]), e(c["priority"]), e(c["claim"]),
                     e(c["test"]), e(c["multiplicity"]), e(", ".join(c["metrics"] + c.get("estimands", []))),
                     status_tag(c["status"]), e(pt(r.get("overall_power"))), e(n), e(r.get("n_families", "—"))])
    S.append(table(["contraste", "hipótese", "prioridade", "alegação", "teste", "multiplicidade", "métricas",
                    "status", "poder", "n", "famílias"], rows, raw_cols=set(range(11))))

    S.append('<h2 id="poder">7. Poder</h2>')
    cl = d["cluster_model"]
    S.append(f"""<p>Cálculo em <code>prereg/power.py</code> (autocontido), resultado em <code>prereg/power.json</code>
(C15 3.0.0, documento de planejamento: n = 0, est nulo, limites 0..1). Alfa {pt(d['alpha'])}, poder alvo
{pt(d['target_power'])}. O poder é o do teste que a análise usa: Wald com erro-padrão sob a alternativa e
crítico t com graus de liberdade pelo número de famílias (aproximação da t não central), conferido por
simulação beta-binomial em <code>tests/prereg</code> (nunca otimista além de 0,03 no regime dos n daqui). Correlação aninhada decisão ⊂ grafo ⊂ repositório ⊂ família:
<code>{e(d['design_effect_formula'])}</code>, com rho grafo {pt(cl['rho']['graph'])}, repositório
{pt(cl['rho']['repository'])}, família {pt(cl['rho']['family'])} e m = {cl['m']['graph']}/{cl['m']['repository']}/{cl['m']['family']}
decisões por grafo/repositório/família numa direção: DE = {pt(d['design_effect_census'])} no censo da partição de
teste e {pt(d['design_effect_deploy'])} na amostra de deploy (inclui pesos desiguais). Fonte: {e(cl['source'])}.</p>
<div class="note"><b>Reestimação cega.</b> {e(d['reestimation'])}</div>""")
    rows = []
    for c in d["contrasts"]:
        r = c["result"]
        if r.get("kind") == "descriptive":
            rows.append([c["contrast_id"], "descritivo", "—", "—", "—", "—", c["planning_source"]])
            continue
        if r["kind"] == "exact":
            rows.append([c["contrast_id"], "McNemar exato", pt(r["unit_power_target"]),
                         f"{r['n_cases_per_family']} casos por família",
                         f"α por teste {pt(r['alpha_per_test'])}",
                         f"poder com {r['fixture_scale_n']} por família: {pt(r['power_at_fixture_scale'])}",
                         c["planning_source"]])
            continue
        if r["kind"] == "events":
            rows.append([c["contrast_id"], "sobrevivência", pt(r["unit_power_target"]), f"{r['events']} eventos",
                         "—", "—", c["planning_source"]])
            continue
        extra = f"limite de viabilidade {r['cap_units']}: poder {pt(r['unit_power_at_cap'])}" if "cap_units" in r else c["feasibility"]["rule"]
        rows.append([c["contrast_id"], c["model"], pt(r["unit_power_target"]),
                     f"{r['n_units']} unidades ({r['n_effective']} efetivas)", f"{r['n_families']} famílias",
                     extra, c["planning_source"]])
    S.append(table(["contraste", "modelo", "poder alvo por unidade", "n necessário", "clusters", "viabilidade",
                    "valores de planejamento"], rows))
    sens = []
    for c in d["contrasts"]:
        if not c["sensitivity"]:
            continue
        rng = [x["n_units"] for x in c["sensitivity"]]
        sens.append([c["contrast_id"], f"{min(rng)}–{max(rng)}",
                     f"{min(x['n_families'] for x in c['sensitivity'])}–{max(x['n_families'] for x in c['sensitivity'])}"])
    S.append("<h3>Sensibilidade (rho × 0,5/1/1,5; m × 0,5/1/2)</h3>")
    S.append(table(["contraste", "n necessário (faixa)", "famílias (faixa)"], sens))
    h9 = next(c for c in d["contrasts"] if c["contrast_id"] == "C-H9")["result"]
    S.append(f"""<div class="note"><b>Achado do cálculo, antes de qualquer dado.</b> Com a escala das fixtures
(12 casos por família de consequências) o poder de H9 é {pt(h9['power_at_fixture_scale'])}: as fixtures dos pilotos
e das CQs não decidem H9. São precisos {h9['n_cases_per_family']} casos fora da calibração por família, com resposta
esperada independente; abaixo disso H9 sai inconclusiva (R-CTRL-4), nunca nula. Do mesmo modo, as direções com OCI
podem não ter famílias suficientes no teste: a contagem do SPLIT decide, pela regra de reestimação, sem olhar
desfecho.</div>""")

    S.append('<h2 id="pilotos">8. Critérios de saída dos pilotos e regra dos três controles</h2>')
    pe = ctx["pilot_exit"]
    S.append(f"<p>Texto normativo em <code>prereg/pilot_exit.yaml</code>. Fatias {e(', '.join(pe['slices']))}; "
             f"{pe['directions']} direções; no máximo {pe['attempts_max']} tentativas. Limiar de cobertura: "
             f"{e(pe['coverage_threshold'])}. {e(pe['runner'])}.</p>")
    S.append(table(["critério", "nome", "exigência", "medidas", "regra de aprovação", "se falhar"],
                   [[c["id"], c["name"], c["requirement"], "; ".join(c["measures"]), c["pass_rule"], c["on_fail"]]
                    for c in pe["criteria"]]))
    cr = pe["reasoning_controls_rule"]
    S.append("<h3>Regra pré-declarada para o resultado dos 3 controles</h3><ul>" +
             "".join(f"<li>{e(x)}</li>" for x in cr["invariants"]) + "</ul>")
    S.append(table(["linha", "condição", "consequência"], [[o["id"], o["condition"], o["consequence"]] for o in cr["outcomes"]]))
    S.append(f"<p>{e(cr['pilot_reading'])}</p>")

    S.append('<h2 id="lopo">9. Leave-one-provider-out e hold-outs</h2>')
    S.append(f"<p><b>Provedor deixado de fora:</b> {e(C.LOPO['left_out'])}. {e(C.LOPO['why_oci'])}.</p><ol>" +
             "".join(f"<li>{e(x)}</li>" for x in C.LOPO["steps"]) + "</ol>")
    S.append(f"<p><b>Critério:</b> {e(C.LOPO['criterion'])}. <b>Contaminação:</b> {e(C.LOPO['contamination'])}.</p>")
    S.append(table(["hold-out", "como"], [[a, b] for a, b in C.LOPO["holdouts"]]))

    S.append('<h2 id="sondas">10. Sondas</h2>')
    pr = ctx["probe_types"]
    S.append(f"<p>Texto normativo em <code>prereg/probe_types.yaml</code> (C22 3.0.0), protocolo "
             f"{e(pr['protocol_version'])}. Limite de custo por execução de um par (dois lados), em dólares, com "
             "armazenamento, tráfego e requisições, dentro do limite total D3. O suporte por provedor fica "
             "<code>unknown</code> até o PROBEKIT validá-lo com o SERVICE-EVIDENCE, antes do sorteio.</p>")
    S.append(table(["tipo", "pré-condições", "controle negativo", "repetições", "tolerância", "polling", "janela",
                    "margem sobre o TTL", "limite de custo"],
                   [[p["probe_type"], "; ".join(p["preconditions"]),
                     f"{p['negative_control']['description']} → {p['negative_control']['expected']}",
                     p["repetitions"], f"{p['tolerance']['kind']} {pt(float(p['tolerance']['value']))}",
                     f"{p['polling']['interval']} até {p['polling']['max_wait']}", p["window"]["duration"],
                     p["window"]["margin_over_ttl"], f"{pt(float(p['cost_limit']['amount']))} dólar(es)"]
                    for p in pr["probe_types"]]))
    S.append("<ul>" + "".join(f"<li>{e(x)}</li>" for x in C.PROBE_RULES) + "</ul>")

    S.append('<h2 id="comparacao">11. Comparação justa com os trabalhos anteriores</h2>')
    h2h = ctx["h2h"]
    S.append(f"<p>Texto normativo em <code>prereg/h2h_fairness.yaml</code> (C28 1.0.0). Orçamento "
             f"{pt(float(h2h['budget']['per_comparator']))} hora-agente por comparador. {e(C.H2H['budget_note'])} O "
             "<code>universe_ref</code> aponta para a definição pré-registrada do frame (metrics_spec.yaml), porque "
             "o universo U ainda não existe; o BENCH-CONTRACT publica a sua versão com o universe.json real e "
             "tem de manter estas regras.</p>")
    S.append("<ul>" + "".join(f"<li>{e(x)}</li>" for x in h2h["rules"]) + "</ul>")
    S.append(f"<p class=\"muted\">Comparadores: {e(', '.join(c['comparator_id'] for c in h2h['comparators']))}.</p>")

    S.append('<h2 id="sementes">12. Sementes</h2>')
    S.append(f"<p>{e(C.SEED_RULE)} Lista em <code>prereg/SEEDS.txt</code>.</p>")
    S.append(table(["nome", "semente", "consumidor", "para quê"], ctx["seeds"]))

    S.append('<h2 id="congelamentos">13. Pontos de congelamento</h2>')
    S.append(table(["ponto", "quando", "o que congela", "produtor", "dono do comprovante", "comprovante", "âncora"],
                   [[n, w, what, prod, C.FREEZE_OWNER, f"$BO_REPO/freeze/{n}/freeze_receipt.json", anc]
                    for n, w, what, prod, anc in C.FREEZES]))
    S.append("<ul>" + "".join(f"<li>{e(x)}</li>" for x in C.FREEZE_RULES) + "</ul>")

    S.append('<h2 id="emendas">14. Regra de emenda e de invalidação</h2><h3>Emenda</h3><ul>' +
             "".join(f"<li>{e(x)}</li>" for x in C.AMENDMENT_RULES) + "</ul><h3>Invalidação</h3><ul>" +
             "".join(f"<li>{e(x)}</li>" for x in C.INVALIDATION_RULES) + "</ul>")

    S.append('<h2 id="objecoes">15. Objeções respondidas</h2>')
    S.append(table(["objeção", "o que era", "resposta aqui", "seção"],
                   [[o, w, r, f'<a href="#{"nota-renomeacao" if a == "renomeacao" else a}">{e(a)}</a>']
                    for o, w, r, a in C.OBJECTIONS], raw_cols={3}))
    S.append("<h3>Fontes lidas</h3>")
    S.append(table(["fonte", "uso"], [[a, b] for a, b in C.SOURCES_READ]))
    S.append(f'<p class="muted">Fim do pré-registro. Conteúdo sha256 {e(ctx["content_sha"][:16])}…; '
             f"escrito em {e(C.AUTHORED_AT)} (America/Recife).</p></main></body></html>\n")
    return "\n".join(S)
