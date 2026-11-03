"""Materializa o CQSRC: python -I -m bo.cqsrc.build [--check]

Lê (só como dado) os quatro tarballs fixados em sources.py e escreve:
  $BO_REPO/cq/cis_controls.csv            um controle CIS Foundations por linha, todas as versões dos mods
  $BO_REPO/cq/cis_cross_provider.csv      alinhamento curado entre provedores (versão mais nova de cada um)
  $BO_REPO/results/CQSRC/CQSRC.html       relatório (método, números, conceitos nos 4, anomalias, auditoria)
  $BO_REPO/results/CQSRC/MANIFEST.sha256  hashes C17 de tudo acima e dos arquivos em $BO_DATA/CQSRC
  $BO_DATA/CQSRC/extraction_report.json   contagens por mod e versão, pastas fora de escopo, anomalias
  $BO_DATA/CQSRC/lexical_audit.json       pares de títulos parecidos que a curadoria não alinhou
  $BO_DATA/CQSRC/concept_coverage.json    provedores e itens de cada conceito
--check não grava nada: sai 1 se algum arquivo publicado difere do que as fontes produzem.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import html
import io
import json
import os
import sys
from collections import Counter
from pathlib import Path

from . import align, concepts, extract, fetch, sources

# Hora em que método e catálogo foram fixados (America/Recife); a saída é determinística.
AUTHORED_AT = "2026-11-03T01:40:00-03:00"

CONTROL_COLS = ["provider", "mod", "benchmark_id", "cis_version", "is_latest", "control_id", "cis_item_id",
                "title_item_id", "section_id", "section_title", "subsection_id", "subsection_title", "parent_id",
                "parent_title", "title", "cis_level", "cis_type", "service", "query", "anomaly", "source_repo",
                "source_tag", "source_commit", "source_file", "source_line", "source_uri"]
CROSS_COLS = ["concept_id", "concept_label", "domain", "concept_providers", "concept_in_all_four", "pair",
              "subject_provider", "subject_cis_version", "subject_control_id", "subject_cis_item_id",
              "subject_title", "predicate", "object_provider", "object_cis_version", "object_control_id",
              "object_cis_item_id", "object_title", "proof_status", "mapping_justification", "direction_basis",
              "subject_params", "object_params", "lexical_jaccard", "extension"]
EXTENSION = "conjunto de configurações conformes ao controle (mais exigente = mais estreito)"


def repo_root() -> Path:
    return Path(os.environ.get("BO_REPO") or Path(__file__).resolve().parents[3])


def load_all() -> tuple[dict[str, list[extract.Control]], dict]:
    report = {"schema": "bo.cqsrc.extraction/1", "generated_at": AUTHORED_AT, "mods": {}}
    controls: dict[str, list[extract.Control]] = {}
    for mod in sources.MODS:
        arc = sources.archive_path(mod)
        if not arc.exists():
            raise SystemExit(f"tarball ausente: {arc} (rode python -I -m bo.cqsrc.fetch)")
        got = fetch.sha256(arc)
        if got != sources.MODS[mod][4]:
            raise SystemExit(f"sha256 de {arc.name} difere do fixado")
        provider = sources.PROVIDER_OF_MOD[mod]
        dirs, skipped = extract.read_mod(arc)
        versions = {}
        allc = []
        for bench_id, files in dirs.items():
            cs = extract.extract_version(provider, bench_id, files)
            versions[bench_id] = {"cis_version": cs[0].cis_version if cs else "", "files": len(files),
                                  "controls": len(cs), "manual": sum(c.cis_type == "manual" for c in cs),
                                  "automated": sum(c.cis_type == "automated" for c in cs),
                                  "anomalies": [{"control_id": c.control_id, "anomaly": c.anomaly}
                                                for c in cs if c.anomaly]}
            allc += cs
        controls[provider] = allc
        report["mods"][mod] = {"provider": provider, "repo": sources.MODS[mod][0], "tag": sources.MODS[mod][1],
                               "commit": sources.MODS[mod][2], "archive_sha256": got,
                               "out_of_scope_cis_dirs": skipped, "versions": versions,
                               "latest": max(dirs, key=lambda d: int(d[5:]))}
    return controls, report


def latest_of(controls, report) -> dict[str, list[extract.Control]]:
    out = {}
    for mod, r in report["mods"].items():
        p = r["provider"]
        out[p] = [c for c in controls[p] if c.benchmark_id == r["latest"]]
    return out


def mod_of(provider: str) -> str:
    return concepts.MOD_OF[provider]


def controls_csv(controls, report) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(CONTROL_COLS)
    for p in concepts.PROVIDERS:
        mod = mod_of(p)
        latest = report["mods"][mod]["latest"]
        repo, tag, commit = sources.MODS[mod][:3]
        for c in sorted(controls[p], key=lambda c: (int(c.benchmark_id[5:]), _item_key(c.cis_item_id), c.control_id)):
            w.writerow([p, mod, c.benchmark_id, c.cis_version, str(c.benchmark_id == latest).lower(), c.control_id,
                        c.cis_item_id, c.title_item_id, c.section_id, c.section_title, c.subsection_id,
                        c.subsection_title, c.parent_id, c.parent_title, c.title, c.cis_level, c.cis_type, c.service,
                        c.query, c.anomaly, repo, tag, commit, c.source_file, c.source_line,
                        sources.blob_url(mod, c.source_file, c.source_line)])
    return buf.getvalue()


def _item_key(item: str):
    return tuple(int(x) if x.isdigit() else 0 for x in item.strip(".").split(".")) if item else (0,)


def cross_csv(rows: list[align.Row]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(CROSS_COLS)
    for r in rows:
        w.writerow([r.concept_id, r.concept_label, r.domain, r.concept_providers, str(r.concept_in_all_four).lower(),
                    r.pair, r.subject.provider, r.subject.cis_version, r.subject.control_id, r.subject.cis_item_id,
                    r.subject.title, r.predicate, r.obj.provider, r.obj.cis_version, r.obj.control_id,
                    r.obj.cis_item_id, r.obj.title, "UNPROVEN", "semapv:ManualMappingCuration", r.direction_basis,
                    r.subject_params, r.object_params, f"{r.lexical_jaccard:.4f}", EXTENSION])
    return buf.getvalue()


def coverage(latest) -> dict:
    members = align.resolve_members(latest)
    out = []
    for con in concepts.CONCEPTS:
        ms = members[con["id"]]
        by = {p: sorted({c.cis_item_id for c, _ in ms if c.provider == p}, key=_item_key) for p in concepts.PROVIDERS}
        out.append({"concept_id": con["id"], "label": con["label"], "domain": con["domain"],
                    "providers": [p for p in concepts.PROVIDERS if by[p]], "items": by})
    return {"schema": "bo.cqsrc.coverage/1", "generated_at": AUTHORED_AT, "concepts": out}


def _esc(x) -> str:
    return html.escape(str(x))


def report_html(controls, report, latest, rows, cov, audit) -> str:
    total = sum(len(v) for v in controls.values())
    nlatest = {p: len(latest[p]) for p in concepts.PROVIDERS}
    preds = Counter(r.predicate for r in rows)
    pairs = Counter(r.pair for r in rows)
    in_concept = {p: len({c.control_id for r in rows for c in (r.subject, r.obj) if c.provider == p})
                  for p in concepts.PROVIDERS}
    all4 = [c for c in cov["concepts"] if len(c["providers"]) == 4]
    by_np = Counter(len(c["providers"]) for c in cov["concepts"])
    anomalies = [(m, b, a) for m, r in report["mods"].items() for b, v in r["versions"].items() for a in v["anomalies"]]
    t = []
    t.append("<!doctype html><html lang='pt-BR'><head><meta charset='utf-8'>"
             "<meta name='viewport' content='width=device-width,initial-scale=1'><title>CQSRC controles CIS</title>"
             "<style>:root{--bg:#fff;--fg:#1d1d1f;--mut:#5f6368;--line:#d9d9de;--acc:#1f5fa8}"
             "@media (prefers-color-scheme:dark){:root{--bg:#141416;--fg:#ececf0;--mut:#a0a0a8;--line:#34343a;"
             "--acc:#7fb0ff}}body{background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,sans-serif;"
             "max-width:1100px;margin:0 auto;padding:16px}h1{font-size:1.5rem}h2{font-size:1.15rem;margin-top:2rem}"
             "table{border-collapse:collapse;width:100%;font-size:13px;display:block;overflow-x:auto}"
             "th,td{border-bottom:1px solid var(--line);padding:4px 8px;text-align:left;vertical-align:top}"
             "th{color:var(--mut);font-weight:600}code{font-size:12px}.mut{color:var(--mut)}</style></head><body>")
    t.append("<h1>CQSRC: controles CIS como uma das fontes externas de CQ</h1>")
    t.append(f"<p class='mut'>Gerado de forma determinística por <code>python -I -m bo.cqsrc.build</code>; "
             f"método fixado em {_esc(AUTHORED_AT)} (America/Recife).</p>")
    t.append("<h2>Fontes</h2><table><tr><th>mod</th><th>provedor</th><th>tag</th><th>commit</th>"
             "<th>versões CIS Foundations</th><th>mais nova</th><th>fora de escopo</th></tr>")
    for m, r in report["mods"].items():
        t.append(f"<tr><td>{_esc(r['repo'])}</td><td>{_esc(r['provider'])}</td><td>{_esc(r['tag'])}</td>"
                 f"<td><code>{_esc(r['commit'][:12])}</code></td><td>{len(r['versions'])}</td>"
                 f"<td>{_esc(r['latest'])} ({_esc(r['versions'][r['latest']]['cis_version'])})</td>"
                 f"<td>{_esc(', '.join(r['out_of_scope_cis_dirs']) or '-')}</td></tr>")
    t.append("</table><p>Os tarballs são lidos como dado (tarfile, sem extrair; HCL por um leitor mínimo; o SQL "
             "das consultas não é lido nem executado). Licença dos mods: Apache-2.0.</p>")
    t.append("<h2>Números</h2><table><tr><th>medida</th><th>valor</th></tr>")
    t.append(f"<tr><td>controles extraídos (todas as versões, 4 mods)</td><td>{total}</td></tr>")
    for p in concepts.PROVIDERS:
        t.append(f"<tr><td>controles na versão mais nova: {p}</td><td>{nlatest[p]} "
                 f"({in_concept[p]} em algum conceito alinhado)</td></tr>")
    t.append(f"<tr><td>conceitos curados</td><td>{len(cov['concepts'])} "
             f"(em 4 provedores: {by_np[4]}; em 3: {by_np[3]}; em 2: {by_np[2]})</td></tr>")
    t.append(f"<tr><td>linhas de alinhamento (pares de controles)</td><td>{len(rows)}</td></tr>")
    for k in ("skos:closeMatch", "skos:broadMatch", "skos:narrowMatch", "skos:relatedMatch"):
        t.append(f"<tr><td>predicado {k}</td><td>{preds.get(k, 0)}</td></tr>")
    t.append("<tr><td>linhas por par</td><td>" + _esc(", ".join(f"{k} {pairs.get(k, 0)}" for k in
                                                                    concepts.PAIR_CODE.values())) + "</td></tr>")
    t.append(f"<tr><td>linhas com prova</td><td>0 (todas UNPROVEN)</td></tr>")
    t.append(f"<tr><td>anomalias da fonte registradas</td><td>{len(anomalies)}</td></tr></table>")
    t.append("<h2>Conceitos presentes nos 4 provedores</h2><p>Base para as fixtures do CQFIX (o plano estimava "
             "cerca de 10; o número medido é o desta tabela).</p><table><tr><th>conceito</th><th>domínio</th>"
             + "".join(f"<th>{p}</th>" for p in concepts.PROVIDERS) + "</tr>")
    for c in all4:
        t.append(f"<tr><td><b>{_esc(c['concept_id'])}</b><br><span class='mut'>{_esc(c['label'])}</span></td>"
                 f"<td>{_esc(c['domain'])}</td>" + "".join(f"<td>{_esc(', '.join(c['items'][p]))}</td>"
                                                          for p in concepts.PROVIDERS) + "</tr>")
    t.append("</table><h2>Todos os conceitos</h2><table><tr><th>conceito</th><th>domínio</th>"
             + "".join(f"<th>{p}</th>" for p in concepts.PROVIDERS) + "</tr>")
    for c in cov["concepts"]:
        t.append(f"<tr><td>{_esc(c['concept_id'])}<br><span class='mut'>{_esc(c['label'])}</span></td>"
                 f"<td>{_esc(c['domain'])}</td>" + "".join(f"<td>{_esc(', '.join(c['items'][p]) or '-')}</td>"
                                                          for p in concepts.PROVIDERS) + "</tr>")
    t.append("</table>")
    t.append("<h2>Método do alinhamento</h2><ul>"
             "<li>Escopo: só a versão CIS Foundations mais nova de cada mod. Versões antigas ficam em "
             "<code>cis_controls.csv</code> (coluna <code>is_latest</code>) e não são alinhadas.</li>"
             "<li>Pertença a conceito: curada pelo agente a partir dos títulos; cada membro tem uma guarda (regex) que "
             "tem de casar com o título extraído, senão a regeneração reprova.</li>"
             "<li>Direção SKOS só por parâmetros lidos no título (portas, dias, tamanho, eventos, nível de controle "
             "da chave). Extensão = configurações conformes; <code>a skos:broadMatch b</code> = b mais amplo. "
             "Categoria diferente, parâmetro ausente de um lado ou sinais mistos dão <code>skos:relatedMatch</code>."
             "</li><li>Nenhuma linha tem prova: o título não prova o que a consulta do mod confere e a curadoria não é "
             "verificação. Todas saem <code>UNPROVEN</code>, com <code>semapv:ManualMappingCuration</code>.</li>"
             "<li>Na v3 os CIS são uma fonte entre outras: as CQs além do CIS vêm do REQUIREMENTS "
             "(<code>requirements/cq_spec.jsonl</code>).</li></ul>")
    t.append(f"<h2>Auditoria lexical</h2><p>Similaridade de Jaccard sobre palavras dos títulos (sem palavras vazias "
             f"e nomes de provedor). Mediana nos pares curados: {audit['curated_jaccard_median']}; pares curados com "
             f"Jaccard 0: {audit['curated_jaccard_zero']} de {audit['curated_pairs']}. Pares entre provedores com "
             f"Jaccard &ge; {audit['threshold']} que a curadoria NÃO alinhou: {len(audit['uncurated_similar_pairs'])} "
             f"(lista completa em <code>$BO_DATA/CQSRC/lexical_audit.json</code>; os 25 primeiros abaixo). "
             f"Sem revisão: {audit['unreviewed']}.</p>"
             "<table><tr><th>par</th><th>sujeito</th><th>objeto</th><th>J</th><th>revisão</th></tr>")
    for d in audit["uncurated_similar_pairs"][:25]:
        t.append(f"<tr><td>{_esc(d['pair'])}</td><td>{_esc(d['subject'])}: {_esc(d['subject_title'])}</td>"
                 f"<td>{_esc(d['object'])}: {_esc(d['object_title'])}</td><td>{d['jaccard']}</td>"
                 f"<td>{_esc(d['review'])}</td></tr>")
    t.append("</table><h2>Anomalias da fonte</h2><p>Registradas como estão; nada foi corrigido.</p><table>"
             "<tr><th>mod</th><th>versão</th><th>controle</th><th>anomalia</th></tr>")
    for m, b, a in anomalies:
        t.append(f"<tr><td>{_esc(m)}</td><td>{_esc(b)}</td><td>{_esc(a['control_id'])}</td>"
                 f"<td>{_esc(a['anomaly'])}</td></tr>")
    t.append("</table></body></html>\n")
    return "\n".join(t)


def render() -> dict[str, str]:
    """{caminho portátil: conteúdo} de tudo o que o módulo publica (menos o MANIFEST)."""
    controls, report = load_all()
    latest = latest_of(controls, report)
    rows = align.align(latest)
    cov = coverage(latest)
    audit = align.lexical_audit(latest, rows)
    audit = {"schema": "bo.cqsrc.lexical_audit/1", "generated_at": AUTHORED_AT, **audit}
    dump = lambda o: json.dumps(o, ensure_ascii=False, indent=1, sort_keys=False) + "\n"  # noqa: E731
    return {
        "$BO_REPO/cq/cis_controls.csv": controls_csv(controls, report),
        "$BO_REPO/cq/cis_cross_provider.csv": cross_csv(rows),
        "$BO_REPO/results/CQSRC/CQSRC.html": report_html(controls, report, latest, rows, cov, audit),
        "$BO_DATA/CQSRC/extraction_report.json": dump(report),
        "$BO_DATA/CQSRC/lexical_audit.json": dump(audit),
        "$BO_DATA/CQSRC/concept_coverage.json": dump(cov),
    }


def real(portable: str) -> Path:
    return Path(portable.replace("$BO_REPO", str(repo_root())).replace("$BO_DATA", str(sources.data_root())))


def manifest(files: dict[str, str]) -> str:
    lines = []
    for k in sorted(files):
        h = hashlib.sha256(files[k].encode("utf-8")).hexdigest()
        rel = k.replace("$BO_REPO/", "", 1) if k.startswith("$BO_REPO/") else k
        lines.append(f"{h}  {rel}")
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="bo.cqsrc.build")
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)
    files = render()
    files["$BO_REPO/results/CQSRC/MANIFEST.sha256"] = manifest(files)
    diff = []
    for k, v in files.items():
        p = real(k)
        if a.check:
            if not p.exists() or p.read_text(encoding="utf-8") != v:
                diff.append(k)
        else:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(v, encoding="utf-8")
    if a.check:
        if diff:
            print("regeneração difere: " + ", ".join(diff))
            return 1
        print(f"regeneração idêntica: {len(files)} arquivo(s)")
        return 0
    print(f"gravados {len(files)} arquivo(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
