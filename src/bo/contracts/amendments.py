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
