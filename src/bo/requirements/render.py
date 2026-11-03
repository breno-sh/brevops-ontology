"""REQUIREMENTS.html: relatório legível gerado dos mesmos registros que vão para os JSONL (determinístico)."""

from __future__ import annotations

import html
from collections import Counter

from . import model, terms

CSS = """
:root{--bg:#fbfaf7;--fg:#1d1f22;--muted:#5d636b;--line:#dcd8cf;--card:#ffffff;--accent:#2b5d8a;
--pos:#1e6b3a;--neg:#9b2c2c;--unk:#7a5a00;--code:#f1eee7;}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){--bg:#15171a;--fg:#e6e3dd;--muted:#a3a8ad;
--line:#33373c;--card:#1d2024;--accent:#8db7de;--pos:#7fc79a;--neg:#ef9a9a;--unk:#e3c46b;--code:#24282d;}}
:root[data-theme="dark"]{--bg:#15171a;--fg:#e6e3dd;--muted:#a3a8ad;--line:#33373c;--card:#1d2024;--accent:#8db7de;
--pos:#7fc79a;--neg:#ef9a9a;--unk:#e3c46b;--code:#24282d;}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.55 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:1100px;margin:0 auto;padding:24px 16px 64px}
h1{font-size:1.6rem;margin:0 0 4px}h2{font-size:1.25rem;margin:36px 0 8px;border-bottom:1px solid var(--line);padding-bottom:4px}
h3{font-size:1.05rem;margin:22px 0 6px}
.meta{color:var(--muted);font-size:.9rem}
.kpis{display:flex;flex-wrap:wrap;gap:10px;margin:16px 0}
.kpi{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:8px 12px;min-width:120px}
.kpi b{display:block;font-size:1.3rem}
table{border-collapse:collapse;width:100%;margin:8px 0;font-size:.88rem}
th,td{border-bottom:1px solid var(--line);padding:6px 8px;vertical-align:top;text-align:left}
th{color:var(--muted);font-weight:600}
.wrap{overflow-x:auto}
code,.fx{font-family:ui-monospace,Menlo,Consolas,monospace;font-size:.8rem}
.fx{background:var(--code);border-radius:6px;padding:6px 8px;white-space:pre-wrap;word-break:break-word;margin:4px 0}
.positive{color:var(--pos);font-weight:600}.negative{color:var(--neg);font-weight:600}.unknown{color:var(--unk);font-weight:600}
details{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:8px 12px;margin:8px 0}
summary{cursor:pointer;font-weight:600}
.note{border-left:3px solid var(--accent);padding:4px 10px;color:var(--muted)}
"""


def e(s) -> str:
    return html.escape(str(s), quote=True)


def fixture_text(f: dict) -> str:
    lines = [f"{f['fixture_id']}: {f['summary']}"]
    ents = []
    for x in f["entities"]:
        k = "+".join([x["kind"]] + x.get("also_kinds", []))
        ents.append(f"{x['id']}:{k}")
    lines.append("  indivíduos: " + " ".join(ents))
    if f["relations"]:
        lines.append("  relações:   " + "; ".join(f"{r['from']} {r['rel']} {r['to']}" for r in f["relations"]))
    if f["attributes"]:
        lines.append("  atributos:  " + "; ".join(f"{a['of']}.{a['attr']}={a['value']}" for a in f["attributes"]))
    rd = f["read"]
    r = f"  leitura:    {rd['completeness']}"
    if rd["not_read"]:
        r += "; não lido: " + ", ".join(f"{n['of']}.{n['what']}" for n in rd["not_read"])
    if rd["withheld"]:
        r += "; retido: " + ", ".join(f"{n['of']}.{n['attr']}" for n in rd["withheld"])
    lines.append(r)
    return "\n".join(lines)


def _exp(x: dict) -> str:
    s = f"<b>{e(x['value'])}</b>"
    if x.get("code"):
        s += f" <code>{e(x['code'])}</code>"
    return s + f" — {e(x['why'])}"


