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
    # ---- emenda 9 (2026-11-04, E6 da tentativa 2 do PILOT-EXIT; razão em results/CONTRACTS/requests_ledger.json)
    {"contract": "C00", "from": "3.1.0", "to": "3.2.0", "at": "2026-11-04T14:00:00-03:00",
     "requested_by": "HARNESS-AWS, HARNESS-AZURE, SERVICE-EVIDENCE",
     "source": "HARNESS-AWS item 2, HARNESS-AZURE proposta 4, SERVICE-EVIDENCE item 7",
     "change": "outcome de persistência com block_code (só com UNKNOWN); schema_source.op shape"},
    {"contract": "C05", "from": "3.0.0", "to": "3.1.0", "at": "2026-11-04T14:00:00-03:00", "requested_by": "UNITS",
     "source": "results/UNITS/CONTRACT_CHANGE.txt (2-7)",
     "change": "duração com unidade NOT_APPLICABLE; byte/bit sem prefixo com convenção NOT_APPLICABLE; unit_candidates; "
               "allowed_values numérico; grandeza do elemento numérico de árvore; counted"},
    {"contract": "C10", "from": "3.1.0", "to": "3.2.0", "at": "2026-11-04T14:00:00-03:00", "requested_by": "TRANSFORMS",
     "source": "results/TRANSFORMS/CONTRACT_CHANGE.txt (2)", "change": "item_type {datatype: any} em porta polimórfica"},
    {"contract": "C25", "from": "1.2.0", "to": "1.3.0", "at": "2026-11-04T14:00:00-03:00",
     "requested_by": "SERVICE-EVIDENCE", "source": "results/SERVICE-EVIDENCE/CONTRACT_CHANGE.txt (7)",
     "change": "rule_id de topo"},
    # ---- emenda 10 (2026-11-04, adendo ADENDO_2026-11-04_OBSERVADO_ALIBABA.html §2)
    {"contract": "C25", "from": "1.3.0", "to": "1.4.0", "at": "2026-11-04T16:30:00-03:00", "requested_by": "COORD",
     "source": "ADENDO_2026-11-04_OBSERVADO_ALIBABA.html §2",
     "change": "nível observed (observation_ref, run_id, repetitions >= 2, control, observed_at); disputa com o "
               "publicado em disputes; só rótulos sintéticos"},
    {"contract": "C25", "from": "1.4.0", "to": "1.5.0", "at": "2026-11-04T17:45:00-03:00",
     "requested_by": "SERVICE-EVIDENCE, COORD", "source": "SERVICE-EVIDENCE itens 10 e 11 (795bffc); PREREG b95403a",
     "change": "observation_ref em OBS-GAPS(-AZ); tipo spec_disputes com status e resolução por observação; disputes "
               "cita publicado ou derivado; aspectos item_identity e namespace_cascade"},
    {"contract": "C00", "from": "3.2.0", "to": "3.3.0", "at": "2026-11-04T18:45:00-03:00", "requested_by": "PILOT-NET-GLOSS",
     "source": "results/PILOT-NET-GLOSS/CONTRACT_CHANGE.txt (CC-NET-5)",
     "change": "evidence_level aceita observed (mesma semântica do C25 1.4.0; sem model_id); o C19 herda"},
    # ---- emenda 13 (2026-11-04, R6 do PREREG b7f804d)
    {"contract": "C25", "from": "1.5.0", "to": "1.6.0", "at": "2026-11-04T22:15:00-03:00", "requested_by": "COORD",
     "source": "PREREG R6 (b7f804d)",
     "change": "spec_disputes: status resolvida-por-publicação (derived_x_derived) com resolved_to e publication_id; "
               "observation_id não exigido"},
    # ---- emenda 14 (2026-11-04, T51b do GRAIN, opção A do COORD)
    {"contract": "C19", "from": "3.1.0", "to": "3.2.0", "at": "2026-11-04T22:30:00-03:00", "requested_by": "GRAIN, COORD",
     "source": "results/GRAIN/CONTRACT_CHANGE.txt (T51b, opção A)",
     "change": "ponta de vínculo {kind: EXTERNAL, symbol, target_type} sem unit_id para referência tipada com valor "
               "simbólico; target_type obrigatório; ao menos uma ponta é unidade"},
    {"contract": "C25", "from": "1.6.0", "to": "1.6.1", "at": "2026-11-04T22:30:00-03:00",
     "requested_by": "SERVICE-EVIDENCE, COORD", "source": "results/SERVICE-EVIDENCE/CONTRACT_CHANGE.txt (12)",
     "change": "resolvida-por-publicação confere o nível dos lados (os dois derived) e da publicação (published) "
               "no service_evidence.jsonl, não o rótulo kind"},
]


