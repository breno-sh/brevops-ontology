"""Materializa o GRAIN: python -I -m bo.grain.build [--check]

Escreve, só a partir de src/bo/grain e de grain/grain_rules.yaml:
  grain/GRAIN.html                         o procedimento (texto normativo para o GRAIN-REPRO) e os resultados
  grain/RULES.sha256                       sha256 de grain_rules.yaml e GRAIN.html (caminhos a partir de $BO_REPO)
  results/GRAIN/packaging.json             4 embalagens do contêiner, reordenação, controles
  results/GRAIN/unknown_exit.json          bateria de mutação de evidência (e o controle no estilo da v2)
  results/GRAIN/priority.json              casos de prioridade
  results/GRAIN/lint.json                  higiene das regras e mutantes do lint
  results/GRAIN/checkers.json              coverage, permutation e relations nos mundos sintéticos
  results/GRAIN/commitment_suite.json      compromissos do REQUIREMENTS com o GRAIN como consumidor
  results/GRAIN/MANIFEST.sha256            (C17) tudo acima, o gate e o código
  $BO_DATA/GRAIN/c19_examples/<mundo>/     canonical_units.jsonl e canonical_atoms.jsonl (C19) dos mundos
--check não grava: sai 1 se algo publicado difere do que o código produz (regeneração idêntica).
"""

from __future__ import annotations

import argparse
import hashlib
import html
import io
import json
import sys
from contextlib import redirect_stdout
from pathlib import Path

import yaml

from . import battery as B
from . import coverage, lint, permutation, priority, relations, suite, unknown_exit
from . import fixtures as F
from . import instance as I
from . import rules as R
from . import schema as S
from .common import data_dir, dump_json, dump_jsonl, now, repo, results_dir, rules_path, sha256_file, stamp
from .evidence import FixtureAdapter

AUTHORED_AT = "2026-11-04T23:06:00-03:00"


def _strip(rep: dict) -> dict:
    rep = dict(rep)
    rep.pop("generated_at", None)
    rep["written_at"] = AUTHORED_AT
    return rep


def packaging_report(rs) -> dict:
    sch, ev = F.bucket_schema(), F.bucket_evidence()
    ad, blocks = FixtureAdapter(ev), F.schema_blocks(sch)
    res = S.decompose_schema(S.candidates_from_tf_schema(F.P, sch), ad, rs)
    sigs = {k: S.signature(res, v) for k, v in F.BUCKET_PACKAGINGS.items()}
    cfgs = F.bucket_configs()
    rows = {k: I.canonical_rows(I.decompose_config(c, ad, blocks, rs)) for k, c in cfgs.items()}
    seeds = list(range(25))
    reorder_ok = {k: all(I.canonical_rows(I.decompose_config(F.shuffled(c, s), ad, blocks, rs)) == rows[k]
                         for s in seeds) for k, c in cfgs.items()}
    occ = I.decompose_config(cfgs["inline"], ad, blocks, rs)
    units = [{"grain": o.grain, "label": o.label, "occurrence": o.occ_id, "parent": o.parent, "key": o.key,
              "config": o.config, "rule": o.rule} for o in sorted(occ, key=lambda o: (o.grain, o.label, o.occ_id))]
    return {"schema": "bo.grain.packaging/1", "module": "GRAIN", "provider": F.P,
            "packagings": {k: {"schema_candidates": v, "schema_units": len(sigs[k]), "instance_units": len(rows[k])}
                           for k, v in F.BUCKET_PACKAGINGS.items()},
            "schema_signatures_equal": len({json.dumps(s) for s in sigs.values()}) == 1,
            "instance_decompositions_equal": len({json.dumps(r) for r in rows.values()}) == 1,
            "reorder_seeds": len(seeds), "reorder_invariant": reorder_ok,
            "content_control_changes": rows["inline"] != I.canonical_rows(I.decompose_config(
                F.bucket_configs(versioning="Suspended")["inline"], ad, blocks, rs)),
            "canonical_units_inline": units}


def checkers_report() -> dict:
    out = {}
    for name, mod, args in (("coverage", coverage, ["--fixtures"]), ("permutation", permutation,
                                                                     ["--fixtures", "--rename"]),
                            ("relations", relations, ["--fixtures"])):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = mod.main(args)
        lines = [ln for ln in buf.getvalue().splitlines() if not ln.startswith("[")]
        out[name] = {"rc": rc, "args": args, "output": lines}
    return {"schema": "bo.grain.checkers/1", "module": "GRAIN", "checkers": out,
            "ok": all(v["rc"] == 0 for v in out.values())}


def lint_report() -> dict:
    text = rules_path().read_text(encoding="utf-8")
    return {"schema": "bo.grain.lint/1", "module": "GRAIN", "hygiene_only": True, "file": "grain/grain_rules.yaml",
            "problems": lint.lint_text(text), "mutants": len(lint.MUTANTS), "mutant_failures": lint.selftest(text)}


def c19_examples(rs) -> dict:
    out = {}
    for name, w in sorted(B.all_worlds().items()):
        u, a = S.to_c19(B.run_schema(w, rs))
        out[f"{name}/canonical_units.jsonl"] = dump_jsonl(u)
        out[f"{name}/canonical_atoms.jsonl"] = dump_jsonl(a)
    return out


# ------------------------------------------------------------------------------------------------- HTML

CSS = """:root{--bg:#fbfaf7;--fg:#1d1f22;--muted:#5d636b;--line:#dcd8cf;--card:#ffffff;--accent:#2b5d8a;
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
.ok{color:var(--pos);font-weight:600}.no{color:var(--neg);font-weight:600}.unk{color:var(--unk);font-weight:600}
.note{border-left:3px solid var(--accent);padding:4px 10px;color:var(--muted)}
nav a{margin-right:10px;font-size:.88rem;color:var(--accent)}
ol li,ul li{margin:3px 0}"""

e = html.escape


def _code(x) -> str:
    return f"<code>{e(x if isinstance(x, str) else json.dumps(x, ensure_ascii=False))}</code>"


def _table(head, rows) -> str:
    h = "".join(f"<th>{e(c)}</th>" for c in head)
    body = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
    return f'<div class="wrap"><table><thead><tr>{h}</tr></thead><tbody>{body}</tbody></table></div>'


