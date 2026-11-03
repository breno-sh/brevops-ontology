"""contracts/CONTRACTS.html: o documento dos contratos v3, gerado dos schemas (nada escrito à mão diverge do que
o validador aplica). Determinístico: sem carimbo de hora variável; a data é a da versão dos contratos."""

from __future__ import annotations

import html as _html
import json

from . import catalog

VERSION_DATE = "2026-11-03 (America/Recife)"
STATUS = {"changed_v3": "mudou na v3 (3.0.0)", "new_v3": "novo na v3 (1.0.0)", "unchanged_v3": "sem mudança (2.0.0)",
          "amended": "emenda versionada depois do merge (ver amendments.py)"}


def esc(s) -> str:
    return _html.escape(str(s), quote=True)


def _fields(defn: dict, sch: dict) -> list[tuple[str, str, bool]]:
    """(campo, tipo resumido, obrigatório) do primeiro nível de uma definição."""
    if "allOf" in defn and "properties" not in defn:
        for part in defn["allOf"]:
            if "$ref" in part:
                return [("(ver)", part["$ref"].split("/")[-1], True)]
    props = defn.get("properties") or {}
    req = set(defn.get("required") or [])
    out = []
    for k, v in props.items():
        out.append((k, _type(v), k in req))
    return out


def _type(v: dict) -> str:
    if "$ref" in v:
        return v["$ref"].rsplit("/", 1)[-1]
    if "const" in v:
        return f"= {json.dumps(v['const'], ensure_ascii=False)}"
    if "enum" in v:
        vals = v["enum"]
        s = " | ".join(json.dumps(x, ensure_ascii=False) for x in vals[:8])
        return s + (" | …" if len(vals) > 8 else "")
    if "oneOf" in v or "anyOf" in v:
        alts = v.get("oneOf") or v.get("anyOf")
        return " ou ".join(_type(a) for a in alts[:4])
    if "allOf" in v:
        return " e ".join(_type(a) for a in v["allOf"][:3])
    t = v.get("type", "qualquer")
    if t == "array":
        return f"lista de {_type(v.get('items') or {})}"
    if isinstance(t, list):
        return " | ".join(t)
    if t == "string" and "pattern" in v:
        return f"texto /{v['pattern'][:48]}{'…' if len(v['pattern']) > 48 else ''}/"
    return t


CSS = """
:root{--bg:#fbfaf7;--fg:#1d1d1b;--mut:#5b5b57;--line:#dedad2;--acc:#1f5f8b;--chip:#eef3f7;--warn:#8a4b00}
@media (prefers-color-scheme: dark){:root{--bg:#161615;--fg:#e9e7e2;--mut:#a9a69e;--line:#34322e;--acc:#7fb8e0;
--chip:#1e2a33;--warn:#e0a35c}}
body{background:var(--bg);color:var(--fg);font:15px/1.5 -apple-system,Segoe UI,Roboto,sans-serif;margin:0}
main{max-width:1100px;margin:0 auto;padding:24px 16px 64px}
h1{font-size:1.6rem;margin:.2em 0}h2{font-size:1.2rem;margin:2em 0 .4em;border-top:1px solid var(--line);padding-top:1em}
h3{font-size:1rem;margin:1.2em 0 .3em}code{font:13px ui-monospace,Menlo,monospace}
.mut{color:var(--mut)}.chip{display:inline-block;background:var(--chip);border-radius:6px;padding:0 6px;margin:0 4px 0 0;
font-size:12px}.warn{color:var(--warn)}table{border-collapse:collapse;width:100%;margin:.4em 0 1em;font-size:13px}
td,th{border-bottom:1px solid var(--line);text-align:left;padding:4px 6px;vertical-align:top}
.wrap{overflow-x:auto}nav a{margin-right:8px;white-space:nowrap}a{color:var(--acc)}
"""


