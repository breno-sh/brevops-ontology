"""Relatórios publicados do CONTRACTS em results/CONTRACTS/:

  adoption.json    propostas mergeadas incorporadas (origem, sha256 na adoção, cópia congelada, o que mudou) e achados
  producers.json   arquivos já publicados pelos produtores (REPO, LIT, REQUIREMENTS, ONTPAT, SEMANTICS) conferidos
                   no validador único, incluindo os que os gates adiados desses módulos chamam
  MANIFEST.sha256  hashes dos artefatos do CONTRACTS (C17)

  python -I -m bo.contracts.report            grava
  python -I -m bo.contracts.report --check    confere (ignora só os carimbos de hora) e o manifesto
"""

from __future__ import annotations

import hashlib
import json
import sys

from . import _base, catalog, validate

ADOPTED = [
    ("results/REQUIREMENTS/C24_proposta/requirements.schema.json", "C24_requirements", "C24", "requirement",
     "adotado sem mudança (só $schema/$id saem, o contrato dá o $id)"),
    ("results/REQUIREMENTS/C24_proposta/commitments.schema.json", "C24_commitments", "C24", "commitment",
     "adotado sem mudança"),
    ("results/REQUIREMENTS/C24_proposta/cq_spec.schema.json", "C24_cq_spec", "C24", "cq_spec", "adotado sem mudança"),
    ("results/ONTPAT/C14_proposta/realization_row.schema.json", "C14_realization", "C14", "realization",
     "provider passa a ser o do C00 (real ou sintético provider_x); guards aceitam texto ou guarda tipada do C10; "
     "acrescenta references (referências entre artefatos criados) e exclusivity_proof, exigida só quando há "
     "alternativas declaradas ProvenExclusive (o exemplo do ONTPAT continua válido)"),
    ("results/SEMANTICS/C09_proposta/correspondence.schema.json", "C09_correspondence", "C09", "correspondence",
     "ids pelo C00; guarda por $ref ao C10; value_type com os marcadores QUDT do C00; translation_fn por nome (o "
     "registro do núcleo/C10 é conferido na regra C09-FN, não num enum congelado); projection e group tipados; "
     "acrescenta alternative_to, exclusivity, supersedes, inverse_of e os slots padrão do SSSOM; registro fechado"),
    ("results/SEMANTICS/C10_proposta/guard.schema.json", "C10_guard", "C10", "guard", "adotado sem mudança"),
    ("results/SEMANTICS/C10_proposta/composition_table.schema.json", "C10_composition_table", "C10",
     "composition_table", "contract_version fixo 3.0.0; linhas de VDR e de fidelidade tipadas; predicate nulo só "
     "com resultado nulo; regra C10-TABLE confere a cobertura dos 25/25/16 pares"),
    ("results/SEMANTICS/C10_proposta/conditions.grammar.json", "C10_conditions_grammar", "C10", "conditions_grammar",
     "o documento proposto vira o formato de conditions.grammar.json, com sat_tests obrigatórios (SAT, UNSAT, "
     "UNKNOWN) executados por bo.semantics.guards.satisfiable"),
]
SUGGESTIONS = [
    {"from": "SEMANTICS (C10_proposta/LEIA.txt, 1)", "suggestion": "C23 sem código para alegação refutada",
     "decision": "REFUTED_BY_RULE entra no C23 (C00 block_code), junto com UNKNOWN_INPUT (T-ABSENCE)"},
    {"from": "SEMANTICS (C09_proposta/LEIA.txt, 1)", "suggestion": "tipo de valor em subject_value_type/object_value_type",
     "decision": "adotado; subject_type/object_type ficam como slots padrão do SSSOM"},
    {"from": "SEMANTICS (C09_proposta/LEIA.txt, 2)", "suggestion": "sssom-py 0.4.22 descarta extensões",
     "decision": "I/O do C09 em bo.contracts.sssom, que delega a bo.semantics.sssom_io (mesmos bytes para as colunas "
                 "da teoria) e preserva as colunas novas; teste em tests/contracts"},
    {"from": "SEMANTICS (C09_proposta/LEIA.txt, 4)", "suggestion": "value_domain_relation = {relation, orientation}",
     "decision": "adotado; a relação calculada × declarada é obrigação do árbitro (bo.semantics.obligations), não de formato"},
    {"from": "REQUIREMENTS (C24_proposta/LEIA.txt)", "suggestion": "adotar os schemas e chamar as regras como validação semântica",
     "decision": "adotado: regra C24-MODEL chama bo.requirements.model.validate_* com os arquivos irmãos"},
    {"from": "ONTPAT (C14_proposta/LEIA.txt)", "suggestion": "linha de realizations.jsonl pelo padrão de descritor",
     "decision": "adotada com acréscimos (references, exclusivity_proof); regra C14-ALT confere alternativas mútuas"},
]
FINDINGS = [
    "bo.semantics.sssom_io.write_tsv só escreve as colunas que a teoria conhece: alternative_to, exclusivity, supersedes "
    "e os slots padrão do SSSOM somem em silêncio. Quem grava C09 3.0.0 usa bo.contracts.sssom.write_tsv.",
    "ontology/patterns/upper_trial/*/cases.ttl não importam bo-patterns.ttl: sozinhos, reprovam no C14 (punning aparente, "
    "porque os papéis vêm do fecho); o ONTPAT os confere junto com o fecho, e o validador confere o fecho dos owl:imports "
    "locais. Os demais TTL do ONTPAT passam.",
    "modulos.json (catálogo do coordenador) passa no C00: ids, branches, worktrees, tmp_dir, ondas recalculadas do DAG, "
    "índices declarados e versões dos 30 contratos iguais às publicadas.",
    "SEMANTICS examples.sssom.tsv passa no C09 3.0.0 sem mudança (20 alegações).",
    "Emenda 2026-11-03: a varredura dos 122 gates 'bo.contracts.validate' do modulos.json achou 9 que resolviam no "
    "tipo errado (o tipo homônimo do contrato ou um padrão de nome estreito): PINS (pins.json), DRIFT "
    "(atom_history.jsonl, sem tipo), GLOSSARY-AUDIT (glossary_audit.jsonl), NONEHUNT-x4 (disputes.jsonl lido como "
    "TSV), DEPSAMPLE (cases_aws.jsonl) e STATS-SUPP (numbers_supp.json). Depois da emenda: 122/122.",
    "paper/numbers_supp.json (STATS-SUPP) não tem contrato no artifact_catalog, mas o gate o valida como C18: "
    "o catálogo do coordenador deveria marcá-lo C18.",
    "Emenda 2: o stub C26 tem um plano por provedor, copiado das fixtures dos HARNESS-* (adopted/C26_plans_stub.json). "
    "Renderizado em 2026-11-03: aws (2 recursos), google (1), azurerm (4) saem RENDERED com fmt -check 0. O oci sai "
    "UNKNOWN_SYMBOLIC_INPUT sem --bindings (compartment_id e tags vêm do contexto privado do run, por desenho do "
    "HARNESS-OCI) e RENDERED com --bindings deploy/fixtures/oci/_templates/examples/bindings.json: o gate do "
    "HARNESS-OCI precisa passar --bindings (decisão do coordenador/HARNESS-OCI; nenhum plano OCI real renderiza sem).",
    "Emenda 2: type_subcategory.jsonl (C03 3.1.0) num só formato, superconjunto dos blocos subcategory/import. O do "
    "DOCS-OCI passa sem mudança; o do DOCS-AZURE precisa renomear import_id para import; o do DOCS-GCP é plano "
    "(subcategoria no topo) e precisa converter para o bloco subcategory; o do DOCS-AWS tem blocos import sem "
    "extraction_method/evidence_level e alguns interpreted sem model_id.",
    "C01 2.1.0: a biblioteca que grava os átomos (src/bo/schema/, FLAGS em core.py) é posse do SCHEMALIB; ela ainda "
    "não grava write_only (campo opcional, os átomos 2.0.0 continuam válidos). Não mexi no código dele.",
    "Emenda 3: o formato provisório de decisions.jsonl do GLOSSARY_BRIEF entra sem mudança no C20 3.1.0 (com "
    "narrower acrescentado); os exemplos de results/BRIEFS/examples/decisions.jsonl passam no schema, mas reprovam "
    "na regra C20-DEC-REF proposta pelo próprio BRIEFS: o glossary.jsonl irmão não tem os conceitos citados. A "
    "ausência tipada do MAPPER_BRIEF (curation_rule bo:NONE_<tipo>) continua aceita; o mapper_examples.sssom.tsv passa.",
    "SCHEMALIB: nested_type (protocolo 6) como UM átomo com tf_type cty cabe no C01 sem mudança (tf_type aceita "
    "lista; stub C01 tem um); o write_only entra como campo opcional (átomos já gravados continuam válidos).",
]
PRODUCER_FILES = [
    ("commitments", "requirements/commitments.jsonl", "REQUIREMENTS G1 (gate adiado)"),
    ("requirements", "requirements/requirements.jsonl", "gates/REQUIREMENTS.sh"),
    ("cq_spec", "requirements/cq_spec.jsonl", "gates/REQUIREMENTS.sh"),
    ("realizations", "results/ONTPAT/C14_proposta/realizations.example.jsonl", "gates/ONTPAT.sh"),
    ("C10_composition_table", "semantics/composition_table.json", "gates/SEMANTICS.sh"),
    ("correspondences", "results/SEMANTICS/C09_proposta/examples.sssom.tsv", "C09 (proposta do SEMANTICS)"),
    ("manifest_receipt", "results/REPO/summary.json", "gates/REPO.sh"),
    ("manifest_receipt", "results/LIT/summary.json", "gates/LIT.sh"),
    ("manifest_receipt", "results/ONTPAT/summary.json", "C17"),
    ("manifest_receipt", "results/REQUIREMENTS/summary.json", "C17"),
    ("manifest_receipt", "results/SEMANTICS/summary.json", "C17"),
    ("C17_manifest", "results/REPO/MANIFEST.sha256", "C17"),
    ("C17_manifest", "results/LIT/MANIFEST.sha256", "C17"),
    ("C17_manifest", "results/ONTPAT/MANIFEST.sha256", "C17"),
    ("C17_manifest", "results/REQUIREMENTS/MANIFEST.sha256", "C17"),
    ("C17_manifest", "results/SEMANTICS/MANIFEST.sha256", "C17"),
    ("C14_ttl", "ontology/patterns/bo-patterns.ttl", "C14 (fecho de imports)"),
    ("C14_ttl", "ontology/patterns/descriptor-pattern.ttl", "C14"),
    ("C14_ttl", "ontology/patterns/example-abox.ttl", "C14 (fecho de imports)"),
    ("C14_ttl", "shapes/patterns.shacl.ttl", "C14"),
    ("atoms", "contracts/stubs/C01/atoms.jsonl", "C01 2.1.0 (write_only e nested_type)"),
]