def render(doc: dict, rs: R.RuleSet, reps: dict) -> str:
    ue, pr, pk, ck, cs, ln = (reps[k] for k in ("unknown_exit", "priority", "packaging", "checkers",
                                                 "commitment_suite", "lint"))
    rules_sha = sha256_file(rules_path())
    st = ue["stats"]
    P = []
    P.append(f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Grão canônico</title>
<style>{CSS}</style></head><body><main>
<h1>Procedimento de grão canônico</h1>
<div class="meta">Módulo GRAIN · contrato de saída C19 {e(doc['contract_version'])} · regras {e(rs.version)}
<b class="unk">{e(rs.status)}</b> (definitivas só depois de {e(', '.join(doc['definitive_after']))}) · escrito em
{e(AUTHORED_AT)} (America/Recife) · grain_rules.yaml sha256 {rules_sha[:16]}… · responde a R1-M2, R1-M7, R2-W2,
Gemini A3/A6, GPT-6 F1/S1</div>
<div class="kpis">
<div class="kpi"><b>{len(rs.rules)}</b>regras (G0–G4, G2-CHILD, G4-NS e G0-NOMATCH)</div>
<div class="kpi"><b>{len(R.IDENTITY_CLASSES)}</b>classes de identidade</div>
<div class="kpi"><b>{len(R.PREDICATES)}</b>predicados (vocabulário fechado)</div>
<div class="kpi"><b>{'4/4' if pk['instance_decompositions_equal'] and pk['schema_signatures_equal'] else 'NÃO'}</b>embalagens do contêiner com a mesma decomposição</div>
<div class="kpi"><b>{st['mutants']}</b>mutantes de evidência, <span class="{'ok' if not ue['violations'] else 'no'}">{len(ue['violations'])} violação(ões)</span></div>
<div class="kpi"><b>{ue['control_v2_style']['violations']}</b>violações pegas no controle estilo v2</div>
<div class="kpi"><b>{sum(c['ok'] for c in pr['checks'])}/{len(pr['checks'])}</b>casos de prioridade</div>
<div class="kpi"><b>{cs['reproduced']}/{cs['n_commitments']}</b>compromissos reproduzidos ({cs['failed']} falha(s), {cs['out_of_scope']} fora do alcance)</div>
</div>
<nav><a href="#leitura">Para quem reimplementa</a><a href="#camadas">Camadas</a><a href="#evidencia">Evidência</a>
<a href="#normalizacao">Normalização</a><a href="#identidade">Identidade</a><a href="#regras">Regras</a>
<a href="#resolucao">Resolução</a><a href="#c19">Saída C19</a><a href="#instancia">Instância</a>
<a href="#adaptadores">Adaptadores</a><a href="#resultados">Resultados</a><a href="#achados">Achados</a><a href="#limites">Limites</a></nav>
""")
    P.append("""<h2 id="leitura">Para quem reimplementa</h2>
<p>Esta página é o contrato do procedimento. O GRAIN-REPRO implementa a partir só dela (sem ler
<code>src/bo/grain/</code>) e mede a concordância; desacordo vira emenda das regras ou UNKNOWN. São normativos:
as seções Evidência, Normalização, Identidade, Regras, Resolução, Saída C19, Instância e a tabela aspecto → alegação (Adaptadores), e o arquivo
<code>grain/grain_rules.yaml</code> (a parte executável das regras; seu sha256 está em <code>grain/RULES.sha256</code>).
O resto (resultados, achados) é informativo. Nenhuma regra cita provedor, prefixo de tipo ou sufixo de nome: o que
cada provedor diz entra pelos adaptadores de evidência, que são permitidos e ficam fora das regras.</p>
<p class="note">Em uma frase: para cada candidato a unidade, junta-se a evidência da API (identidade, chave de
importação, chave de nome, controlador de ciclo de vida, dono, alcance, ligação com a API); deriva-se a classe de
identidade; tenta-se G0 → G1 → G2 → G3 → G4 nessa ordem; a primeira regra cujo <i>match</i> vale decide, e se lhe
falta evidência o resultado é UNKNOWN com a lista do que falta, sem cair para a regra seguinte.</p>""")
    P.append("<h2 id=\"camadas\">Três camadas</h2>" + _table(
        ["camada", "o que é"], [[_code(k), e(v)] for k, v in doc["layers"].items()]) +
        "<p>Um candidato é um elemento da camada Terraform: um tipo de recurso (<code>tipo</code>), um bloco aninhado "
        "(<code>tipo.bloco.subbloco</code>) ou um grupo de atributos que a evidência liga a um aspecto da API "
        "(<code>tipo.bloco:grupo</code>). A unidade de domínio sai da camada de API (o rótulo vem dela); a camada "
        "Terraform é só embalagem e fica registrada em <code>layers.terraform</code>.</p>")
    ev_rows = [[_code(k), e(v["meaning"]), _code(v["claim"])] for k, v in doc["evidence"].items()]
    P.append(f"""<h2 id="evidencia">Evidência estruturada</h2>
<p>Cada campo é uma lista de alegações (uma por fonte). Toda alegação pode trazer <code>source</code> (item de evidência
do C00: nível publicado/derivado/interpretado e ref, doc ou citação) e <code>status: unknown</code> (a fonte não sabe)
ou <code>status: contradictory</code> (a fonte diz que as fontes divergem).</p>
{_table(["campo", "significado", "forma da alegação"], ev_rows)}
<h3>Consolidação de um campo</h3>
<ol><li>Alguma alegação com <code>status: contradictory</code> → <b>CONTRADICTORY</b>.</li>
<li>Descartam-se as alegações <code>unknown</code>. Nenhuma sobrou → <b>UNKNOWN</b>.</li>
<li>Normaliza-se cada alegação (listas ordenadas; <code>via</code> vira lista ordenada; booleanos ausentes = falso)
e compara-se por JSON canônico. Todas iguais → <b>KNOWN</b> com esse valor; senão → <b>CONTRADICTORY</b>.</li></ol>
<p>Ao lado das alegações, o adaptador entrega por candidato: <code>field_map</code> (nome canônico do campo →
<code>path</code> relativo no candidato, normalizador <code>norm</code>, <code>ref: true</code> se é referência,
<code>config: true</code> se é configuração, <code>by_name: true</code> se a referência é pelo nome de um elemento
irmão); <code>references</code> (campo de referência → candidato-alvo); <code>parent_role</code> (papel do pai
estrutural quando ele entra numa tupla de vínculo; padrão <code>parent</code>); <code>groups</code> (grupos de
atributos ligados a aspectos, com a evidência própria de cada grupo). Os nomes nas chaves de identidade são os
nomes canônicos do <code>field_map</code>, nunca o nome do provedor.</p>""")
    proc = "".join(f"<li><b>{e(s['step'])}</b>: {e(s['text'])}</li>" for s in doc["procedure"])
    P.append(f"""<h2 id="normalizacao">Normalização de cima para baixo</h2><ol>{proc}</ol>
<p><b>Coleção de objetos (T2, emenda GRAIN-A2)</b>: atributo cujo <code>tf_type</code> cty é
<code>["list"|"set", ["object", {{campo: tipo}}]]</code> (ou a forma nested_type <code>[modo, {{...}}, opcionais]</code>) vira
o candidato <code>tipo.bloco….atributo</code>, com nesting = o modo e atributos = os campos do objeto, recursivamente
para campos que também são coleções. Os sub-átomos <code>provedor:tipo:caminho.atributo.campo</code> são VIRTUAIS:
derivados do tipo cty, não do schema de blocos (os átomos do SCHEMA-* não são regenerados); o átomo da coleção
(<code>…atributo</code>) fica com a unidade do contêiner. O verificador de cobertura aceita sub-átomo virtual só sob um
átomo de coleção do C01. Lista de objetos com um só elemento não muda nada: a cardinalidade não decide.</p>
<p><b>Transparente (T0)</b> = api_resource KNOWN com <code>status: payload</code> E identity KNOWN com
<code>status: absent</code>. O pai efetivo de um transparente aninhado é o pai estrutural (já pulando outros
transparentes); o de um recurso de topo transparente é o alvo da única referência da sua chave de importação (sem
ela, não é transparente). Átomos de um transparente vão para a unidade do pai efetivo, com
<code>path_in_unit</code> = caminho a partir do bloco do pai (ou o caminho completo no próprio tipo, quando o pai
é outro recurso).</p>
<p><b>Ordem</b>: um nó depende do pai estrutural efetivo e dos alvos dos campos de referência citados nas
alegações de identidade, chave de importação, ciclo de vida, dono e alcance. Decide-se em ordem topológica (empate:
ordem lexicográfica do id, o que não muda nenhuma decisão porque cada uma só lê as dependências). Nó com dono em
dois ou mais campos (<code>owner.via</code> com 2+ itens) espera também todo nó com duas ou mais referências na
identidade (os vínculos possíveis), salvo se isso fechar ciclo. O que sobrar num ciclo sai
<b>UNKNOWN</b> com <code>identity</code> (<code>GRAIN-G0-CYCLE</code>).</p>""")
    cls = "".join(f"<li><b>{e(c['id'])}</b>: {e(c['when'])}</li>" for c in doc["identity_classes"])
    P.append(f"""<h2 id="identidade">Classe de identidade</h2>
<p>Notação: <code>idf</code>, <code>imp</code>, <code>nk</code> = identity, import_key, element_name_key
consolidados; R = campos com <code>ref: true</code> no field_map.</p>
<ol>
<li>Algum dos três CONTRADICTORY → CONTRADICTORY. Os três UNKNOWN → ABSENT.</li>
<li>api_resource KNOWN <code>payload</code> e <code>idf</code> não KNOWN → ABSENT.</li>
<li>Se <code>idf</code> = present: escopo, <code>surrogate</code>, <code>anonymous</code> vêm dele; chave própria da API =
key_fields fora de R (vazia se surrogate); referências da API = key_fields em R. Se <code>imp</code> = present:
referências = fields em R; chave própria = fields fora de R. Se <code>nk</code> = present: chave própria = fields.</li>
<li>As chaves próprias NÃO vazias das três fontes têm de ser o mesmo conjunto, senão CONTRADICTORY.
<code>idf</code> = absent com chave própria em <code>imp</code> ou <code>nk</code> → CONTRADICTORY; <code>nk</code> present
com <code>anonymous</code> → CONTRADICTORY.</li>
<li>Relativa ao pai = <code>idf</code> absent, ou escopo <code>within_parent</code>, ou <code>nk</code> present sem escopo
declarado. Relativa e aninhada → acrescenta-se a referência <code>$parent</code> (o pai estrutural efetivo).
Relativa, de topo, sem nenhuma referência e não absent → CONTRADICTORY.</li>
<li>Aninhado sem escopo, sem <code>nk</code>, sem referência e sem <code>idf</code> KNOWN → ABSENT.</li>
<li>Surrogate com <code>imp</code> UNKNOWN e sem <code>nk</code> → ABSENT (o id opaco não diz o que o objeto liga).
Surrogate sem chave própria e sem referência → chave própria = <code>$id</code>.</li>
<li>Resolve-se cada referência da chave (<code>$parent</code> e os campos). Alvo ausente ou decidido UNKNOWN →
UNRESOLVED.</li>
<li>O = chave própria; T = alvos (na camada de schema, um por campo, porque dois papéis podem ter o mesmo tipo; na
de instância, alvos distintos). Classes:</li></ol><ul>{cls}</ul>
<p><code>key_fields</code> do C19 = chave própria (sem <code>$id</code>) mais os campos de referência da chave (sem
<code>$parent</code>); se vazio e surrogate, os key_fields da alegação. <code>anonymous</code> = há chave própria, ela
não é nome (sem <code>nk</code> e alegação <code>anonymous</code>) e não é <code>$id</code>.</p>""")
    pred_rows = [[_code(k), e(v), _code(R.PREDICATES[k])] for k, v in doc["predicates"].items()]
    rule_rows = []
    for r in rs.rules:
        rule_rows.append([f"<b>{e(r.id)}</b>", str(r.priority), _code(r.grain), _code(r.match),
                          _code(r.needs) if r.needs else "—", _code(r.guard) if r.guard else "—",
                          _code(r.emit) if r.emit else (_code(r.missing) if r.missing else "—"), e(r.text)])
    po = "".join(f"<li><b>{e(x['id'])}</b> ({e(x['grain'])}): {e(x['text'])}</li>" for x in doc["procedural_outcomes"])
    P.append(f"""<h2 id="regras">Regras, em ordem de prioridade</h2>
{_table(["id", "prio", "grão", "match", "needs", "guard", "emit / missing", "texto"], rule_rows)}
<h3>Avaliação</h3><ol>
<li>Para cada regra em prioridade crescente: se algum predicado de <code>match</code> é falso, passa-se à próxima.</li>
<li>G0-IDENTITY casou → UNKNOWN; missing = <code>identity</code> + os campos de <code>also_missing_if_unknown</code>
que não estão KNOWN + ciclo de vida, dono e alcance cujo <code>via</code> aponta para uma referência não resolvida.</li>
<li>G0-NOMATCH (match vazio, sempre casa) → UNKNOWN; missing = os campos lidos pelos predicados de guard que
falharam nas regras anteriores, na ordem do C19, ou <code>identity</code> se nenhum.</li>
<li>Outra regra casou: se algum campo de <code>needs</code> não está KNOWN, ou está KNOWN mas o alvo do seu
<code>via</code> não resolve, o resultado é UNKNOWN (<code>GRAIN-G0-NEEDS</code>) com esses campos. <b>Não</b> se tenta a
próxima regra: falta de evidência nunca vira outro grão.</li>
<li>Senão avalia-se <code>guard</code>: todos verdadeiros → o grão da regra; algum falso → anota-se o campo lido e
passa-se à próxima regra.</li></ol>
<h3>Predicados</h3>{_table(["predicado", "verdadeiro quando", "campo lido"], pred_rows)}
<p>Grão de um alvo ainda não decidido conta como UNKNOWN. <code>owner_targets_count</code> e
<code>owner_targets_kind_in</code> leem os alvos do dono depois da troca por vínculo (seção Resolução).</p>
<h3>Desfechos do procedimento</h3><ul>{po}</ul>""")
    P.append("""<h2 id="resolucao">Resolução de ciclo de vida, dono, alcance e pontas</h2><ul>
<li><code>via</code> ausente: <code>$parent</code> se o nó é aninhado; senão, o único campo de referência da chave se T
tem uma unidade; senão nada (não resolve).</li>
<li>Ciclo de vida e alcance com kind <code>parent</code>/<code>container</code> resolvem um único alvo; dono com kind
<code>parent</code> resolve a lista de alvos de <code>via</code>. Kind <code>self</code>, <code>provider</code>,
<code>external</code>, <code>global</code> não tem alvo. Alcance <code>container</code> sem via usa o via do dono.</li>
<li>Alvo que não resolve (ausente ou UNKNOWN) torna o campo "faltando" para <code>needs</code> e para G0.</li>
<li>Dono com 2+ alvos: procura-se, entre os vínculos já decididos, um cujas pontas (multiconjunto ordenado) sejam
exatamente esses alvos; achou → o dono passa a ser esse vínculo (a faceta fica no vínculo). Não achou → o guard de
G3 falha e o resultado é UNKNOWN com <code>owner</code>. A alternativa "declarar a lista de donos" não cabe no C19
3.0.0 (owner é um só objeto); ver Achados.</li>
<li>Pontas do vínculo (G1): papel → alvo, para cada referência da chave; <code>$parent</code> recebe o papel
<code>parent_role</code>.</li>
<li>Pai emitido: G2 = alvo do ciclo de vida; G3 = alvo do dono (depois da troca por vínculo); G1, G4 = nenhum.</li></ul>""")
    P.append("""<h2 id="c19">Saída C19 (camada de schema)</h2>""" + _table(["campo", "valor"], [
        [_code("unit_id"), "<code>CU-&lt;provider&gt;-&lt;candidato&gt;</code> (candidato com <code>:</code> para grupo)"],
        [_code("kind"), "grão decidido"],
        [_code("layers.terraform"), "resource_type e block_path (blocos separados por ponto; ausente no topo)"],
        [_code("layers.domain_unit"), "rótulo da API (<code>api_resource.label</code>); sem ele, o último nome do candidato"],
        [_code("layers.api_resource"), "service e resource da alegação de API, quando os dois existem"],
        [_code("identity"), "evidence = fontes de identity/import_key/element_name_key; key_fields, anonymous e "
                            "occurrence_key = chave própria quando anônimo (senão vazio)"],
        [_code("endpoints"), "só em BINDING: <code>[{role, unit_id}]</code> ordenado por papel; <code>$parent</code> leva o "
                             "papel <code>parent_role</code> (C19 3.1.0)"],
        [_code("lifecycle_controller / owner / effective_scope"), "kind consolidado (UNKNOWN se está em missing) e ref = unit_id do "
                                                                 "alvo; owner leva o primeiro alvo (um só, depois da troca por vínculo)"],
        [_code("evidence"), "fontes de todas as alegações do candidato (sem repetição)"],
        [_code("rule_applied / missing_evidence"), "regra ou desfecho; campos que faltam na ordem identity, "
                                                   "lifecycle_controller, owner, effective_scope, api_resource"],
        [_code("canonical_atoms"), "um registro por atributo do schema: atom_id, unit_id da unidade (ou do pai efetivo do "
                                   "transparente), path_in_unit, role do C04 quando informado"]]))
    P.append("""<h2 id="instancia">Camada de instância e identidade de ocorrência</h2>
<p>Configuração: <code>{"provider", "resources": [{"type", "name", "values"}]}</code>; bloco single = objeto;
list/set = lista; referência = <code>{"$ref": "tipo.nome"}</code>; valor não resolvido =
<code>{"$unknown": motivo}</code>. Cada recurso, bloco presente e grupo com algum atributo presente vira um nó com a
evidência do seu candidato; transparentes como na camada de schema (o de topo segue o <code>$ref</code> da sua única
referência). Referência <code>by_name</code>: o valor é o nome de um elemento do candidato-alvo dentro do mesmo
recurso (chave de nome com um campo); um único casamento resolve, senão não resolve. O mesmo motor decide cada nó,
com as referências resolvidas entre ocorrências (alvos distintos).</p>
<p><b>Identidade de ocorrência</b> = sha256 (hex) do JSON canônico (chaves ordenadas, separadores <code>,</code> e
<code>:</code>, UTF-8 sem escape) de</p>
<div class="fx">{"grain": G, "label": rótulo, "parent": identidade do pai ou null,
 "endpoints": {papel: identidade da ponta}  (só vínculo),
 "key": {campo da chave própria: valor normalizado, campo de referência da chave que não é o pai: identidade do alvo}}</div>
<ul><li>ENTITY: parent null, key = chave própria. COMPONENT e FACET: parent = identidade do pai emitido. FACET: key vazia
(o rótulo distingue os aspectos). BINDING: endpoints.</li>
<li>Valor ausente ou simbólico num campo da chave, chave só <code>$id</code>, ou pai/ponta/alvo sem identidade →
ocorrência UNKNOWN com <code>identity</code>.</li>
<li>A posição textual nunca entra. Só entra como o campo <code>$index</code> (posição na lista), quando a evidência põe a
ordem na chave (onde o provedor deriva o índice da ordem).</li>
<li>Normalizadores: <code>str</code> (sem espaços nas pontas), <code>lower</code>, <code>int</code>, <code>bool</code>
(true/enabled/on/yes e false/disabled/off/no/suspended), <code>cidr</code> (rede canônica, sem bits de host),
<code>set_of_*</code> (lista ordenada sem repetição do JSON canônico de cada item), <code>ordinal</code> (= int).</li>
<li>Duas declarações com a mesma identidade: com a mesma configuração normalizada, uma ocorrência só (as duas
camadas Terraform anotadas); com configuração diferente, as duas UNKNOWN (<code>GRAIN-G0-DUPLICATE</code>).</li>
<li>Comparação entre embalagens: por ocorrência, (identidade, grão, rótulo, pai, pontas, chave, configuração
normalizada pelos nomes canônicos <code>config: true</code> do próprio nó e dos transparentes que sobem para ele,
referências simples fora da chave, regra, missing). A camada Terraform não entra.</li></ul>""")
    from . import c25_aspects as A
    tab = _table(["campo", "aspecto", "regra", "tradução"], [[_code(f), _code(a), e(r), e(x)] for f, a, r, x in A.TABLE])
    sc = _table(["provedor", "campos de escopo do provedor (fora da chave)"],
                [[_code(k), _code(sorted(v))] for k, v in sorted(A.PROVIDER_SCOPE_FIELDS.items())])
    P.append(f"""<h2 id="adaptadores">Adaptadores de evidência</h2><ul>
<li><b>FixtureAdapter</b>: a tabela <code>{{candidato: {{campo: [alegações], field_map, references, parent_role, groups,
roles}}}}</code>, usada pelos mundos sintéticos.</li>
<li><b>C25Adapter</b> (service_evidence.jsonl do SERVICE-EVIDENCE, C25 1.0.0). Se algum registro traz
<code>value.aspect</code> (a forma real do SERVICE-EVIDENCE), todos os fatos de grão do provedor passam pela tabela por
aspecto abaixo (emenda GRAIN-A1, CC-1). Fato afirmado sem aspecto segue a convenção anterior (T99).</li></ul>
<h3 id="aspectos">Tabela aspecto → alegação (normativa)</h3>
<ul><li>Nada é inventado: aspecto sem tradução, aspecto fora da tabela e fato com status unknown viram alegação UNKNOWN
com o motivo, que fica na fonte da alegação e nos motivos do relatório; a consolidação os ignora.</li>
<li>Dono da IDENTIDADE (identity_scope, parent, parent_attribute) não é dono da CONFIGURAÇÃO: nunca vira o campo
owner. Por isso, hoje, nenhum aspecto dá owner a um tipo de topo: só os blocos (block_config_owner) e os fatos T99.</li>
<li>destroy_effect <code>suspend</code> num recurso separado é indício de faceta do pai; <code>not_deleted</code> e
<code>state_only</code> dizem que o destroy não apaga, não quem apaga.</li>
<li>Bloco aninhado só ganha alegação com fato de <code>block_path</code>; sem ela é UNKNOWN pela G0, nunca FACET por
omissão. Aspecto de bloco sem ligação com a API (não há block_api) deixa o bloco UNKNOWN com api_resource.</li>
<li>Nenhuma heurística de nome: <code>block_schema.facet_word</code> não é lido; alvo de referência só pela chave
compartilhada (T02) ou por fato explícito.</li>
<li>Fonte de cada alegação traduzida: <code>{{level: derived, ref: evidence_id, note: "&lt;regra&gt;: &lt;fato&gt;/&lt;aspecto&gt;"}}</code>.
Ordem: primeiro todos os aspectos que não dependem de outro candidato; depois T02 (que lê o ciclo de vida já
consolidado dos pares), T21, T01/T10 com as referências e T40.</li></ul>
{tab}
<p>Campos de escopo do provedor (conhecimento do adaptador, permitido fora das regras; T20 acrescenta account_id e
region quando identity_scope os marca):</p>{sc}""")
    ex = pk["packagings"]
    pk_rows = [[_code(k), _code(v["schema_candidates"]), str(v["schema_units"]), str(v["instance_units"]),
                '<span class="ok">sim</span>' if pk["reorder_invariant"][k] else '<span class="no">não</span>']
               for k, v in ex.items()]
    pr_rows = [[e(c["case"]), '<span class="ok">OK</span>' if c["ok"] else '<span class="no">FALHA</span>',
                _code(c["detail"])] for c in pr["checks"]]
    cs_rows = [[e(r["commitment_id"]), {"REPRODUCED": '<span class="ok">reproduz</span>',
                                        "FAILED": '<span class="no">falha</span>',
                                        "OUT_OF_SCOPE": '<span class="unk">fora do alcance</span>'}[r["status"]],
                e(r.get("how") or ("decide: " + r.get("decided_by", "")))] for r in cs["rows"]]
    ck_rows = [[_code(k), '<span class="ok">OK</span>' if v["rc"] == 0 else '<span class="no">FALHA</span>',
                e(" ".join(v["output"]))] for k, v in ck["checkers"].items()]
    P.append(f"""<h2 id="resultados">Resultados (mundos sintéticos)</h2>
<h3>Quatro embalagens do mesmo contêiner de objetos</h3>
<p>Provedor sintético <code>{e(pk['provider'])}</code>. Assinaturas de schema iguais:
<b class="{'ok' if pk['schema_signatures_equal'] else 'no'}">{pk['schema_signatures_equal']}</b>; decomposições de instância
iguais: <b class="{'ok' if pk['instance_decompositions_equal'] else 'no'}">{pk['instance_decompositions_equal']}</b>;
reordenação de recursos, blocos e chaves em {pk['reorder_seeds']} sementes; controle de conteúdo (mudar o
versionamento muda a decomposição): {pk['content_control_changes']}.</p>
{_table(["embalagem", "candidatos de schema", "unidades (schema)", "ocorrências", "invariante à reordenação"], pk_rows)}
<h3>Saída UNKNOWN (bo.grain.unknown_exit)</h3>
<p>{st['mutants']} mutantes (apagar ou contradizer cada campo de cada candidato, e apagar toda a evidência de
identidade) em {st['worlds']} mundos: {st['became_unknown']} candidatos viraram UNKNOWN listando o campo mutado,
{st['changed_nodes']} nós mudaram, {len(ue['violations'])} violações; {st['named_cases']} casos nomeados dos
compromissos. Controle: as regras no estilo da v2 (o resto vira entidade) dão
{ue['control_v2_style']['violations']} violações, e a bateria as reprova.</p>
<h3>Prioridade (bo.grain.priority)</h3>{_table(["caso", "", "detalhe"], pr_rows)}
<h3>Verificadores do DECOMPOSE nos mundos sintéticos</h3>{_table(["verificador", "", "saída"], ck_rows)}
<h3>Lint de higiene (não é evidência de validade)</h3>
<p>{len(ln['problems'])} problema(s) em <code>grain/grain_rules.yaml</code>; {ln['mutants'] - len(ln['mutant_failures'])}/{ln['mutants']}
mutantes reprovados (provedor, provedor sintético, prefixo de tipo, prefixo sintético, predicado de sufixo, sufixo
de embalagem, curinga, chave de tipo).</p>
<h3>Compromissos do REQUIREMENTS com o GRAIN como consumidor</h3>{_table(["compromisso", "", "como"], cs_rows)}""")
    P.append("""<h2 id="achados">Achados e decisões (inclusive contra a hipótese)</h2><ul>
<li>A bateria de mutação achou um caso em que faltar a alegação de identidade de um recurso de carga útil o fazia
virar faceta incompleta sem listar <code>identity</code>: a chave de importação dava identidade emprestada, mas só a
alegação de identidade diz se o candidato é transparente. Correção: carga útil sem alegação de identidade é ABSENT.</li>
<li>Id opaco da API sem a chave de importação afirmada fazia uma anexação parecer entidade independente. Correção:
surrogate sem import_key KNOWN é ABSENT. Sem isso, faltar evidência viraria ENTITY.</li>
<li>Na camada de schema, um vínculo entre dois objetos do mesmo tipo (rede ↔ rede) tem alvos iguais; contar alvos
distintos o fazia parecer faceta. As pontas são contadas por papel no schema e por ocorrência na instância.</li>
<li>A prioridade G1 &gt; G4 pedida pelo plano é garantida em boa parte pela classe de identidade (uma chave só de
referências nunca é INDEPENDENT). A prioridade que de fato decide é G1 &gt; G2: numa anexação embutida com ciclo de
vida preso à instância, G1 e G2 aceitam a evidência, e trocar a ordem troca BINDING por COMPONENT (caso P4).</li>
<li>Elementos embutidos que se referem a irmãos pelo nome (regra → pool no balanceador embutido) precisam de
referência <code>by_name</code>; sem ela, o grafo embutido perde relações que o separado tem.</li>
<li>Emenda 0.1.1 (CC-1): a primeira versão lia uma convenção que o SERVICE-EVIDENCE nunca gravou; os testes
sintéticos usavam a mesma convenção e não pegaram. Entraram o adaptador por aspecto e testes com o arquivo real.</li>
<li>Emenda 0.2.4 — 2026-11-05T00:20-03:00 (motivo: <code>results/PILOT-EXIT/DIAG_T3.json</code>, PILOT-EXIT tentativa 3, E2
reprovado; F1, F2, F3 e F5 de classe "regra GRAIN", F4 de classe "adaptador" com a camada de instância do GRAIN). Cada
regra tem caso sintético e, quando o pin reproduz a classe, caso de calibração sobre o SERVICE-EVIDENCE com configuração
escrita no teste (<code>tests/grain/test_grain_diag_t3.py</code>; vermelho antes da emenda: 16 de 23, em
$BO_DATA/GRAIN/diag_t3/red_before.txt). Nenhuma fixture retida foi lida. <b>F1/F2 (T03)</b>: id composto (dois ou mais
atributos nomeados da configuração) de candidato sem outra alegação de identidade passa a ter tradução: identidade com
esses campos, relativa ao pai se um deles é referência tipada; com UMA referência tipada e nenhum ciclo de vida afirmado,
ciclo de vida, dono e alcance = o pai (o id é sintetizado do pai + campos próprios: a API não dá identidade nem vida
próprias), e o recurso separado sai COMPONENT do pai, como a forma embutida e como a variante irmã de id de API. Controles:
ciclo de vida próprio afirmado bloqueia a herança; id de um atributo só (opaco) segue sem tradução; dois campos com
referência na configuração não promovem nada. <b>Achado no dado real</b>: a variante de regra separada de id composto
da AWS não tem <code>reference_target</code> no campo do conjunto-pai no SERVICE-EVIDENCE do pin (só nos campos de origem
e de lista de prefixos); sem alvo tipado, o esquema não sabe qual campo da chave nomeia o pai, e a identidade fica
UNKNOWN (nunca independente por omissão): a unidade de esquema continua G0-IDENTITY. Na instância, o único campo da chave composta cuja
configuração é referência a um recurso é o pai (derivado, citado com o fato do id composto) e a regra sai COMPONENT do
grupo, igual ao bloco embutido e à outra variante (teste de calibração). A unidade C19 de esquema que o PILOT-NET-GLOSS
regenera continua UNKNOWN para esse tipo até o SE publicar o alvo tipado. <b>F3/F5 (T51c)</b>: referência com valor
simbólico (var., data. ou module.) vira ponta externa identificada só pelo símbolo, com ou sem alvo tipado (antes, só
com alvo tipado); o pai simbólico é o símbolo; vínculo com ponta simbólica tem identidade = (símbolo, alvo); o tipo,
quando há, não entra na identidade da ponta. Valor computado continua sem ponta (CMT-NIC-U02). <b>F4 (T59c)</b>:
repetição idêntica de elemento anônimo é multiconjunto só com evidência de que a repetição é aceita (o OBSERVED da
security list da OCI tem <code>duplicates_accepted</code>); repetição inválida ou idempotente funde as declarações com
nota; sem evidência, as declarações saem UNKNOWN (desfecho novo GRAIN-G0-REPEAT); o teste antigo que fundia a regra
anônima repetida em silêncio foi trocado por três (sem evidência, idempotente, aceita). <b>Fronteira com o PILOT-NET-E2E</b>
(que corrige o adaptador em paralelo): a ocorrência passa a expor <code>parent_symbol</code> (o símbolo do pai),
<code>endpoint_symbols</code> (papel → símbolo), <code>name_key</code> (chave de nome do elemento, calculada mesmo
quando o pai não resolve) e <code>multiplicity</code> ({index, count, evidence, rule} da repetição); o adaptador lê
esses campos para escrever o pai, a chave de ocorrência e as pontas, e não deduplica ocorrências que o GRAIN dá como
distintas. O símbolo <code>local.</code> fica fora (o padrão de símbolo do C19 só aceita var., data. e module.).
Medida: calibração NET 45/45 com as unidades do GLOSS, reordenação 45/45, embalagem 3/3; só com o GRAIN 33/45, igual à
0.2.3; STO 21/21, reordenação 1455/1455, embalagem 80/80; no esquema real das fatias NET e STO (164 candidatos), nenhuma
decisão muda (grão, regra, falta e pai iguais aos da 0.2.3).</li>
<li>Manutenção 0.2.3 — 2026-11-04T23:06-03:00 (CC-NET-6 do PILOT-NET-GLOSS; nenhuma lógica muda): o rule_id da regra G1b
passa a <code>GRAIN-G1B-REFERENCE</code>, no padrão rule_id do C00 (<code>^[A-Z][A-Z0-9]*(-[A-Z0-9]+)+$</code>); o
nome antigo, com letra minúscula, fazia o canonical_units reprovar. Teste novo confere todo rule_id do GRAIN (regras e
desfechos do procedimento) contra o padrão do C00.</li>
<li>Emenda 0.2.2 — 2026-11-04T22:47-03:00 (regra G1b, decisão do coordenador por coerência interna, não por número). O
mesmo fenômeno saía de dois jeitos: o elemento de <code>vpc_security_group_ids</code> da AWS, guardado no atributo da
instância, saía BINDING (R-GRAIN-LISTELEM: ciclo de vida do dono); a associação NSG↔NIC/subnet do Azure, guardada no
campo <code>networkSecurityGroup</code> da NIC/subnet (OBSERVED), era recusada pela G1 porque o dono observado é a NIC.
Nos dois casos uma referência guardada na origem liga duas unidades. <b>G1b</b>: a unidade que É uma referência tipada
entre duas unidades — identidade emprestada da origem e um campo que a evidência descreve como a ligação da origem a uma
unidade-alvo (anexação da spec, attachment_attribute), com alvo tipado — sai BINDING entre a origem e o alvo, mesmo
quando o armazenamento e o ciclo de vida são da origem; registra <code>stored_in</code> = origem (item de evidência
<code>stored_in=&lt;unit_id&gt;</code> no C19) e ciclo de vida = origem. Isso separa onde está guardado do que é, e
<b>unifica o LISTELEM da AWS e a associação do Azure</b>. A origem pode ser externa à decomposição (como na G1, A16); o
alvo do campo de anexação passa a ser dependência de decisão. Controles negativos: sem o fato de anexação, a
referência é só atributo da origem (FACET); anexação descrita num atributo sem referência tipada a unidade não vira
vínculo; atributo escalar comum continua FACET/atributo. Medida na calibração: NET 40/42 com o cache por tipo
recalculado pelo caminho do GLOSS (restam as 3 regras do NSG OCI, alcance em disputa aberta, à espera da R6) e
31/42 só com o GRAIN (na instância a NIC/subnet das fixtures não tem nome nem grupo na configuração, então a origem
não se resolve); STO 21/21; invariância de reordenação e embalagem nos dois modos.</li>
<li>Emenda 0.2.1 — 2026-11-04T22:30-03:00 (T51b, opção A do pedido de mudança; C19 3.2.0, emenda 14 do CONTRACTS):
referência tipada com valor simbólico (var., data. ou module.) vira ponta externa do tipo do alvo, identificada pelo
símbolo; no C19 a ponta é <code>{role, kind: EXTERNAL, symbol, target_type}</code>, sem unit_id. Valor computado ou
desconhecido de outra forma não é símbolo e não vira ponta: o compromisso CMT-NIC-U02 (interface separada com
referência computada) continua UNKNOWN. A G1 passa a aceitar a ponta EXTERNAL, como aceita SELECTOR; sem isso a
ligação com alvo externo caía na G2 e saía COMPONENT, contra a A7. O pedido em results/GRAIN/CONTRACT_CHANGE.txt fica
atendido. Disputa <code>resolvida-por-publicação</code> (C25 1.6.x) confirmada no adaptador (R6, 0.2.0).</li>
<li>Complemento da 0.2.0 — 2026-11-04T22:15-03:00 (sem regra nova): disputa com status
<code>resolvida-por-publicação</code> (R6 do PREREG, b7f804d) vale o lado reproduzido, como a
<code>resolvida-por-observação</code> (R2). Fatos do SE CC-14 (3ba4079) conferidos no adaptador: estado de conexão,
efeito "só permite", precedência e suporte a tag/TTL não são fatos de grão e ficam fora; os
<code>reference_target</code> entram pela T44; <code>rule_applies_to</code>, <code>spec_field</code>,
<code>spec_member</code> e <code>delete_blocked_while_referenced</code> não têm tradução na tabela e entram como
alegação desconhecida, sem voto (o alcance da regra do NSG OCI segue pela disputa, hoje aberta).</li>
<li>Emenda 0.2.0 — 2026-11-04T21:40-03:00 (ciclo v4, depois do PILOT-EXIT 2/2; ajuste olhando só a calibração).
<b>(a) Item sem id do provedor = COMPONENT anônimo do dono (T59b)</b>. Ocorrência = (pai, caminho, conteúdo configurado,
índice de multiplicidade), independente da posição. Justificativa pelo OBSERVED (OBS-GAPS, OCI, 2 repetições com
controle): a regra da security list não tem id, a lista é substituída inteira e aceita duplicata. O item não tem nome
nem id, mas é membro distinto da coleção do dono, com semântica própria (direção, protocolo, estado por regra) e
ciclo de vida preso ao dono: é unidade, não aspecto (não é um por pai) nem carga transparente (o domínio o emite e
compara). Como a duplicata é aceita, duas regras iguais são dois membros (índice de multiplicidade); como a lista é
substituída inteira, a posição não identifica. "Sem id" no schema (block_identity absent) e no experimento
(item_identity has_id=false) dizem a mesma coisa e viram a forma anônima, sem disputa. O mesmo vale, na instância,
para o bloco cuja chave de API o provedor atribui depois da criação (regra embutida do grupo de segurança AWS): sem o
valor na configuração, a ocorrência é por conteúdo, o que fecha a limitação A12 (a regra embutida e a separada saem
iguais também sem o cache por tipo). Chave própria simbólica não entra (controle). Substitui a decisão "valor-lista
do dono, sem unidade" da 0.1.11 para esse caso. <b>(b) T51b</b>: NÃO aplicada — conflita com o compromisso
CMT-NIC-U02 ("referência simbólica não resolvida não vira anexação"); pedido em results/GRAIN/CONTRACT_CHANGE.txt.
<b>(c) Associação NSG↔NIC/subnet do Azure</b>: os fatos OBSERVED de ciclo de vida e dono (= a NIC/subnet, via o campo
de referência) não chegavam à decisão porque a T56b tirava a referência do campo que também é a chave de API da
associação (R-ID-SPEC-ATTACH); sem a referência, o via do pai não resolvia. Agora o campo que a evidência dá como via
do pai continua referência. O alcance que faltava sai pela regra declarada T47 (a anexação descrita pela spec,
attachment_attribute, vale onde está anexada: alcance próprio). Com isso, pelas regras declaradas: identidade
emprestada da NIC/subnet, ciclo de vida e dono do pai → G3 FACET; a da subnet sai FACET da subnet, a da NIC fica
UNKNOWN por falta de ponte de API (api_resource). O gabarito diz BINDING; a G1 exige dono = a própria associação e o
OBSERVED diz que o dono é a NIC/subnet: divergência declarada, não ajustada. <b>(d) Alcance da regra do NSG OCI</b>
(doc self × spec parent): aguarda o SE; segue CONTRADICTORY. <b>T31 (CC-NET-3 do PILOT-NET-GLOSS)</b>: a política de
remoção do Terraform (argumento deletion_policy, o que o terraform destroy faz) fica fora da decisão de grão, como
dono, ciclo de vida e alcance da camada Terraform; só a política da API (layer api) conta. Medida: calibração NET
31/42 com o cache por tipo recalculado e 30/42 só com o GRAIN, invariância de reordenação e embalagem nos dois; STO
21/21 com invariância.</li>
<li>Propostas para a fase 2 — 2026-11-04T18:40-03:00 (NÃO aplicadas; decisão do coordenador: o GRAIN fica congelado
em ed1fc66 até o PILOT-EXIT 2/2; nenhuma regra muda). Origem: diagnóstico "só GRAIN" na calibração NET (sem o cache por
tipo do PILOT-NET-GLOSS: 13/42 e o par AWS embutido × separado quebra; com o cache recalculado pelo caminho do GLOSS na
0.1.11: 24/42 e embalagem invariante; mesma quebra já na 0.1.9, então não é regressão). Limitação declarada (A12): bloco
cuja chave de API é atribuída pelo provedor depois da criação (ex.: id da regra do grupo de segurança herdado do tipo
gêmeo) decide o grão no esquema, mas na instância fica sem identidade de ocorrência, porque o endereço do bloco é
posicional; o recurso separado usa o endereço (T59). <b>T59b (proposta)</b>: esse bloco ganharia um símbolo de
ocorrência = (ocorrência do pai, caminho do bloco, conteúdo configurado), independente da posição; muda só a identidade
da ocorrência, não o grão (cuidado: tem a forma da chave por conteúdo recusada para a regra da security list sem id).
<b>T51b (proposta)</b>: referência tipada com valor simbólico (variável) viraria ponta externa identificada pelo
símbolo, como a T51 faz para referência fora da configuração; resolveria o pai simbólico da regra separada e a
anexação por variável.</li>
<li>Manutenção de teste — 2026-11-04T18:20-03:00 (sem mudança de regra; GRAIN congelado na 0.1.11): o SE publicou os
fatos OBSERVED (365e6ed) e as 2 disputas de dono e ciclo de vida da regra de NSG OCI ficaram
<code>resolvida-por-observação</code> a favor da spec. O teste CC-8 exigia CONTRADICTORY para toda disputa; passa a
exigir CONTRADICTORY só para disputa aberta e o lado reproduzido para disputa resolvida, como a R2 já fazia.</li>
<li>Emenda 0.1.11 — 2026-11-04T17:15-03:00 (adendo de 04/11 §2, C25 1.4.0, regra de consolidação do PREREG de
17:05 e revisão adversarial). <b>OBSERVED</b>: o fato <code>observed</code> entra com esse nível na citação (run,
repetições e controle na nota). <b>Consolidação R1–R5</b> (substitui a proposta anterior "OBSERVED prevalece", que não
entrou): R1 nada é sobrescrito; R2 disputa PUBLISHED × PUBLISHED já registrada (spec_disputes) com status
<code>resolvida-por-observação</code> vale o lado reproduzido, e o fato vencido continua citado sem voto
(<code>R-GRAIN-R2</code>); R3 OBSERVED que contradiz PUBLISHED sem disputa prévia abre disputa: o campo fica
CONTRADICTORY; R4 OBSERVED num campo sem fato publicado preenche o campo; R5 vale para qualquer resultado.
<b>Item da lista sem id (T64)</b>: identity absent e, com a ponte para o campo-lista (T62), carga útil do pai; pela
procedura T0 o item é transparente: <b>valor-lista do dono, sem unidade própria</b>. Não há chave declarada nem por
conteúdo, então não sai COMPONENT (o gabarito diz COMPONENT: a divergência é resultado, não ajuste). <b>Item com id que
não existe sem o pai</b> (regra do NSG OCI): a referência ao pai entra na chave como pai de caminho e, com ciclo de vida
próprio de API, sai COMPONENT do pai pela G2-CHILD; controle: sem a dependência do pai, não. <b>Cascata do
namespace</b>: <code>cascade_delete_by</code> só com evidência de cascata do TIPO de namespace
(<code>namespace_cascade</code> com cascade, ou <code>destroy_effect</code> cascade); contêiner que precisa estar vazio,
ou sem evidência, continua namespace (G4-NS) sem a relação. Antes, a G4-NS emitia a relação para todo namespace
(inclusive o compartimento OCI, que exige estar vazio): corrigido; o grupo de recursos do Azure só ganha a relação
quando o SE publicar o fato; o projeto GCP é campo de escopo, fora da chave. <b>SELECTOR e EXTERNAL</b> são nós de
ponta (seletor por predicado; contêiner fora da decomposição), não grãos: o C19 os cita só como ponta
(<code>endpoints</code>), nunca como <code>kind</code>; o texto da emenda A7 ("grão EXTERNAL") fica corrigido aqui.
Testes com fatos sintéticos no formato do C25 OBSERVED em tests/grain/test_grain_observed.py. Depois desta emenda o
GRAIN congela até o PILOT-EXIT 2/2.</li>
<li>Emenda 0.1.10 (rodada final antes do PILOT-EXIT 2/2; E2 NET da calibração com 37 tipos UNKNOWN). Por que a
R-GRAIN-LISTELEM não cobriu as anexações por <code>vpc_security_group_ids</code>: ela dá ciclo de vida, dono e
alcance a um elemento de ligação que JÁ existe, e a ligação só nascia de fato do SERVICE-EVIDENCE sobre o atributo
(alvo tipado, frase da doc, anexação ou seleção); o SE não tem nenhum fato sobre esse atributo, então não havia
ocorrência. Entrou a R-GRAIN-LISTREF (T61, derivada): atributo-lista de escalares do dono, sem fato do SE, cujos
elementos são referências a recursos na configuração vira ligação com citação do átomo do schema; elemento literal
ou simbólico não cria ligação; fato do SE prevalece. Entrou também a leitura da ponta FACET como a unidade dona da
faceta (a faceta não tem identidade própria): sem ela, a lista dentro de um bloco-faceta sairia COMPONENT da faceta
e a mesma lista no recurso sairia BINDING. Nenhuma das duas decide sozinha: o vínculo segue UNKNOWN enquanto o dono
for UNKNOWN (o dono é ponta e a G1 lê o grão dele). O que falta é evidência do SE, não regra: dono
<code>aws_instance</code> sem ciclo de vida, dono e alcance na camada de API e com ponte sem recurso; dono
<code>oci_core_instance</code> sem identidade de API e bloco <code>create_vnic_details</code> sem ponte; associações
azurerm sem identidade (a da NIC também sem ciclo de vida e dono de API); regras da security list sem ponte. Com
esses fatos postos à mão (contrafactual, não é resultado), as 14 anexações AWS por referência e as 2 OCI saem
BINDING; a AWS por variável simbólica segue UNKNOWN. Sensibilidade: esquema e STO não mudam; na instância NET a
LISTREF cria 14 ocorrências AWS e 8 azurerm (lista de NICs da VM), todas UNKNOWN pelo dono. A ponte nova do SE para
as regras da security list OCI aponta um campo-lista de itens (<code>list[IngressSecurityRule]</code>): pela T49 cada
regra viraria FACET (aspecto do pai), o que o objeto da API não sustenta — cada bloco é UM item da coleção. T62: essa
ponte não vira aspecto e, sem identidade do item (nome ou conteúdo) na evidência, FACET e COMPONENT anônimo não se
distinguem; as 11 regras seguem UNKNOWN em api_resource, agora com esse motivo (na instância OCI, 8 ocorrências que a
T49 daria FACET passam a UNKNOWN; o esquema OCI perde as 2 FACET das regras). Relatório em
$BO_DATA/GRAIN/listref_sensitivity.json. T63: o aspecto novo do SE <code>attachment_attribute</code> (campo da spec que liga o dono ao alvo, casado ao atributo pela leitura do modelo) vira ligação com alvo tipado; o nível INTERPRETED e o model_id vão para a citação e não são promovidos; com ele a ligação AWS vem do SE e a LISTREF deixa de ser usada ali. T56b refinada: com a identidade de API da regra de NSG relativa ao pai (R-ID-SPEC within_parent) e a do NSG com o grupo de recursos na chave, a referência tipada ao pai ou ao contêiner de namespace continua referência (antes virava campo próprio, dando identidade contraditória e perdendo a G4-NS); o controle negativo da G4-NS passa a tirar também a identidade de API independente, que sozinha decide.</li>
<li>Emenda 0.1.9 (PILOT-EXIT 1/2: o E2 NET reprovou porque a camada de instância não tinha as regras 0.1.5–0.1.8): a
instância aplica agora contêiner externo (T51: <code>$ref</code> fora da configuração ou id literal), faceta implícita
(T57), fora do domínio (T45), bloco repetido de coleção de objetos detectado pela evidência (T2) e o namespace do pai
herdado pelo bloco (T52b). Ligação por atributo-lista de referências e seleção por valor (rótulo) viram candidato
<code>&lt;tipo&gt;:&lt;atributo&gt;</code> e uma ocorrência por elemento (T58): a identidade é (dono, alvo); a decisão só sai
com fatos da ligação (attribute = o atributo) — sem eles, UNKNOWN com o que falta; seleção aponta um seletor externo,
sem grão. Recurso de topo de id opaco é identificado pelo endereço do recurso (T59, símbolo por configuração); bloco
de id opaco não (o endereço do bloco é posicional e quebraria a invariância à reordenação). Pontes que nomeiam o
mesmo recurso com nomes de serviço diferentes entre a doc e o SDK da spec (iaas × core) são uma só (T53).
Decisão do coordenador incluída na 0.1.9 (T60): a seleção por rótulo é VÍNCULO com um nó SELECTOR. O seletor não é
recurso e não tem ciclo de vida: é o predicado (chave do seletor e valor), com identidade = predicado normalizado
(dois donos que selecionam o mesmo rótulo apontam o mesmo seletor). A G1 aceita a ponta SELECTOR só quando a
evidência descreve o atributo, com citação, como seleção ou alvo por rótulo (alcance por anexação com "applies_to",
ou fato selection); sem isso segue UNKNOWN. Lista de ids de recurso com referência tipada é referência, nunca
seletor (controle negativo). O elemento de atributo-lista é valor escalar do dono: dono da configuração = a própria
associação (não há outra configuração), ciclo de vida = o do dono (some quando o dono deixa de listá-lo), alcance
próprio; fatos da ligação, se houver, prevalecem. O gêmeo pode apontar o bloco correspondente (twin_block_path), e
a identidade de API prevalece sobre a de bloco derivada do schema (T56c): com isso, o E2 STO do lifecycle_rule
embutido × rule do recurso separado sai igual (COMPONENT sob a faceta de configuração de ciclo de vida, implícita no
embutido).
Condições do coordenador para a derivação do elemento de atributo-lista (R-GRAIN-LISTELEM): é alegação DERIVADA com
citação do átomo do schema que prova que o atributo é do dono (ref = provedor:tipo:caminho), nunca default
silencioso; fato do SERVICE-EVIDENCE sobre o atributo entra junto e, se diverge, o campo fica CONTRADICTORY (não há
sobrescrita). Sensibilidade (dado da iteração 2): só a fatia NET depende dela — google 4 vs 3 unidades no esquema e
96 vs 58 ocorrências na instância (as 38 seleções), oci 25 vs 18 na instância (7 anexações por lista); STO não muda.
Relatório em $BO_DATA/GRAIN/listelem_sensitivity.json.</li>
<li>Emenda 0.1.8 (faceta implícita, T3/T57, decisão do coordenador): quando a API só aceita os blocos como membros
de um único objeto-faceta do pai, configurado por uma operação única sobre o pai (ex.: a configuração de ciclo de vida
do contêiner, com as regras como membro, gravada por uma só operação sobre o contêiner), a forma embutida — que não
tem esse nível — ganha a faceta implícita <code>&lt;pai&gt;:&lt;faceta&gt;</code>, FACET do pai, e os blocos pendem
dela, como na forma separada. Justificativa: o objeto da API é o mesmo nas duas embalagens; sem o nível, a forma
embutida poria as regras como componentes diretos do contêiner e o E2 divergiria por construção. Condições: só com
fato da spec no bloco (<code>spec_facet_member</code> ou <code>implicit_facet</code>, com <code>operation</code> citada e
<code>single_operation</code>); id determinístico por pai e faceta; <code>implicit=true</code> e a citação da spec nos
itens de evidência do C19. Sem a operação citada não há faceta implícita; bloco que a API aceita sozinho, por operação
própria de criar/apagar (<code>spec_operation</code> no bloco), também não (controles negativos nos testes). Na 0.1.9 a camada de instância também ganha o nível.</li>
<li>Emenda 0.1.7 (regra nova G2-CHILD, decisão do coordenador): um sub-recurso com CRUD próprio na API continua
sendo parte do pai; ter API própria não o torna entidade independente. Justificativa: a identidade dele só existe
dentro do pai (o caminho da spec o põe abaixo do pai, …/pai/{p}/filho/{f}), o pai o apaga em cascata, e as operações
próprias só mudam QUEM pode criá-lo e apagá-lo sem mexer no resto do pai, não a quem ele pertence. A regra exige: classe
WITHIN ou REF_TUPLE_PLUS em que as referências da chave que não são namespace apontam para UM pai marcado pela
evidência como segmento de caminho acima (T54: o tipo de API da ponte está aninhado no tipo de API do pai de
contenção; no bloco gêmeo, o pai estrutural herda a marca) e ciclo de vida de API publicado self. Sai COMPONENT do
pai, com <code>own_api_lifecycle=true</code> e <code>cascade_delete_by</code> apontando o pai (itens de evidência no
C19). Junto: G1 passa a contar as pontas sem os contêineres de namespace (senão a regra filha virava vínculo entre o
pai e o grupo de recursos), e T52b leva a marca de namespace do pai ao filho. Controles negativos: a entidade sob
namespace (G4-NS) continua ENTITY; faceta sem CRUD próprio continua FACET; filho sem ciclo de vida self segue a G2
comum; sem a marca de caminho, segue UNKNOWN.</li>
<li>Emenda 0.1.7, ainda (fatos de API da regra de SG da AWS, SE ce1e590): a identidade de API da regra
(SecurityGroupRuleId) contradizia a identidade de recurso do Terraform (<code>id</code>), e uma referência tipada tirada
da frase da doc punha o próprio identificador como referência a outro tipo. A identidade da camada de API agora
prevalece (T56, T56b), e o pai sem via é resolvido pelo recurso pai da spec (T55). Resultado: regra embutida e regra
separada saem COMPONENT do SG pela G2 comum (ciclo de vida do pai), e o E2 decide igual nos três pares.</li>
<li>Emenda 0.1.6, ainda: com o SERVICE-EVIDENCE do CC-10 (767bb22), pontes que nomeiam o mesmo recurso com grafia
diferente (doc "objectstorage/Bucket" e spec "object_storage/bucket") contradiziam-se; T53 as unifica. Blocos que
herdam do gêmeo (T09) podem sair FACET quando o gêmeo tem ligação de API de aspecto: é evidência herdada, não
omissão.</li>
<li>Emenda 0.1.6 (regra nova G4-NS, decisão do coordenador): identidade qualificada por um contêiner de NAMESPACE
(grupo de recursos, compartimento; conta, região e projeto já eram escopo do provedor) não é composição. Justificativa:
o contêiner de namespace só dá unicidade ao nome; a configuração e o ciclo de vida de API da unidade são dela, e o
apagamento em cascata pelo namespace é efeito do contêiner, registrado como relação <code>cascade_delete_by</code>
(item de evidência <code>cascade_delete_by=&lt;unit_id&gt;</code> no C19 e relação nos verificadores), nunca como dono nem
como ciclo de vida do pai. A regra exige: classe WITHIN ou REF_TUPLE_PLUS com TODAS as referências da chave marcadas
namespace pela evidência (T52), ciclo de vida de API self, dono self e ligação de API de recurso. Sem a marca, a
contenção segue composição e o resultado segue UNKNOWN; uma faceta verdadeira (ciclo de vida do pai) nunca passa,
porque o guard pede self (controle negativo nos testes).</li>
<li>Emenda 0.1.5 (T51, pai fora da fatia): o grupo de recursos do Azure deixou de impedir a identidade (contêiner
externo). Achado: o NSG e a conta de armazenamento passam de UNRESOLVED a G0-NOMATCH com lifecycle_controller,
porque a identidade é relativa ao grupo de recursos e o ciclo de vida de API publicado é self; G2 pede ciclo de vida
preso ao pai e G4 pede identidade independente. A evidência não exprime "apagado pela própria operação E em cascata
pelo grupo"; fica UNKNOWN até a evidência ou uma emenda de regra (depois do GRAIN-REPRO) decidir.</li>
<li>Emenda 0.1.4 (CC-8): com os fatos da spec (R-BRIDGE-SPEC, R-LIFE-SPEC, R-LIFE-SPEC-PARENT, R-OWN-SPEC, camada de
API) o contêiner da AWS decide (ENTITY) e o bloqueio de acesso público separado decide FACET dele. Três defeitos do
adaptador apareceram só com esse dado: a ponte (status resource) contradizia o suspend (status aspect) — T49; o
suspend sem via contradizia a spec com via bucket — T50; e a chave compartilhada tinha duas raízes com ciclo de vida
próprio — o desempate pelo parent_resource da spec (T02). As 12 disputas spec × doc saem CONTRADICTORY, de
propósito. As demais facetas separadas da AWS ficam UNKNOWN só por effective_scope (o alcance de API ainda não é
publicado para elas).</li>
<li>Emenda 0.1.3 (CC-1d, CC-1e): a herança do gêmeo testava <code>via in conjunto</code> antes de ver se via era
lista (TypeError no azurerm). Fatos de API sem aspecto (R-OWN-API, R-LIFE-API, R-SCOPE-SELF com layer api) são
consumidos; com layer terraform continuam recusados. Achado no caminho: com a referência tipada ao contêiner fora
da chave, um escopo de criptografia filho da conta saía ENTITY; a contenção (owner/parent) agora põe essa
referência na chave, e o caso volta a UNKNOWN (contêiner sem decisão), que é o que a evidência sustenta.</li>
<li>Emenda 0.1.2 (CC-1b, CC-1c): o adaptador 0.1.1 era anterior aos fatos de gêmeo, referência tipada e timeouts
do SERVICE-EVIDENCE; os blocos embutidos saíam com "twin_type sem tradução" e o E2 não chegava ao grão. Achado no
caminho: os fatos block_* do bloco (camada Terraform) contradiziam a identidade herdada do gêmeo; a evidência do
gêmeo agora substitui a do bloco. Fatos sem aspecto com layer terraform (R-OWN-TOP, R-LIFE-TF) não viram dono de
tipo de topo nem ciclo de vida: aceitá-los faria toda faceta separada dona de si.</li>
<li>Emenda 0.1.1 (CC-NET-1): regras embutidas como atributo lista/conjunto de objetos não viravam unidade; agora
viram bloco repetido (T2) com sub-átomos virtuais, e embutido × separado dá a mesma decomposição com a mesma
evidência de API.</li>
<li>A emenda 3.1.0 do C19 (CONTRACTS) trouxe <code>endpoints</code> e <code>owner.refs</code>, propostos aqui: as pontas
do vínculo saem em <code>endpoints</code> (antes iam em <code>identity.evidence</code>). Faceta de vários donos SEM vínculo
entre eles continua UNKNOWN com <code>owner</code> nas regras 0.1.1; usar <code>owner.refs</code> para ela é decisão de
regra (G3 tem um só pai) e fica para emenda depois do GRAIN-REPRO. O C25 1.0.0 não tem fact_kind para chave de nome
nem para alvo de referência; a convenção de <code>value</code> acima os carrega.</li></ul>""")
    P.append("""<h2 id="limites">Limites</h2><ul>
<li>Tudo aqui roda em mundos sintéticos (provedores <code>provider_a</code> a <code>provider_h</code>); os 4 schemas reais
entram no DECOMPOSE, e o GRAIN-REPRO roda os gabaritos adversariais reais.</li>
<li>A qualidade da decomposição é a da evidência: o procedimento não inventa identidade, dono, alcance nem ciclo de
vida; onde a evidência falta, o resultado é UNKNOWN, e o número de UNKNOWN é resultado, não defeito a esvaziar.</li>
<li>Dado real (SERVICE-EVIDENCE da onda atual, medido por <code>python -I -m bo.grain.realdata</code> e pelos testes
<code>test_grain_real_*</code>): a fatia de armazenamento não levanta mais EvidenceError, mas os contêineres dos quatro
provedores saem UNKNOWN, porque faltam fatos, não tradução: nenhum aspecto dá dono da configuração a tipo de topo; o
ciclo de vida do contêiner é not_documented (AWS, Azure, OCI) ou só tem deletion_policy sem valores (Google); a
ponte de API é UNKNOWN na AWS e no Google; a chave compartilhada da AWS não tem raiz com ciclo de vida self; a
contenção do Azure não diz o atributo de referência. Com o gêmeo (T09) e a referência tipada (T44), o E2 no dado
real sai igual para SG ingress, SG egress e NSG security_rule (mesmo grão, regra, falta, rótulo e relações; os dois
lados ainda UNKNOWN pela mesma falta). Os controles positivos dos testes mostram que, com esses
fatos, o mesmo caminho decide o contêiner (ENTITY), a faceta separada (FACET) e a regra embutida igual à separada
(COMPONENT, mesmas relações).</li>
<li>O lint é lexical e de higiene; validade vem dos compromissos, do GRAIN-REPRO e dos pilotos.</li>
<li>Regras provisórias: mudam só por emenda versionada depois do GRAIN-REPRO e do PILOT-EXIT.</li></ul>
</main></body></html>
""")
    return "".join(P)


def build(check: bool) -> int:
    rs = R.load()
    doc = yaml.safe_load(rules_path().read_text(encoding="utf-8"))
    buf = io.StringIO()
    with redirect_stdout(buf):
        ue = unknown_exit.run(rs)
        ctl = unknown_exit.run(unknown_exit.broken_rules(rs))
    ue["control_v2_style"] = {"violations": len(ctl["violations"]), "detected": not ctl["ok"],
                              "sample": ctl["violations"][:5]}
    reps = {"unknown_exit": _strip(ue), "priority": _strip(priority.run(rs)), "packaging": _strip(packaging_report(rs)),
            "checkers": _strip(checkers_report()), "commitment_suite": _strip(suite.run()), "lint": _strip(lint_report())}
    bad = []
    if not ue["ok"] or not ue["control_v2_style"]["detected"]:
        bad.append("unknown_exit")
    if not reps["priority"]["ok"]:
        bad.append("priority")
    if not (reps["packaging"]["schema_signatures_equal"] and reps["packaging"]["instance_decompositions_equal"]
            and all(reps["packaging"]["reorder_invariant"].values())):
        bad.append("packaging")
    if not reps["checkers"]["ok"]:
        bad.append("checkers")
    if reps["commitment_suite"]["failed"]:
        bad.append("commitment_suite")
    if reps["lint"]["problems"] or reps["lint"]["mutant_failures"]:
        bad.append("lint")
    if bad:
        print(stamp(f"build: resultados reprovados, nada gravado: {bad}"), file=sys.stderr)
        return 1
    R_ = repo()
    files: dict[Path, str] = {}
    for k, v in reps.items():
        files[results_dir() / f"{k}.json"] = dump_json(v)
    html_text = render(doc, rs, reps)
    files[R_ / "grain" / "GRAIN.html"] = html_text
    rules_text = rules_path().read_text(encoding="utf-8")
    sha = lambda s: hashlib.sha256(s.encode("utf-8")).hexdigest()  # noqa: E731
    files[R_ / "grain" / "RULES.sha256"] = (f"{sha(rules_text)}  grain/grain_rules.yaml\n"
                                            f"{sha(html_text)}  grain/GRAIN.html\n")
    data = {data_dir() / "c19_examples" / k: v for k, v in c19_examples(rs).items()}
    # MANIFEST (C17): resultados, regras, página, gate, código e testes
    man_paths = sorted([p for p in files if p.parent == results_dir()] + [R_ / "grain" / "GRAIN.html",
                                                                          R_ / "grain" / "RULES.sha256"])
    man = {}
    for p in man_paths:
        man[str(p.relative_to(R_))] = sha(files[p])
    man["grain/grain_rules.yaml"] = sha(rules_text)
    for p in sorted(list((R_ / "src" / "bo" / "grain").glob("*.py")) + list((R_ / "tests" / "grain").rglob("*.py"))
                    + [R_ / "gates" / "GRAIN.sh"]):
        if p.is_file():
            man[str(p.relative_to(R_))] = sha256_file(p)
    files[results_dir() / "MANIFEST.sha256"] = "".join(f"{v}  {k}\n" for k, v in sorted(man.items()))
    diff = []
    for p, text in {**files, **data}.items():
        cur = p.read_text(encoding="utf-8") if p.is_file() else None
        if cur != text:
            diff.append(p)
            if not check:
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(text, encoding="utf-8")
    n = len(files) + len(data)
    if check:
        print(stamp(f"build --check: {n - len(diff)}/{n} idênticos"))
        for p in diff:
            print("  difere:", p)
        return 1 if diff else 0
    print(stamp(f"build: {n} arquivo(s); {len(diff)} reescrito(s)"))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)
    return build(a.check)


if __name__ == "__main__":
    sys.exit(main())
