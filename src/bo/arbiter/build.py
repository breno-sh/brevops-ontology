"""Materializa o ARBITERLIB: python -I -m bo.arbiter.build [--check]

Escreve, só a partir de src/bo/arbiter e das bibliotecas congeladas que ele importa:
  arbiter/RULES.html                     regras, precedência, convenções de entrada, saídas e arquivos congelados
  arbiter/ARBITER.sha256                 sha256 de todo arquivo de que o veredito depende (bo.arbiter.freeze)
  results/ARBITERLIB/battery.jsonl       o mundo plantado (C09 decodificado; contém erros plantados de propósito)
  results/ARBITERLIB/battery_verdicts.jsonl  vereditos C21 do mundo plantado (hora fixa, sha do árbitro congelado)
  results/ARBITERLIB/battery_cycles.jsonl    tentativas de composição do K4
  results/ARBITERLIB/battery_report.json     relatório (conflito genuíno × estrutura válida)
  results/ARBITERLIB/MANIFEST.sha256     (C17) dos arquivos acima em results/ARBITERLIB
--check não grava: sai 1 se algo publicado difere do que o código produz (regeneração idêntica).
"""

from __future__ import annotations

import argparse
import html
import json
import sys

from bo.semantics.composition import semantic_table

from . import battery as B
from . import engine
from .common import dump_json, dump_jsonl, emit, now, repo, sha256_bytes
from .freeze import MANIFEST, RULES_HTML, frozen_files, manifest_text
from .rules import ARB_RULES, PRECEDENCE, RULE_ALIASES, RULE_ID_PATTERN, SEM_RULES, published_id

AUTHORED_AT = "2026-11-04T12:30:00-03:00"
RES = "results/ARBITERLIB"

