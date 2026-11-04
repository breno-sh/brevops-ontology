"""Mutantes de cada stub para o --mutation-test: cada um TEM de reprovar.

Três famílias: (1) estruturais, derivadas do schema publicado (tirar cada campo obrigatório do primeiro registro,
trocar o tipo de um campo, corromper um enum, acrescentar campo em objeto fechado); (2) de formato (TSV, Parquet,
Turtle, EDOAL, manifesto, .tex); (3) semânticas, escritas à mão, uma por regra que o schema não exprime (as que dão
sentido ao contrato: união de desfechos, claim_id imutável, NOT_APPLICABLE ≠ UNKNOWN, grupo, projeção, alternativas…).
Nenhum mutante grava identificador real: os poucos que precisam de um formato proibido montam o texto em partes."""

from __future__ import annotations

import copy
import io
import json
import re

import yaml

from . import catalog
from ._base import jsonl

# formatos "proibidos" montados em partes (o código-fonte não pode conter o padrão inteiro)
FAKE_ARN = "ar" + "n:aws:iam::" + "1" * 6 + "2" * 6 + ":role/x"
TWELVE = "4" * 6 + "5" * 6


# ------------------------------------------------------------------------------------------------ util
def _set(o, path: str, v):
    keys = path.split(".")
    for k in keys[:-1]:
        o = o[int(k)] if isinstance(o, list) else o[k]
    last = keys[-1]
    if isinstance(o, list):
        o[int(last)] = v
    else:
        o[last] = v


def _del(o, path: str):
    keys = path.split(".")
    for k in keys[:-1]:
        o = o[int(k)] if isinstance(o, list) else o[k]
    if isinstance(o, list):
        o.pop(int(keys[-1]))
    else:
        o.pop(keys[-1])


def S(*ops):
    """Mutação semântica como lista de operações (('set', caminho, valor) | ('del', caminho) | ('fn', f))."""
    def f(recs):
        for op in ops:
            if op[0] == "set":
                _set(recs, op[1], copy.deepcopy(op[2]))
            elif op[0] == "del":
                _del(recs, op[1])
            elif op[0] == "fn":
                op[1](recs)
        return recs
    return f


def _retag(recs):
    """tag errada com digest recalculado: tem de reprovar pela regra da tag, não pelo digest."""
    from bo.repo import receipts
    r = recs[0]
    r["git"]["tag"] = "bo-freeze-OUTRO"
    r["digest"] = receipts.receipt_digest(r)
    r["ots"]["digest"] = r["digest"]


def _dup_first(recs):
    recs.append(copy.deepcopy(recs[0]))


