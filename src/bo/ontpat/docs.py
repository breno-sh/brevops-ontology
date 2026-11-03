"""Gera ontology/patterns/ONTPAT.html e UPPER_DECISION.html a partir dos artefatos e dos resultados
(nenhum número digitado: tudo sai de results/ONTPAT/*.json e dos TTL).

  python -I -m bo.ontpat.docs [--check]
"""

from __future__ import annotations

import html
import sys

import rdflib
from rdflib.namespace import OWL, RDF

from . import common as c
from . import trial_spec as S

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
.box{background:var(--card);border:1px solid var(--line);border-left:4px solid var(--accent);border-radius:8px;padding:10px 14px;margin:12px 0}
.note{border-left:3px solid var(--accent);padding:4px 10px;color:var(--muted)}
details{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:8px 12px;margin:8px 0}
summary{cursor:pointer;font-weight:600}"""

E = html.escape


def page(title: str, body: str) -> str:
    return (f'<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">\n'
            f'<meta name="viewport" content="width=device-width, initial-scale=1">\n<title>{E(title)}</title>\n'
            f"<style>\n{CSS}\n</style></head><body><main>\n{body}\n</main></body></html>\n")


def yn(b, yes="sim", no="não") -> str:
    return f'<span class="ok">{yes}</span>' if b else f'<span class="no">{no}</span>'


# ---------------------------------------------------------------- UPPER_DECISION.html

def upper_decision_html(doc: dict) -> str:
    cands = doc["candidates"]
    dec = doc["decision"]
    order = list(c.CANDIDATES)
    n = len(S.CASES)
    chosen = dec.get("chosen")
    rows = dec["rows"]
    lbl = {k: cands[k]["label"] for k in order}
    b = [f"<h1>Decisão da ontologia de topo</h1>",
         f'<p class="meta">Módulo ONTPAT · S2 · resultado de {E(doc["generated_at"])} (America/Recife) · regra de decisão '
         f'v{E(doc["decision_rule"]["version"])} escrita em {E(doc["decision_rule"]["written_at"])}, antes da primeira execução · '
         f'ROBOT {E(doc["toolchain"]["robot"])}, HermiT {E(doc["toolchain"]["hermit"])} · fonte: results/ONTPAT/upper_trial.json</p>']
    b.append('<div class="box"><b>Decisão: ' + E(lbl.get(chosen, "nenhuma elegível")) + f"</b> ({E(chosen or '-')}). "
             + E(dec["why"]) + ".</div>")
    own = {k: rows[k]["D3_protecoes_proprias"] for k in order}
    max_own = max(len(v) for v in own.values())
    allrep = all(cands[k]["reproduced"] == n for k in order)
    sentences = []
    sentences.append(f"As {len(order)} candidatas foram levadas aos {len(doc['case_ids'])} compromissos com eixo de topo do REQUIREMENTS "
                     f"(identidade {doc['axes_count']['identity']}, tempo {doc['axes_count']['time']}, papel {doc['axes_count']['role']}) "
                     f"e ao caso extra {', '.join(doc['extra_case_ids'])}, cada um com alinhamento mínimo de melhor esforço.")
    if allrep:
        sentences.append(f"Todas reproduzem as {n} respostas esperadas: as respostas vêm dos padrões do bo, não da ontologia de topo.")
    if max_own == 0:
        sentences.append("Nenhuma candidata protege sozinha algum compromisso quando os axiomas de exclusão do bo são retirados "
                         "(D3 = 0 para todas), então a decisão cai no custo (D4). 'Nenhuma' não ganhou por não gerar inferência: "
                         f"as candidatas geram inferências próprias (até {max(cands[k]['expected_inferences']['count'] for k in order)} "
                         "tipos inferidos nas fixtures), mas nenhuma delas protege resposta que o bo já não proteja, e o preço é "
                         "maior em desajustes, axiomas e tempo.")
    elif chosen and chosen != "none":
        cn = cands[chosen]["cost"]
        nn = cands["none"]["cost"]
        sentences.append(f"Só {chosen} protege sozinha algum compromisso com as exclusões do bo retiradas: "
                         f"{', '.join(own[chosen])}. Pela regra escrita antes, isso decide em D3, antes do custo. O custo é real e "
                         f"fica declarado: {cn['misfits']} desajustes, {cn['closure_axioms_typical_case']} axiomas lógicos no fecho de um "
                         f"caso típico contra {nn['closure_axioms_typical_case']} sem ontologia de topo, e {cn['hermit_ms_total']} ms de "
                         f"HermiT no teste contra {nn['hermit_ms_total']} ms. A margem é de {len(own[chosen])} proteção; o Breno pode "
                         "vetar (D14), e o veto depois do FREEZE0 invalida os dependentes.")
    b.append("<p>" + " ".join(E(s) for s in sentences) + "</p>")
    if chosen and chosen != "none" and own[chosen]:
        ex = exclusion_axioms_via_alignment(chosen)
        b.append("<p class='note'>De onde vem a proteção própria: axiomas de exclusão da própria candidata alcançados pelo "
                 "alinhamento mínimo: <code>" + E("; ".join(ex) or "nenhum identificado") + "</code>.</p>")

    b.append("<h2>Regra (escrita antes de rodar)</h2><table><tr><th>passo</th><th>texto</th></tr>")
    for it in doc["decision_rule"]["items"]:
        b.append(f"<tr><td><b>{E(it['id'])}</b></td><td>{E(it['text'])}</td></tr>")
    ab = doc["decision_rule"]["ablation"]
    b.append(f"</table><p class='note'>Axiomas de exclusão retirados no modo D3: {E(', '.join(ab['predicates'] + ab['types']))}; "
             f"{E(', '.join(ab['other']))}. Chaves e propriedades funcionais ficam (identificam, não excluem).</p>")

    b.append("<h2>Resultado por candidata</h2><div class='wrap'><table><tr><th></th>"
             + "".join(f"<th>{E(k)}</th>" for k in order) + "</tr>")
    def row(name, f):
        return "<tr><td>" + E(name) + "</td>" + "".join(f"<td>{f(k)}</td>" for k in order) + "</tr>"
    b.append(row("candidata", lambda k: E(lbl[k])))
    b.append(row(f"D1 reproduz ({n})", lambda k: f"{cands[k]['reproduced']}/{n} " + yn(rows[k]["D1_reproduz_todos"])))
    b.append(row("D2 fecho OWL 2 DL", lambda k: yn(cands[k]["profile"]["in_profile"])))
    b.append(row("D2 consistente com o ABox de exemplo", lambda k: yn(cands[k]["example_abox_consistent"])))
    b.append(row("D2 alinhamento sem punning", lambda k: yn(not cands[k]["alignment_punning"])))
    b.append(row("sem exclusões do bo: reproduz", lambda k: f"{cands[k]['reproduced_without_bo_exclusions']}/{n}"))
    b.append(row("D3 proteções próprias", lambda k: f"{len(own[k])} " + E(", ".join(own[k]))))
    b.append(row("D4a desajustes declarados", lambda k: str(cands[k]["cost"]["misfits"])))
    b.append(row("D4b axiomas lógicos no fecho (caso típico)", lambda k: str(cands[k]["cost"]["closure_axioms_typical_case"])))
    b.append(row("D4c HermiT, ms no teste", lambda k: str(cands[k]["cost"]["hermit_ms_total"])))
    b.append(row("axiomas lógicos da candidata", lambda k: str(cands[k]["cost"]["candidate_axioms"])))
    b.append(row("axiomas do alinhamento", lambda k: str(cands[k]["cost"]["alignment_axioms"])))
    b.append(row("fecho com o ABox de exemplo (axiomas)", lambda k: str(cands[k]["cost"]["closure_axioms_example_abox"])))
    b.append(row("tempo de parede do harness (s)", lambda k: str(cands[k]["cost"]["harness_wall_s"])))
    b.append(row("mutações que viraram a resposta", lambda k: f"{cands[k]['mutations_flipped']}/{cands[k]['mutations_total']}"))
    b.append(row("inferências esperadas (tipos da candidata)", lambda k: str(cands[k]["expected_inferences"]["count"])))
    b.append("</table></div>")

    b.append("<h2>Casos de identidade, tempo e papel</h2><p class='meta'>completo / sem exclusões do bo. A resposta esperada vem de "
             "requirements/commitments.jsonl; a mutação de cada variante tem de virar a resposta (prova que a consulta não passa por vacuidade).</p>"
             "<div class='wrap'><table><tr><th>compromisso</th><th>eixos</th><th>esperado</th>"
             + "".join(f"<th>{E(k)}</th>" for k in order) + "<th>mutação</th></tr>")
    for cid in list(doc["case_ids"]) + list(doc["extra_case_ids"]):
        ref = cands[order[-1]]["cases"][cid]
        exp = ref["expected"]
        expt = f"{exp['value']}" + (f" ({exp['code']})" if exp.get("code") else "")
        cells = "".join(f"<td>{yn(cands[k]['cases'][cid]['reproduces'], 'ok', 'falha')} / "
                        f"{yn(cands[k]['cases'][cid]['reproduces_without_bo_exclusions'], 'ok', 'falha')}</td>" for k in order)
        muts = [vv["mutation"] for vv in ref["variants"] if vv.get("mutation")]
        mtxt = "; ".join(f"{m['label']} → {m['observed']}" for m in muts) or "-"
        axes = ", ".join(ref["axes"]) or "extra"
        b.append(f"<tr><td><code>{E(cid)}</code></td><td>{E(axes)}</td><td>{E(expt)}</td>{cells}<td>{E(mtxt)}</td></tr>")
    b.append("</table></div>")

    b.append("<h2>Inferências esperadas por candidata</h2><p>O que cada candidata acrescenta às fixtures (tipos da própria "
             "candidata inferidos para os indivíduos dos casos). São corretas sob o alinhamento, mas nenhuma decide resposta de compromisso.</p>")
    for k in order:
        ei = cands[k]["expected_inferences"]
        if not ei["count"]:
            b.append(f"<p><b>{E(k)}</b>: nenhuma (sem ontologia de topo).</p>")
            continue
        top = sorted(ei["by_class"].items(), key=lambda x: -x[1])[:8]
        b.append(f"<p><b>{E(k)}</b>: {ei['count']} tipos inferidos; por classe: " + E(", ".join(f"{a} {v}" for a, v in top))
                 + ". Exemplos: <code>" + E("; ".join(ei["examples"][:4])) + "</code></p>")

    b.append("<h2>Alinhamento mínimo e desajustes</h2>")
    for k in order:
        r = cands[k]
        b.append(f"<details><summary>{E(k)}: {len(r['alignment_axioms'])} axiomas, {len(r['misfits'])} desajustes</summary>")
        if r["alignment_axioms"]:
            b.append("<div class='fx'>" + E("\n".join(r["alignment_axioms"])) + "</div>")
        b.append("<ul>" + "".join(f"<li>{E(m)}</li>" for m in r["misfits"]) + "</ul>" if r["misfits"] else "<p>sem desajuste.</p>")
        if r["role_probe"]:
            p = r["role_probe"]
            extra = f"; punning: {len(p.get('punning', []))} IRI" if "punning" in p else ""
            b.append(f"<p>Sonda do eixo papel: {E(p['label'])} → consistente: {yn(p['consistent'])}{E(extra)}.</p>")
        pa = r.get("protective_alignment_exploratory")
        if pa:
            got = ", ".join(f"{cid} {'protegido' if v else 'não'}" for cid, v in pa["cases"].items())
            b.append(f"<p class='note'>Exploratório (fora da regra, acrescentado depois da primeira execução): com "
                     f"<code>{E(pa['alignment_extra'])}</code>, sem as exclusões do bo: {E(got)}. Preço: {E(pa['misfit'])}.</p>")
        b.append("</details>")

    if chosen == "none":
        b.append("<h2>O que se perde e quando reabrir</h2><ul>"
                 "<li>Sem ontologia de topo, o bo não herda categorias de terceiros: interoperar com uma ontologia construída sobre "
                 "gUFO, DUL ou BFO exige um módulo de alinhamento à parte. Os quatro <code>upper_trial/*/cases.ttl</code> ficam como "
                 "ponto de partida desse módulo.</li>"
                 "<li>As proteções de categoria passam a depender só dos axiomas de exclusão do bo, que são compromissos protegidos (F9).</li>"
                 "<li>Reabrir se um compromisso novo com eixo de topo não puder ser reproduzido só com o bo, se um consumidor externo "
                 "exigir uma candidata, ou por veto do Breno (D14).</li></ul>")
    elif chosen:
        r = cands[chosen]
        b.append("<h2>Como aplicar a decisão</h2><ul>"
                 f"<li>O alinhamento mínimo de {E(chosen)} ({len(r['alignment_axioms'])} axiomas, acima) vira um módulo próprio "
                 f"(<code>bo-align-{E(chosen)}</code>, gerado pelo OWL), importado pelo núcleo; o perfil OWL 2 DL do trio bo-patterns + "
                 f"{E(chosen)} + alinhamento já foi conferido aqui: {'em' if r['profile']['in_profile'] else 'FORA do'} perfil. "
                 "bo-patterns.ttl continua sem importar a candidata: os padrões não dependem dela, e o teste mostra que todas as "
                 "respostas saem do bo.</li>"
                 f"<li>Arquivo da candidata: <code>{E(r['file'] or '-')}</code>, sha256 <code>{E((r['file_sha256'] or '')[:16])}</code>…; "
                 "a licença do arquivo do DUL não está declarada nele (SOURCE.txt: UNRESOLVED): importar por IRI não redistribui, "
                 "mas copiar para o repositório exige conferir a licença antes.</li>"
                 f"<li>O preço em raciocínio entra no orçamento do TRANSLATOR e do REASONING-PROOF: {r['cost']['hermit_ms_total']} ms de "
                 f"HermiT no teste contra {cands['none']['cost']['hermit_ms_total']} ms sem ontologia de topo.</li>"
                 "<li>As proteções do bo continuam: a da candidata é redundante com elas no modo completo e só pesa se um reparo "
                 "retirar um axioma de exclusão do bo (F9).</li>"
                 "<li>Reabrir se o custo de raciocínio inviabilizar o TRANSLATOR, se a proteção própria deixar de valer com o "
                 "vocabulário definitivo (CLASS/OWL), ou por veto do Breno (D14).</li></ul>")
    b.append("<h2>Limites</h2><ul>"
             "<li>O alinhamento mínimo de cada candidata foi escrito pelo mesmo agente que escreveu os padrões; os desajustes "
             "estão declarados para que outra leitura possa contestá-los.</li>"
             "<li>Tempos do HermiT dependem da máquina; entram só como desempate (D4c) e são re-medidos a cada execução.</li>"
             "<li>O teste usa um vocabulário de teste (tv:) com os rótulos de trabalho do REQUIREMENTS; as classes de domínio "
             "definitivas vêm do CLASS/OWL. O caso extra não tem eixo de topo; entra porque é o erro de categoria S1 que uma "
             "ontologia de topo poderia proteger.</li></ul>")
    return page("Decisão de topo BrevOps", "\n".join(b))


def exclusion_axioms_via_alignment(cand: str) -> list[str]:
    """Axiomas de exclusão (assimetria, irreflexividade, disjunção) da candidata sobre os termos que o alinhamento usa."""
    from . import upper_trial as U
    cf = U.candidate_file(cand)
    if not cf:
        return []
    g = rdflib.Graph().parse(cf, format="turtle")
    al = rdflib.Graph().parse(data=S.PREFIXES + S.ALIGNMENTS[cand]["ttl"], format="turtle")
    out = []
    for s_, p_, o_ in sorted(al):
        loc = str(o_).split("#")[-1].split("/")[-1]
        if p_ == rdflib.RDFS.subPropertyOf:
            for t in (OWL.AsymmetricProperty, OWL.IrreflexiveProperty):
                if (o_, RDF.type, t) in g:
                    out.append(f"{str(s_).split('#')[-1]} ⊑ {loc}, que é {t.split('#')[-1]}")
        elif p_ == rdflib.RDFS.subClassOf:
            for d in sorted(set(g.objects(o_, OWL.disjointWith)) | set(g.subjects(OWL.disjointWith, o_))):
                out.append(f"{str(s_).split('#')[-1]} ⊑ {loc}, disjunta de {str(d).split('#')[-1].split('/')[-1]}")
    return out


# ---------------------------------------------------------------- ONTPAT.html

PATTERNS = [
    ("P1", "Modelo S1: recurso, descrição, estado observado, observação",
     "O contrato anterior não separava código, registro de estado, objeto da API e leitura datada (S1).",
     "Quatro classes disjuntas: <code>bo:Resource</code> (o objeto que o provedor guarda), <code>bo:ConfigurationDescription</code> "
     "(o que o código declara, versionado por <code>bo:previousVersion</code> ⊑ <code>prov:wasRevisionOf</code>), <code>bo:ObservedState</code> "
     "(o que a leitura devolveu, <code>prov:wasGeneratedBy</code> uma <code>bo:Observation</code>) e <code>bo:Observation</code> ⊑ <code>prov:Activity</code> "
     "(com instante, escopo e completude). Valores vivem na descrição ou no estado, nunca direto no recurso; assim desejado e observado "
     "divergentes coexistem sem inconsistência e a deriva é uma consulta.",
     "CMT-CFG-P01, CMT-CFG-N01, CMT-CFG-N02", "ConfigurationDescriptionShape, ObservedStateShape, ObservationShape, S1SeparationShape"),
    ("P2", "Identidade composta e encarnação",
     "Identidade por posição ou por nome mistura recursos distintos e separa o mesmo recurso lido duas vezes.",
     "<code>owl:hasKey</code> em <code>bo:IndependentResource</code> sobre conta sintética, provedor, localização, tipo do provedor, chave local "
     "<b>e chave de encarnação</b>. Os cinco componentes do plano identificam o lugar; sozinhos fundiriam o recurso substituído com o novo "
     "(o teste mostra a inconsistência). A encarnação é o identificador opaco que o provedor troca na substituição; sem ela, a identidade "
     "através do tempo fica UNKNOWN. Componente anônimo: chave <code>(bo:componentOf, bo:occurrenceKey)</code>, com os campos de identidade "
     "normalizados, nunca a posição textual.",
     "CMT-ID-P01, CMT-ID-P02, CMT-ID-N01, CMT-ID-U01, CMT-ID-U02, CMT-NIC-P05", "ResourceShape, IndependentResourceShape, ComponentShape, ReplacedShape"),
    ("P3", "Parte-todo tipada: entidade, componente, faceta, vínculo",
     "Blocos tratados como recursos e um tipo realizando várias classes (R1-M2); parte-todo confundida com referência.",
     "<code>bo:Unit</code> = união disjunta de <code>bo:Resource</code>, <code>bo:Facet</code> e <code>bo:Binding</code>; <code>bo:Resource</code> = união "
     "disjunta de <code>bo:IndependentResource</code> e <code>bo:Component</code>. <code>bo:componentOf</code> e <code>bo:facetOf</code> são "
     "subpropriedades de <code>bo:lifecycleControlledBy</code> e disjuntas de <code>bo:references</code>. Faceta separa dono (<code>bo:facetOf</code>), "
     "onde o código a declara (<code>bo:declaredOn</code>) e alcance efetivo (<code>bo:appliesTo</code>).",
     "CMT-BKT-P03, CMT-NIC-P01..P03", "FacetShape, ComponentShape, IndependentResourceShape"),
    ("P4", "Ciclo de vida",
     "Sem controlador declarado, não se sabe o que apagar o pai apaga.",
     "<code>bo:endedBy</code> com as cadeias <code>bo:lifecycleControlledBy ∘ bo:endedBy ⊑ bo:endedBy</code> e "
     "<code>bo:relates ∘ bo:endedBy ⊑ bo:endedBy</code>: o fim desce do controlador ao controlado e de um extremo ao vínculo, nunca sobe. "
     "<code>bo:EndedUnit</code> é fase (antirrígida) sob <code>bo:Unit</code>. Substituição: <code>bo:replacedBy</code> irreflexiva e assimétrica.",
     "CMT-LC-P01, CMT-LC-N01, CMT-ID-P02", "EndedShape, ReplacedShape"),
    ("P5", "Vínculo reificado e relação n-ária",
     "Associação e atribuição modeladas como propriedade e também como classe (R1-M3, R2-W5).",
     "Vínculo (<code>bo:Binding</code>): unidade com ciclo de vida, identidade = tupla dos extremos; cada posição é subpropriedade funcional de "
     "<code>bo:relates</code> e o domínio declara <code>owl:hasKey</code> sobre elas. Relação n-ária (<code>bo:NaryRelation</code>): nó reificado sem "
     "ciclo de vida que não conta no grão (valor, realização, projeção, guarda, perda, marca de desconhecido).",
     "CMT-IAM-P01, CMT-NIC-P01 (anexação com índice), CMT-LC-N01", "BindingShape"),
    ("P6", "Valor reificado e vocabulário de ausência",
     "Desconhecido, ausente, não lido e retido viravam o mesmo vazio; padrão do provedor virava configurado.",
     "<code>bo:SettingValue</code> com <code>bo:of</code> (descritor), origem (<code>bo:Configured</code>, <code>bo:Inferred</code>, "
     "<code>bo:ProviderDefault</code>, <code>bo:Observed</code>) e estado (<code>bo:Known</code>, <code>bo:Unknown</code>, <code>bo:Absent</code>, "
     "<code>bo:NotRead</code>, <code>bo:Withheld</code>), vocabulários fechados (<code>owl:oneOf</code> + <code>owl:AllDifferent</code>). Desconhecido "
     "e não lido declaram o motivo (<code>bo:UnknownReason</code>: MISSING_EVIDENCE, INCOMPLETE_READ, UNKNOWN_SYMBOLIC_INPUT, OUT_OF_PIN, ...). "
     "Ausente só sob leitura completa. Retido: presença conhecida, nenhum valor, nenhum hash. <code>bo:UnknownMarker</code> registra componente "
     "de identidade não lido.",
     "CMT-CFG-P02, CMT-CFG-U01, CMT-ABS-P01, CMT-ABS-U01, CMT-ABS-N01, CMT-ID-U02", "SettingValueShape, KnownValueShape, WithheldShape, UnknownNeedsReasonShape, AbsentNeedsCompleteReadShape, DefaultNotConfiguredShape, UnknownMarkerShape"),
    ("P7", "Realização reificada com PROV-O e fidelidade por direção",
     "Realização em string ('aws=R; google=R'), proveniência em string, injetividade (R1-M5, F3).",
     "<code>bo:Realization</code>: <code>bo:of</code> descritor, <code>bo:onProvider</code>, <code>bo:realizedBy</code> (1:N artefatos), "
     "<code>bo:liftingFidelity</code> e <code>bo:loweringFidelity</code> separadas, <code>bo:evidenceState</code> (escada §9.2), "
     "<code>prov:wasDerivedFrom</code> o schema fixado, <code>prov:wasGeneratedBy</code> a atividade de mapeamento, <code>prov:wasAttributedTo</code> o "
     "agente. Alternativas: <code>bo:alternativeTo</code> com guarda e exclusividade provada ou AMBIGUOUS; perdas em <code>bo:LossRecord</code>; "
     "projeções por ocorrência. Fidelidade sem perda exige evidência documental.",
     "CMT-LOSS-P01, CMT-LOSS-N02, CMT-LOSS-U02", "RealizationShape, GuardShape, LossRecordShape, ProjectionShape, ProviderArtifactShape, SchemaSourceShape"),
    ("P8", "Padrão de descritor (sem punning, sem metamodelagem)",
     "<code>adm:hasRealization rdfs:domain owl:Class</code> tirava o esqueleto do OWL 2 DL; citar a propriedade como objeto faz punning.",
     "Cada propriedade ou classe citada em ABox ganha um indivíduo <code>bo:PropertyDescriptor</code> / <code>bo:ClassDescriptor</code>; "
     "<code>bo:of</code> aponta para o indivíduo; o indivíduo liga-se à entidade OWL por anotação (<code>bo:describesProperty</code>, "
     "<code>bo:describesClass</code>), que o raciocinador não vê e que não tipa o IRI. O SHACL confere unicidade, que o alvo é propriedade "
     "(ou classe) declarada e que o alvo não é indivíduo. O gate <code>bo.ontpat.no_punning</code> confere o resto.",
     "R1-M5, S1", "PropertyDescriptorShape, ClassDescriptorShape, OfShape"),
    ("P9", "Escopo de localização",
     "Sem modelo de escopo global, regional e zonal (R2-W5).",
     "<code>bo:Location</code> com <code>bo:locationScope</code> (global, regional, zonal), <code>bo:withinLocation</code> (zona em região, região "
     "no global) e chave <code>(bo:ofProvider, bo:locationCode)</code>. Recurso global aponta para a localização global do provedor.",
     "CMT-ID-N01, CMT-ID-U02", "LocationShape"),
    ("P10", "Unidades QUDT por IRI; durações",
     "Unidades em string e quatro propriedades de retenção sem relação (R1-M6).",
     "<code>bo:hasUnit</code> aponta para o IRI de unidade do QUDT usado como indivíduo de <code>bo:UnitOfMeasure</code>, ou para "
     "<code>bo:UnitNotApplicable</code> ≠ <code>bo:UnitUnknown</code>. Valor numérico exige unidade. Duração é <code>xsd:duration</code> e "
     "carrega a própria unidade; mês e ano não viram segundos (TRANSFORMS decide com contexto de calendário).",
     "CMT-LOSS-U01", "NumericNeedsUnitShape, UnitIriShape, DurationNoUnitShape"),
    ("P11", "Papel e OntoClean corrigido",
     "Papéis como tipos rígidos e exemplo OntoClean invertido na v2 (R1-M3, F9).",
     "Papel é classe definida antirrígida SOB o tipo rígido (ex.: membro de pool ≡ recurso endereçável ⊓ ∃membro.pool). A rigidez é "
     "anotação (<code>bo:rigidity</code>); o verificador reprova classe rígida ou semirrígida sob antirrígida, nas duas direções, sobre a "
     "hierarquia asserida e sobre a inferida pelo HermiT.",
     "CMT-LB-P04, CMT-LB-N01, CMT-TAX-P01, CMT-TAX-N04, CMT-DB-P02", "(verificador bo.ontpat.ontoclean)"),
]


def ontpat_html(stats: dict, prof: dict, trial: dict | None, suite: dict | None) -> str:
    b = ["<h1>Padrões de ontologia (ODP) do BrevOps</h1>",
         f'<p class="meta">Módulo ONTPAT · contrato C14 (parte TTL) · padrões escritos em 2026-11-02 (America/Recife) · '
         f'ROBOT {E(prof["toolchain"]["robot"])}, HermiT {E(prof["toolchain"]["hermit"])}, ELK {E(prof["toolchain"]["elk"])}, '
         f'OWLAPI {E(prof["toolchain"]["owlapi"])} (ontology/patterns/toolchain_pins.json)</p>',
         '<div class="kpis">'
         + "".join(f'<div class="kpi"><b>{v}</b>{E(k)}</div>' for k, v in stats["kpis"].items()) + "</div>",
         "<p>Arquivos: <code>bo-patterns.ttl</code> (padrões, importa <code>descriptor-pattern.ttl</code>), "
         "<code>example-abox.ttl</code> (um exemplo de cada padrão), <code>shapes/patterns.shacl.ttl</code>, <code>naming_rules.yaml</code>, "
         "<code>UPPER_DECISION.html</code> e <code>upper_trial/*/cases.ttl</code>. Espaço de nomes dos termos: "
         "<code>https://w3id.org/brevops/ontology#</code> (ainda não registrado no w3id).</p>"]
    b.append("<h2>Perfil e regimes de entailment (S3)</h2><table>"
             f"<tr><td>fecho de imports de bo-patterns.ttl em OWL 2 DL</td><td>{yn(prof['closure']['in_profile'])}</td></tr>"
             f"<tr><td>HermiT: fecho consistente e sem classe insatisfatível</td><td>{yn(prof['closure']['hermit_consistent_coherent'])}</td></tr>"
             f"<tr><td>HermiT: ABox de exemplo + fecho consistente</td><td>{yn(prof['example_abox_hermit_consistent_coherent'])}</td></tr>"
             f"<tr><td>PROV-O publicado (2013-04-30) em OWL 2 DL</td><td>{yn(prof['prov_o']['in_profile'])} "
             f"({prof['prov_o']['violations']} violações: {E(', '.join(t.split('#')[-1] for t in prof['prov_o']['punned_terms']))} são ao mesmo tempo "
             "propriedade de objeto e de anotação)</td></tr></table>"
             "<p>Consequência do último item: o PROV-O não é importado (o fecho sairia do DL); os termos usados são declarados em "
             "<code>bo-patterns.ttl</code> com <code>rdfs:isDefinedBy</code> a versão 2013-04-30, só como propriedade de objeto. É exatamente "
             "o que checar o perfil no arquivo isolado, e não no fecho, deixaria passar.</p><table>")
    for k, v in stats["regimes"].items():
        b.append(f"<tr><td><b>{E(k)}</b></td><td>{E(v)}</td></tr>")
    b.append("</table><p class='note'>O import de descriptor-pattern.ttl é relativo ao documento: resolve igual no repositório "
             "principal, numa worktree e quando publicado ao lado, sem catálogo e sem rede. Proposta ao OWL (dono do fecho de trabalho): "
             "catálogo <code>catalog-v001.xml</code> com IRIs w3id quando o w3id for registrado.</p>")
    b.append("<h2>Padrões</h2>")
    for pid, title, prob, sol, cmts, shapes in PATTERNS:
        b.append(f"<h3>{pid}. {E(title)}</h3><p><b>Problema.</b> {prob}</p><p><b>Solução.</b> {sol}</p>"
                 f"<p class='meta'>compromissos: {E(cmts)} · formas: {E(shapes)}</p>")
    if suite:
        b.append("<h2>Compromissos do REQUIREMENTS como casos de teste dos padrões</h2>"
                 f"<p>{suite['summary']['pass']} de {suite['summary']['total']} compromissos que listam o ONTPAT como consumidor "
                 f"reproduzem a resposta esperada nos padrões (HermiT + SHACL + verificador OntoClean); "
                 f"{suite['summary']['out_of_scope']} ficam fora do alcance dos padrões, com o módulo que os decide. Fonte: results/ONTPAT/commitment_suite.json.</p>"
                 "<div class='wrap'><table><tr><th>compromisso</th><th>esperado</th><th>resultado</th><th>como</th></tr>")
        for cid, r in suite["cases"].items():
            res = (yn(r["pass"], "reproduz", "diverge") if r["status"] == "tested" else f'<span class="unk">fora do alcance</span>')
            b.append(f"<tr><td><code>{E(cid)}</code></td><td>{E(str(r['expected']))}</td><td>{res}</td><td>{E(r['how'])}</td></tr>")
        b.append("</table></div>")
    if trial:
        d = trial["decision"]
        b.append(f"<h2>Ontologia de topo</h2><p>Decisão: <b>{E(trial['candidates'][d['chosen']]['label'] if d.get('chosen') else '-')}</b>. "
                 f"{E(d['why'])}. Detalhes em <code>UPPER_DECISION.html</code>.</p>")
    b.append("<h2>Achados contra a hipótese de trabalho</h2><ul>"
             "<li>A identidade composta de cinco componentes do plano não basta através do tempo: com <code>owl:hasKey</code> só sobre ela, o "
             "recurso substituído e o novo são inferidos o mesmo e a ontologia fica inconsistente (mutação de CMT-ID-P02). Entrou o sexto "
             "componente, a encarnação.</li>"
             "<li>O PROV-O publicado não está em OWL 2 DL; importar inteiro tiraria o fecho do perfil.</li>"
             "<li>Alinhamento sem declarações explícitas faz o OWLAPI tomar subpropriedade por anotação e o fecho sai do DL "
             "(primeira execução do teste de topo, corrigida no gerador).</li></ul>")
    b.append("<h2>Limites</h2><ul><li>Domínio e classes concretas não são deste módulo (CLASS, PROP, OWL): o exemplo usa uma extensão "
             "<code>exv:</code> só para exercitar os padrões.</li><li>Os gates lexicais de nome (naming_rules.yaml) são higiene, não validade.</li>"
             "<li>O SHACL valida o grafo como dado; quem chama tem de materializar os tipos antes (ABOX-LIFT).</li></ul>")
    return page("Padrões ONTPAT BrevOps", "\n".join(b))


def stats() -> dict:
    from . import pins
    pdir = c.patterns_dir()
    closure, _ = c.load_closure(pdir / c.PATTERNS)
    ex = c.parse(pdir / c.EXAMPLE)
    sh = c.parse(c.repo() / "shapes" / "patterns.shacl.ttl")
    bo = str(c.BO)
    n_cls = sum(1 for s in closure.subjects(RDF.type, OWL.Class) if str(s).startswith(bo))
    n_prop = sum(1 for t in (OWL.ObjectProperty, OWL.DatatypeProperty, OWL.AnnotationProperty)
                 for s in closure.subjects(RDF.type, t) if str(s).startswith(bo))
    n_shapes = sum(1 for _ in sh.subjects(RDF.type, rdflib.URIRef("http://www.w3.org/ns/shacl#NodeShape")))
    return {"kpis": {"padrões": len(PATTERNS), "classes bo:": n_cls, "propriedades bo:": n_prop,
                     "formas SHACL": n_shapes, "triplas no exemplo": len(ex)},
            "regimes": pins.REGIMES}


def targets() -> dict:
    import json
    res = c.results_dir()
    trial = c.read_json(res / "upper_trial.json") if (res / "upper_trial.json").exists() else None
    prof = c.read_json(res / "profile" / "profile.json")
    suite = c.read_json(res / "commitment_suite.json") if (res / "commitment_suite.json").exists() else None
    out = {c.patterns_dir() / "ONTPAT.html": ontpat_html(stats(), prof, trial, suite)}
    if trial:
        out[c.patterns_dir() / "UPPER_DECISION.html"] = upper_decision_html(trial)
    return out


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    bad = []
    for p, text in targets().items():
        if "--check" in argv:
            if not p.exists() or p.read_text(encoding="utf-8") != text:
                bad.append(str(p))
        else:
            p.write_text(text, encoding="utf-8")
            c.emit(f"escrito {p}")
    for b in bad:
        c.emit("difere do gerado: " + b)
    if "--check" in argv and not bad:
        c.emit("ONTPAT.html e UPPER_DECISION.html conferem com o gerado")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
