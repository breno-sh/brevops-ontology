"""Materializa o SEMANTICS: python -I -m bo.semantics.build [--check]

Escreve, só a partir de src/bo/semantics (código e content/) e das entradas congeladas do REQUIREMENTS:
  semantics/composition_table.json      tabela formal (calculada)
  semantics/counterexamples.jsonl       contraexemplos por regra (pares mínimos)
  semantics/SEMANTICS.html              a teoria
  semantics/SEMANTICS.sha256            hashes dos três acima, do código, dos testes e do gate
  results/SEMANTICS/C09_proposta/, C10_proposta/   propostas de contrato ao CONTRACTS
  results/SEMANTICS/commitment_suite.json, edoal_roundtrip.json, owl_separation.json
  results/SEMANTICS/MANIFEST.sha256     (C17)
Antes de gravar, confere: todo contraexemplo rejeitado com controle aceito; compromissos reproduzidos.
--check não grava: sai 1 se algo publicado difere do que o código produz (regeneração idêntica).
"""

from __future__ import annotations

import argparse
import copy
import sys
from pathlib import Path

from . import common
from . import edoal
from . import owl_theory
from . import projections as PJ
from . import schemas
from . import transforms as TR
from .composition import table_document
from .content import counterexamples as CEC
from .content import examples as E
from .counterexamples import verify
from .fixtures import suite
from .render import render
from .sssom_io import write_tsv

AUTHORED_AT = "2026-11-03T00:30:00-03:00"
MS_EXAMPLES = "https://example.org/mapping-set/semantics-examples"

FINDINGS = [
    "O sssom-py 0.4.22 (versão do requirements.lock) descarta os slots de extensão declarados em "
    "extension_definitions ao ler o TSV. As colunas próprias do C09 (guarda, perda, predicado, prova...) não "
    "sobrevivem ao conversor oficial; o C09 é lido e escrito por bo.semantics.sssom_io, e o sssom-py fica como "
    "referência independente das quatro colunas padrão (o RDF delas sai isomorfo ao nosso).",
    "subject_type e object_type são slots PADRÃO do SSSOM (EntityTypeEnum). Usá-los para o tipo de valor faz o "
    "sssom-py descartar a linha inteira em silêncio ('not well-formed'). O C09 proposto usa subject_value_type e "
    "object_value_type.",
    "broad∘narrow e narrow∘broad não dão relação: pela composição RCC5, PP∘PPi admite as cinco relações e PPi∘PP "
    "quatro. Só exact∘exact dá exact; close∘close dá ⊥ (nem exact nem close).",
    "O fecho OWL do SKOS infere exactMatch entre pontas cujas guardas são incompatíveis; a regra executável dá "
    "composição vazia. A teoria OWL não pode ser usada para transportar.",
    "PERSISTENCE_VERIFIED não promove significado: dias de retenção e contagem de cópias persistem iguais e são "
    "grandezas diferentes (KIND-EQ pega; a leitura de volta não).",
    "O C23 não tem código de bloqueio para alegação refutada; o transporte usa REFUTED_BY_RULE (proposta ao CONTRACTS).",
    "A gramática de guarda do plano (sete operadores, sem negação) só prova exclusividade de alternativas por "
    "interseção UNSAT; complemento ('qualquer edição menos X') não é exprimível, e é preciso listar o enum.",
    "Arredondamento declarado muda a relação de domínios: GiB->GB tem imagem disjunta do reticulado inteiro do "
    "destino, mas é subconjunto do envoltório que o arredondamento cobre. O cálculo usa o envoltório quando há "
    "arredondamento declarado; sem ele, o valor é bloqueado.",
    "{n_rule_only} de {n_ce} contraexemplos não isolam a sua regra sozinhos (rule_only): desligada a regra, outra "
    "regra ainda os segura (ex.: marcador de ausência cai fora do tipo). Isso é redundância de defesa, relatada.",
]
LIMITS = [
    "Os exemplos usam provedores sintéticos (pa, pb, pc) e evidência sintética ('fixture:'); servem à teoria, não "
    "afirmam nada sobre provedores reais. Nomes de schema públicos só aparecem nas projeções, sem estado de evidência.",
    "O núcleo de funções e de unidades é o mínimo para executar a teoria; o registro fechado é do TRANSFORMS e os "
    "IRIs QUDT são conferidos pelo UNITS.",
    "A relação de domínios é exata para enums, faixas com passo e envoltórios contínuos; para strings com formato, "
    "documentos e árvores ela é unknown (não prova sem perda).",
    "O veredito oficial por alegação é do árbitro (ARBITERLIB, C21); este módulo fixa as obrigações e dá a "
    "implementação de referência que ele congela.",
    "EDOAL: só exact/broad/narrow como relação; close e related não têm equivalente e não são exportados; guarda, "
    "perda e prova vão como anotação bosx na célula.",
    "preserved_observations é registrado, exportado e vai ao traço, mas não é obrigação de prova aqui: quem o "
    "testa é a observação sob protocolo (PROBE-JOIN). Nenhum transporte depende dele.",
    "A semântica de conjuntos de broad/narrow (extensão do sujeito ⊂ do objeto) é mais forte que a do SKOS, que "
    "não torna broader transitiva; o que se transporta segue a nossa, o que se infere em OWL segue a do SKOS.",
]