def sha(p) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def adoption() -> dict:
    root = _base.repo()
    items = []
    for src, name, cid, record, change in ADOPTED:
        p, copy = root / src, _base.PKG / "adopted" / f"{name}.json"
        items.append({"source": src, "source_sha256_now": sha(p) if p.is_file() else None,
                      "frozen_copy": f"src/bo/contracts/adopted/{name}.json", "frozen_sha256": sha(copy),
                      "drift": (sha(p) != sha(copy)) if p.is_file() else None,
                      "contract": cid, "definition": f"#/$defs/{record}", "change": change})
    from .amendments import AMENDMENTS
    return {"schema": "bo.contracts_adoption/1", "module": "CONTRACTS", "generated_at": _base.now(),
            "adopted": items, "suggestions": SUGGESTIONS, "amendments": AMENDMENTS, "findings": FINDINGS}


def producers() -> dict:
    root = _base.repo()
    rows = []
    for alias, rel, why in PRODUCER_FILES:
        r = validate.validate(alias, root / rel)
        rows.append({"alias": alias, "file": rel, "kind": r.kind, "why": why, "items": r.n, "ok": r.ok,
                     "errors": r.errors[:5]})
    return {"schema": "bo.contracts_producers/1", "module": "CONTRACTS", "generated_at": _base.now(),
            "checked": len(rows), "ok": sum(r["ok"] for r in rows), "files": rows}