def render(reqs: list, cmts: list, cqs: list, authored_at: str, content_sha: str) -> str:
    pol = Counter(c["polarity"] for c in cmts)
    fam = Counter(q["family"] for q in cqs)
    nfx = sum(len(c["fixtures"]) for c in cmts) + 3 * len(cqs)
    out = ["<!doctype html><html lang=\"pt-BR\"><head><meta charset=\"utf-8\">",
           "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">",
           "<title>Requisitos BrevOps</title>", f"<style>{CSS}</style></head><body><main>",
           "<h1>Requisitos, compromissos semânticos e CQs</h1>",
           f"<p class=\"meta\">Módulo REQUIREMENTS · contrato C24 {model.CONTRACT_VERSION} · conteúdo escrito em "
           f"{e(authored_at)} (America/Recife), antes de qualquer indução · sha256 do conteúdo <code>{e(content_sha[:16])}</code></p>",
           "<div class=\"kpis\">"]
    for label, v in [("requisitos", len(reqs)), ("compromissos", len(cmts)), ("positivos", pol["positive"]),
                     ("negativos", pol["negative"]), ("desconhecidos", pol["unknown"]), ("CQs", len(cqs)),
                     ("fixtures", nfx)]:
        out.append(f"<div class=\"kpi\"><b>{v}</b>{e(label)}</div>")
    out.append("</div>")
    out.append(
        "<p class=\"note\">Tudo aqui está em vocabulário independente de provedor e da futura ontologia: os tipos, "
        "relações e atributos das fixtures são rótulos de trabalho (seção Vocabulário), não IRIs. Provedores só "
        "aparecem no aterramento dos compromissos, como dica de instanciação para o CQFIX e os oráculos, sempre "
        "com estado de evidência UNRESOLVED até o SERVICE-EVIDENCE confirmar. A ausência de termo de provedor no "
        "texto é conferida por um gate de higiene, que não prova nada sobre o significado.</p>")
    out.append("<h2>Como ler</h2><ul>"
               "<li><span class=\"positive\">positivo</span>: a ontologia tem de aceitar ou inferir "
               "(<code>entails</code>, <code>count</code>, <code>invariant</code>).</li>"
               "<li><span class=\"negative\">negativo</span>: contraexemplo que tem de continuar rejeitado "
               "(<code>rejects</code>: inconsistência, violação de forma ou tradução bloqueada; "
               "<code>not_entails</code>: a conclusão errada não pode sair).</li>"
               "<li><span class=\"unknown\">desconhecido</span>: falta informação e a resposta certa é UNKNOWN, "
               "às vezes com código (OUT_OF_PIN, CONDITION_INDETERMINATE, UNPROVEN...).</li>"
               "<li><code>code</code> junto de REJECTED é o motivo esperado da rejeição (INCONSISTENT, "
               "SHACL_VIOLATION) ou o código do bloqueio correto (UNKNOWN_INPUT, RELATED_ONLY); junto de "
               "UNKNOWN, o código que acompanha o desconhecido.</li>"
               "<li>Resposta definida (positivo, negativo, CQ conforme e não conforme) exige leitura completa "
               "declarada; toda fixture de UNKNOWN declara o que não foi lido.</li>"
               "<li>CQ: \"conforme\" é a fixture em que o critério vale; \"não conforme\", a em que não vale; "
               "\"incompleta\", a em que falta informação (resposta UNKNOWN).</li></ul>")
    # requisitos
    out.append("<h2>Requisitos</h2><div class=\"wrap\"><table><tr><th>id</th><th>área</th><th>requisito</th>"
               "<th>por quê</th><th>responde</th></tr>")
    for r in reqs:
        out.append(f"<tr><td><code>{e(r['req_id'])}</code></td><td>{e(model.AREAS[r['area']])}</td>"
                   f"<td>{e(r['statement'])}</td><td>{e(r['rationale'])}</td><td>{e(', '.join(r['answers']))}</td></tr>")
    out.append("</table></div>")
    # compromissos
    out.append("<h2>Compromissos semânticos</h2>")
    for case in model.ALL_CASES:
        cs = [c for c in cmts if c["case"] == case]
        cnt = Counter(c["polarity"] for c in cs)
        title = model.CASES.get(case, "outros compromissos: taxonomia, configuração x observação, ausência, "
                                      "identidade, ciclo de vida, perda, provedor novo")
        out.append(f"<h3>{e(case)} — {e(title)}</h3><p class=\"meta\">{cnt['positive']} positivos, "
                   f"{cnt['negative']} negativos, {cnt['unknown']} desconhecidos</p>")
        for c in cs:
            axes = f" · eixos de topo: {e(', '.join(c['upper_axes']))}" if c["upper_axes"] else ""
            out.append(f"<details><summary><code>{e(c['commitment_id'])}</code> "
                       f"<span class=\"{c['polarity']}\">{e(c['polarity'])}</span> "
                       f"<code>{e(c['check']['kind'])}</code> — {e(c['statement'])}</summary>")
            out.append(f"<p><b>Checagem:</b> <code>{e(c['check']['assertion'])}</code></p>")
            out.append(f"<p><b>Resposta esperada:</b> {_exp(c['expected_answer'])}</p>")
            out.append(f"<p class=\"meta\">protege: {e(c['protects'])} · camada: {e(c['layer'])}{axes} · "
                       f"requisitos: {e(', '.join(c['requirement_ids']))} · responde: {e(', '.join(c['answers']))} · "
                       f"consumidores: {e(', '.join(c['consumers']))}</p>")
            for f in c["fixtures"]:
                out.append(f"<div class=\"fx\">{e(fixture_text(f))}</div>")
            if c["provider_grounding"]:
                out.append("<table><tr><th>provedor</th><th>aterramento (a confirmar)</th><th>estado</th></tr>")
                for g in c["provider_grounding"]:
                    out.append(f"<tr><td><code>{e(g['provider'])}</code></td><td>{e(g['note'])}</td>"
                               f"<td><code>{e(g['evidence_state'])}</code></td></tr>")
                out.append("</table>")
            out.append("</details>")
    # CQs
    out.append("<h2>Perguntas de competência além do CIS</h2><p class=\"meta\">"
               + " · ".join(f"{e(v)}: {fam.get(k, 0)}" for k, v in model.FAMILIES_BEYOND_CIS.items())
               + " · as CQs CIS vêm do CQSRC</p>")
    for k, v in model.FAMILIES_BEYOND_CIS.items():
        out.append(f"<h3>{e(v)}</h3>")
        for q in [q for q in cqs if q["family"] == k]:
            out.append(f"<details><summary><code>{e(q['cq_id'])}</code> {e(q['question'])}</summary>")
            out.append(f"<p><b>Critério:</b> {e(q['criterion'])} · <b>forma:</b> {e(q['answer_form'])}"
                       + (" · <b>usa negação</b> (só sob leitura completa)" if q['closed_world']['uses_negation'] else "")
                       + "</p>")
            out.append(f"<p><b>O que a resposta exige:</b> {e(q['reasoning_needs'])}</p>")
            for role, label in (("conforming", "conforme"), ("nonconforming", "não conforme"), ("incomplete", "incompleta")):
                s = q["fixtures"][role]
                out.append(f"<p><b>{label}:</b> {_exp(s['expected'])}</p><div class=\"fx\">{e(fixture_text(s['fixture']))}</div>")
            out.append(f"<p class=\"meta\">requisitos: {e(', '.join(q['requirement_ids']))} · compromissos: "
                       f"{e(', '.join(q['commitment_ids']) or '-')} · casos: {e(', '.join(q['cases']) or '-')} · "
                       f"aplicabilidade: {e(q['applicability'])}</p></details>")
    # vocabulário
    out.append("<h2>Vocabulário de requisitos</h2><p class=\"meta\">Rótulos de trabalho das fixtures; não são a "
               "ontologia e não obrigam o NAMING.</p>")
    for title, d in (("tipos", terms.KINDS), ("relações", terms.RELATIONS), ("atributos", terms.ATTRIBUTES),
                     ("o que pode faltar (não lido)", terms.NOT_READ_WHAT)):
        out.append(f"<details><summary>{e(title)} ({len(d)})</summary><table>")
        for k in sorted(d):
            out.append(f"<tr><td><code>{e(k)}</code></td><td>{e(d[k])}</td></tr>")
        out.append("</table></details>")
    out.append("<h2>Limites</h2><ul>"
               "<li>As respostas esperadas são as do desenho, escritas antes da indução; os fatos de provedor no "
               "aterramento são hipóteses a confirmar pelo SERVICE-EVIDENCE, não gabarito.</li>"
               "<li>Fixtures são situações abstratas; o CQFIX as instancia por provedor e marca NOT_APPLICABLE só com "
               "evidência. Onde o provedor não tem a estrutura, a CQ não vira zero.</li>"
               "<li>O validador do contrato (bo.contracts.validate) é do CONTRACTS, que depende deste módulo; até ele "
               "existir, vale o validador do produtor (bo.requirements.validate) com o schema proposto em "
               "results/REQUIREMENTS/C24_proposta/.</li></ul>")
    out.append("</main></body></html>\n")
    return "\n".join(out)