CONVENTIONS = [
    ("Entrada", "C09 em SSSOM TSV (bo.contracts.sssom) ou JSONL; vários arquivos e globs; opcionalmente o glossário "
                "auditado C20 (pasta com claims.jsonl e glossary_audit.jsonl) e os átomos C01."),
    ("Versões", "Só a versão corrente de cada claim_id é julgada (a que nenhuma outra substitui). Bifurcação, inclusive "
                "o mesmo claim_id em dois arquivos, refuta as duas (ARB-VERSION): claim_id é global."),
    ("Projeção", "A alegação fala da parte que a projeção do campo extrai. Tipo do lado = tipo da projeção; etapa inicial "
                 "de translation_fn igual ao extrator é descartada; entrada de teste que o extrator aceita é o campo "
                 "inteiro. Várias projeções do mesmo campo numa alegação: transporta a de concept igual ao conceito da "
                 "alegação."),
    ("Grupo", "Regra sobre subgrafo: variáveis ?nome com lado, campo e ocorrência; passos com argumentos nomeados. Os "
              "tipos das variáveis são os componentes da tupla do seu lado (nome sem '?'). Testes "
              "{input: {?var_sujeito: v}, expected: {?var_objeto: v}}. Linha com bo_group_id e sem group usa a definição "
              "única de outra linha."),
    ("Registro", "Etapa só do registro fechado do TRANSFORMS é tipada (check_chain) e testada pelo registro; não compõe "
                 "no K4 (a referência não tem imagem nem inversa dela)."),
    ("Âncoras", "basis=shared_concept exige anchors com claim_id/claim_version_id do C20; o estado vale pela versão "
                "corrente e pela última auditoria, não pelo que o mapeador declarou. DOC_SUPPORTED ou OBSERVATION_TESTED; "
                "PERSISTENCE_VERIFIED não conta para âncora (leitura de volta não prova significado, regra do SEMANTICS; "
                "é a leitura do '≥ DOC_SUPPORTED' do brief com essa exceção). Sem glossário, UNPROVEN."),
    ("Ids de regra", "Todo id publicado casa com o padrão do C21 ({pat}). Duas regras do SEMANTICS têm id de uma palavra e "
                     "saem com id conforme, mantido o antigo como alias (aceito em 'disabled'): {al}. A regra não muda; "
                     "só o nome publicado (CC-2 do PILOT-STO-MAP, 04/11/2026)."),
    ("Recongelamento", "2026-11-04: o fecho congelado mudou a montante (emendas 3 a 6 do CONTRACTS: esquemas C00, C09, C20 e "
                       "src/bo/contracts/rules.py, spec_a..d.py, sssom.py) e o árbitro foi recongelado sobre bo/base; "
                       "depois, o SEMANTICS 61d6fae (CC-3: invert aceita função do registro) mudou claims.py e "
                       "transforms.py do fecho e o árbitro foi recongelado de novo (ARBITER-20261104-2); depois da emenda 7 "
                       "do CONTRACTS e dos merges do SEMANTICS e do TRANSFORMS que ela pediu, recongelado pela "
                       "terceira vez (ARBITER-20261104-3), com o HEAD de bo/base conferido dentro da trava. Comprovante "
                       "vigente: results/ARBITERLIB/freeze_receipt_ARBITER-20261104-3.json; os anteriores ficam como "
                       "histórico. Motivo: contrato e referência a montante, "
                       "não ajuste de resultado (CC-1 do PILOT-STO-MAP)."),
    ("Ausência", "Linha com sssom:NoTermFound (C09-NONE; C09 3.2.0 com absence.side) tem veredito próprio: OK quando a "
                 "ausência é bem formada, de tipo provado (ABSENCE_DEMONSTRATED, OUT_OF_PIN, UNSUPPORTED_BY_TRANSLATOR) e "
                 "com evidência citada; UNPROVEN quando UNRESOLVED ou sem evidência; REFUTED quando mal formada. Não é "
                 "related (sem ARB-RELATED-EV), não entra nas regras de conjunto nem no K4, e o relatório a conta à parte "
                 "(n_absences, verdicts_absences, absences_by_kind). CC-7 do PILOT-STO-MAP."),
    ("Domínio no registro", "Cadeia só do registro do TRANSFORMS com domínio do sujeito finito (enum, booleano, inteiro "
                            "com faixa curta): a relação de domínios é calculada aplicando o registro a cada valor; "
                            "vale VDR-COMPUTED e FID-COHERENT como no núcleo, e 'sem perda' deixa de ser UNPROVEN quando "
                            "o cálculo o prova. CC-9 do PILOT-STO-MAP."),
    ("Saída da conferência", "bo.arbiter.run com --check-unproven e sem --out grava em $BO_TMP/arbiter, nunca em $BO_DATA "
                             "(o gate não regrava o dado publicado). CC-MAP-NET-4 do PILOT-NET-MAP."),
    ("Ciclo", "cycle do C21 é a rodada do árbitro (1; com --previous, 1 + a maior já gravada). Os ciclos do grafo K4 "
              "vão em cycles.jsonl (cada tentativa de composição e as diretas conferidas)."),
    ("Compostos", "Todo composto COMPOSED do K4 sai em verdicts.jsonl com claim_id = pernas ligadas por ∘ e "
                  "composition_used = a cadeia: OK, ou CONTESTED se contradiz uma direta. Composto UNPROVEN por regra "
                  "da tabela, das guardas ou do domínio também sai; o que não compõe porque uma perna não é OK fica só "
                  "em cycles.jsonl. Alegação afirmada contestada por ciclo leva composition_used = a cadeia mais curta."),
    ("Indecidido", "Guarda com satisfatibilidade UNKNOWN entre duas alegações não vira conflito nem exclusividade: vai a "
                   "'undecided' no relatório (e, para realizações, a interseção UNKNOWN conta como não exclusiva)."),
]


def _t(x) -> str:
    return html.escape(str(x))


def rules_html(files: list[str]) -> str:
    st = semantic_table()
    rows_arb = "".join(f"<tr><td><code>{_t(r['rule_id'])}</code></td><td>{_t(r['layer'])}</td><td>{_t(r['family'])}</td>"
                       f"<td>{_t(r['on_fail'])}</td><td>{_t(r['text'])}</td><td>{_t(', '.join(r['answers']))}</td></tr>"
                       for r in ARB_RULES.values())
    rows_sem = "".join(f"<tr><td><code>{_t(published_id(r['rule_id']))}</code>"
                       + (f" (alias do SEMANTICS: <code>{_t(r['rule_id'])}</code>)" if published_id(r['rule_id']) != r['rule_id'] else "")
                       + f"</td><td>{_t(r['family'])}</td><td>{_t(r['on_fail'])}</td>"
                       f"<td>{_t(r['text'])}</td></tr>" for r in SEM_RULES.values())
    rows_tab = "".join(f"<tr><td>{_t(a)}</td><td>{_t(b)}</td><td>{_t(v['result'] or '⊥ (UNPROVEN)')}</td>"
                       f"<td>{_t(v['why'])}</td></tr>" for (a, b), v in st.items())
    al = ", ".join(f"{a} -> {b}" for a, b in sorted(RULE_ALIASES.items()))
    rows_conv = "".join(f"<tr><th>{_t(k)}</th><td>{_t(v.replace("{pat}", RULE_ID_PATTERN).replace("{al}", al))}</td></tr>"
                        for k, v in CONVENTIONS)
    rows_files = "".join(f"<li><code>{_t(f)}</code></li>" for f in files)
    return f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Regras do árbitro</title>
