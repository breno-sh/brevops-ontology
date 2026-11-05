"""SEMANTICS.html: a teoria, gerada dos mesmos objetos que o código executa (determinístico)."""

from __future__ import annotations

import html
import json

from . import guards as G
from . import transforms as TR
from .composition import SEM
from .rules import RULES
from .vocab import VDR_JEPD, FIDELITIES

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
.ok{color:var(--pos);font-weight:600}.no{color:var(--neg);font-weight:600}.unk{color:var(--unk);font-weight:600}
.note{border-left:3px solid var(--accent);padding:4px 10px;color:var(--muted)}
nav a{margin-right:10px;font-size:.88rem;color:var(--accent)}
"""


def e(s) -> str:
    return html.escape(str(s), quote=True)


def table(head, rows, cls=""):
    h = "".join(f"<th>{e(x)}</th>" for x in head)
    b = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
    return f'<div class="wrap"><table class="{cls}"><thead><tr>{h}</tr></thead><tbody>{b}</tbody></table></div>'


def code(x) -> str:
    return f"<code>{e(x)}</code>"


def fx(obj) -> str:
    return f'<div class="fx">{e(json.dumps(obj, ensure_ascii=False, sort_keys=True))}</div>'


def render(ctx: dict) -> str:
    T = ctx["table"]
    ces = ctx["ce_results"]
    suite = ctx["suite"]
    rt = ctx["roundtrip"]
    sep = ctx["separation"]
    ed = ctx["edoal"]
    n_ok = sum(1 for x in ces if x["ok"])
    parts = []
    A = parts.append
    A(f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Semântica das correspondências</title>
<style>{CSS}</style></head><body><main>
<h1>Semântica das correspondências</h1>
<div class="meta">versão 3.0 da teoria (emenda 3, 2026-11-04)</div>
<div class="meta">Módulo SEMANTICS · contratos C09 (correspondências) e C10 (guarda, composição) · escrito em {e(ctx['at'])}
(America/Recife) · conteúdo sha256 {e(ctx['content_sha'][:16])}… · revisão GPT-6 F2, F3, F4, N4 · R1-M6, R2-W1</div>
<div class="kpis">
<div class="kpi"><b>{len(RULES)}</b>regras executáveis</div>
<div class="kpi"><b>{n_ok}/{len(ces)}</b>contraexemplos rejeitados (com controle aceito e mutação)</div>
<div class="kpi"><b>{sum(1 for x in ces if x['mutation']=='strict')}</b>isolam a regra sozinhos (strict)</div>
<div class="kpi"><b>{suite['n_reproduces']}/{suite['n']}</b>compromissos e CQs de perda reproduzidos</div>
<div class="kpi"><b>{rt['n_ok']}/{rt['n']}</b>checagens SKOS ida e volta</div>
</div>
<nav><a href="#def">definição</a><a href="#campos">três campos</a><a href="#skos">direção SKOS</a><a href="#prova">obrigações</a>
<a href="#guarda">guardas</a><a href="#perda">tradução e perda</a><a href="#tipos">tipos (N4)</a><a href="#comp">composição</a>
<a href="#proj">projeções e grupos</a><a href="#owl">OWL × transporte</a><a href="#f4">âncoras (F4)</a>
<a href="#regras">regras</a><a href="#cmt">compromissos</a><a href="#achados">achados</a><a href="#limites">limites</a>
<a href="#emendas">emendas</a></nav>
""")
    A("""<h2>A revisão como lista de conferência</h2>""")
    A(table(["item da revisão", "o que foi feito", "onde se executa"], [
        ["F2 três relações fundidas", "semantic_relation, value_domain_relation (calculada, orientada) e transport_fidelity separados, com regras de coerência", code("obligations.assess") + " · VDR-COMPUTED, FID-COHERENT"],
        ["F2 direção broad/narrow invertida", "'a broadMatch b' = b mais amplo, conferido contra o core.rdf do W3C e o fecho OWL 2 RL", code("python -I -m bo.semantics.skos_roundtrip")],
        ["F2 sem obrigações de prova", "obrigação por tipo; sem prova = UNPROVEN; testes executados", "EXACT-NORM, EXACT-TESTS, CLOSE-LOSS, BN-PRED, FIXED-DATED, EVIDENCE"],
        ["F2 arredondamento, saturação, ausência, sentinelas, edição/região/versão", "contrato de perda com cinco tipos e aplicação no transporte", "T-ROUNDING, T-SATURATION, T-ABSENCE, SENTINEL, T-SENTINEL, CTX-DEP"],
        ["F2 unknown==unknown não é prova", "grandeza/unidade UNKNOWN em qualquer lado = UNPROVEN", "KIND-UNKNOWN, VDR-UNKNOWN"],
        ["F2 composição sem guardas nem domínio", "tabela formal; interseção de guardas com satisfatibilidade; tipo do nó do meio", code("python -I -m bo.semantics.composition_check")],
        ["F3 injetividade anula 1:N/N:M", "projeções por ocorrência com sobreposição declarada; grupos como regras sobre subgrafo", "P-OCC, P-EXEC, P-OVERLAP, G-VARS, G-ARITY, G-OCC"],
        ["F3 uma realização por célula", "alternativas guardadas com exclusividade provada (UNSAT) ou AMBIGUOUS", "A-EXCL"],
        ["F3 EDOAL exportar e reimportar", f"subconjunto suportado: {ed['exported']} exportadas, {len(ed['skipped'])} fora do subconjunto (close, related), reimportação igual = {ed['same']}", code("edoal.roundtrip")],
        ["F4 âncora no mesmo conceito já é mapeamento", "átomo→conceito←átomo = composição das âncoras; mesmo conceito sem DOC_SUPPORTED nas duas âncoras = UNPROVEN", "ANCHOR-NOT-PROOF, K-HUB"],
        ["F4 leitura de volta como prova", "PERSISTENCE_VERIFIED sem citação não sustenta significado", "EVIDENCE"],
        ["N4 NOT_APPLICABLE ≠ UNKNOWN; janela; byte/GiB; kind só escalar", "parte do tipo; conversão exata ou refutação", "KIND-EQ, KIND-TUPLE, UNIT-WINDOW, UNIT-BYTES"],
    ]))

    A("""<h2 id="def">1. Correspondência = relação tipada entre configurações</h2>
<p>Uma alegação liga um atributo (ou subgrafo) do lado sujeito <i>a</i> a um do lado objeto <i>b</i> e é a tupla
⟨a, b, G, τ, L, R<sub>sem</sub>, R<sub>dom</sub>, F, P, E⟩:</p>""")
    A(table(["componente", "o que é", "semântica executável"], [
        ["G guarda", "condição tipada sobre região, edição, versão do provider e valores vizinhos", "conjunção decidível; SAT/UNSAT/UNKNOWN; avaliação TRUE/FALSE/INDETERMINATE"],
        ["τ tradução", "função parcial do núcleo fechado (ou cadeia), com inversa parcial quando existe", "fora do domínio = TRANSFORM_OUT_OF_DOMAIN"],
        ["L contrato de perda", "arredondamento, saturação, ausência, sentinelas, dependência de contexto, não exprimível, perda semântica", "aplicado depois de τ; cada perda vira registro no traço"],
        ["R<sub>sem</sub>", "exact | close | broad | narrow | related (significado)", "obrigação de prova por tipo"],
        ["R<sub>dom</sub>", "equal | subset | superset | overlap | disjoint | unknown entre τ(dom a) e dom b", "calculada; a declarada tem de bater"],
        ["F fidelidade", "lossless | declared_loss | partial | none, na direção a→b", "coerente com R<sub>dom</sub> e L; a da volta é recalculada"],
        ["P prova", "testes da normalização, predicado de pertença, evidência citada, contexto datado", "executada pelo verificador"],
        ["E evidência", "STRUCTURALLY_VALID < DOC_SUPPORTED < PERSISTENCE_VERIFIED < OBSERVATION_TESTED; UNRESOLVED", "transporte primário só com DOC_SUPPORTED/observação citada"],
    ]))
    A("""<p>Observações preservadas (<code>preserved_observations</code>) dizem o que continua verdadeiro depois do
transporte; close declara também o que se perde. Exemplo (sintético) de alegação completa:</p>""")
    A(fx(ctx["example_claim"]))

    A("""<h2 id="campos">2. Três campos que a v2 misturava</h2>""")
    A(table(["campo", "pergunta", "valores", "regras de coerência"], [
        ["semantic_relation", "os conceitos têm o mesmo significado?", "exact, close, broad, narrow, related", "SKOS-PRED (bate com predicate_id)"],
        ["value_domain_relation", "os valores admitidos cabem um no outro (orientação sujeito→objeto, depois de τ)?", ", ".join(VDR_JEPD) + ", unknown", "VDR-COMPUTED (igual à calculada); função parcial indefinida em parte do domínio finito conta como valor sem contraparte"],
        ["transport_fidelity", "o que a tradução leva?", ", ".join(FIDELITIES), "FID-COHERENT, CLOSE-LOSS, RELATED-NT, VDR-UNKNOWN"],
    ]))
    A("""<p class="note">Exemplo da separação: retenção em dias com o mesmo significado nos dois lados (exact), domínio
1..3650 contra 1..365 (superset) e saturação declarada (declared_loss). Conversão exata de unidade é exact, não close
(CMT-LOSS e CQ-LOSS-01).</p>""")

    A("""<h2 id="skos">3. Direção SKOS corrigida e transporte por direção</h2>
<p><code>a skos:broadMatch b</code> quer dizer que <b>b é o mais amplo</b> (a ⊂ b). A direção é conferida contra o
schema SKOS do próprio W3C (core.rdf, sha256 fixado): <code>broadMatch</code> ⊑ <code>broader</code>, cuja definição
oficial é <i>"Relates a concept to a concept that is more general in meaning."</i>; <code>broadMatch owl:inverseOf
narrowMatch</code>. O teste de ida e volta grava a alegação em SSSOM, lê como RDF, aplica o fecho OWL 2 RL e
confere quem é o mais amplo.</p>""")
    A(table(["alegação", "mais amplo", "A→B", "B→A"], [
        ["a skos:exactMatch b", "nenhum (mesmo significado no escopo)", "com a normalização declarada", "pela inversa parcial"],
        ["a skos:closeMatch b", "nenhum (perda declarada)", "se τ está definida no valor; perda registrada", "só com inversa parcial; perda registrada"],
        ["a skos:broadMatch b", "b (a ⊂ b)", "por inclusão (todo valor de a cabe)", "só onde o predicado de pertença a 'a' é verdadeiro (OUT_OF_SUBSET no resto)"],
        ["a skos:narrowMatch b", "a (b ⊂ a)", "só onde o predicado de pertença a 'b' é verdadeiro", "por inclusão"],
        ["a skos:relatedMatch b", "não se aplica", "não transporta (RELATED_ONLY)", "não transporta"],
        ["guarda", "—", "verdadeira: segue; falsa: CONDITION_FALSE; indeterminada: intervalo entre os limites", "idem (papéis trocados)"],
        ["fixed/default", "—", "só com valor, contexto e evidência datados e se o valor coincide", "—"],
    ]))
    A(table(["checagem do ida e volta (último build)", "resultado"],
            [[e(c["check"]), '<span class="ok">ok</span>' if c["ok"] else '<span class="no">falha</span>'] for c in rt["checks"]]))

    A("""<h2 id="prova">4. Obrigações de prova por tipo</h2>""")
    A(table(["tipo", "obrigação", "sem ela", "regras"], [
        ["exact", "significado preservado no escopo (guarda), normalização explícita do núcleo, testes executados, valor canônico preservado, evidência citada", "UNPROVEN (falta) ou REFUTED (teste ou grandeza desmentem)", "EXACT-NORM, EXACT-TESTS, NORM-PRESERVE, KIND-EQ, EVIDENCE"],
        ["close", "declarar o que se perde (contrato de perda) e nunca alegar sem perda", "REFUTED", "CLOSE-LOSS"],
        ["broad / narrow", "predicado de pertença EXECUTÁVEL com orientação (lado subconjunto) e testes de membro e não membro; com domínios finitos, coincide com a imagem do lado estreito em todo valor", "UNPROVEN (sem predicado) ou REFUTED (orientação, teste)", "BN-PRED, SKOS-ORIENT, BN-PRED-TESTS"],
        ["related", "nada: não habilita transporte", "REFUTED se alegar fidelidade ou função", "RELATED-NT, T-RELATED"],
        ["FIXED / DEFAULT", "valor, contexto tipado e evidência com data e fonte", "UNPROVEN", "FIXED-DATED, T-FIXED"],
        ["toda alegação que transporta", "tipos conhecidos dos dois lados, guarda bem tipada e satisfazível, domínio coerente", "UNPROVEN/REFUTED", "KIND-UNKNOWN, GUARD-TYPE, GUARD-SAT, VDR-*, FID-COHERENT"],
    ]))

    A(f"""<h2 id="guarda">5. Guardas: gramática tipada e decidível</h2>
<p>Conjunção de átomos ⟨termo, operador, valor⟩ com os sete operadores do plano: {', '.join(code(o) for o in G.OPS)}.
Termo = papel.caminho (papel ∈ subject, object); região, edição e versão são termos de contexto reservados; termo
vizinho declara o tipo. Sem negação nem disjunção, a satisfatibilidade é decidida termo a termo (interseção de
conjuntos, de faixas de versão e de presença) e devolve testemunha. Tipos de referência distintos só se excluem
com disjunção declarada; sem ela, UNKNOWN. A avaliação é de três valores: termo não lido ou simbólico deixa a
guarda indeterminada.</p>""")

    A("""<h2 id="perda">6. Função parcial de tradução e contrato de perda</h2>
<p>Núcleo de referência (o registro fechado é do TRANSFORMS). Escalar não muda grandeza; combinador de tupla
declara tipos por componente.</p>""")
    A(table(["função", "tipo", "domínio", "codomínio", "erro", "inversa parcial"],
            [[code(s.name), s.kind, e(s.domain), e(s.codomain), e(s.error), e(s.inverse)] for s in TR.REGISTRY.values()]))
    A(table(["perda", "quando", "no traço"], [
        ["rounding", "valor fora do passo do destino", "declared_loss com de/para; sem declaração, bloqueio"],
        ["saturation", "valor fora da faixa do destino", "declared_loss com de/para (CMT-LOSS-P01); sem declaração, bloqueio"],
        ["absence", "origem sem valor", "obrigatório no destino: UNKNOWN_INPUT; opcional: omitted"],
        ["sentinel", "valor especial da origem (ex. 0 = nunca expira)", "tabela declarada; sem equivalente, perda declarada e nada emitido"],
        ["context_dependence", "a tradução depende de edição, região ou versão", "os termos têm de estar na guarda (CTX-DEP)"],
        ["not_expressible", "valor que o destino não exprime (ex. negar)", "bloqueio com perda declarada (CQ-LOSS-02)"],
        ["semantic", "o que o close perde em significado", "declared_loss no valor afetado"],
    ]))

    A("""<h2 id="tipos">7. Tipos (N4)</h2>
<p>NOT_APPLICABLE (não há grandeza: nome, enum, booleano) é diferente de UNKNOWN (há, mas não se sabe qual); UNKNOWN em
qualquer lado dá UNPROVEN. Janela de taxa (por minuto × por segundo) e convenção de byte (IEC × SI) fazem parte do
tipo: identidade entre elas é refutada pelo valor canônico. Durações em xsd:duration com mês ou ano não têm número
fixo de segundos: sem contexto de calendário, TRANSFORM_OUT_OF_DOMAIN. kind_in = kind_out só vale para escalar.</p>""")

    A("""<h2 id="comp">8. Composição pela tabela formal</h2>
<p>Linha (r1, r2) = m1∘m2 com m1: A→B por r1 e m2: B→C por r2. As linhas de exact, broad e narrow saem da semântica de
conjuntos (equal, subset, superset) pela composição RCC5; close e related por política declarada. A parte de
domínios é calculada por enumeração exaustiva (universo de 4 pontos, conferida igual com 5) e conferida contra
linhas da tabela RCC5 da literatura.</p>""")
    st = {(r["r1"], r["r2"]): r for r in T["semantic_relation"]}
    rows = []
    for r1 in SEM:
        rows.append([f"<b>{r1}</b>"] + [
            (f'<span class="ok">{st[(r1, r2)]["result"]}</span>' if st[(r1, r2)]["result"] else '<span class="no">⊥</span>')
            for r2 in SEM])
    A(table(["m1 \\ m2"] + list(SEM), rows))
    A('<p class="meta">⊥ = nenhuma relação derivável: a composição é UNPROVEN (sem prova direta da alegação A→C).</p>')
    vr = {(r["r1"], r["r2"]): r["possible"] for r in T["value_domain_relation"]["rows"]}
    A(table(["R(A,B) \\ R(B,C)"] + list(VDR_JEPD),
            [[f"<b>{a}</b>"] + [e("{" + ", ".join(vr[(a, b)]) + "}") for b in VDR_JEPD] for a in VDR_JEPD]))
    A(table(["regra", "texto"], [[e(k), e(T[k]["rule"])] for k in ("guard", "domain", "evidence", "verdict", "closure")]
            + [["transport_fidelity", e(T["transport_fidelity"]["rule"])]]))

    A("""<h2 id="proj">9. Projeções por ocorrência, alternativas e grupos (F3)</h2>
<p>A injetividade sai. Um campo pode alimentar vários conceitos, cada uso com a sua projeção: a consulta de um
alarme em linguagem de métricas (<code>Metrica[1m].mean() &gt; 80</code>) projeta métrica, janela, estatística,
operador e limiar, cinco projeções do mesmo campo sem sobreposição; um documento JSON de política de reenvio dá
duas decisões (destino e máximo de entregas); o mapa de rótulos é TAG inteiro e a chave Name é NAME. Sobreposição
(duas projeções que leem a mesma parte, como TAG e NAME) tem de ser declarada. Campo dentro de bloco repetido exige chave de ocorrência por campos de identidade.
Realizações alternativas do mesmo alvo só são exclusivas com interseção de guardas UNSAT; senão AMBIGUOUS.</p>
<p>Grupos são regras sobre subgrafos com variáveis nomeadas, ocorrências e passos com argumentos nomeados:</p>""")
    A(table(["grupo", "cardinalidade", "exemplo executado"], ctx["group_rows"]))

    A(f"""<h2 id="owl">10. Teoria OWL (o que se infere) × regras executáveis (o que se transporta)</h2>
<p>O fecho OWL 2 RL sobre os axiomas SKOS vê triplas: infere o inverso, a subpropriedade e a transitividade de
exactMatch; não vê guardas, domínios nem perdas. No mesmo par de alegações exact com guardas incompatíveis no nó
do meio (edição standard × premium), o fecho infere {code(', '.join(sep['owl_inferred_between_ends']))} entre as pontas,
e a composição executável dá {code(sep['composition_outcome'])} ({code(sep['composition_rule'])}). Consequência OWL
nunca habilita transporte; o transporte composto sai só da tabela. O SKOS também não torna broadMatch transitiva
(broader não é transitiva); a regra broad∘broad = broad daqui vem da semântica de conjuntos assumida para a
extensão, mais forte que a do SKOS, e é declarada como tal.</p>""")

    A("""<h2 id="f4">11. Âncora de glossário não é prova (F4)</h2>
<p>Dois átomos ancorados no mesmo conceito já são uma correspondência: átomo→conceito←átomo é a composição
âncora<sub>a</sub> ∘ inversa(âncora<sub>b</sub>) e passa pela mesma tabela, herdando as obrigações das duas âncoras.
Alegação com base no conceito compartilhado exige DOC_SUPPORTED nas duas âncoras; com âncoras UNRESOLVED, UNPROVEN.
A leitura de volta (PERSISTENCE_VERIFIED) confirma que a API guardou o valor, não que o significado é o mesmo.</p>""")

    A("""<h2 id="regras">12. Regras e contraexemplos</h2>
<p>Cada regra tem ao menos um contraexemplo (par mínimo) em <code>semantics/counterexamples.jsonl</code>: o input é
rejeitado pela própria regra, o controle é aceito e, com a regra desligada, o input passa (strict) ou a falha dela
some (rule_only, com o motivo de outra regra o segurar).</p>""")
    byr = {}
    for x in ces:
        byr.setdefault(x["rule_id"], []).append(x)
    A(table(["regra", "família", "falha dá", "texto", "contraexemplos"],
            [[code(k), e(v["family"]), e(v["on_fail"]), e(v["text"]),
              " ".join(f'<span class="{"ok" if x["ok"] else "no"}">{e(x["ce_id"])}</span>'
                       f'<span class="meta"> ({x["mutation"]})</span>' for x in byr.get(k, []))]
             for k, v in RULES.items()]))

    A(f"""<h2 id="cmt">13. Compromissos e CQs do REQUIREMENTS (família perda)</h2>
<p>{suite['n_reproduces']} de {suite['n']} reproduzem a resposta esperada escrita antes deste módulo, pelo adaptador
fixo de <code>bo.semantics.fixtures</code>.</p>""")
    A(table(["id", "esperado", "obtido", "traço"],
            [[e(r["id"]), e(json.dumps(r["expected"], ensure_ascii=False)), e(json.dumps(r["got"], ensure_ascii=False)),
              e(", ".join(f"{k}={r['trace'][k]}" for k in ("result", "code", "rule") if r["trace"].get(k)))]
             for r in suite["rows"]]))

    A("""<h2 id="achados">14. Achados</h2><ul>""")
    for f in ctx["findings"]:
        A(f"<li>{f}</li>")
    A("</ul>")
    A("""<h2 id="limites">15. Limites</h2><ul>""")
    for f in ctx["limits"]:
        A(f"<li>{f}</li>")
    A("</ul>")
    A("""<h2 id="emendas">16. Emendas versionadas</h2>
<p>Versão 2.0 (2026-11-04). A emenda 2 responde ao CC-5 e ao CC-6 do PILOT-STO-MAP (CONTRACTS emenda 7).
<b>Coleções</b>: o tipo de valor aceita list, set e map com item_type (e key_type no map), como o C09 3.2.0. A
grandeza de uma coleção é a do elemento, de modo que lista de texto não é mais KIND-UNKNOWN. Cadeia escalar entre
coleções do mesmo tipo vale elemento a elemento, com perda registrada por elemento. Entre coleção e escalar é
preciso combinador de coleção (do registro do C10), e list→set exige perda declarada (regra KIND-COLL).
<b>Grandeza de dado</b>: BYTE, BIT e prefixos passam a quantitykind:AmountOfData, como no UNITS. O QUDT 3.5.3
(VOCAB_QUDT-UNITS-ALL.ttl, release v3.5.3 de qudt/qudt-public-repo, sha256 em $BO_DATA/downloads/qudt-3.5.3/SOURCE.txt)
liga essas unidades a AmountOfData e ByteDataVolume por qudt:unitForQuantityKind, e não a InformationEntropy, que a
versão 1 usava sem conferir. Um teste cruzado compara o núcleo com bo.units.rules e com o arquivo do QUDT.</p>
<p>Versão 3.0 (emenda 3, ciclo v4, pedido do ARBITERLIB b424605). Lista e conjunto tipados do C09 3.2.0 contam como
lado estruturado para combinador de tupla. Combinador do registro fechado com uma porta só aceita o valor posicional
(o valor solto da alegação) e devolve o valor solto quando tem uma saída só; entradas nomeadas continuam valendo.
<b>wrap_list</b> (escalar → lista) é exact só no domínio: a imagem são listas de UM item, subconjunto próprio do
destino, que admite mais. A relação calculada é subset, e a volta só existe para lista de tamanho 1.
<b>unwrap_single</b> (lista → escalar) é parcial: definido só em lista de tamanho 1, com relação superset e nunca sem
perda. A forma dos dois (escalar ↔ lista, mesma grandeza no elemento) é conferida por KIND-COLL e KIND-EQ.</p>""")
    A(table(["versão", "data", "pedido", "o que resolve", "commit"],
            [[e(x["versao"]), e(x["data"]), e(x["pedido"]), e(x["resolve"]),
              code(x["commit"] or ("neste merge: " + x["assunto"]))] for x in ctx["emendas"]]))
    A("""<h2>Arquivos e contratos</h2>""")
    A(table(["arquivo", "o que é"], [[code(k), e(v)] for k, v in ctx["files"].items()]))
    A("</main></body></html>\n")
    return "".join(parts)
