"""Livro de pedidos de mudança (results/CONTRACTS/requests_ledger.json): todo pedido dos CONTRACT_CHANGE.txt dos
PILOT-* e dos módulos que eles consomem, com dono, decisão e o commit/versão que fecha. Insumo do E6 do PILOT-EXIT.

Decisões:
  ACEITO              mudança de contrato feita por emenda versionada (contrato@versão, commit)
  RECUSADO            sem mudança de contrato, com motivo
  ADIADO_FASE_2       fica para a fase 2, com motivo
  DE_OUTRO_DONO       não é contrato: o dono decide; status RESOLVIDO (commit) ou ABERTO
"""

from __future__ import annotations

# commits das emendas do CONTRACTS em bo/base
E1, E2, E2B, E3, E4, E5, E6, E7, E8 = ("3995e6a", "3c2141f", "513113d", "bdceb64", "469c4d7", "79d04b7", "2f3c0d3",
                                       "9919e4c", "4abc6e3")
E9 = "emenda 9"   # substituído pelo sha do commit da emenda 9 no relatório (ver EMENDA9_COMMIT)
EMENDA9_COMMIT = "85b8a6e"   # commit da emenda 9 (as mudanças de contrato)

A, R, D, O = "ACEITO", "RECUSADO", "ADIADO_FASE_2", "DE_OUTRO_DONO"
RES, ABE = "RESOLVIDO", "ABERTO"

