"""prereg/ADDENDUM_PILOTS.html: o adendo do pré-registro, escrito ANTES da escala, com o que o yaml exige:
resultado dos 3 controles nas retidas (contagens por polaridade e justificativas), a linha R-CTRL aplicada e a
consequência pré-declarada para H9, cada emenda do E6 com motivo e as duas leituras, e o esforço medido (E7).
Só contagens: nenhum conteúdo de fixture retida entra aqui.
"""
from __future__ import annotations

import html

from . import common as C

CSS = """
:root{--bg:#fbfaf7;--fg:#1d1d1b;--mut:#5d5b55;--line:#d9d5cc;--ok:#1f6f43;--bad:#9b2c2c;--card:#ffffff}
@media (prefers-color-scheme: dark){:root{--bg:#161614;--fg:#eceae4;--mut:#a9a59b;--line:#3a3833;--ok:#7fd1a2;--bad:#f0a0a0;--card:#1f1f1c}}
body{background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,-apple-system,Segoe UI,sans-serif;margin:0;padding:24px 16px}
main{max-width:980px;margin:0 auto}h1{font-size:1.5rem;margin:.2rem 0}h2{font-size:1.15rem;margin-top:2rem;border-bottom:1px solid var(--line)}
table{border-collapse:collapse;width:100%;margin:.6rem 0;font-size:.92rem;display:block;overflow-x:auto}
th,td{border:1px solid var(--line);padding:4px 8px;text-align:left;vertical-align:top}th{background:var(--card)}
.mut{color:var(--mut)}.ok{color:var(--ok);font-weight:600}.bad{color:var(--bad);font-weight:600}code{font-size:.88em}
"""


def e(x) -> str:
    return html.escape(str(x))


def _ctrl_table(cnt: dict) -> str:
    rows = []
    for c in ("c1", "c2", "c3"):
        for p in ("positive", "negative", "unknown"):
            v = cnt.get(c, {}).get(p, {})
            rows.append(f"<tr><td>{c}</td><td>{p}</td><td>{v.get('correct', 0)}</td><td>{v.get('incorrect', 0)}</td>"
                        f"<td>{v.get('absent', 0)}</td></tr>")
    return ("<table><tr><th>controle</th><th>polaridade</th><th>corretas</th><th>incorretas</th><th>ausentes</th></tr>"
            + "".join(rows) + "</table>")


def _fam_table(fam: dict) -> str:
    rows = []
    for f, v in sorted(fam.items()):
        rows.append(f"<tr><td>{e(f)}</td><td>{v['n_cases']}</td>"
                    + "".join(f"<td>{v[k]['c3_only'] if 'c3_only' in v[k] else ''}/{v[k]['control_only']} "
                              f"(p={v[k]['p_one_sided']:.4g})</td>" for k in ("c3_vs_c1", "c3_vs_c2", "c2_vs_c1"))
                    + "</tr>")
    return ("<table><tr><th>família</th><th>n</th><th>c3×c1 (só c3 / só c1)</th><th>c3×c2</th><th>c2×c1</th></tr>"
            + "".join(rows) + "</table>")


