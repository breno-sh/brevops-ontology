"""Gerador do LIT: escreve, a partir de data.py e do livro de resolução,

  lit/related.bib  lit/positioning_matrix.csv  lit/RELATED_WORK.html
  results/LIT/cocoon_disambiguation.json  results/LIT/MANIFEST.sha256

  python -I -m bo.lit.build            escreve
  python -I -m bo.lit.build --check    regenera em memória e reprova se algo diferir (regeneração idêntica)

A saída é determinística: o carimbo vem de data.EDITED_AT e do livro (resolved_at), não do relógio.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import html
import io
import json
from pathlib import Path

from bo.repo import core

from . import bib, data, ids, verify

OUT_BIB = "lit/related.bib"
OUT_CSV = "lit/positioning_matrix.csv"
OUT_HTML = "lit/RELATED_WORK.html"
OUT_COCOON = "results/LIT/cocoon_disambiguation.json"
OUT_MANIFEST = "results/LIT/MANIFEST.sha256"


def esc(s) -> str:
    return html.escape(str(s), quote=True)


def entries_by_key() -> dict:
    return {e["key"]: e for e in data.ENTRIES}


def fields(key: str) -> dict:
    return dict(entries_by_key()[key]["fields"])


def render_csv() -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=data.COLUMNS, lineterminator="\n", quoting=csv.QUOTE_MINIMAL)
    w.writeheader()
    for r in data.ROWS:
        missing = set(data.COLUMNS) - set(r)
        extra = set(r) - set(data.COLUMNS)
        if missing or extra:
            raise core.BoError(f"linha {r.get('row_id')}: colunas faltando {sorted(missing)} sobrando {sorted(extra)}")
        w.writerow(r)
    return buf.getvalue()


def render_cocoon() -> str:
    out = []
    for c in data.COCOON["entries"]:
        f = fields(c["bibkey"])
        out.append({
            "bibkey": c["bibkey"], "authors": bib.authors(f["author"]), "first_author_given": c["first_author_given"],
            "year": f["year"], "venue": f["booktitle"], "venue_short": c["venue_short"], "pages": f.get("pages"),
            "doi": f["doi"], "title": f["title"], "cited_by": c["cited_by"],
            "metadata_note": f.get("crossref_mismatch", ""),
        })
    doc = {
        "schema": "bo.lit.cocoon_disambiguation/1", "module": "LIT", "edited_at": data.EDITED_AT,
        "question": "O PDF de Kalinin e Skvortsov e a revisão R4 citam entradas distintas para o CoCoOn.",
        "resolution": ("São duas obras distintas com o mesmo nome de ontologia: a versão de 2012 "
                       "(CollaborateCom, Miranda Zhang et al., descoberta de serviços IaaS) é a que Kalinin e "
                       "Skvortsov citam; a versão de 2019 (ISWC Resources, Qian Zhang, Haller e Wang, comparação "
                       "de preço e desempenho de IaaS) é a que a R4 cita. As duas entram no related.bib."),
        "entries": out,
    }
    return json.dumps(doc, ensure_ascii=False, indent=1) + "\n"


CSS = """
:root{--bg:#fbfaf7;--fg:#1d1f21;--muted:#5b616b;--line:#dcd8cf;--accent:#1f5f8b;--warn:#8a4b00;--crit:#9b1c1c;--chip:#efece6}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){--bg:#15171a;--fg:#e7e5e0;--muted:#a3a7ad;--line:#34383e;--accent:#7cb7e0;--warn:#e0a35c;--crit:#ef8b8b;--chip:#24272c}}
:root[data-theme="dark"]{--bg:#15171a;--fg:#e7e5e0;--muted:#a3a7ad;--line:#34383e;--accent:#7cb7e0;--warn:#e0a35c;--crit:#ef8b8b;--chip:#24272c}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.55 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:1100px;margin:0 auto;padding:24px 16px 64px}h1{font-size:1.6rem;margin:.2em 0}h2{font-size:1.2rem;margin-top:2.2em;border-bottom:1px solid var(--line);padding-bottom:.2em}
.meta{color:var(--muted);font-size:.9rem}a{color:var(--accent)}code{font-size:.88em;background:var(--chip);padding:0 .25em;border-radius:3px;word-break:break-all}
.tbl{overflow-x:auto;border:1px solid var(--line);border-radius:6px}table{border-collapse:collapse;width:100%;font-size:.86rem}
th,td{text-align:left;vertical-align:top;padding:6px 8px;border-bottom:1px solid var(--line)}th{background:var(--chip);position:sticky;top:0}
.critico{color:var(--crit);font-weight:600}.alto{color:var(--warn);font-weight:600}.chip{display:inline-block;background:var(--chip);border-radius:10px;padding:0 .5em;font-size:.8rem;margin:1px}
ul.tight li{margin:.25em 0}
"""


def ledger_summary(ledger: dict) -> list[tuple]:
    rows = []
    entries = bib.parse(bib.render(data.ENTRIES, data.EDITED_AT))
    for e in entries:
        vd = verify.check_entry(e, ledger)
        rows.append((e["key"], "ok" if vd.ok else "FALHA", vd.basis or "-", vd.verified_ids))
    return rows


def render_html(ledger: dict) -> str:
    k = fields(data.KALININ["bibkey"])
    rows = data.ROWS
    by_threat = {t: [r["work"] for r in rows if r["threat_to_novelty"] == t] for t in ("critico", "alto")}
    h = []
    a = h.append
    a('<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">'
      '<meta name="viewport" content="width=device-width, initial-scale=1">'
      '<title>Trabalhos relacionados BrevOps</title><style>' + CSS + '</style></head><body><main>')
    a('<h1>Trabalhos relacionados e posicionamento</h1>')
    a(f'<p class="meta">BrevOps Ontology, módulo LIT. Conteúdo editado em {esc(data.EDITED_AT)} (America/Recife); '
      f'livro de identificadores gravado em {esc(ledger.get("resolved_at", "?"))} (cada identificador traz a própria '
      'hora de conferência em results/LIT/id_resolution.json). Gerado por '
      '<code>python -I -m bo.lit.build</code>; fontes em <code>lit/related.bib</code> e '
      '<code>lit/positioning_matrix.csv</code>.</p>')

    a('<h2 id="resumo">Em poucas linhas</h2><ul class="tight">')
    a('<li>Construir uma ontologia a partir de schemas Terraform de vários provedores já foi feito e publicado '
      '(Kalinin e Skvortsov 2026). Isso não é contribuição deste estudo e é citado como tal.</li>')
    a('<li>Ameaças críticas à novidade: ' + "; ".join(esc(x) for x in by_threat["critico"]) +
      '. Ameaças altas: ' + "; ".join(esc(x) for x in by_threat["alto"]) + '.</li>')
    a('<li>Metadado de mapeamento (SSSOM), linguagem de correspondência complexa (EDOAL), códigos de evidência '
      '(ECO) e pipeline de release (ODK/ROBOT) são padrões a reusar, não contribuição.</li>')
    a('<li>O que resta defender é medição: invariância do grão, semântica executável e cobertura operacional '
      'por direção, contra comparadores no mesmo universo e nas mesmas CQs. Onde um comparador não se aplica, '
      'o valor é NOT_APPLICABLE, nunca zero.</li>')
    a(f'<li>{len(data.ENTRIES)} entradas bibliográficas, {len(rows)} linhas na matriz; cada linha tem fonte com '
      'identificador verificado (DOI no Crossref ou identificador alternativo).</li></ul>')

    a('<h2 id="kalinin">Kalinin e Skvortsov 2026, descrito como está</h2>')
    a(f'<p><strong>O artigo está publicado</strong>: N. A. Kalinin e N. A. Skvortsov, "{esc(k["title"])}", '
      f'<em>{esc(k["journal"])}</em> {esc(k["volume"])}({esc(k["number"])}):{esc(k["pages"].replace("--", "–"))}, '
      f'{esc(k["year"])}, DOI <a href="https://doi.org/{esc(k["doi"])}">{esc(k["doi"])}</a>, numa edição especial '
      'com artigos selecionados da DAMDID/RCDL-2025. <strong>O artefato ontológico está indisponível</strong>: o '
      'artigo não traz link, IRI nem repositório, e uma busca no GitHub em 02/11/2026 não achou nada.</p>')
    a('<p>O que eles implementam: uma ontologia OWL DL com owlready2, construída de baixo para cima a partir dos '
      'schemas dos providers Terraform (cada tipo de recurso vira classe candidata, cada parâmetro vira propriedade '
      'candidata), generalizada em 6 passos e organizada em 4 camadas, com CloudResource no topo e ids convertidos em '
      'object properties (p. 561–562). A ABox vem do inventário coletado pelo CloudQuery; as consultas CSPM são '
      'escritas em SQL (views) ou SPARQL (p. 563–564); as cadeias de ataque usam regras SWRL com o raciocinador '
      'HermiT (p. 565). Há 5 perguntas de competência, todas de segurança (p. 561), e a escolha de ontologia de topo '
      'fica deliberadamente para depois.</p>')
    a('<p>O que falta: <strong>avaliação quantitativa</strong> (nenhum número de classes, propriedades ou '
      'cobertura, nenhuma precisão dos alinhamentos, nenhum resultado de teste das 5 CQs) e <strong>artefato '
      'inspecionável</strong>. O alinhamento é por julgamento de especialista, sem tipo de equivalência '
      '(exata, ampla, estreita) e sem tratamento de 1:N; a camada atômica é o próprio tipo Terraform; deriva de '
      'schema entre versões não é tratada.</p>')
    a('<p>Provedores: os deles são AWS, Azure, GCP, Yandex Cloud e Cloud.ru. Frente ao nosso estudo (AWS, Azure, '
      'GCP, OCI), saem Yandex Cloud e Cloud.ru e entra OCI. Como o texto deixa escolhas em aberto (pesos, '
      'clusterização, limiares), a comparação usa uma família de reconstruções do método e relata a faixa '
      '(módulos BENCH-CONTRACT e KALININ-RECON). O PDF é de uso local e não é redistribuído; aqui só há paráfrase '
      'com número de página.</p>')

    a('<h2 id="matriz">Matriz de posicionamento</h2>')
    a('<p class="meta">Resumo da <code>positioning_matrix.csv</code> (' + str(len(data.COLUMNS)) + ' colunas). "Sugestão" é insumo para o '
      'BENCH-CONTRACT, que decide quem entra como comparador. O nível de evidência diz de onde vem a descrição: só '
      'Kalinin e Skvortsov foram lidos em texto integral nesta etapa.</p>')
    a('<div class="tbl"><table><thead><tr><th>Trabalho</th><th>Grupo</th><th>Artigo</th><th>Artefato</th>'
      '<th>Ameaça</th><th>O que temos de mostrar</th><th>Sugestão</th><th>Evidência</th><th>Fonte</th></tr></thead><tbody>')
    for r in rows:
        a(f'<tr id="row-{esc(r["row_id"])}"><td><strong>{esc(r["work"])}</strong><br><span class="meta">'
          f'{esc(r["what_it_does"])}</span></td><td>{esc(r["group"])}</td><td>{esc(r["article_status"])}</td>'
          f'<td>{esc(r["artifact_status"])}</td><td class="{esc(r["threat_to_novelty"])}">{esc(r["threat_to_novelty"])}</td>'
          f'<td>{esc(r["what_we_must_show"])}</td><td>{esc(r["comparator_suggestion"])}</td>'
          f'<td>{esc(r["evidence_level"])}</td><td><code>{esc(r["source"])}</code></td></tr>')
    a('</tbody></table></div>')

    c12, c19 = (fields(c["bibkey"]) for c in data.COCOON["entries"])
    cc = data.COCOON["entries"]
    a('<h2 id="cocoon">CoCoOn: as duas entradas</h2>')
    a('<p>O PDF de Kalinin e Skvortsov e a revisão R4 citam entradas distintas. São duas obras diferentes com o '
      'mesmo nome de ontologia, as duas com primeiro autor de sobrenome Zhang e com Armin Haller entre os '
      'autores; por isso a confusão. As duas estão no <code>related.bib</code>:</p><ol>')
    for c, f in ((cc[0], c12), (cc[1], c19)):
        a(f'<li><strong>{esc(f["author"].replace(" and ", "; "))}</strong>. "{esc(f["title"])}". '
          f'{esc(f["booktitle"])}, {esc(f["year"])}, p. {esc(f["pages"].replace("--", "–"))}. DOI '
          f'<a href="https://doi.org/{esc(f["doi"])}">{esc(f["doi"])}</a>. Citada por: {esc(c["cited_by"])}.</li>')
    a('</ol><p>A versão de 2012 é a de descoberta e seleção de serviços IaaS (base do CloudRecommender), que Kalinin e '
      'Skvortsov descrevem na p. 560. A versão de 2019 é o recurso do ISWC para comparar preço e desempenho de IaaS, '
      'com artefato em w3id.org/cocoon. Nota de metadados: o registro ICST da versão de 2012 no Crossref lista 5 '
      'autores (Nepal primeiro, sem Menzel) e não tem páginas; a lista de 6 autores e as páginas 524–530 vêm do '
      'IEEE Xplore (documento 6450944, cópia arquivada), que é a forma citada por Kalinin e Skvortsov. A diferença '
      'está declarada no campo <code>crossref_mismatch</code>.</p>')

    w = fields("paulo2025webmedia")
    a('<h2 id="webmedia2025">WebMedia 2025, em terceira pessoa</h2>')
    a(f'<p>Paulo, Vasconcelos e Ferraz ({esc(w["year"])}), "{esc(w["title"])}", WebMedia 2025, DOI '
      f'<a href="https://doi.org/{esc(w["doi"])}">{esc(w["doi"])}</a>, modelam conceitos de infraestrutura em '
      'ontologias OWL e usam essa representação como contexto estruturado para a geração de Terraform por LLM. A '
      'ontologia deles serve à geração; ela não é avaliada como modelo neutro entre provedores nem como caminho de '
      'tradução. O trabalho é citado em terceira pessoa, e nenhum dado ou número dele é reaproveitado.</p>')

    a('<h2 id="discrepancias">Discrepâncias achadas nas fontes</h2><ul class="tight">')
    a('<li>CoCoOn: Kalinin e Skvortsov citam a versão de 2012 (referência [16]); a R4 cita a de 2019. Resolvido acima.</li>')
    a('<li>CoCoOn 2012: Crossref (ICST) e IEEE Xplore divergem na lista de autores e nas páginas. Declarado.</li>')
    a('<li>Cloud Services Ontology: Kalinin e Skvortsov citam o capítulo do IDCS 2014 (estudo de caso OpenStack, '
      'referência [6]), mas descrevem "uma ontologia OWL para portabilidade e interoperabilidade", que é o título '
      'do artigo do IJWGS 2015. Os dois estão no .bib.</li>')
    a('<li>Fix Inventory: a R4 cita o commit 2118338, que não existe no repositório; o commit é '
      '211833381fdd07690bc789d30ffc2bd84a67744e, de 2025-03-28. A R4 também aponta a data como 28/03/2025 num '
      'documento e 28/03/2026 em outro; o repositório confirma 2025.</li>')
    a('<li>CertGraph: a R4 agrupa CPG e CertGraph sob os DOIs de 2021 (que é o Cloud Property Graph) e 2023 (SAC); '
      'o CertGraph propriamente dito é Schöberl et al. 2024 (MODELS Companion). Aqui são linhas separadas.</li>')
    a('<li>Kumara et al. 2020: a R4 cita só o preprint arXiv 2007.02135; o registro do arXiv aponta a versão '
      'publicada no WIMS 2020 (DOI 10.1145/3405962.3405979), que é a usada.</li>')
    a('<li>Kalinin e Skvortsov: a R4 não teve acesso ao texto integral. A leitura integral confirma OWL DL, ABox, CSPM e HermiT e '
      'confirma a ausência de números e de artefato (correção V1 da revisão GPT-6).</li>')
    a('<li>mOSAIC 2011: sem DOI; as páginas 973–980 citadas por Kalinin e Skvortsov batem com o índice dos anais '
      'FedCSIS 2011. O ISBN impresso no cabeçalho do artigo (978-83-60810-22-4) passa no dígito verificador; o '
      'mostrado no índice dos anais (978-83-60810-34-4) não passa, e não é usado.</li></ul>')

    a('<h2 id="ids">Identificadores</h2>')
    a('<p class="meta">Cada entrada passa no <code>bo.lit.check_ids</code> por DOI que resolve no Crossref (título, '
      'ano e autores conferidos) ou por identificador alternativo verificado: ISBN (dígito verificador), cópia '
      'arquivada no Wayback (responde 200), commit do GitHub (a API devolve o mesmo sha), arXiv. Uma norma só vale '
      'com a cópia arquivada.</p>')
    a('<div class="tbl"><table><thead><tr><th>Entrada</th><th>Situação</th><th>Base</th><th>Identificadores verificados</th></tr></thead><tbody>')
    for key, st, basis, vids in ledger_summary(ledger):
        a(f'<tr><td><code>{esc(key)}</code></td><td>{esc(st)}</td><td>{esc(basis)}</td><td>'
          + " ".join(f'<span class="chip">{esc(v if len(v) < 90 else v[:87] + "...")}</span>' for v in vids)
          + '</td></tr>')
    a('</tbody></table></div>')

    a('<h2 id="limites">Limites desta matriz</h2><ul class="tight">')
    a('<li>Só Kalinin e Skvortsov foram lidos em texto integral. O resto vem de especificação, repositório, resumo, '
      'metadados do Crossref ou descrição de terceiros (a R4 e o próprio artigo de Kalinin), e a coluna '
      '<code>evidence_level</code> diz qual.</li>')
    a('<li>"nao_localizado" quer dizer que o artefato não foi achado nas buscas feitas aqui; não é prova de que não '
      'existe. O PRIOR ingere os artefatos que existem e anota o método dos que não existem.</li>')
    a('<li>Valores UNKNOWN não foram conferidos. NOT_APPLICABLE quer dizer que a dimensão não se aplica ao '
      'trabalho, e nunca vira zero numa comparação.</li>')
    a('<li>Direção SKOS usada em todo o projeto: "a skos:broadMatch b" quer dizer que b é mais amplo. '
      'Correspondência sem prova é UNPROVEN.</li></ul>')
    a('</main></body></html>\n')
    return "".join(x if x.endswith("\n") else x + "\n" for x in h)


def render_all(root: Path) -> dict[str, str]:
    led_path = root / ids.LEDGER_REL
    ledger = json.loads(led_path.read_text(encoding="utf-8")) if led_path.is_file() else {"records": {}}
    out = {
        OUT_BIB: bib.render(data.ENTRIES, data.EDITED_AT),
        OUT_CSV: render_csv(),
        OUT_HTML: render_html(ledger),
        OUT_COCOON: render_cocoon(),
    }
    man_paths = [OUT_BIB, OUT_CSV, OUT_HTML, OUT_COCOON] + ([ids.LEDGER_REL] if led_path.is_file() else [])
    lines = []
    for p in man_paths:
        b = out[p].encode("utf-8") if p in out else led_path.read_bytes()
        lines.append(f"{hashlib.sha256(b).hexdigest()}  {p}")
    out[OUT_MANIFEST] = "\n".join(lines) + "\n"
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -I -m bo.lit.build")
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)
    root = ids.repo_root()
    out = render_all(root)
    if a.check:
        diff = []
        for rel, text in out.items():
            p = root / rel
            if not p.is_file() or p.read_text(encoding="utf-8") != text:
                diff.append(rel)
        for d in diff:
            core.emit(f"DIFERE {d} (rode python -I -m bo.lit.build)")
        core.emit(f"regeneração idêntica: {len(out) - len(diff)} de {len(out)} arquivos iguais")
        return 1 if diff else 0
    for rel, text in out.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        core.emit(f"escrito {rel}")
    return 0


if __name__ == "__main__":
    core.run_main(main)