C09_LEIA = """Proposta do SEMANTICS para o C09 3.0.0 ({at}, America/Recife)

O CONTRACTS (dono de contracts/C09_*.schema.json e do bo.contracts.validate) vem depois do SEMANTICS. Esta pasta
descreve o formato que a teoria executa e que o árbitro, os mapeadores e o reconciliador vão produzir:

  correspondence.schema.json  um registro por linha SSSOM, com as colunas próprias já decodificadas (JSON)
  examples.sssom.tsv          as alegações-exemplo da teoria, no TSV com extension_definitions

Pontos que o CONTRACTS precisa saber:
  1. subject_type/object_type são slots padrão do SSSOM: o tipo de valor vai em subject_value_type/object_value_type.
  2. O sssom-py 0.4.22 descarta slots de extensão: o leitor do C09 é bo.semantics.sssom_io (ou outro que os preserve).
  3. Colunas estruturadas (guard, translation_fn, loss_contract, membership_predicate, proof, ...) são JSON numa célula.
  4. value_domain_relation = {{relation, orientation: subject_to_object}}; a relação declarada tem de bater com a
     calculada (bo.semantics.obligations).
Regras que o schema não exprime (guarda na gramática, semantic_relation = predicate_id, obrigações de prova) estão
em python -I -m bo.semantics.validate c09 ARQ [--assess].
"""

C10_LEIA = """Proposta do SEMANTICS para a parte dele do C10 3.0.0 ({at}, America/Recife)

  composition_table.schema.json   formato de semantics/composition_table.json (publicado pelo SEMANTICS)
  guard.schema.json               gramática de guarda tipada (os sete operadores do plano)
  conditions.grammar.json         proposta ao TRANSFORMS para transforms/conditions.grammar.json
  transforms_kernel.json          núcleo de funções que a teoria executa (o registro fechado é do TRANSFORMS)

Sugestões ao CONTRACTS e ao TRANSFORMS:
  1. O C23 não tem código para alegação refutada; o transporte daqui usa REFUTED_BY_RULE.
  2. Códigos do C24 que vêm de bloqueio: KIND-UNKNOWN -> MISSING_EVIDENCE, falta de prova -> UNPROVEN.
  3. A semântica da guarda (SAT/UNSAT/UNKNOWN, TRUE/FALSE/INDETERMINATE, eliminação existencial do nó do meio)
     é a de bo.semantics.guards; o bo.transforms.guard_sat deve dar o mesmo resultado nos mesmos casos.
"""