<style>
:root{{--bg:#fbfaf7;--fg:#1d1f22;--muted:#5d636b;--line:#dcd8cf;--card:#ffffff;--accent:#2b5d8a;--code:#f1eee7;}}
@media (prefers-color-scheme: dark){{:root:not([data-theme="light"]){{--bg:#15171a;--fg:#e6e3dd;--muted:#a3a8ad;
--line:#33373c;--card:#1d2024;--accent:#8db7de;--code:#24282d;}}}}
:root[data-theme="dark"]{{--bg:#15171a;--fg:#e6e3dd;--muted:#a3a8ad;--line:#33373c;--card:#1d2024;--accent:#8db7de;--code:#24282d;}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--fg);font:15px/1.55 system-ui,-apple-system,"Segoe UI",sans-serif}}
main{{max-width:1100px;margin:0 auto;padding:24px 16px 64px}}
h1{{font-size:1.6rem;margin:0 0 4px}}h2{{font-size:1.25rem;margin:36px 0 8px;border-bottom:1px solid var(--line);padding-bottom:4px}}
.meta{{color:var(--muted);font-size:.9rem}}
.wrap{{overflow-x:auto}}
table{{border-collapse:collapse;width:100%;margin:8px 0;font-size:.88rem}}
th,td{{border-bottom:1px solid var(--line);padding:6px 8px;vertical-align:top;text-align:left}}
code{{background:var(--code);padding:1px 4px;border-radius:4px;font-size:.85em}}
ol li,ul li{{margin:4px 0}}
</style></head><body><main>
<h1>Regras do árbitro (ARBITERLIB)</h1>
<p class="meta">Contrato de saída C21 3.0.0 · versão das regras {AUTHORED_AT} (America/Recife) · código congelado em
<code>{MANIFEST}</code>; o <code>arbiter_sha256</code> de cada veredito é o sha256 desse arquivo.</p>
<p>O árbitro é código: não chama LLM, não vota e não desempata. Cada alegação C09 sai com um veredito
(OK, REFUTED_BY_RULE, UNPROVEN, CONTESTED ou AMBIGUOUS), as regras que o decidiram e, quando um ciclo do K4
a contesta, a composição usada. As obrigações por tipo são as do SEMANTICS (bo.semantics.obligations, com as
guardas corrigidas no commit f48865f); as transformações são as do núcleo do SEMANTICS e do registro fechado do
TRANSFORMS; a composição é a tabela formal do SEMANTICS (semantics/composition_table.json).</p>
<h2>Camadas do objetivo</h2>
<ol>
<li><b>A1</b> bem-formação: grupo como regra sobre subgrafo (G-VARS, G-ARITY, G-OCC, ARB-G-DUP, ARB-G-CONSIST), ocorrência
identificada (P-OCC, ARB-OCC-ID), versões e esquema (ARB-VERSION, ARB-C09-SCHEMA).</li>
<li><b>A2</b> tipo e grandeza para TODA correspondência que transporta valor (exact, close, broad, narrow e grupos): TYPE-WF,
KIND-UNKNOWN, KIND-EQ, UNIT-*, ARB-G-TYPE, ARB-FN-TYPE, ARB-ATOM-TYPE.</li>
<li><b>A3</b> obrigação de prova do tipo declarado: EXACT-NORM/TESTS, CLOSE-LOSS, BN-PRED/TESTS com orientação SKOS,
FIXED-DATED, EVIDENCE-DOC; mesmo conceito não prova (ANCHOR-NOT-PROOF, ARB-ANCHOR); unknown==unknown é UNPROVEN.</li>
<li><b>A4</b> composição no K4 pela tabela formal, com interseção das guardas, satisfatibilidade e domínio compatível
(K-*); closeMatch não compõe por fecho; conflito de ciclo (ARB-K4-REL, ARB-K4-VDR, ARB-K4-VALUE) e de par
(SKOS-DISJ, ARB-PAIR-REL, ARB-PAIR-VALUE).</li>
<li><b>A5</b> projeções sobrepostas declaradas e verificadas (P-OVERLAP, também entre alegações; ARB-PROJ-DECL,
ARB-PROJ-PART); realizações múltiplas do mesmo alvo exigem exclusividade provada das guardas ou viram AMBIGUOUS
(A-EXCL, ARB-REAL-MULTI, ARB-ALT-MUTUAL).</li>
</ol>
<h2>Precedência</h2>
<p>{' &gt; '.join(_t(v) for v in PRECEDENCE)}. Conflito marca todas as alegações envolvidas; nenhuma ganha.
CONTESTED e AMBIGUOUS só nascem entre alegações que passaram nas próprias obrigações (o K4 e as realizações usam as
OK; SKOS-DISJ e o tipo do átomo, as não refutadas).</p>
<h2>Convenções de entrada e saída</h2>
<div class="wrap"><table>{rows_conv}</table></div>
<h2>Regras próprias do árbitro</h2>
<div class="wrap"><table><tr><th>regra</th><th>camada</th><th>família</th><th>saída</th><th>texto</th><th>responde</th></tr>
{rows_arb}</table></div>
<h2>Regras do SEMANTICS aplicadas (referência congelada)</h2>
<div class="wrap"><table><tr><th>regra</th><th>família</th><th>saída</th><th>texto</th></tr>{rows_sem}</table></div>
<h2>Tabela formal de composição (relação semântica)</h2>
<div class="wrap"><table><tr><th>r1</th><th>r2</th><th>r1∘r2</th><th>por quê</th></tr>{rows_tab}</table></div>
<h2>Como rodar</h2>
<ul>
<li><code>python -I -m bo.arbiter.run --frozen --in ARQ.sssom.tsv [--glossary DIR] [--check-unproven]</code></li>
<li><code>python -I -m bo.arbiter.unproven</code> · <code>python -I -m bo.arbiter.no_llm</code> (higiene) ·
<code>python -I -m bo.arbiter.permutation --rename</code> · <code>python -I -m bo.arbiter.determinism</code></li>
<li><code>shasum -a 256 -c arbiter/ARBITER.sha256</code> (rodado de $BO_REPO)</li>
</ul>
<h2>Arquivos congelados ({len(files)})</h2>
<ul>{rows_files}</ul>
</main></body></html>
"""


def products() -> dict[str, str]:
    """Tudo em memória: o manifesto usa os bytes do RULES.html novo (não precisa gravá-lo antes)."""
    r = repo()
    files = frozen_files()
    out = {RULES_HTML: rules_html(files)}
    lines = []
    for f in files:
        data = out[RULES_HTML].encode("utf-8") if f == RULES_HTML else (r / f).read_bytes()
        lines.append(f"{sha256_bytes(data)}  {f}\n")
    out[MANIFEST] = "".join(lines)
    sha = sha256_bytes(out[MANIFEST].encode("utf-8"))
    claims, expect, cases = B.world()
    res = engine.arbitrate(B.items_of(claims), decided_at=AUTHORED_AT, arbiter_sha256=sha)
    out[f"{RES}/battery.jsonl"] = dump_jsonl(claims)
    out[f"{RES}/battery_verdicts.jsonl"] = dump_jsonl(res["verdicts"])
    out[f"{RES}/battery_cycles.jsonl"] = dump_jsonl(res["cycles"])
    rep = dict(res["report"])
    rep.update(generated_at=AUTHORED_AT, timezone="America/Recife", arbiter_sha256=sha,
               planted={"cases": [{"case": c["case"], "expect": c["expect"]} for c in cases],
                        "met": sum(1 for cid, e in expect.items()
                                   if {v["verdict"] for v in res["verdicts"] if v["claim_id"] == cid} == {e}),
                        "n": len(expect)})
    out[f"{RES}/battery_report.json"] = dump_json(rep)
    keep = sorted(k for k in out if k.startswith(RES))
    out[f"{RES}/MANIFEST.sha256"] = "".join(f"{sha256_bytes(out[k].encode('utf-8'))}  {k}\n" for k in keep)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="bo.arbiter.build")
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)
    r = repo()
    out = products()
    diff = []
    for rel, text in sorted(out.items()):
        p = r / rel
        cur = p.read_text(encoding="utf-8") if p.exists() else None
        if cur != text:
            diff.append(rel)
            if not a.check:
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(text, encoding="utf-8")
    if a.check:
        for d in diff:
            emit(f"  DIFERE {d}")
        emit(f"[{now()}] build --check: {len(out)} produto(s), {len(diff)} diferente(s) do publicado")
        return 1 if diff else 0
    emit(f"[{now()}] build: {len(out)} produto(s), {len(diff)} reescrito(s)")
    rep = json.loads(out[f"{RES}/battery_report.json"])
    emit(f"  bateria: {rep['planted']['met']}/{rep['planted']['n']} vereditos plantados; {rep['verdicts']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