# ---- registro do E6 (ciclo v4): pedidos dos pilotos resolvidos por mudança VERSIONADA de outro dono, e citações
# por módulo de emendas do CONTRACTS que já existiam (uma entrada por módulo, para o avaliador do PILOT-EXIT ler
# 'results/<módulo>/CONTRACT_CHANGE.txt (<item>)' sem misturar itens de módulos diferentes). Cada entrada aponta a
# versão de->para e o commit em bo/base; nenhuma é emenda de contrato do CONTRACTS ('kind' external | citation).
# Recusados e adiados NÃO entram aqui (não houve mudança versionada): ver results/CONTRACTS/CONTRACT_CHANGE.txt.
_X = "2026-11-04T19:30:00-03:00"


def _ext(owner, frm, to, commit, module, items, change):
    return {"contract": owner, "kind": "external", "from": frm, "to": to, "commit": commit, "at": _X,
            "requested_by": module, "source": f"results/{module}/CONTRACT_CHANGE.txt ({', '.join(items)})",
            "change": change}


def _cite(cid, frm, to, commit, module, items):
    return {"contract": cid, "kind": "citation", "from": frm, "to": to, "commit": commit, "at": _X,
            "requested_by": module, "source": f"results/{module}/CONTRACT_CHANGE.txt ({', '.join(items)})",
            "change": f"mesma emenda {cid} {frm}->{to} do CONTRACTS, citada por módulo"}