def group_rows():
    rows = []
    cases = [
        (E.ALARM_GROUP, {"?al": {"pa:alarm.query": "CpuUtilization[5m].max() >= 90"}}),
        (E.PORT_GROUP, {"?r": {"pa:rule.protocol": "tcp", "pa:rule.from_port": 80, "pa:rule.to_port": 443}}),
        (E.CIDR_GROUP, {"?n": {"pa:network.base_address": "10.1.0.0"}, "?s": {"pa:subnet_sizing.prefix_length": 16}}),
    ]
    from .render import e
    from .transport import _jsonable
    for g, inst in cases:
        chk = PJ.check_group(g)
        out = PJ.apply_group(g, inst)
        rows.append([e(g["bo_group_id"]) + f" ({chk['verdict']})", e(g["cardinality"]),
                     e(f"{_jsonable(inst)} -> {_jsonable(out)}")])
    return rows


def produce() -> dict[str, bytes]:
    files: dict[str, bytes] = {}
    table = table_document()
    files["semantics/composition_table.json"] = common.dump_json(table).encode()
    ces = CEC.records()
    files["semantics/counterexamples.jsonl"] = common.dump_jsonl(ces).encode()
    results = [verify(c) for c in ces]
    bad = [r["ce_id"] for r in results if not r["ok"]]
    if bad:
        raise SystemExit(f"build: contraexemplos que não passam: {bad} (nada gravado)")
    st = suite()
    if st["n_reproduces"] != st["n"]:
        raise SystemExit(f"build: compromissos/CQs não reproduzidos: "
                         f"{[r['id'] for r in st['rows'] if not r['reproduces']]} (nada gravado)")
    examples = sorted(E.all_examples().values(), key=lambda r: r["claim_id"])
    files["results/SEMANTICS/C09_proposta/correspondence.schema.json"] = common.dump_json(schemas.C09_RECORD).encode()
    files["results/SEMANTICS/C09_proposta/examples.sssom.tsv"] = write_tsv(examples, MS_EXAMPLES).encode()
    files["results/SEMANTICS/C09_proposta/LEIA.txt"] = C09_LEIA.format(at=AUTHORED_AT).encode()
    files["results/SEMANTICS/C10_proposta/composition_table.schema.json"] = common.dump_json(schemas.COMPOSITION_TABLE).encode()
    files["results/SEMANTICS/C10_proposta/guard.schema.json"] = common.dump_json(schemas.GUARD).encode()
    files["results/SEMANTICS/C10_proposta/conditions.grammar.json"] = common.dump_json(schemas.grammar_document()).encode()
    files["results/SEMANTICS/C10_proposta/transforms_kernel.json"] = common.dump_json(
        {"note": "núcleo de referência do SEMANTICS; o registro fechado é do TRANSFORMS",
         "items": [{"name": s.name, "kind": s.kind, "domain": s.domain, "codomain": s.codomain,
                    "precondition": s.precondition, "error": s.error, "loss": "declarada à parte (loss_contract)",
                    "inverse": s.inverse} for s in TR.REGISTRY.values()]}).encode()
    files["results/SEMANTICS/C10_proposta/LEIA.txt"] = C10_LEIA.format(at=AUTHORED_AT).encode()
    files["results/SEMANTICS/commitment_suite.json"] = common.dump_json(st).encode()
    ed = edoal.roundtrip(examples, {"CLM-TU-01": {"object_ids": ["pb:alarm.metric_name", "pb:alarm.comparison",
                                                                  "pb:alarm.threshold", "pb:alarm.period", "pb:alarm.statistic"]}})
    files["results/SEMANTICS/edoal_roundtrip.json"] = common.dump_json(ed).encode()
    m1 = E.with_guard(E.EXACT_DAYS_HOURS, E.EDITION_STD)
    m2 = E.with_guard(E.EXACT_HOURS_SECS, [{"term": "subject.edition", "op": "edition_in", "value": ["premium"]}])
    sep = owl_theory.separation_report(m1, m2)
    files["results/SEMANTICS/owl_separation.json"] = common.dump_json(sep).encode()
    from .skos_roundtrip import checks as rt_checks
    rt = rt_checks()
    rts = {"n": len(rt), "n_ok": sum(c["ok"] for c in rt), "checks": [{"check": c["check"], "ok": c["ok"]} for c in rt]}
    files["results/SEMANTICS/skos_roundtrip.json"] = common.dump_json(rts).encode()
    content_sha = common.sha256_bytes(b"".join(files[k] for k in sorted(files)))
    ctx = {"at": AUTHORED_AT, "content_sha": content_sha, "table": table, "ce_results": results, "suite": st,
           "roundtrip": rts, "separation": sep, "edoal": ed, "example_claim": E.BROAD_ARCHIVE,
           "group_rows": group_rows(),
           "findings": [f.format(n_rule_only=sum(1 for r in results if r["mutation"] == "rule_only"), n_ce=len(results))
                        for f in FINDINGS], "limits": LIMITS,
           "files": {"semantics/SEMANTICS.html": "esta teoria", "semantics/composition_table.json": "tabela formal (C10)",
                     "semantics/counterexamples.jsonl": "contraexemplos por regra",
                     "semantics/SEMANTICS.sha256": "hashes (teoria, código, testes, gate)",
                     "src/bo/semantics/": "implementação de referência", "tests/semantics/": "testes (pytest)",
                     "results/SEMANTICS/C09_proposta/": "proposta do C09 ao CONTRACTS",
                     "results/SEMANTICS/C10_proposta/": "proposta da parte do C10 (guarda, tabela, núcleo de funções)",
                     "results/SEMANTICS/commitment_suite.json": "compromissos e CQs de perda reproduzidos"}}
    files["semantics/SEMANTICS.html"] = render(ctx).encode()
    return files