SEM: dict[str, list] = {
    # ----- C00
    "C00:module": [("branch-errada", S(("set", "0.branch", "bo/outro"))),
                   ("tmp-em-tmp", S(("set", "0.tmp_dir", "/tmp/EXAMPLE-MOD"))),
                   ("id-diferente", S(("set", "0.stable_id", "OUTRO-MOD")))],
    "C00:module_catalog": [("onda-nao-calculada", S(("set", "0.modules.1.wave", 3))),
                           ("dep-inexistente", S(("set", "0.modules.1.deps", ["NAO-EXISTE"]))),
                           ("indice-nao-declarado", S(("set", "0.modules.1.outputs", ["$BO_REPO/results/X/{foo}.json"]))),
                           ("reticencias", S(("set", "0.modules.1.inputs", ["$BO_REPO/results/.../x.json"]))),
                           ("versao-de-contrato", S(("set", "0.contracts.C00.version", "2.0.0"))),
                           ("ciclo", S(("set", "0.modules.0.deps", ["EXAMPLE-NEXT"])))],
    # ----- C01–C05
    "C01:atoms": [("atom-id-nao-bate", S(("set", "0.atom_id", "aws:aws_db_instance:outro"))),
                  ("required-e-optional", S(("set", "0.required", True))),
                  ("configurable-errado", S(("set", "1.configurable", False))),
                  ("nesting-errado", S(("set", "1.nesting", "set"))),
                  ("write-only-computed", S(("set", "2.computed", True))),
                  ("write-only-nao-configuravel", S(("set", "2.optional", False), ("set", "2.configurable", False))),
                  ("write-only-nao-booleano", S(("set", "2.write_only", "sim")))],
    "C02:types": [("configurable-nao-soma", S(("set", "0.counts.configurable", 70))),
                  ("type-id-nao-bate", S(("set", "0.type_id", "aws:aws_s3_bucket")))],
    "C03:docs_facts": [("unknown-com-valor", S(("set", "1.value", 5))),
                       ("default-sem-data", S(("del", "0.as_of"))),
                       ("interpretado-sem-modelo", S(("del", "1.model_id"))),
                       ("publicado-com-modelo", S(("set", "0.model_id", "claude-opus-5-5"))),
                       ("fato-repetido", S(("fn", lambda r: r.__setitem__(1, {**r[0]})))),
                       ("applies-to-publicado", S(("set", "2.evidence_level", "published"))),
                       ("applies-to-outro-tipo", S(("set", "2.applies_to", ["aws:aws_s3_bucket:x"]))),
                       ("applies-to-de-si", S(("set", "2.applies_to", [
                           "aws:aws_wafv2_rule_group:rule.statement.and_statement.statement.byte_match_statement.search_string"]))),
                       ("redacted-nao-booleano", S(("set", "2.source.redacted", "sim")))],
    "C03:type_subcategory": [("type-id-nao-bate", S(("set", "0.type_id", "azurerm:azurerm_outro"))),
                             ("guid-de-assinatura", S(("set", "0.import.value",
                                                       ["/subscriptions/" + "0a1b2c3d" + "-0a1b-" + "4c5d-8e9f-0a1b2c3d4e5f/x"]))),
                             ("unknown-com-valor", S(("set", "1.subcategory.value", "Load Balancing"))),
                             ("unknown-com-formato", S(("set", "1.subcategory.id_format", "{{id}}"))),
                             ("stated-sem-fonte", S(("del", "0.subcategory.source"))),
                             ("data-source-com-import", S(("set", "2.import", {"status": "unknown",
                                                                               "unknown_reason": "not_supported",
                                                                               "extraction_method": "parser",
                                                                               "evidence_level": "published"}))),
                             ("tipo-repetido", S(("fn", _dup_first))),
                             ("apelido-de-si", S(("set", "1.alias_of.type_id", "aws:aws_alb"))),
                             ("metodo-fora", S(("set", "1.import.methods", ["clicar_no_console"])))],
    "C04:roles": [("papel-repetido", S(("fn", _dup_first))), ("papel-fora", S(("set", "0.role", "LABEL")))],
    "C05:value_space": [("na-com-unidade", S(("set", "1.unit_qudt", "unit:DAY"))),
                        ("unknown-com-unidade", S(("set", "4.unit_qudt", "unit:SEC"))),
                        ("enum-com-grandeza", S(("set", "1.quantity_kind", "quantitykind:Time"),
                                                ("set", "1.unit_qudt", "unit:DAY"))),
                        ("na-vira-unknown-de-enum", S(("set", "1.quantity_kind", "UNKNOWN"),
                                                      ("set", "1.unit_qudt", "UNKNOWN"))),
                        ("bytes-sem-convencao", S(("set", "2.byte_convention", "NOT_APPLICABLE"))),
                        ("taxa-sem-janela", S(("set", "3.rate_window", None))),
                        ("enum-sem-lista", S(("del", "1.enum"))),
                        ("range-invertido", S(("set", "0.range.min", 99)))],
    # ----- C06–C08
    "C06:symbolic_config": [("nome-real-no-endereco", S(("set", "0.resource_address", "aws_db_instance.prod_db"))),
                            ("arn-no-documento", S(("set", "2.term.tree.Statement.0.Principal.AWS", FAKE_ARN))),
                            ("conta-no-literal", S(("set", "0.term", {"kind": "literal", "datatype": "string",
                                                                      "value": TWELVE}))),
                            ("retido-com-valor", S(("set", "4.term.value", "x"))),
                            ("endereco-de-outro-tipo", S(("set", "0.resource_type", "aws_s3_bucket"))),
                            ("termo-sem-tipo", S(("set", "1.term.kind", "raw")))],
    "C06:usage": [("contagem-nao-soma", S(("set", "0.n_literal", 2))),
                  ("split-no-uso", S(("set", "0.partition", "train")))],
    "C07:universe": [("pilot-sem-unidade", S(("del", "0.pilot_exposed.CU-aws-db-backup-window"))),
                     ("holdout-em-claro", S(("set", "0.holdout.path", "$BO_DATA/SPLIT/holdout.jsonl"))),
                     ("unidade-repetida", S(("fn", lambda r: r[0]["units"].append(copy.deepcopy(r[0]["units"][0])))))],
    "C08:candidates": [("campo-de-ouro", S(("set", "0.features.gold_match", True))),
                       ("ouro-no-registro", S(("set", "0.is_match", True))),
                       ("aresta-solta", S(("set", "0.subject.edges.0.to", "n9"))),
                       ("provedor-fora-do-par", S(("set", "0.object_provider", "oci")))],
    # ----- C09
    "C09:correspondences": [
        ("predicado-invertido", S(("set", "2.predicate_id", "skos:narrowMatch"))),
        ("versao-de-outra-alegacao", S(("set", "0.claim_version_id", "CLM-OUTRA@1"))),
        ("claim-id-com-versao", S(("set", "0.claim_id", "CLM-EX-01@1"), ("set", "0.claim_version_id", "CLM-EX-01@1@1"))),
        ("evento-igual-entre-versoes", S(("set", "1.event_id", "EV-CLM-EX-01-1"))),
        ("supersedes-outra-alegacao", S(("set", "1.supersedes", "CLM-BR-01@1"))),
        ("guarda-fora-da-gramatica", S(("set", "0.guard", {"all": [{"term": "object.x", "op": "regex", "value": "a"}]}))),
        ("funcao-fora-do-nucleo", S(("set", "0.translation_fn", {"name": "eval_python", "params": {}}))),
        ("vdr-sem-orientacao", S(("set", "0.value_domain_relation", {"relation": "subset"}))),
        ("broad-direcao", S(("set", "2.semantic_relation", "narrow"))),
        ("ausencia-sem-tipo", S(("del", "3.absence"))),
        ("ausencia-com-termo", S(("set", "3.object_id", "pb:spin_speed"))),
        ("ausencia-exata", S(("set", "3.predicate_id", "skos:exactMatch"), ("set", "3.semantic_relation", "exact"))),
        ("ausencia-transporta", S(("set", "3.transport_fidelity", "lossless"))),
        ("ausencia-tipo-fora", S(("set", "3.absence.kind", "NOT_PORTABLE"))),
        ("ausencia-legada-diverge", S(("set", "3.curation_rule", "bo:NONE_UNRESOLVED"))),
        ("ausencia-sem-busca", S(("del", "3.absence.searched"))),
        ("disputa-de-si", S(("set", "5.disputes", ["CLM-HUNT-01"])))],
    "C09:correspondences_jsonl": [
        ("predicado-invertido", S(("set", "2.predicate_id", "skos:narrowMatch"))),
        ("versao-repetida", S(("set", "1.claim_version_id", "CLM-EX-01@1"), ("del", "1.supersedes"))),
        ("hash-como-claim-id", S(("set", "2.claim_id", "ab" * 16), ("set", "2.claim_version_id", "ab" * 16 + "@1")))],
    # ----- C10
    "C10:transforms": [("escalar-muda-grandeza", S(("set", "0.scalar.1.codomain.quantity_kind", "quantitykind:Length"))),
                       ("inversa-inexistente", S(("set", "0.combinators.0.inverse.name", "nao_existe"))),
                       ("duracao-sem-calendario", S(("del", "0.scalar.2.duration_calendar"))),
                       ("calendario-sem-contexto", S(("set", "0.scalar.2.duration_calendar", "with_context"))),
                       ("tupla-em-escalar", S(("set", "0.scalar.0.codomain.datatype", "tuple")))],
    "C10:conditions_grammar": [("sat-esperado-errado", S(("set", "0.sat_tests.1.expected", "SAT"))),
                               ("sem-caso-unsat", S(("del", "0.sat_tests.1"))),
                               ("operador-faltando", S(("del", "0.operators.version_range")))],
    "C10:composition_table": [("par-repetido", S(("set", "0.semantic_relation.1.r2", "exact"))),
                              ("vdr-incoerente", S(("set", "0.value_domain_relation.rows.0.result", "overlap"))),
                              ("fidelidade-par-repetido", S(("set", "0.transport_fidelity.rows.1.f2", "lossless")))],
    "C10:guard": [("operador-fora", S(("set", "0.all.0.op", "regex"))),
                  ("termo-sem-papel", S(("set", "0.all.0.term", "edition")))],
    # ----- C11–C13
    "C11:cases": [("cq-sem-id", S(("del", "1.cq_id"))), ("versao-de-outra", S(("set", "0.claim_version_id", "CLM-X@1"))),
                  ("lista-de-caminhos", S(("set", "0.paths", ["a.b"]))), ("tolerancia-faltando",
                                                                          S(("del", "1.comparator.tolerance")))],
    "C12:readback": [("no-e-campo-repetidos", S(("set", "0.fields.4.node_id", "r1"))),
                     ("no-fora-do-padrao", S(("set", "0.fields.3.node_id", "n1"))),("retido-com-valor", S(("set", "0.fields.1.value", "x"))),
                     ("retido-sem-redacao", S(("del", "0.fields.1.redaction"))),
                     ("redacao-fora-da-origem", S(("set", "0.fields.1.redaction.at_source", False)))],
    "C12:outcomes": [("eixo-errado", S(("set", "0.outcome.axis", "behavior"))),
                     ("valor-de-comportamento", S(("set", "0.outcome.value", "OBSERVATIONS_MATCH_UNDER_PROTOCOL"))),
                     ("valor-fora-da-uniao", S(("set", "0.outcome.value", "OK"))),
                     ("desfecho-plano", S(("set", "0.outcome", "PERSISTED"))),
                     ("evidencia-sobe-sem-persisted", S(("set", "1.evidence_state_after", "PERSISTENCE_VERIFIED"))),
                     ("persisted-sem-leitura", S(("del", "0.readback_id"))),
                     ("leitura-inexistente", S(("set", "0.readback_id", "RB-9999")))],
    "C13:events": [("intervalo-vazio", S(("set", "0.version_interval.after", "6.0.0"))),
                   ("renome-igual", S(("set", "0.to_atom", "aws:aws_db_instance:name"))),
                   ("adicao-sem-atomo", S(("del", "1.atom_id"))),
                   ("atomo-de-outro-tipo", S(("set", "1.atom_id", "aws:aws_s3_bucket:x")))],
    "C13:history_versions": [("pin-nao-e-a-ultima", S(("set", "0.providers.0.pin", "5.90.0"))),
                             ("pin-diverge-do-pins", S(("set", "0.providers.0.pin", "6.1.0"),
                                                       ("set", "0.providers.0.versions_doc.versions.1.version", "6.1.0"),
                                                       ("set", "0.providers.0.selection.1.version", "6.1.0"))),
                             ("schema-sha-diverge", S(("set", "0.providers.0.versions_doc.versions.1.schema_sha256",
                                                       "f" * 64))),
                             ("selecao-fora-de-ordem", S(("fn", lambda r: r[0]["providers"][0]["selection"].reverse()))),
                             ("selecao-data-diverge", S(("set", "0.providers.0.selection.0.released_at", "2026-03-02"))),
                             ("versions-doc-fora-de-ordem", S(("fn", lambda r: r[0]["providers"][0]["versions_doc"][
                                 "versions"].reverse()))),
                             ("publicado-com-fuso-local", S(("set", "0.providers.0.selection.0.published_at",
                                                             "2026-03-01T12:00:00-03:00"))),
                             ("motivo-fora", S(("set", "0.providers.0.selection.0.reasons", ["porque_sim"])))],
    "C13:atom_history": [("first-seen-errado", S(("set", "0.first_seen", "5.90.0"))),
                         ("historia-fora-de-ordem", S(("fn", lambda r: r[0]["history"].reverse()))),
                         ("ausente-com-tipo", S(("set", "0.history.0.tf_type", "string"))),
                         ("presente-sem-flags", S(("del", "0.history.1.required"))),
                         ("atom-id-nao-bate", S(("set", "1.path", "nome"))),
                         ("required-e-optional", S(("set", "1.history.0.required", True)))],
    "C13:versions": [("fora-de-ordem", S(("fn", lambda r: r[0]["versions"].reverse())))],
    "C13:pins": [("provider-repetido", S(("set", "0.providers.1.provider", "aws"))),
                 ("fonte-fora-do-registro", S(("set", "0.providers.0.source", "github.com/x/y")))],
    # ----- C14
    "C14:classes": [("ortogonal-sem-eixo", S(("del", "1.parents.1.axis"))),
                    ("condicional-sem-guarda", S(("del", "1.parents.2.guard"))),
                    ("pai-de-si", S(("set", "0.parents", [{"iri": "x:Resource", "kind": "nested"}]))),
                    ("obsoleta-sem-substituta", S(("del", "2.replaced_by"))),
                    ("recurso-sem-identidade", S(("del", "0.identity")))],
    "C14:properties": [("uniao-de-um", S(("set", "0.domain.classes", ["x:StorageContainer"]))),
                       ("dois-dominios", S(("set", "0.domain", ["x:StorageContainer", "x:DatabaseInstance"])))],
    "C14:realizations": [("alternativa-nao-mutua", S(("set", "2.alternative_to", []))),
                         ("perda-sem-losses", S(("del", "0.losses"))),
                         ("alternativa-sem-guarda", S(("del", "1.guards"))),
                         ("exclusividade-divergente", S(("set", "1.exclusivity", "ProvenExclusive"),
                                                        ("set", "1.exclusivity_proof",
                                                         {"method": "documented_exclusive",
                                                          "evidence": [{"level": "derived", "ref": "x"}]}))),
                         ("exclusiva-sem-prova", S(("set", "1.exclusivity", "ProvenExclusive"),
                                                   ("set", "2.exclusivity", "ProvenExclusive")))],
    # ----- C15–C18
    "C15:result": [("est-acima-do-teto", S(("set", "0.metrics.0.operational_coverage.est", 0.9))),
                   ("termo-antigo", S(("set", "0.metrics.0.ceiling", 1.0))),
                   ("termo-antigo-em-data", S(("set", "0.data.portability_teto", 1))),
                   ("correlacao-solta", S(("set", "0.metrics.0.joint_uncertainty.correlated_with", ["M-NADA"]))),
                   ("est-nulo-com-n", S(("set", "0.metrics.1.operational_coverage.n", 4))),
                   ("n-known-maior-que-n", S(("set", "0.metrics.2.operational_coverage.n_known", 2))),
                   ("est-nulo-com-conhecidos", S(("set", "0.metrics.2.operational_coverage.n_known", 1))),
                   ("est-numerico-sem-conhecidos", S(("set", "0.metrics.2.operational_coverage.est", 0.0)))],
    "C15:summary_results": [("sem-results", S(("del", "0.results"))),
                            ("est-fora", S(("set", "0.results.0.operational_coverage.lower", 0.6)))],
    "C15:metrics_spec": [("leitura-fora", S(("set", "0.metrics.0.reading", "row")))],
    "C16:intent_manifest": [("tag-sem-tags", S(("del", "0.tags"))),
                            ("expurgo-antes", S(("set", "0.purge_deadline", "2026-11-02T08:00:00-03:00"))),
                            ("id-da-conta", S(("set", "0.effective_identity_check.identity_sha256", TWELVE)))],
    "C16:run_manifest": [("sem-intencao", S(("set", "1.intent_id", "INT-9999"))),
                         ("fora-de-ordem", S(("set", "0.at", "2026-11-03T10:00:00-03:00"))),
                         ("publico-com-id", S(("set", "1.provider_resource_ref", "i-0abc"))),
                         ("identidade-fora", S(("set", "1.effective_identity_check.matches_allowlist", False))),
                         ("criado-sem-checagem", S(("del", "1.effective_identity_check")))],
    "C17:summary": [("modelo-fable", S(("set", "0.agent_provenance.model_id", "claude-fable-1"))),
                    ("fonte-sem-licenca", S(("del", "0.sources.0.license")))],
    "C17:freeze_receipt": [("comprovante-editado", S(("set", "0.owner", "outro"))),
                           ("tag-errada", S(("fn", _retag))),
                           ("carimbo-sem-motivo", S(("del", "0.ots.reason")))],
    "C18:numbers": [("prefixo-errado", S(("set", "0.macros.PersFieldRate.category", "coverage"))),
                    ("tex-diverge", S(("set", "0.macros.CovFieldN.display", "121"))),
                    ("nome-com-digito", S(("fn", lambda r: r[0]["macros"].__setitem__("Cov2", r[0]["macros"]["CovFieldN"]))))],
    # ----- C19–C23
    "C19:canonical_units": [("unknown-sem-falta", S(("set", "2.missing_evidence", []))),
                            ("entidade-com-falta", S(("set", "0.missing_evidence", ["owner"]))),
                            ("anonimo-sem-ocorrencia", S(("set", "1.identity.occurrence_key", []))),
                            ("entidade-sem-evidencia", S(("set", "0.evidence", []))),
                            ("pontas-em-entidade", S(("set", "0.endpoints", [{"role": "a", "unit_id": "CU-x"},
                                                                             {"role": "b", "unit_id": "CU-y"}]))),
                            ("ponta-unica", S(("set", "3.endpoints", [{"role": "subnet", "unit_id": "CU-aws-subnet"}]))),
                            ("papel-repetido", S(("set", "3.endpoints.1.role", "subnet"))),
                            ("ponta-de-si", S(("set", "3.endpoints.0.unit_id", "CU-aws-route-table-assoc"))),
                            ("dono-fora-de-refs", S(("set", "4.owner.ref", "CU-aws-outro"))),
                            ("dono-de-si", S(("set", "4.owner.refs", ["CU-aws-vpc-peering", "CU-aws-peering-options"]))),
                            ("um-so-dono-em-refs", S(("set", "4.owner.refs", ["CU-aws-vpc-peering"])))],
    "C19:canonical_atoms": [("unidade-inexistente", S(("set", "0.unit_id", "CU-nada"))),
                            ("atomo-em-duas", S(("set", "1.atom_id", "aws:aws_db_instance:backup_retention_period")))],
    "C20:glossary": [("na-com-unidade", S(("set", "1.unit", "unit:DAY"))),
                     ("unknown-com-unidade", S(("set", "3.unit", "unit:SEC"))),
                     ("fundido-sem-destino", S(("del", "1.replaced_by")))],
    "C20:claims": [("claim-id-muda-entre-versoes", S(("set", "1.claim_id", "ANC-aws-0099"),
                                                    ("set", "1.claim_version_id", "ANC-aws-0099@2"))),
                   ("versao-repetida", S(("set", "1.claim_version_id", "ANC-aws-0001@1"), ("del", "1.supersedes"))),
                   ("evento-reusado", S(("set", "1.event_id", "EV-GLOSS-0001"))),
                   ("supersedes-posterior", S(("set", "0.supersedes", "ANC-aws-0001@2"))),
                   ("evento-com-forma-de-versao", S(("set", "1.event_id", "EV-ANC@2"))),
                   ("doc-sem-fonte", S(("del", "1.source"))),
                   ("bloco-sem-implicacao", S(("del", "2.implication"))),
                   ("bloco-com-atomo", S(("set", "2.atom_id", "google:google_compute_firewall:priority"))),
                   ("bloco-sem-block-id", S(("del", "2.block_id"))),
                   ("bloco-com-escolha-de-tipo", S(("set", "2.implication.realization", "type_choice"))),
                   ("tipo-com-bloco", S(("set", "3.block_id", "aws:aws_vpc_security_group_egress_rule:x"))),
                   ("alternativa-mesmo-valor", S(("set", "3.implication.alternatives.0.value", "egress"))),
                   ("alternativa-de-si", S(("set", "2.implication.alternatives.0.ref",
                                            "google:google_compute_firewall:deny"))),
                   ("atomo-com-implicacao", S(("set", "0.implication", {"realization": "block_choice", "value": 1,
                                                                        "rule": "regra sintética longa"}))),
                   ("atomo-sem-atom-id", S(("del", "0.atom_id"))),
                   ("ancora-fora", S(("set", "2.anchor_kind", "page")))],
    "C20:decisions": [("ciclo", S(("set", "1.kind", "broader"))),
                      ("conceito-de-si", S(("set", "0.related_concept", "concept:backup_retention_automated"))),
                      ("conceito-fora-do-glossario", S(("set", "3.related_concept", "concept:nao_existe"))),
                      ("broader-sem-relacionado", S(("del", "0.related_concept"))),
                      ("valor-fora-de-value-type", S(("set", "0.value", {"datatype": "integer"}))),
                      ("value-type-sem-valor", S(("del", "2.value"))),
                      ("tipo-fora", S(("set", "3.kind", "related"))),
                      ("decisao-repetida", S(("fn", _dup_first)))],
    "C20:glossary_audit": [("versao-inexistente", S(("set", "0.claim_version_id", "ANC-aws-0001@7")))],
    "C21:verdicts": [("refutado-sem-regra", S(("set", "1.rules", []))), ("versao-de-outra", S(("set", "0.claim_version_id",
                                                                                             "CLM-X@1"))),
                     ("veredito-fora", S(("set", "0.verdict", "PERSISTED")))],
    "C22:observations": [("contagem-nao-soma", S(("set", "1.counts.errors", 0))),
                         ("julgamento-local", S(("set", "0.outcome", {"axis": "behavior",
                                                                      "value": "OBSERVATIONS_MATCH_UNDER_PROTOCOL"})))],
    "C22:pair_judgements": [("eixo-errado", S(("set", "0.outcome.axis", "persistence"))),
                            ("valor-de-persistencia", S(("set", "0.outcome.value", "PERSISTED"))),
                            ("lado-trocado", S(("set", "0.observations", {"A": "OBS-B-0001", "B": "OBS-A-0001"}))),
                            ("juiz-errado", S(("set", "0.judged_by", "PROBE-AWS")))],
    "C22:probe_types": [("tipo-repetido", S(("fn", lambda r: r[0]["probe_types"].append(copy.deepcopy(r[0]["probe_types"][0])))))],
    "C23:translation_trace": [("carregado-com-codigo", S(("set", "0.block_code", "UNPROVEN"))),
                              ("bloqueado-sem-codigo", S(("del", "1.block_code"))),
                              ("guarda-incoerente", S(("set", "1.guard_evaluated.result", "TRUE"))),
                              ("codigo-fora", S(("set", "2.block_code", "NOT_PORTABLE"))),
                              ("axioma-e-metadado", S(("set", "0.consulted_metadata",
                                                       ["x:backupRetention rdfs:domain (StorageContainer ⊔ DatabaseInstance)"]))),
                              ("omitido-com-saida", S(("set", "3.output", {"atom_id": "aws:aws_db_instance:x",
                                                                          "term": {"kind": "literal", "datatype": "null",
                                                                                   "value": None}})))],
    # ----- C24–C29
    "C24:commitments": [("polaridade-x-checagem", S(("set", "2.check.kind", "entails"))),
                        ("letra-do-id-x-polaridade", S(("set", "0.commitment_id", "CMT-CFG-N02"))),
                        ("unknown-com-leitura-completa", S(("fn", lambda r: [f["read"].update({"completeness": "complete", "not_read": []})
                                                                             for c in r if c["polarity"] == "unknown"
                                                                             for f in c["fixtures"]]))),
                        ("requisito-inexistente", S(("set", "0.requirement_ids", ["REQ-NADA-01"])))],
    "C24:cq_spec": [("conforme-igual-nao-conforme", S(("fn", lambda r: r[0]["fixtures"]["nonconforming"]["expected"].update(
        {"value": r[0]["fixtures"]["conforming"]["expected"]["value"]})))),
                    ("compromisso-inexistente", S(("set", "0.commitment_ids", ["CMT-NADA-P01"])))],
    "C24:pilot_expected_answers": [
        ("case-id-repetido", S(("set", "0.directions.DX-AWS-AZ-T1-negative-01.c11_case_seed.case_id", "CASE-PSTO-DX-01"))),
        ("campo-na-semente-e-pendente", S(("set", "0.directions.DX-AWS-AZ-T1-acceptable-01.c11_case_seed.pending.values",
                                           "idem"))),
        ("semente-incompleta", S(("del", "0.directions.DX-AWS-AZ-T1-acceptable-01.c11_case_seed.pending.weight"))),
        ("par-de-outra-direcao", S(("set", "0.directions.DX-AWS-AZ-T1-acceptable-01.direction", "google->oci"))),
        ("direcao-para-si", S(("set", "0.directions.DX-AWS-AZ-T1-acceptable-01.direction", "aws->aws"))),
        ("retida-em-claro", S(("set", "0.heldout.answers", {"DX-1": "ACCEPT"}))),
        ("veredito-fora", S(("set", "0.directions.DX-AWS-AZ-T1-acceptable-01.expect.verdict", "MAYBE"))),
        ("claim-sem-veredito", S(("set", "0.fixtures.FX-STO-AWS-VER-P01.checks.1.expect", "ACCEPT"))),
        ("pending-campo-fora", S(("set", "0.directions.DX-AWS-AZ-T1-acceptable-01.c11_case_seed.pending.cor", "azul")))],
    "C25:protocol_support": [("validado", S(("set", "0.validated", True))),
                             ("suportado-sem-publicada", S(("set", "0.evidence", [{"level": "derived", "note": "nota sintética"}]))),
                             ("unknown-sem-motivo", S(("del", "1.reason"))),
                             ("repetido", S(("fn", _dup_first))),
                             ("interpretado-sem-modelo", S(("del", "0.evidence.1.model_id"))),
                             ("suportado-sem-atributo", S(("set", "0.attributes", [])))],
    "C24:requirements": [("id-repetido", S(("fn", _dup_first))), ("area-fora", S(("set", "0.area", "magic")))],
    "C25:service_evidence": [("publicado-sem-sentenca", S(("del", "0.citation.sentence"))),
                             ("interpretado-sem-modelo", S(("del", "2.model_id"))),
                             ("derivado-de-nada", S(("set", "1.derived_from", ["SE-nada"]))),
                             ("unknown-com-valor", S(("set", "2.value", True))),
                             ("unknown-sem-consulta", S(("del", "6.consulted"))),
                             ("default-sem-data", S(("del", "5.as_of"))),
                             ("schema-sem-sha", S(("del", "3.schema.schema_sha256"))),
                             ("schema-op-fora", S(("set", "3.schema.op", "tree"))),
                             ("bloco-sem-tipo", S(("del", "3.terraform_resource_type"))),
                             ("afirmado-sem-nivel", S(("del", "4.level"))),
                             ("publicado-sem-fonte", S(("del", "4.citation")))],
    "C26:graph_ir": [("componente-orfao", S(("set", "2.components.0.of", "r9"))),
                     ("referencia-solta", S(("set", "0.references.0.to", "r7"))),
                     ("no-repetido", S(("set", "0.resources.1.node_id", "r1"))),
                     ("termo-repetido", S(("fn", lambda r: r[3]["terms"].append(copy.deepcopy(r[3]["terms"][0]))))),
                     ("precondicao-solta", S(("set", "0.preconditions", [{"precondition_id": "PRE-0001",
                                                                         "guard": {"all": []}, "applies_to": ["c5"]}])))],
    "C26:lowering_plan": [("ordem-repetida", S(("set", "0.steps.1.order", 1))),
                          ("depende-do-futuro", S(("set", "0.steps.0.depends_on", [2]))),
                          ("sintetizado-sem-marca", S(("set", "0.steps.0.values.1.marked", False))),
                          ("escolha-fora", S(("set", "3.steps.3.typed_choices.0.selected", "r_outra"))),
                          ("fechado-com-falta", S(("set", "0.dependency_closure.missing", ["x"]))),
                          ("termo-fora-do-grafo", S(("set", "0.steps.0.derived_name.from_terms", ["t9"]))),
                          ("no-fora-do-grafo", S(("set", "1.steps.0.node_id", "r9"))),
                          ("grafo-inexistente", S(("set", "2.graph_id", "GIR-NADA"))),
                          ("alvo-de-referencia-fora", S(("set", "0.steps.1.values.0.term.target_node", "r9"))),
                          ("alvo-de-referencia-futuro", S(("set", "0.steps.0.values.0.term",
                                                           {"kind": "reference", "target_type": "aws_subnet",
                                                            "target_address": "aws_subnet.SYM-a1b2c3d4e5f60718",
                                                            "target_node": "r2"}))),
                          ("campo-do-nome-invalido", S(("set", "0.steps.0.derived_name.field", "Nome Errado"))),
                          ("tag-de-execucao", S(("fn", lambda r: r[3]["steps"][0]["values"].append(
                              {"field": "freeform_tags.bo_run", "marked": True, "origin": "synthesized",
                               "term": {"kind": "literal", "datatype": "string", "value": "run-01"}}))))],
    "C27:split": [("teste-em-claro", S(("set", "0.partitions.test.family_ids", ["F-0a0b0c0d0e0f"]))),
                  ("papel-ve-teste", S(("set", "0.role_projections.mapper.partitions", ["train", "test"]))),
                  ("teste-sem-cifra", S(("set", "0.partitions.test.encrypted.path", "$BO_DATA/SPLIT/test.jsonl")))],
    "C27:families": [("repo-em-duas", S(("set", "1.members", ["R-00a1b2c3d4e5"]))),
                     ("familia-de-teste", S(("set", "1.partition", "test"))),
                     ("contagem-diverge", S(("set", "1.partition", "train")))],
    "C28:comparators": [("na-vira-zero", S(("set", "0.comparators.0.metrics.1.value", 0))),
                        ("na-sem-motivo", S(("del", "0.comparators.0.metrics.1.reason"))),
                        ("sem-artefato-traduz", S(("set", "0.comparators.0.axes", ["native", "representation",
                                                                                   "translation"])))],
    "C28:h2h_fairness": [("orcamento-desigual", S(("set", "0.comparators.1.budget_hours", 12))),
                         ("outro-universo", S(("set", "0.comparators.0.same_universe", False)))],
    "C29:domain_contracts": [("fragmento-inexistente", S(("set", "0.domains.0.network_fragment", "FRG-NADA"))),
                             ("ausencia-sem-evidencia", S(("del", "0.domains.0.authorization.combination.evidence"))),
                             ("dimensao-faltando", S(("del", "0.domains.0.authorization.inheritance")))],
    "C29:fragment": [("aresta-solta", S(("set", "0.edges.0.to", "n9"))), ("no-repetido", S(("set", "0.nodes.1.node_id", "n0")))],
}