# (módulo, item, resumo, dono, decisão, fecha: contrato@versão, commit ou status, motivo)
ITEMS = [
    # ---------------------------------------------------------------- PILOT-NET-E2E
    ("PILOT-NET-E2E", "CC-NET-E2E-1", "termo de lista de referências (security_list_ids)", "CONTRACTS; HARNESS-*", A,
     "C00@3.1.0, C26@1.3.0", E7, "renderizar o termo list é dos HARNESS-*"),
    ("PILOT-NET-E2E", "CC-NET-E2E-2", "tipo da anexação, seleção por rótulo e regras OCI saem UNKNOWN",
     "GRAIN (b, c); SERVICE-EVIDENCE (a)", O, ABE,
     "SERVICE-EVIDENCE respondeu (a) no item 8 (regras OCI com dono, ciclo e alcance); (b) e (c) são do GRAIN", ""),
    ("PILOT-NET-E2E", "CC-NET-E2E-3", "c2_taxonomy traduz fixture inválida; c3_full recusa", "-", R, "-", "-",
     "achado sobre os controles, sem pedido de mudança"),
    # ---------------------------------------------------------------- PILOT-NET-GLOSS
    ("PILOT-NET-GLOSS", "CC-1", "C25 por aspecto ilegível para o adaptador do GRAIN", "GRAIN", O, RES,
     "d8ada03", "o adaptador lê o C25 por aspecto; fixar a tradução no C25 duplicaria a tabela do GRAIN"),
    ("PILOT-NET-GLOSS", "CC-NET-1", "atributos de coleção de objetos sem átomo por campo", "CONTRACTS; SCHEMALIB; GRAIN",
     A, "C01@2.2.0", E7, "SCHEMALIB 1.1.0 já emite os elementos; refresh dos SCHEMA-*/HIST-* e o T1 do GRAIN na fase 2"),
    ("PILOT-NET-GLOSS", "CC-NET-2", "âncora em bloco ou tipo (efeito e sentido pela estrutura)", "CONTRACTS", A,
     "C20@3.2.0", E4, ""),
    ("PILOT-NET-GLOSS", "CC-NET-3", "alvo das referências, timeouts, deletion_policy", "SERVICE-EVIDENCE; GRAIN; CAND", O,
     ABE, "-", "não é formato de contrato"),
    ("PILOT-NET-GLOSS", "CC-NET-4", "âncora citando fato do C03 do átomo ou do C25 do tipo", "CONTRACTS", A,
     "C20@3.3.0 (evidence_ref)", E7, ""),
    # ---------------------------------------------------------------- PILOT-NET-MAP
    ("PILOT-NET-MAP", "CC-MAP-NET-1", "árbitro congelado diverge da base", "ARBITERLIB", O, RES, "52371e8/ddcdae7",
     "toda emenda que toca contracts/ pede novo recongelamento (coordenador)"),
    ("PILOT-NET-MAP", "CC-MAP-NET-2", "rule_id de uma palavra (EVIDENCE, SENTINEL)", "ARBITERLIB", R, "-", "35e299f",
     "o ARBITERLIB renomeou as regras; o rule_id do C00 continua com hífen"),
    ("PILOT-NET-MAP", "CC-MAP-NET-3", "consume_check: entradas mudaram depois do consumo", "PILOT-NET-GLOSS; PREREG", O,
     RES, "fe9c60c, 5b53dd8", ""),
    ("PILOT-NET-MAP", "CC-MAP-NET-4", "G3 regrava o dado publicado (sem --out)", "ARBITERLIB", O, RES, "cc57c0a",
     "com --check-unproven e sem --out o árbitro grava em $BO_TMP/arbiter"),
    ("PILOT-NET-MAP", "F-1", "lista e mapa sem datatype no C09 (KIND-UNKNOWN)", "CONTRACTS; SEMANTICS; TRANSFORMS", A,
     "C09@3.2.0, C10@3.1.0/3.2.0", f"{E7}, {E8}", "o KIND de coleção no árbitro é do SEMANTICS"),
    ("PILOT-NET-MAP", "F-1 (resto, adendo 13:13)", "grupo de portas contra faixa em lista: variável intermediária sem campo",
     "SEMANTICS; CONTRACTS", D, "-", "-",
     "a G-VARS do SEMANTICS exige campo para toda variável; o C09 acompanha quando o SEMANTICS definir a variável "
     "intermediária (fase 2)"),
    ("PILOT-NET-MAP", "F-2", "campos de bloco embutido sem tipo no pacote", "SCHEMALIB; UNITS; GRAIN", O, ABE,
     "-", "elementos de coleção chegam com o refresh da fase 2 (SCHEMALIB 1.1.0, C01 2.2.0)"),
    ("PILOT-NET-MAP", "F-3", "valores de enum suspeitos no pacote", "SCHEMA-*; UNITS", O, ABE, "-", ""),
    ("PILOT-NET-MAP", "F-4", "sentido da regra NSG oci em texto livre", "UNITS; DOCS-OCI", O, ABE, "-", ""),
    ("PILOT-NET-MAP", "F-5", "efeito fixo (aws, oci só permitem) sem decisão nem sentença", "PILOT-NET-GLOSS", O, ABE, "-",
     "decisão C20 (value_type com a semântica) cabe no contrato vigente; falta a decisão do glossarista"),
    ("PILOT-NET-MAP", "F-6", "ausência do lado objeto", "CONTRACTS", A, "C09@3.2.0 (absence.side)", E7, ""),
    ("PILOT-NET-MAP", "F-7", "árbitro devolve UNPROVEN para toda ausência", "ARBITERLIB", O, ABE, "-",
     "regra congelada; o C09 já tem a ausência tipada desde a emenda 3"),
    # ---------------------------------------------------------------- PILOT-NET-ORACLE
    ("PILOT-NET-ORACLE", "1", "tipo de arquivo para o gabarito do piloto", "CONTRACTS", A, "C24@1.1.0", E5, ""),
    ("PILOT-NET-ORACLE", "2", "origem pilot no C11", "CONTRACTS", A, "C11@3.1.0", E5, ""),
    ("PILOT-NET-ORACLE", "3", "estado de conexão sem evidência", "SERVICE-EVIDENCE", O, RES, "item 8 do SE",
     "procurado na doc e nas specs fixadas: continua UNKNOWN (achado)"),
    ("PILOT-NET-ORACLE", "4", "linha do NSG oci só interpretada", "SERVICE-EVIDENCE", O, RES, "item 8 do SE",
     "linha publicada com R-CONN-DOC"),
    ("PILOT-NET-ORACLE", "5", "prioridade única do NSG Azure ambígua", "-", R, "-", "-",
     "ambiguidade da documentação; o oráculo trata como UNKNOWN"),
    # ---------------------------------------------------------------- PILOT-STO-GLOSS
    ("PILOT-STO-GLOSS", "CC-1", "grão não lê a evidência real", "GRAIN; SERVICE-EVIDENCE", O, RES, "d8ada03, b952d98", ""),
    ("PILOT-STO-GLOSS", "CC-2", "glossarista sem docs_facts nas entradas", "COORD; BRIEFS", O, RES, "91bef3f", ""),
    ("PILOT-STO-GLOSS", "CC-3", "C01 fora das entradas", "COORD; BRIEFS", O, RES, "91bef3f", ""),
    ("PILOT-STO-GLOSS", "CC-4", "saídas e versões do piloto no catálogo; conteúdo do bundle", "COORD; CAND", O, ABE, "-",
     "o catálogo ainda carimba C19/C20 3.0.0 (o validador aceita a cadeia de emendas)"),
    ("PILOT-STO-GLOSS", "CC-5", "grão 100% UNKNOWN por falta de effective_scope", "GRAIN; SERVICE-EVIDENCE", O, ABE, "-", ""),
    ("PILOT-STO-GLOSS", "CC-6", "âncora UNRESOLVED sem sentença", "CONTRACTS; BRIEFS", A, "C20@3.3.0", E7, ""),
    ("PILOT-STO-GLOSS", "CC-7", "fonte de ciclo de vida, dono e alcance na camada de API", "GRAIN; SERVICE-EVIDENCE", O,
     ABE, "-", ""),
    # ---------------------------------------------------------------- PILOT-STO-MAP
    ("PILOT-STO-MAP", "CC-1", "árbitro congelado diverge da base", "ARBITERLIB", O, RES, "52371e8", ""),
    ("PILOT-STO-MAP", "CC-2", "rule_id de uma palavra", "ARBITERLIB", R, "-", "35e299f", "regras renomeadas no ARBITERLIB"),
    ("PILOT-STO-MAP", "CC-3", "invert com função do registro", "SEMANTICS", O, RES, "61d6fae", ""),
    ("PILOT-STO-MAP", "CC-4", "consume_check do pacote", "PILOT-STO-GLOSS", O, RES, "5f0ebb5", ""),
    ("PILOT-STO-MAP", "CC-5", "grandeza de unit:BYTE", "UNITS; SEMANTICS; TRANSFORMS", O, ABE, "UNITS 1.0.0, ea53bcf",
     "UNITS e SEMANTICS em AmountOfData; o TRANSFORMS ainda diverge (13 unidades); stub do C05 corrigido na emenda 9"),
    ("PILOT-STO-MAP", "CC-6", "lista/conjunto/mapa no C09 e combinadores", "CONTRACTS; SEMANTICS; TRANSFORMS", A,
     "C09@3.2.0, C10@3.1.0", f"{E7}, {E8}", ""),
    ("PILOT-STO-MAP", "CC-7", "ausência tipada como veredito próprio", "ARBITERLIB", O, ABE, "-", ""),
    ("PILOT-STO-MAP", "CC-8", "occurrence_key de bloco repetido", "GRAIN", O, ABE, "-", ""),
    ("PILOT-STO-MAP", "CC-9", "domínio de função do registro com tabela finita", "ARBITERLIB; TRANSFORMS", O, ABE, "-", ""),
    ("PILOT-STO-MAP", "CC-10", "privacy_lint e o event_id do árbitro", "COORD", O, RES, "7e444c2", ""),
    ("PILOT-STO-MAP", "CC-11", "consume_check (GRAIN 0.1.6, PREREG)", "PILOT-STO-GLOSS; PREREG", O, RES, "5f0ebb5, 5b53dd8", ""),
    ("PILOT-STO-MAP", "CC-12", "G3 regrava o dado publicado", "ARBITERLIB", O, RES, "cc57c0a", ""),
    ("PILOT-STO-MAP", "CC-13", "domínio de wrap_list no árbitro (VDR-UNKNOWN)", "SEMANTICS; ARBITERLIB", O, ABE, "-",
     "o formato já existe (C10 3.1.0/3.2.0); falta a imagem calculada"),
    ("PILOT-STO-MAP", "D-1", "ausência do segundo provedor como sujeito", "CONTRACTS", A, "C09@3.2.0 (absence.side)", E7, ""),
    # ---------------------------------------------------------------- HARNESS-*
    ("HARNESS-AWS", "1", "stub C26 sem plano aws", "CONTRACTS", A, "C26@1.1.0", E2, ""),
    ("HARNESS-AWS", "2", "UNKNOWN_INPUT sem campo tipado no C12", "CONTRACTS", A, "C00@3.2.0 (outcome.block_code)", E9, ""),
    ("HARNESS-AWS", "3", "nó do campo no readback", "CONTRACTS", A, "C12@3.1.0 (node_id)", E2, ""),
    ("HARNESS-AWS", "4", "entradas do harness no catálogo (pins, schema)", "COORD", O, ABE, "-", ""),
    ("HARNESS-AWS", "5", "campo do nome derivado", "CONTRACTS", A, "C26@1.1.0 (derived_name.field)", E2, ""),
    ("HARNESS-AZURE", "P1", "stub C26 sem plano azurerm", "CONTRACTS", A, "C26@1.1.0", E2, ""),
    ("HARNESS-AZURE", "1", "target_node na referência", "CONTRACTS", A, "C00@3.0.1, C26@1.1.0", E2, ""),
    ("HARNESS-AZURE", "2", "derived_name.field", "CONTRACTS", A, "C26@1.1.0", E2, ""),
    ("HARNESS-AZURE", "3", "nó do campo no readback", "CONTRACTS", A, "C12@3.1.0", E2, ""),
    ("HARNESS-AZURE", "4", "bloqueio pré-deploy sem lugar no C12", "CONTRACTS", A, "C00@3.2.0 (outcome.block_code)", E9, ""),
    ("HARNESS-AZURE", "5", "identificadores da conta sempre withheld", "JUDGE", O, ABE, "-", "política do juiz"),
    ("HARNESS-GCP", "P1", "caminho do stub no gate", "COORD", O, RES, "catálogo (opção B)", ""),
    ("HARNESS-GCP", "achado", "stub google não renderizava no 8.9.0", "CONTRACTS", A, "C26@1.1.0", E2, ""),
    ("HARNESS-GCP", "C12", "node_id no readback", "CONTRACTS", A, "C12@3.1.0", E2, ""),
    ("HARNESS-OCI", "P1", "caminho do stub no gate", "COORD", O, RES, "catálogo (opção B)", ""),
    ("HARNESS-OCI", "P2", "um plano oci renderizável no stub", "CONTRACTS", A, "C26@1.1.0", E2,
     "renderiza com --bindings (compartment vem do contexto privado)"),
    ("HARNESS-OCI", "P3", "derived_name.field", "CONTRACTS", A, "C26@1.1.0", E2, ""),
    ("HARNESS-OCI", "ACHADO 4", "tag de execução no plano", "CONTRACTS", A, "C26@1.2.0 (C26-NOTAG)", E6, ""),
    # ---------------------------------------------------------------- SERVICE-EVIDENCE
    ("SERVICE-EVIDENCE", "1", "fonte publicada = schema do binário assinado", "CONTRACTS", A, "C00@3.0.3, C25@1.1.0", E4, ""),
    ("SERVICE-EVIDENCE", "2", "nível de fato UNKNOWN", "CONTRACTS", A, "C25@1.1.0 (consulted)", E4, ""),
    ("SERVICE-EVIDENCE", "3", "fact_kind api_bridge e default", "CONTRACTS", A, "C25@1.1.0", E4, ""),
    ("SERVICE-EVIDENCE", "4", "api_resource.resource UNKNOWN", "CONTRACTS", A, "C25@1.1.0 (C25-API)", E4, ""),
    ("SERVICE-EVIDENCE", "5", "protocol_support.jsonl", "CONTRACTS", A, "C25@1.2.0", E5, ""),
    ("SERVICE-EVIDENCE", "6", "block_path de topo", "CONTRACTS", A, "C25@1.1.0", E4, ""),
    ("SERVICE-EVIDENCE", "7a", "schema_source.op shape", "CONTRACTS", A, "C00@3.2.0", E9, ""),
    ("SERVICE-EVIDENCE", "7b", "rule_id de topo", "CONTRACTS", A, "C25@1.3.0", E9, ""),
    # ---------------------------------------------------------------- UNITS
    ("UNITS", "1", "grandeza de bytes e bits (AmountOfData)", "UNITS; SEMANTICS; TRANSFORMS; CONTRACTS (stub)", A,
     "stub C05@3.1.0", E9, "SEMANTICS adotou (ea53bcf); o TRANSFORMS ainda diverge (bo.units.crosscheck)"),
    ("UNITS", "2", "byte e bit sem prefixo com convenção NOT_APPLICABLE", "CONTRACTS", A, "C05@3.1.0", E9, ""),
    ("UNITS", "3", "duração com unidade NOT_APPLICABLE", "CONTRACTS", A, "C05@3.1.0", E9, ""),
    ("UNITS", "4", "prefixo de byte sem convenção (unit_candidates)", "CONTRACTS", A, "C05@3.1.0", E9, ""),
    ("UNITS", "5", "valores válidos numéricos", "CONTRACTS", A, "C05@3.1.0 (allowed_values)", E9, ""),
    ("UNITS", "6", "unidade do elemento numérico de árvore", "CONTRACTS", A, "C05@3.1.0", E9,
     "string com unidade no texto continua NOT_APPLICABLE (o tipo é texto)"),
    ("UNITS", "7", "coisa contada", "CONTRACTS", A, "C05@3.1.0 (counted)", E9, ""),
    # ---------------------------------------------------------------- TRANSFORMS, BRIEFS
    ("TRANSFORMS", "1", "list/set/map nas portas", "CONTRACTS", A, "C10@3.1.0", E8, ""),
    ("TRANSFORMS", "2", "any para porta polimórfica (C09 sem any)", "CONTRACTS", A, "C10@3.2.0", E9,
     "any só como item_type de porta do C10; o value_type do C09 (alegação) continua sem any"),
    ("BRIEFS", "1", "hierarquia e decisões do glossário", "CONTRACTS", A, "C20@3.1.0", E3, ""),
    ("BRIEFS", "2", "ausência tipada", "CONTRACTS", A, "C09@3.1.0", E3, ""),
    ("BRIEFS", "3", "fiação do catálogo (VALIDATOR_BRIEF, papéis)", "COORD", O, ABE, "-", ""),
    ("BRIEFS", "4", "skos_roundtrip --file", "SEMANTICS", O, RES, "63cb3ed", ""),
    ("BRIEFS", "5", "catálogo carimba C19/C20 3.0.0 nas saídas dos pilotos", "COORD", O, ABE, "-",
     "regenerar o artifact_catalog com as versões de contracts/ (amendments.py)"),
    # ---------------------------------------------------------------- DOCS-*
    ("DOCS-AWS", "1", "type_subcategory.jsonl", "CONTRACTS", A, "C03@3.1.0", E2, ""),
    ("DOCS-AWS", "2", "ID de importação é do tipo", "CONTRACTS", A, "C03@3.1.0 (type_fact.import)", E2, ""),
    ("DOCS-AWS", "3", "tamanho: fato por bloco repetido", "CONTRACTS; COORD", A, "C03@3.1.0 (applies_to)", E2,
     "privacy_lint por streaming (9f0cd52)"),
    ("DOCS-AZURE", "1", "type_subcategory.jsonl", "CONTRACTS", A, "C03@3.1.0", E2, ""),
    ("DOCS-AZURE", "2", "frase redigida", "CONTRACTS", A, "C00@3.0.1 (doc_source.redacted)", E2, ""),
    ("DOCS-AZURE", "3", "coverage.json no C15", "-", R, "-", "-", "cabe no C15 result vigente"),
    ("DOCS-GCP", "1", "type_subcategory.jsonl", "CONTRACTS", A, "C03@3.1.0", E2, ""),
    ("DOCS-GCP", "2", "ID de importação sem fact_kind", "CONTRACTS", A, "C03@3.1.0 (type_fact.import)", E2, ""),
    ("DOCS-GCP", "3", "eixo do C15 para cobertura de documentação", "-", R, "-", "-",
     "representability/field/observed_fraction descreve o censo"),
    ("DOCS-OCI", "1", "type_subcategory.jsonl", "CONTRACTS", A, "C03@3.1.0", E2, ""),
    ("DOCS-OCI", "2", "tamanho do docs_facts e privacy_lint", "COORD", O, RES, "9f0cd52", ""),
    ("DOCS-OCI", "3", "applicable_when", "CONTRACTS", A, "C03@3.1.0", E2, ""),
    ("DOCS-OCI", "4", "um formato só para type_subcategory", "CONTRACTS", A, "C03@3.1.0", E2, ""),
    # ---------------------------------------------------------------- SCHEMALIB, SCHEMA-*, PINS, METRICSLIB
    ("SCHEMALIB", "1", "write_only no C01", "CONTRACTS", A, "C01@2.1.0", E1, ""),
    ("SCHEMALIB", "2", "nested_type como um átomo", "-", R, "-", "-", "registro; cabe no C01 vigente"),
    ("SCHEMALIB", "3", "crosscheck dos SCHEMA-*", "SCHEMALIB", O, RES, "SCHEMALIB (causas mecânicas)", ""),
    ("SCHEMA-AWS", "1", "texto grande não varrido no --strict", "COORD", O, RES, "9f0cd52", ""),
    ("SCHEMA-AWS", "2", "falso positivo de tipo cty", "COORD", O, RES, "9f0cd52", ""),
    ("SCHEMA-AZURE", "1", "falso positivo de tipo cty", "COORD", O, RES, "9f0cd52", ""),
    ("SCHEMA-GCP", "1", "crosscheck: páginas só beta", "SCHEMALIB", O, RES, "SCHEMALIB (so_beta)", ""),
    ("SCHEMA-GCP", "2", "privacy_lint: binário grande e tipo cty", "COORD", O, RES, "1d74cd8, 9f0cd52", ""),
    ("SCHEMA-GCP", "3", "lacuna da biblioteca", "SCHEMALIB", O, ABE, "-", ""),
    ("SCHEMA-OCI", "1", "falso positivo de tipo cty", "COORD", O, RES, "9f0cd52", ""),
    ("SCHEMA-OCI", "2", "crosscheck no oci 9.11.0", "SCHEMALIB", O, RES, "SCHEMALIB (pagina_sem_tipo_no_schema)", ""),
    ("PINS", "1", "alias versions resolve pelo arquivo", "CONTRACTS", A, "catalog.resolve (mudança A)", E1, ""),
    ("PINS", "2", "history_versions.json", "CONTRACTS", A, "C13@3.1.0", E1, ""),
    ("PINS", "DRIFT", "atom_history.jsonl sem tipo", "CONTRACTS", A, "C13@3.1.0", E1, ""),
    ("METRICSLIB", "1", "n_known para célula com n > 0 e tudo desconhecido", "CONTRACTS", A, "C15@3.1.0", E2, ""),
]


def ledger(now: str, e9_commit: str | None = None) -> dict:
    rows = []
    for mod, item, summary, owner, dec, closes, commit, why in ITEMS:
        if dec == O:
            status, commit_ = closes, commit
            closes_ = "-"
        else:
            status, closes_, commit_ = ("FECHADO" if dec == A else "-"), closes, commit
        if commit_ == E9:
            commit_ = e9_commit or E9
        rows.append({"module": mod, "item": item, "summary": summary, "owner": owner, "decision": dec,
                     "status": status, "closes": closes_, "commit": commit_, "why": why})
    by = {}
    for r in rows:
        by[r["decision"]] = by.get(r["decision"], 0) + 1
    open_ = sum(1 for r in rows if r["status"] == ABE)
    return {"schema": "bo.contracts_requests_ledger/1", "module": "CONTRACTS", "generated_at": now,
            "scope": "CONTRACT_CHANGE.txt dos PILOT-* e dos módulos que eles consomem (bo/base)",
            "n": len(rows), "by_decision": dict(sorted(by.items())), "open_elsewhere": open_, "items": rows}