def _sha_lines(paths: list[str], root: Path, extra: dict[str, bytes]) -> bytes:
    lines = []
    for p in sorted(paths):
        b = extra[p] if p in extra else (root / p).read_bytes()
        lines.append(f"{common.sha256_bytes(b)}  {p}\n")
    return "".join(lines).encode()


def frozen_code(root: Path) -> list[str]:
    out = []
    for base in ("src/bo/semantics", "tests/semantics"):
        for f in sorted((root / base).rglob("*.py")):
            if "__pycache__" not in f.parts:
                out.append(str(f.relative_to(root)))
    if (root / "gates/SEMANTICS.sh").is_file():
        out.append("gates/SEMANTICS.sh")
    return out


def all_files(root: Path) -> dict[str, bytes]:
    files = produce()
    sem = ["semantics/SEMANTICS.html", "semantics/composition_table.json", "semantics/counterexamples.jsonl"]
    files["semantics/SEMANTICS.sha256"] = _sha_lines(sem + frozen_code(root), root, files)
    man = sorted(k for k in files if k != "results/SEMANTICS/MANIFEST.sha256")
    if (root / "gates/SEMANTICS.sh").is_file():
        man.append("gates/SEMANTICS.sh")
    if (root / "results/SEMANTICS/summary.json").is_file():
        man.append("results/SEMANTICS/summary.json")
    files["results/SEMANTICS/MANIFEST.sha256"] = _sha_lines(man, root, files)
    return files


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)
    root = common.repo()
    files = all_files(root)
    if a.check:
        diff = [p for p, b in files.items() if not (root / p).is_file() or (root / p).read_bytes() != b]
        for p in diff:
            common.emit(f"  difere: {p}")
        common.emit(f"[{common.now()}] build --check: {len(files) - len(diff)}/{len(files)} idênticos")
        return 1 if diff else 0
    for p, b in files.items():
        q = root / p
        q.parent.mkdir(parents=True, exist_ok=True)
        q.write_bytes(b)
    common.emit(f"[{common.now()}] build: {len(files)} arquivo(s) gravado(s) em {root}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