# ------------------------------------------------------------------------------------------- estruturais
def _def_of(fk: catalog.FileKind, sch: dict) -> dict | None:
    if not fk.record:
        return None
    return sch[fk.cid]["$defs"][fk.record]


def structural(fk, recs: list, sch: dict) -> list[tuple[str, list]]:
    d = _def_of(fk, sch)
    if d is None or "properties" not in d:
        return []
    out = []
    first = recs[0]
    for k in d.get("required") or []:
        if k in first:
            r = copy.deepcopy(recs)
            r[0].pop(k)
            out.append((f"sem-obrigatorio:{k}", r))
    props = d["properties"]
    for k, v in props.items():
        if k in first and "enum" in v:
            r = copy.deepcopy(recs)
            r[0][k] = "__MUTADO__"
            out.append((f"enum-corrompido:{k}", r))
            break
    for k, v in first.items():
        if isinstance(v, str) and k in props:
            r = copy.deepcopy(recs)
            r[0][k] = 12345
            out.append((f"tipo-trocado:{k}", r))
            break
    if d.get("additionalProperties") is False and fk.format != "sssom_tsv":
        r = copy.deepcopy(recs)
        r[0]["campo_nao_declarado"] = 1
        out.append(("campo-extra", r))
    return out


# --------------------------------------------------------------------------------------------- por formato
def _records(fk, data: bytes):
    t = data.decode("utf-8") if fk.format not in ("parquet",) else None
    if fk.format == "jsonl":
        return [json.loads(l) for l in t.splitlines() if l.strip()]
    if fk.format == "json":
        return [json.loads(t)]
    if fk.format == "yaml":
        return [yaml.safe_load(t)]
    if fk.format == "sssom_tsv":
        from .sssom import read_tsv
        return read_tsv(t)[1]
    return None


