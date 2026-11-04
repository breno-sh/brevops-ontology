"""Emendas versionadas dos contratos (depois do merge, mudança só por emenda). Cada emenda é aditiva e compatível:
documentos gravados na versão anterior continuam válidos (os cabeçalhos aceitam as duas versões, ACCEPT).

O catálogo do coordenador (modulos.json) pode continuar dizendo a versão anterior até ser regenerado; a regra
C00-CONTRACTS e os testes aceitam a versão do catálogo quando ela está na cadeia de emendas da publicada."""

from __future__ import annotations

AMENDMENTS = [
    {"contract": "C01", "from": "2.0.0", "to": "2.1.0", "at": "2026-11-03T02:10:00-03:00", "requested_by": "SCHEMALIB",
     "source": "$BO_REPO/results/SCHEMALIB/CONTRACT_CHANGE.txt",
     "change": "campo opcional write_only (ausente = false) e regra C01-WRITEONLY; nested_type continua UM átomo com "
               "tf_type cty (['object', {...}] ou [modo, objeto, opcionais]), aceito sem mudança"},
    {"contract": "C09", "from": "3.0.0", "to": "3.0.1", "at": "2026-11-03T02:10:00-03:00", "requested_by": "CONTRACTS",
     "source": "varredura dos gates do modulos.json",
     "change": "correspondences_jsonl casa com *.jsonl (os disputes.jsonl dos NONEHUNT-* eram lidos como TSV)"},
    {"contract": "C11", "from": "3.0.0", "to": "3.0.1", "at": "2026-11-03T02:10:00-03:00", "requested_by": "CONTRACTS",
     "source": "varredura dos gates do modulos.json",
     "change": "cases casa com cases*.jsonl (cases_aws.jsonl do DEPSAMPLE)"},
    {"contract": "C13", "from": "3.0.0", "to": "3.1.0", "at": "2026-11-03T02:10:00-03:00", "requested_by": "PINS, DRIFT",
     "source": "/Users/breno/doutorado/pesquisa-lanes/bo-pins/results/PINS/CONTRACT_CHANGE.txt",
     "change": "tipos novos history_versions (universe/history_versions.json, regras C13-HIST-PIN e C13-HIST-SEL) e "
               "atom_history ($BO_DATA/DRIFT/atom_history.jsonl, regra C13-ATOMHIST); cabeçalhos aceitam 3.0.0 e 3.1.0"},
    {"contract": "C17", "from": "3.0.0", "to": "3.0.1", "at": "2026-11-03T02:10:00-03:00", "requested_by": "COORD",
     "source": "commit [COORD] 294b956 em results/SEMANTICS/summary.json",
     "change": "entrada de agent_provenance.inputs aceita sha256_before_<motivo> (hash anterior a uma emenda do "
               "coordenador); cabeçalhos aceitam 3.0.0 e 3.0.1"},
    {"contract": "C18", "from": "2.0.0", "to": "2.0.1", "at": "2026-11-03T02:10:00-03:00", "requested_by": "CONTRACTS",
     "source": "varredura dos gates do modulos.json",
     "change": "numbers casa com numbers*.json (numbers_supp.json do STATS-SUPP); o .tex irmão é o de mesmo nome-base"},
    # ---- emenda 2 (2026-11-03, pedidos dos HARNESS-*, DOCS-*, GRAIN e METRICSLIB)
    {"contract": "C00", "from": "3.0.0", "to": "3.0.1", "at": "2026-11-03T08:00:00-03:00",
     "requested_by": "HARNESS-AZURE, DOCS-AZURE", "source": "results/{HARNESS-AZURE,DOCS-AZURE}/CONTRACT_CHANGE.txt",
     "change": "term.reference.target_node e doc_source.redacted, ambos opcionais"},
    {"contract": "C03", "from": "3.0.0", "to": "3.1.0", "at": "2026-11-03T08:00:00-03:00",
     "requested_by": "DOCS-AWS, DOCS-GCP, DOCS-AZURE, DOCS-OCI",
     "source": "results/DOCS-*/CONTRACT_CHANGE.txt (bo/base e lanes bo-docs-*)",
     "change": "tipo type_subcategory (type_subcategory.jsonl, registro type_fact: subcategoria e importação por tipo); "
               "fact_kind applicable_when; applies_to opcional em fato derived (blocos repetidos)"},
    {"contract": "C12", "from": "3.0.0", "to": "3.1.0", "at": "2026-11-03T08:00:00-03:00",
     "requested_by": "HARNESS-GCP, HARNESS-AWS, HARNESS-AZURE", "source": "results/HARNESS-GCP/CONTRACT_CHANGE.txt",
     "change": "readback.fields[].node_id opcional; unicidade por (node_id, path)"},
    {"contract": "C15", "from": "3.0.0", "to": "3.1.0", "at": "2026-11-03T08:00:00-03:00", "requested_by": "METRICSLIB",
     "source": "results/METRICSLIB/CONTRACT_CHANGE.txt",
     "change": "operational_coverage.n_known opcional; est nulo também com n > 0 e n_known = 0"},
    {"contract": "C19", "from": "3.0.0", "to": "3.1.0", "at": "2026-11-03T08:00:00-03:00", "requested_by": "GRAIN",
     "source": "src/bo/grain/schema.py (to_c19: pontas em identity.evidence por falta de campo)",
     "change": "endpoints (pontas do vínculo) e owner.refs (faceta com vários donos), opcionais"},
    {"contract": "C26", "from": "1.0.0", "to": "1.1.0", "at": "2026-11-03T08:00:00-03:00",
     "requested_by": "HARNESS-AWS, HARNESS-GCP, HARNESS-AZURE, HARNESS-OCI",
     "source": "results/HARNESS-*/CONTRACT_CHANGE.txt",
     "change": "derived_name.field opcional; regra C26-TARGET; stub com um plano renderizável por provedor"},
    # ---- emenda 3 (2026-11-03, pedido do BRIEFS, antes dos pilotos de glossário e mapeamento)
    {"contract": "C00", "from": "3.0.1", "to": "3.0.2", "at": "2026-11-03T18:00:00-03:00", "requested_by": "BRIEFS",
     "source": "results/BRIEFS/CONTRACT_CHANGE.txt", "change": "absence_kind (os quatro tipos de ausência do C29)"},
    {"contract": "C09", "from": "3.0.1", "to": "3.1.0", "at": "2026-11-03T18:00:00-03:00", "requested_by": "BRIEFS",
     "source": "results/BRIEFS/CONTRACT_CHANGE.txt",
     "change": "ausência tipada: absence {kind, block_code?, searched, evidence} com object_id sssom:NoTermFound; "
               "disputes; a forma provisória em curation_rule continua aceita"},
    {"contract": "C20", "from": "3.0.0", "to": "3.1.0", "at": "2026-11-03T18:00:00-03:00", "requested_by": "BRIEFS",
     "source": "results/BRIEFS/CONTRACT_CHANGE.txt (formato provisório do GLOSSARY_BRIEF)",
     "change": "tipo decisions (decisions.jsonl, bo.glossary_decision/1) com broader/narrower e regras de direção, "
               "referência e aciclicidade"},
    # ---- emenda 4 (2026-11-04, PILOT-NET-GLOSS CC-NET-2 e SERVICE-EVIDENCE)
    {"contract": "C00", "from": "3.0.2", "to": "3.0.3", "at": "2026-11-04T08:00:00-03:00",
     "requested_by": "SERVICE-EVIDENCE", "source": "bo-service-evidence/results/SERVICE-EVIDENCE/CONTRACT_CHANGE.txt",
     "change": "schema_source (citação do schema do binário assinado do pin)"},
    {"contract": "C20", "from": "3.1.0", "to": "3.2.0", "at": "2026-11-04T08:00:00-03:00",
     "requested_by": "PILOT-NET-GLOSS", "source": "bo-pilot-net-gloss/results/PILOT-NET-GLOSS/CONTRACT_CHANGE.txt (CC-NET-2)",
     "change": "âncora em átomo, bloco ou tipo (anchor_kind, block_id, type_id) com implication obrigatória fora do átomo"},
    {"contract": "C25", "from": "1.0.0", "to": "1.1.0", "at": "2026-11-04T08:00:00-03:00",
     "requested_by": "SERVICE-EVIDENCE", "source": "bo-service-evidence/results/SERVICE-EVIDENCE/CONTRACT_CHANGE.txt",
     "change": "block_path; schema (fonte publicada do binário); consulted e level opcional em unknown; fact_kind "
               "api_bridge e default (com as_of)"},
    # ---- emenda 5 (2026-11-04, oráculos dos pilotos e SERVICE-EVIDENCE)
    {"contract": "C11", "from": "3.0.1", "to": "3.1.0", "at": "2026-11-04T09:00:00-03:00",
     "requested_by": "PILOT-NET-ORACLE, PILOT-STO-ORACLE", "source": "results/PILOT-NET-ORACLE/CONTRACT_CHANGE.txt (2)",
     "change": "origin pilot"},
    {"contract": "C24", "from": "1.0.0", "to": "1.1.0", "at": "2026-11-04T09:00:00-03:00",
     "requested_by": "PILOT-NET-ORACLE, PILOT-STO-ORACLE", "source": "results/PILOT-NET-ORACLE/CONTRACT_CHANGE.txt (1)",
     "change": "tipo pilot_expected_answers (expected_answers.json das duas fatias), com semente C11 comum"},
    {"contract": "C25", "from": "1.1.0", "to": "1.2.0", "at": "2026-11-04T09:00:00-03:00",
     "requested_by": "SERVICE-EVIDENCE", "source": "bo-service-evidence/results/SERVICE-EVIDENCE/CONTRACT_CHANGE.txt (5)",
     "change": "tipo protocol_support (protocol_support.jsonl, bo.protocol_support/1)"},
    {"contract": "C26", "from": "1.1.0", "to": "1.2.0", "at": "2026-11-04T09:30:00-03:00", "requested_by": "COORD",
     "source": "results/HARNESS-OCI/CONTRACT_CHANGE.txt (ACHADO 4, opção B)",
     "change": "tag de execução nunca vem no plano (C26-NOTAG); stub sem freeform_tags.bo_run (oci) e labels.bo_case (google)"},
    # ---- emenda 7 (2026-11-04, E6 do PILOT-EXIT: pedidos dos pilotos; tabela em results/CONTRACTS/emenda7.json)
    {"contract": "C00", "from": "3.0.3", "to": "3.1.0", "at": "2026-11-04T13:00:00-03:00", "requested_by": "PILOT-NET-E2E",
     "source": "results/PILOT-NET-E2E/CONTRACT_CHANGE.txt (CC-NET-E2E-1)", "change": "termo list"},
    {"contract": "C01", "from": "2.1.0", "to": "2.2.0", "at": "2026-11-04T13:00:00-03:00", "requested_by": "PILOT-NET-GLOSS",
     "source": "results/PILOT-NET-GLOSS/CONTRACT_CHANGE.txt (CC-NET-1 a)",
     "change": "block_path[].kind = nested_attribute para elemento de coleção de objetos"},
    {"contract": "C09", "from": "3.1.0", "to": "3.2.0", "at": "2026-11-04T13:00:00-03:00",
     "requested_by": "PILOT-NET-MAP, PILOT-STO-MAP", "source": "PILOT-NET-MAP F-1/F-6, PILOT-STO-MAP CC-6/D-1",
     "change": "value_type list/set/map (item_type, key_type); absence.side (ausência do lado objeto)"},
    {"contract": "C20", "from": "3.2.0", "to": "3.3.0", "at": "2026-11-04T13:00:00-03:00",
     "requested_by": "PILOT-STO-GLOSS, PILOT-NET-GLOSS", "source": "PILOT-STO-GLOSS CC-6, PILOT-NET-GLOSS CC-NET-4",
     "change": "âncora UNRESOLVED sem sentença (motivo no context); evidence_ref ao fato C03/C25"},
    {"contract": "C22", "from": "3.0.0", "to": "3.1.0", "at": "2026-11-04T13:00:00-03:00", "requested_by": "PROBEKIT",
     "source": "results/PROBEKIT/CROSS_MODULE_NOTES.txt (5)", "change": "counts.observed_out_of_tolerance"},
    {"contract": "C26", "from": "1.2.0", "to": "1.3.0", "at": "2026-11-04T13:00:00-03:00", "requested_by": "PILOT-NET-E2E",
     "source": "results/PILOT-NET-E2E/CONTRACT_CHANGE.txt (CC-NET-E2E-1)",
     "change": "C26-LIST: lista de referências como termo list, não campo indexado"},
    # ---- emenda 8 (2026-11-04, TRANSFORMS)
    {"contract": "C10", "from": "3.0.0", "to": "3.1.0", "at": "2026-11-04T12:40:00-03:00", "requested_by": "TRANSFORMS",
     "source": "bo-transforms/results/TRANSFORMS/CONTRACT_CHANGE.txt",
     "change": "portas e domínio/codomínio aceitam list/set/map com item_type e key_type (C10-COLL)"},
]


def chain(cid: str) -> list[str]:
    """Versões aceitas de um contrato, da mais antiga à publicada."""
    vs = []
    for a in AMENDMENTS:
        if a["contract"] == cid:
            if not vs:
                vs.append(a["from"])
            vs.append(a["to"])
    return vs


def accepted(cid: str, published: str) -> list[str]:
    c = chain(cid)
    return c if c and c[-1] == published else [published]