AMENDMENTS += [
    _ext("GRAIN", "0.1.0", "0.1.1", "04f37f6", "PILOT-NET-GLOSS", ["CC-1"],
         "emenda 0.1.1 do GRAIN: adaptador do C25 por aspecto"),
    _ext("GRAIN", "0.1.3", "0.1.9", "a296cd0..071daf6", "PILOT-STO-GLOSS", ["CC-5", "CC-7"],
         "emendas 0.1.4–0.1.9 do GRAIN com os fatos da camada de API do SERVICE-EVIDENCE (767bb22, ce1e590, 83953b9)"),
    _ext("ARBITERLIB", "ARBITER-20261104", "ARBITER-20261104-2", "52371e8", "PILOT-NET-MAP", ["CC-MAP-NET-1"],
         "recongelamento do árbitro sobre a base (freeze_receipt_ARBITER-20261104-2)"),
    _ext("ARBITERLIB", "ARBITER-20261104", "ARBITER-20261104-2", "52371e8", "PILOT-STO-MAP", ["CC-1"],
         "recongelamento do árbitro sobre a base (freeze_receipt_ARBITER-20261104-2)"),
    _ext("ARBITERLIB", "5c5662d", "ARBITER-20261104", "35e299f", "PILOT-NET-MAP", ["CC-MAP-NET-2"],
         "recongelamento com os ids de regra do C21 renomeados (EVIDENCE, SENTINEL)"),
    _ext("ARBITERLIB", "5c5662d", "ARBITER-20261104", "35e299f", "PILOT-STO-MAP", ["CC-2"],
         "recongelamento com os ids de regra do C21 renomeados"),
    _ext("ARBITERLIB", "ARBITER-20261104-2", "ARBITER-20261104-3", "2028169, cc57c0a", "PILOT-NET-MAP",
         ["CC-MAP-NET-4"], "saída padrão em $BO_TMP/arbiter com --check-unproven sem --out"),
    _ext("ARBITERLIB", "ARBITER-20261104-2", "ARBITER-20261104-3", "2028169, cc57c0a", "PILOT-STO-MAP", ["CC-7"],
         "veredito próprio para ausência tipada"),
    _ext("TRANSFORMS", "1.0.0", "1.1.0", "e3f14b1", "PILOT-STO-MAP", ["CC-9"], "domínio finito de enum_to_bool"),
    _ext("TRANSFORMS", "1.2.0", "1.3.0", "325a84b", "PILOT-STO-MAP", ["CC-5"],
         "bytes e bits em AmountOfData (com SEMANTICS ea53bcf, UNITS emenda 1 e C05 3.1.0)"),
    _ext("SEMANTICS", "1.2", "1.3", "61d6fae", "PILOT-STO-MAP", ["CC-3"], "invert aceita funções do registro fechado"),
    _ext("PILOT-STO-GLOSS", "MANIFEST 7d2efa60", "MANIFEST f5f2131d", "5f0ebb5", "PILOT-STO-MAP", ["CC-4"],
         "pacote novo do glossário sobre o GRAIN 0.1.6 e o SERVICE-EVIDENCE 767bb22"),
    _ext("REPO", "privacy_lint d4559dd", "privacy_lint 7e444c2", "7e444c2", "PILOT-STO-MAP", ["CC-10"],
         "regra de 12 dígitos ignora id hex curto com letra"),
    _ext("SERVICE-EVIDENCE", "37fbcf0", "83953b9", "83953b9", "PILOT-NET-ORACLE", ["4"],
         "linha do NSG oci publicada (R-CONN-DOC)"),
    _ext("SERVICE-EVIDENCE", "3bcf3b6", "3ba4079", "3ba4079", "PILOT-NET-ORACLE", ["3", "5"],
         "CC-14: guias oficiais como fonte publicada; (3) estado de conexão publicado no SG aws e no firewall gcp, "
         "no NSG azurerm continua unknown publicado; (5) prioridade única por NSG e direção (frase do guia)"),
    _ext("GRAIN", "0.1.11", "0.2.0", "dcb5c52", "PILOT-NET-E2E", ["CC-NET-E2E-2"],
         "T59b (item sem id é COMPONENT anônimo do dono) e associação NSG azurerm; T51b recusada na 0.2.0 até a "
         "decisão do pedido do GRAIN sobre o CMT-NIC-U02 (results/GRAIN/CONTRACT_CHANGE.txt)"),
    _ext("GRAIN", "0.1.11", "0.2.0", "dcb5c52", "PILOT-STO-MAP", ["CC-8"],
         "T59b: bloco repetido sem id do provedor tem chave de ocorrência pelo conteúdo configurado"),
    _ext("GRAIN", "0.1.11", "0.2.0", "dcb5c52", "PILOT-NET-GLOSS", ["CC-NET-3"],
         "(c) T31: deletion_policy do Terraform fora do grão, só a política da API conta; (b) timeouts fora do "
         "domínio desde a 0.1.2 (T45, 957870a); (a) alvos de referência da fatia no SERVICE-EVIDENCE (b952d98)"),
    _cite("C20", "3.2.0", "3.3.0", "9919e4c", "PILOT-NET-GLOSS", ["CC-NET-4"]),
    _cite("C09", "3.1.0", "3.2.0", "9919e4c", "PILOT-STO-MAP", ["CC-6"]),
]


def chain(cid: str) -> list[str]:
    """Versões aceitas de um contrato, da mais antiga à publicada (só as emendas do CONTRACTS)."""
    vs = []
    for a in AMENDMENTS:
        if a["contract"] == cid and not a.get("kind"):
            if not vs:
                vs.append(a["from"])
            vs.append(a["to"])
    return vs


def accepted(cid: str, published: str) -> list[str]:
    c = chain(cid)
    return c if c and c[-1] == published else [published]