def _encode(fk, recs: list, data: bytes) -> bytes:
    if fk.format == "jsonl":
        return jsonl(recs).encode()
    if fk.format == "json":
        return (json.dumps(recs[0], ensure_ascii=False, indent=1) + "\n").encode()
    if fk.format == "yaml":
        return yaml.safe_dump(recs[0], sort_keys=False, allow_unicode=True).encode()
    if fk.format == "sssom_tsv":
        from .sssom import read_tsv, write_tsv
        meta = read_tsv(data.decode("utf-8"))[0]
        return write_tsv(recs, meta.get("mapping_set_id"), meta.get("curie_map")).encode()
    raise ValueError(fk.format)


def _format_mutants(fk, data: bytes, rel: str) -> list[tuple[str, bytes]]:
    t = data.decode("utf-8") if fk.format != "parquet" else ""
    out = []
    if fk.format == "jsonl":
        out += [("linha-em-branco", (t + "\n").encode()), ("json-quebrado", (t + "{\n").encode()),
                ("sem-quebra-final", t.rstrip("\n").encode())]
    elif fk.format in ("json", "yaml"):
        out += [("documento-quebrado", (t[: len(t) // 2]).encode())]
    elif fk.format == "sssom_tsv":
        lines = t.splitlines(keepends=True)
        out.append(("extensao-nao-declarada",
                    "".join(l for l in lines if "slot_name: guard" not in l and "property: bosx:guard" not in l
                            and "type_hint" not in l or not l.startswith("#")).encode()))
        out.append(("prefixo-fora-do-curie-map", "".join(l for l in lines if not l.startswith("#   pa:")).encode()))
        out.append(("sem-linhas", "".join(l for l in lines if l.startswith("#") or l.startswith("subject_id")).encode()))
        body = [i for i, l in enumerate(lines) if not l.startswith("#")]
        extra = list(lines)
        extra[body[0]] = extra[body[0]].rstrip("\n") + "\tcoluna_nao_declarada\n"
        for i in body[1:]:
            extra[i] = extra[i].rstrip("\n") + "\tx\n"
        ext_at = max(i for i, l in enumerate(lines) if l.startswith("# extension_definitions:"))
        extra.insert(ext_at + 1, "# - property: bosx:colunaNaoDeclarada\n#   slot_name: coluna_nao_declarada\n"
                                 "#   type_hint: http://www.w3.org/2001/XMLSchema#string\n")
        out.append(("coluna-declarada-fora-do-contrato", "".join(extra).encode()))
    elif fk.format == "parquet":
        import pyarrow as pa
        import pyarrow.parquet as pq
        tbl = pq.read_table(io.BytesIO(data))

        def w(t2):
            b = io.BytesIO()
            pq.write_table(t2, b)
            return b.getvalue()
        out.append(("coluna-faltando", w(tbl.drop_columns(["n_attrs"]))))
        out.append(("tipo-de-coluna", w(tbl.set_column(tbl.schema.get_field_index("n_attrs"), "n_attrs",
                                                       pa.array([str(x) for x in tbl["n_attrs"].to_pylist()])))))
        out.append(("coluna-extra", w(tbl.append_column("split", pa.array(["train"] * tbl.num_rows)))))
        out.append(("nome-real", w(tbl.set_column(tbl.schema.get_field_index("resource_address"), "resource_address",
                                                  pa.array(["aws_db_instance.prod_db"] * tbl.num_rows)))))
        out.append(("arquivo-corrompido", data[: len(data) // 2]))
    elif fk.format == "turtle":
        out.append(("punning", (t + "\nx:Resource a owl:NamedIndividual .\n").encode()))
        out.append(("dois-dominios", (t + "\nx:backupRetention rdfs:domain x:StorageContainer .\n").encode()))
        out.append(("metamodelagem", (t + "\nx:hasClass a owl:ObjectProperty ; rdfs:range owl:Class .\n").encode()))
        out.append(("sintaxe", (t + "\nx:a x:b .. \n").encode()))
    elif fk.format == "edoal_ttl":
        out.append(("sem-claim-id", re.sub(r"\n\s*bosx:claimId [^;]+;", "\n", t).encode()))
        out.append(("relacao-fora", t.replace('align:relation "="', 'align:relation "%"').encode()))
        out.append(("medida-fora", re.sub(r'align:measure "[0-9.]+"', 'align:measure "7.0"', t).encode()))
        out.append(("sintaxe", (t + "\n<<<\n").encode()))
    elif fk.format == "sha256_manifest":
        first = t.splitlines()[0]
        out.append(("hash-curto", ("abc  x/y.json\n" + t).encode()))
        out.append(("caminho-repetido", (t + first + "\n").encode()))
        out.append(("reticencias", (t + "0" * 64 + "  results/.../x.json\n").encode()))
        out.append(("um-espaco", (t.replace("  ", " ", 1)).encode()))
    elif fk.format == "tex_macros":
        out.append(("exibicao-diverge", t.replace("{120}", "{121}").encode()))
        out.append(("linha-estranha", (t + "\\def\\x{1}\n").encode()))
        out.append(("macro-a-mais", (t + "\\newcommand{\\CovExtra}{3}\n").encode()))
    return out


def mutants(fk: catalog.FileKind, data: bytes, rel: str, sch: dict) -> list[tuple[str, bytes]]:
    """Mutantes; um mutante igual ao original (mutação nula) também é devolvido e conta como sobrevivente."""
    out = list(_format_mutants(fk, data, rel))
    recs = _records(fk, data)
    if recs is not None:
        for mid, r in structural(fk, recs, sch):
            out.append((mid, _encode(fk, r, data)))
        key = f"{fk.cid}:{fk.kind}"
        sem = list(SEM.get(key, []))
        if rel == "complex.sssom.tsv":
            sem = COMPLEX
        for mid, f in sem:
            out.append((f"semantica:{mid}", _encode(fk, f(copy.deepcopy(recs)), data)))
    return out


# ------------------------------------------------------------------------------------- C09 complexo (G3)
def _loose_var(r):
    r[0]["group"]["variables"].append({"name": "?solta", "side": "subject", "field": "pa:rule.x", "occurrence": "?r"})


def _arity(r):
    st = r[0]["group"]["steps"][1]
    st["inputs"] = {"start": "?from", "to_port": "?to"}


def _occ_mix(r):
    r[1]["group"]["joins"] = []


def _overlap(r):
    r[2]["projection"][1]["extractor"]["component"] = "from_port"
    r[2]["projection"][1]["tests"] = [{"input": "80-443", "expected": 80}]


COMPLEX = [
    ("grupo-variavel-solta", S(("fn", _loose_var))),
    ("grupo-aridade", S(("fn", _arity))),
    ("grupo-ocorrencias-sem-juncao", S(("fn", _occ_mix))),
    ("grupo-cardinalidade", S(("set", "0.group.cardinality", "1:1"))),
    ("grupo-saida-na-origem", S(("set", "0.group.steps.0.outputs", {"value": "?from"}))),
    ("grupo-id-diverge", S(("set", "0.bo_group_id", "GRP-OUTRO"))),
    ("grupo-sem-id", S(("del", "0.bo_group_id"))),
    ("grupo-variavel-sem-nome", S(("set", "0.group.variables.0.name", "proto"))),
    ("projecao-bloco-sem-chave", S(("del", "2.projection.0.occurrence.key_fields"))),
    ("projecao-chave-posicional", S(("set", "2.projection.0.occurrence.key_fields", ["index"]))),
    ("projecao-sobreposta-nao-declarada", S(("fn", _overlap))),
    ("projecao-extrator-errado", S(("set", "2.projection.0.tests.0.expected", 81))),
    ("alternativa-nao-mutua", S(("set", "4.alternative_to", ["CLM-GRP-PORTS-01"]))),
    ("alternativa-guardas-cruzam", S(("set", "4.guard", {"all": [{"term": "object.edition", "op": "edition_in",
                                                                    "value": ["standard", "premium"]}]}))),
    ("alternativa-outro-sujeito", S(("set", "4.subject_id", "pa:outra_coisa"))),
    ("alternativa-sem-guarda", S(("set", "4.guard", {"all": []}))),
    ("alternativa-fora-do-arquivo", S(("set", "3.alternative_to", ["CLM-NADA"]), ("set", "4.alternative_to", ["CLM-NADA"]))),
    ("alternativa-sem-exclusividade", S(("del", "3.exclusivity"))),
    ("alternativa-exclusividade-divergente", S(("set", "4.exclusivity", "Ambiguous"))),
]