def manifest_paths() -> list[str]:
    root = _base.repo()
    out = sorted(str(p.relative_to(root)) for p in (root / "contracts").rglob("*") if p.is_file())
    out += ["results/CONTRACTS/adoption.json", "results/CONTRACTS/producers.json"]
    return out


def _strip_time(d: dict) -> dict:
    return {k: v for k, v in d.items() if k != "generated_at"}


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    root = _base.repo()
    out = _base.results_dir()
    docs = {"adoption.json": adoption(), "producers.json": producers()}
    if "--check" in argv:
        bad = []
        for name, d in docs.items():
            p = out / name
            if not p.is_file() or _strip_time(json.loads(p.read_text(encoding="utf-8"))) != _strip_time(d):
                bad.append(name)
        if docs["producers.json"]["ok"] != docs["producers.json"]["checked"]:
            bad.append("producers.json: arquivo de produtor reprovado")
        if any(a["drift"] for a in docs["adoption.json"]["adopted"]):
            bad.append("adoption.json: proposta mudou depois da adoção (emenda?)")
        for b in bad:
            print(f"  DIFERE {b}")
        print(f"[{_base.now()}] report --check: {len(docs)} relatório(s), {len(bad)} problema(s); produtores "
              f"{docs['producers.json']['ok']}/{docs['producers.json']['checked']}")
        return 1 if bad else 0
    out.mkdir(parents=True, exist_ok=True)
    for name, d in docs.items():
        (out / name).write_text(json.dumps(d, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    lines = [f"{sha(root / p)}  {p}" for p in manifest_paths()]
    (out / "MANIFEST.sha256").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[{_base.now()}] report: adoption ({len(ADOPTED)} propostas), producers "
          f"({docs['producers.json']['ok']}/{docs['producers.json']['checked']}), MANIFEST ({len(lines)} arquivos)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