def render(doc: dict, yaml_rule: dict) -> str:
    outcomes = {o["id"]: o for o in yaml_rule.get("outcomes", [])}
    parts = [f"<!doctype html><html lang='pt-BR'><head><meta charset='utf-8'>"
             f"<meta name='viewport' content='width=device-width,initial-scale=1'><title>Adendo dos pilotos</title>"
             f"<style>{CSS}</style></head><body><main>",
             "<h1>Adendo do pré-registro: saída dos pilotos</h1>",
             f"<p class='mut'>Escrito por PILOT-EXIT em {e(doc['written_at'])} (America/Recife), antes de qualquer "
             f"módulo de escala. Critérios: <code>prereg/pilot_exit.yaml</code> sha256 {e(doc['criteria_sha256'][:16])}; "
             f"tentativa {doc['attempt']} de {doc['attempts_max']}. Leitura dos pilotos: só contagem descritiva; a "
             f"decisão sobre H9 é tomada na partição de teste depois do UNSEAL.</p>",
             "<h2>1. Os 3 controles nas fixtures retidas</h2>"]
    for sl, c in sorted(doc["controls"].items()):
        parts.append(f"<h3>Fatia {e(sl)}</h3>")
        if not c.get("available"):
            parts.append(f"<p class='bad'>Controles indisponíveis: {e(c.get('why', ''))}</p>")
            continue
        parts.append(f"<p>Entrada idêntica nos 3 controles: <b>{'sim' if c['same_input'] else 'não'}</b> "
                     f"(sha da entrada: {e(', '.join(sorted(set(c['input_sha'].values())))[:80])}). "
                     f"Casos: {c['n_cases']}. Consequências de c3 com justifying_axioms separados de consulted_metadata: "
                     f"{c['justified']['c3_carried'] - c['justified']['c3_bad_justification']} de {c['justified']['c3_carried']}.</p>")
        parts.append(_ctrl_table(c["counts"]))
        parts.append(_fam_table(c["rule"]["families"]))
        parts.append(f"<p>Justificativa das contagens: correto = igual à resposta esperada do oráculo independente "
                     f"(retidas seladas do {e(c['oracle'])}); incorreto = consequência diferente dela; ausente = nenhuma "
                     f"consequência emitida. {e(c.get('note', ''))}</p>")
    parts.append("<h2>2. Linha R-CTRL aplicada e consequência pré-declarada para H9</h2>")
    for sl, c in sorted(doc["controls"].items()):
        r = c.get("rule") if c.get("available") else None
        if not r:
            parts.append(f"<p>Fatia {e(sl)}: sem controles, nenhuma linha aplicável (E5 reprova).</p>")
            continue
        main = outcomes.get(r["main"], {})
        parts.append(f"<p><b>Fatia {e(sl)}: {e(r['main'])}</b> — condição: {e(main.get('condition', ''))}. "
                     f"Por quê: {e(r['why'])}.<br>Consequência pré-declarada: {e(main.get('consequence', ''))}</p>")
        for x in r["extra"]:
            o = outcomes.get(x["id"], {})
            parts.append(f"<p><b>{e(x['id'])}</b> ({x['cases']} caso(s)): {e(o.get('consequence', ''))}</p>")
    parts.append(f"<p class='mut'>{e(yaml_rule.get('pilot_reading', ''))}</p>")
    parts.append("<h2>3. Emendas exigidas pelos pilotos (E6)</h2>"
                 "<table><tr><th>módulo</th><th>item</th><th>situação</th><th>leitura primária (congelada)</th>"
                 "<th>leitura emendada</th></tr>")
    for r in doc["amendments"]["requests"]:
        if r["status"] == "VERSIONED":
            a, b = "sem a mudança (versão anterior)", f"com a emenda: {r['versioned_by']}"
        else:
            a, b = "sem a mudança (vale esta)", "não existe: pedido aberto, sem emenda versionada"
        parts.append(f"<tr><td>{e(r['module'])}</td><td>{e(r['item'])}</td>"
                     f"<td class='{'ok' if r['status'] == 'VERSIONED' else 'bad'}'>{e(r['status'])}</td>"
                     f"<td>{e(a)}</td><td>{e(b)}</td></tr>")
    parts.append("</table><p class='mut'>Motivo de cada item: o texto do pedido em "
                 "<code>results/&lt;módulo&gt;/CONTRACT_CHANGE.txt</code>, citado pelo rótulo.</p>")
    ef = doc["effort"]
    parts.append("<h2>4. Esforço medido (E7)</h2><table><tr><th>módulo do piloto</th><th>medido (h)</th>"
                 "<th>plano (h)</th><th>retrabalho (h)</th></tr>")
    for m, r in sorted(ef["pilot_modules"].items()):
        parts.append(f"<tr><td>{e(m)}</td><td>{e(r.get('measured_h'))}</td><td>{e(r.get('plan_h', ''))}</td>"
                     f"<td>{e(r.get('rework_span_h', ''))}</td></tr>")
    parts.append(f"</table><p>Razão medida por classe: {e(ef['class_ratio'])}. Passos do E2E sem esforço medido: "
                 f"{e(ef['steps_without_effort'])}. Cronograma: plano {e(ef['schedule']['plan']['makespan_h'])} h, "
                 f"recalibrado {e(ef['schedule']['recalibrated']['makespan_h'])} h (teto de "
                 f"{e(ef['schedule']['concurrency_cap'])} agentes).</p>")
    parts.append("<h2>5. Resultado dos critérios</h2><table><tr><th>critério</th><th>resultado</th></tr>")
    for cid, v in sorted(doc["criteria"].items()):
        parts.append(f"<tr><td>{e(cid)} {e(v.get('name', ''))}</td>"
                     f"<td class='{'ok' if v['pass'] else 'bad'}'>{'passa' if v['pass'] else 'reprova'}</td></tr>")
    parts.append(f"</table><p><b>{e(doc['decision'])}</b></p></main></body></html>\n")
    return "\n".join(parts)