def html_doc(gen: dict) -> str:
    rows, body = [], []
    for cid, s in sorted(gen.items()):
        x = s["x-bo-contract"]
        rows.append(f"<tr><td><a href='#{cid}'>{cid}</a></td><td><code>{esc(x['name'])}</code></td>"
                    f"<td>{esc(x['version'])}</td><td>{esc(STATUS[x['status']])}</td>"
                    f"<td>{', '.join('<code>' + esc(f['file']) + '</code>' for f in x['files'])}</td></tr>")
        b = [f"<h2 id='{cid}'>{cid} · {esc(x['name'])} <span class='mut'>{esc(x['version'])}</span></h2>",
             f"<p>{esc(s['description'])}</p>",
             f"<p class='mut'>Schema: <code>contracts/{esc(catalog.schema_filename(cid))}</code> · "
             f"<code>$id</code> {esc(s['$id'])}</p>"]
        if x["adopted_from"]:
            b.append("<p>Incorpora: " + ", ".join(f"<code>{esc(a)}</code>" for a in x["adopted_from"]) + "</p>")
        if x["producers"]:
            b.append("<p class='mut'>Produtores: " + esc(", ".join(x["producers"])) +
                     (" · consumidores: " + esc(", ".join(x["consumers"])) if x["consumers"] else "") + "</p>")
        for f in x["files"]:
            b.append(f"<h3><code>{esc(f['file'])}</code> <span class='chip'>{esc(f['kind'])}</span>"
                     f"<span class='chip'>{esc(f['format'])}</span><span class='chip'>por {esc(f['unit'])}</span></h3>")
            if f.get("note"):
                b.append(f"<p class='mut'>{esc(f['note'])}</p>")
            if f["record"]:
                fl = _fields(s["$defs"][f["record"]], s)
                b.append("<div class='wrap'><table><tr><th>campo</th><th>tipo</th><th></th></tr>" +
                         "".join(f"<tr><td><code>{esc(k)}</code></td><td>{esc(t)}</td>"
                                 f"<td>{'obrigatório' if r else ''}</td></tr>" for k, t, r in fl) + "</table></div>")
        b.append("<h3>Regras além do schema</h3><ul>" + "".join(f"<li>{esc(r)}</li>" for r in x["semantic_rules"]) +
                 "</ul>")
        b.append(f"<p class='mut'>Stub: <code>contracts/stubs/{cid}/</code>" +
                 (" e <code>contracts/stubs/complex.sssom.tsv</code>" if cid == "C09" else "") + "</p>")
        body.append("\n".join(b))
    nav = " ".join(f"<a href='#{c}'>{c}</a>" for c in sorted(gen))
    return f"""<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Contratos BrevOps v3</title><style>{CSS}</style></head><body><main>
<h1>Contratos de interface v3 (C00–C29)</h1>
<p class="mut">Módulo CONTRACTS · versão dos contratos de {esc(VERSION_DATE)} · gerado por
<code>python -I -m bo.contracts.build</code> a partir de <code>src/bo/contracts/spec_*.py</code>.</p>
<p>Cada contrato é o formato exato de um arquivo que um módulo produz e outro consome: JSON Schema (draft 2020-12),
o validador único <code>python -I -m bo.contracts.validate &lt;contrato|tipo&gt; ARQ</code> e um stub mínimo válido.
Mudança depois do merge só por emenda versionada (contrato novo ou versão nova, com invalidação dos dependentes).
As definições comuns ficam no C00 (<code>#/$defs/…</code>) e são referenciadas pelo <code>$id</code>.</p>
<h2>Pontos que atravessam contratos</h2>
<ul>
<li><b>União discriminada de desfechos</b> (C00 <code>outcome</code>): <code>{{axis, value}}</code> com
<code>axis = persistence</code> (PERSISTED, ALTERED, REJECTED_BY_API, NOT_READABLE, INFRA_ERROR, UNKNOWN) ou
<code>axis = behavior</code> (OBSERVATIONS_MATCH_UNDER_PROTOCOL, OBSERVATIONS_DIFFER_UNDER_PROTOCOL,
NOT_OBSERVED_IN_WINDOW, PROTOCOL_UNSUPPORTED, INFRA_ERROR, UNKNOWN). O C12 e o C22 referenciam a mesma definição e
fixam o eixo; <code>python -I -m bo.contracts.enum_union</code> confere que nenhum valor de desfecho existe fora dela.</li>
<li><b>IDs de alegação</b>: <code>claim_id</code> é imutável e nunca carrega versão (<code>@n</code>), evento
(<code>EV-</code>) nem hash de linha; <code>claim_version_id = claim_id@n</code> e <code>event_id</code> ficam em
campos próprios; <code>supersedes</code> aponta para a versão anterior da mesma alegação
(<code>python -I -m bo.contracts.claim_ids</code>).</li>
<li><b>NOT_APPLICABLE ≠ UNKNOWN</b>: grandeza e unidade são IRI QUDT, NOT_APPLICABLE (não há grandeza) ou UNKNOWN (há,
mas não se sabe); no C28, NOT_APPLICABLE nunca vira 0.</li>
<li><b>Códigos de bloqueio do C23</b>: os 13 do plano, mais UNKNOWN_INPUT (T-ABSENCE do SEMANTICS) e REFUTED_BY_RULE
(alegação refutada, proposta do SEMANTICS).</li>
<li><b>C09 complexo</b>: grupo como regra sobre subgrafo (variáveis e argumentos nomeados, ocorrências ligadas por
junção), projeção por ocorrência (chave de ocorrência que não é posição) e realizações alternativas guardadas
(<code>alternative_to</code> + <code>exclusivity</code>, conferidas pela interseção das guardas) — stub
<code>contracts/stubs/complex.sssom.tsv</code>. O I/O do TSV passa por <code>bo.contracts.sssom</code>, que delega a
<code>bo.semantics.sssom_io</code> e preserva as colunas novas (o sssom-py 0.4.22 descarta extensões em silêncio).</li>
</ul>
<h2>Índice</h2><nav>{nav}</nav>
<div class="wrap"><table><tr><th>id</th><th>nome</th><th>versão</th><th>situação</th><th>arquivos</th></tr>
{''.join(rows)}</table></div>
{''.join(body)}
</main></body></html>
"""


def html(gen: dict) -> str:
    return html_doc(gen)
