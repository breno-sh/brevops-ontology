"""C09–C14: correspondências, transformações/guarda/composição, casos, leitura e desfecho, versões e eventos,
tabelas da ontologia. Incorpora as propostas mergeadas (results/SEMANTICS/C09_proposta, C10_proposta e
results/ONTPAT/C14_proposta), copiadas sem mudança em src/bo/contracts/adopted/."""

from __future__ import annotations

import copy
import json

from ._base import (BASE_URI, PKG, arr, boolean, c00, const, contract_schema, enum, file_kind, header, integer,
                    local, nullable, number, obj, string, text)
from .spec_a import BLOCK_CODES, SCALARS

SEMANTIC_RELATIONS = ("exact", "close", "broad", "narrow", "related")
SKOS_PREDICATES = ("skos:exactMatch", "skos:closeMatch", "skos:broadMatch", "skos:narrowMatch", "skos:relatedMatch")
VDR = ("equal", "subset", "superset", "overlap", "disjoint", "unknown")
FIDELITIES = ("lossless", "declared_loss", "partial", "none")
LOSS_KINDS = ("rounding", "saturation", "absence", "sentinel", "context_dependence", "not_expressible", "semantic")
GUARD_OPS = ("eq", "in", "present", "refers_to_kind", "region_in", "edition_in", "version_range")
EXCLUSIVITY = ("ProvenExclusive", "Ambiguous")
# colunas do SSSOM 0.15 (sssom_schema.Mapping), aceitas como slots padrão
SSSOM_SLOTS = ("record_id", "subject_label", "subject_category", "predicate_label", "predicate_modifier",
               "object_label", "object_category", "author_id", "author_label", "reviewer_id", "reviewer_label",
               "creator_id", "creator_label", "license", "subject_type", "subject_source", "subject_source_version",
               "object_type", "object_source", "object_source_version", "predicate_type", "mapping_provider",
               "mapping_source", "mapping_cardinality", "cardinality_scope", "mapping_tool", "mapping_tool_id",
               "mapping_tool_version", "mapping_date", "publication_date", "review_date", "confidence",
               "reviewer_agreement", "curation_rule", "curation_rule_text", "subject_match_field",
               "object_match_field", "match_string", "subject_preprocessing", "object_preprocessing",
               "similarity_score", "similarity_measure", "see_also", "issue_tracker_item", "other", "comment")
C10_GUARD = {"$ref": f"{BASE_URI}C10/transforms.schema.json#/$defs/guard"}
C14_GUARDED = {"$ref": f"{BASE_URI}C10/transforms.schema.json#/$defs/guard"}


def adopted(name: str) -> dict:
    return json.loads((PKG / "adopted" / f"{name}.json").read_text(encoding="utf-8"))


def _strip(s: dict) -> dict:
    s = copy.deepcopy(s)
    for k in ("$schema", "$id"):
        s.pop(k, None)
    return s


# ------------------------------------------------------------------------------------------------- C09
def value_type() -> dict:
    """Tipo de valor do SEMANTICS (ValueType) com os marcadores do C00 no lugar de 'string livre'."""
    return obj({"datatype": enum("integer", "decimal", "boolean", "string", "enum", "duration", "tuple"),
                "quantity_kind": c00("quantity_kind"), "unit": c00("unit_qudt"),
                "rate_window": nullable(c00("xsd_duration")), "byte_convention": enum("SI", "IEC", None),
                "enum": {"type": "array"}, "range": {"type": "object"}, "step": {"type": ["string", "integer"]},
                "sentinels": {"type": "object"}, "components": {"type": "array"}, "required": boolean()},
               ["datatype"])


def projection() -> dict:
    occ = obj({"scope": enum("resource", "block"),
               "key_fields": arr({"type": "string", "minLength": 1, "not": {"enum": ["index", "position", "ordinal"]}},
                                 unique=True)}, ["scope"],
              allOf=[{"if": {"properties": {"scope": const("block")}},
                      "then": {"required": ["key_fields"], "properties": {"key_fields": {"minItems": 1}}}}])
    return obj({"projection_id": string(r"^PRJ-[A-Za-z0-9_\-]+$"), "field": string(r"^[a-z][a-z0-9_]*:\S+$"),
                "occurrence": occ,
                "extractor": obj({"name": string(r"^[a-z][a-z0-9_]*$"), "component": string(r"^[a-z][a-z0-9_]*$"),
                                  "params": {"type": "object"}}, ["name"]),
                "concept": c00("concept_id"), "type": local("value_type"),
                "overlaps": arr(string(r"^PRJ-[A-Za-z0-9_\-]+$"), unique=True),
                "tests": arr(obj({"input": {}, "expected": {}}, ["input", "expected"]))},
               ["projection_id", "field", "occurrence", "extractor", "concept", "type", "tests"])


def group() -> dict:
    var = string(r"^\?[a-z][a-z0-9_]*$")
    return obj({
        "bo_group_id": string(r"^GRP-[A-Za-z0-9_\-]+$"), "cardinality": enum("1:1", "1:N", "N:1", "N:M"),
        "variables": arr(obj({"name": var, "side": c00("side"), "field": string(r"^[a-z][a-z0-9_]*:\S+$"),
                              "occurrence": var}, ["name", "side", "field", "occurrence"]), 2),
        "occurrence_vars": arr(var, 1, unique=True),
        "joins": arr(obj({"left": var, "right": var,
                          "via": enum("facet_of", "component_of", "reference", "attachment", "same_block")},
                         ["left", "right", "via"])),
        "steps": arr(obj({"name": string(r"^[a-z][a-z0-9_]*$"), "params": {"type": "object"},
                          "inputs": obj({}, extra=var, minProperties=1),
                          "outputs": obj({}, extra=var, minProperties=1)}, ["name", "inputs", "outputs"]), 1)},
        ["bo_group_id", "cardinality", "variables", "occurrence_vars", "joins", "steps"],
        description="grupo como regra sobre subgrafo: variáveis nomeadas por lado e ocorrência, argumentos nomeados")


def correspondence() -> dict:
    base = _strip(adopted("C09_correspondence"))
    props = base["properties"]
    for k in ("claim_id", "claim_version_id", "event_id"):
        props[k] = c00(k)
    props["guard"] = C10_GUARD
    props["subject_value_type"] = local("value_type")
    props["object_value_type"] = local("value_type")
    props["subject_concept"] = c00("concept_id")
    props["object_concept"] = c00("concept_id")
    props["subject_id"] = string(r"^[A-Za-z][A-Za-z0-9_.\-]*:\S+$")
    props["object_id"] = string(r"^[A-Za-z][A-Za-z0-9_.\-]*:\S+$")
    fn = obj({"name": string(r"^[a-z][a-z0-9_]*$"), "params": {"type": "object"}}, ["name"])
    props["translation_fn"] = {"oneOf": [{"type": "null"}, fn, arr(fn, 1)]}
    props["loss_contract"] = arr(obj({"kind": enum(*LOSS_KINDS)}, ["kind"], extra=True))
    props["projection"] = arr(local("projection"), 1)
    props["group"] = local("group")
    props["bo_group_id"] = string(r"^GRP-[A-Za-z0-9_\-]+$")
    props["alternative_to"] = arr(c00("claim_id"), 1, unique=True)
    props["exclusivity"] = enum(*EXCLUSIVITY)
    props["supersedes"] = c00("claim_version_id")
    props["inverse_of"] = c00("claim_id")
    for s in SSSOM_SLOTS:
        props.setdefault(s, {"type": ["string", "number"]})
    props["confidence"] = number(minimum=0, maximum=1)
    rec = {"type": "object", "title": base["title"].replace("C09 3.0.0", "C09 3.0.0 (CONTRACTS)"),
           "required": base["required"], "properties": dict(sorted(props.items())), "additionalProperties": False,
           "allOf": [
               {"if": {"required": ["group"]}, "then": {"required": ["bo_group_id"]}},
               {"if": {"required": ["alternative_to"]}, "then": {"required": ["exclusivity", "guard"]}}]}
    return rec


def c09() -> dict:
    defs = {"correspondence": correspondence(), "value_type": value_type(), "projection": projection(),
            "group": group()}
    return contract_schema(
        "C09", "correspondences", "3.0.1", "alegações de correspondência (SSSOM + EDOAL)", status="amended",
        description="Colunas SSSOM mais claim_id (imutável), claim_version_id, event_id; semantic_relation (predicado "
                    "SKOS na direção correta: 'a skos:broadMatch b' = b mais amplo), value_domain_relation orientada, "
                    "transport_fidelity; guard (gramática tipada do C10); translation_fn; loss_contract; "
                    "membership_predicate para broad/narrow; grupo como regra sobre subgrafo (bo_group_id, variáveis "
                    "e argumentos nomeados, ocorrência do bloco); projection por ocorrência; realizações alternativas "
                    "guardadas (alternative_to + exclusivity); proof; evidence_state (C20); conceitos ou bo:UNGLOSSED. "
                    "Colunas estruturadas são JSON numa célula. O I/O passa por bo.contracts.sssom (que delega a "
                    "bo.semantics.sssom_io e preserva as colunas novas): o sssom-py 0.4.22 descarta extensões em "
                    "silêncio.",
        files=[file_kind("correspondences", "*.sssom.tsv", "sssom_tsv", "correspondence", "row"),
               file_kind("correspondences_jsonl", "*.jsonl", "jsonl", "correspondence", "record",
                         "mesma linha já decodificada (colunas estruturadas como JSON)"),
               file_kind("edoal", "*.edoal.ttl", "edoal_ttl", None, "cell",
                         "subconjunto EDOAL do bo.semantics.edoal (=, <, >), anotações bosx:* com os ids")],
        defs=defs, adopted=["results/SEMANTICS/C09_proposta/correspondence.schema.json"],
        producers=["MAP-{pair}-{domain}", "PILOT-{slice}-MAP", "RECONCILE", "GOLD-*", "NONEHUNT-{provider}"],
        rules=["C09-SSSOM: cabeçalho com curie_map (todo prefixo usado declarado), mapping_set_id, license e "
               "extension_definitions de toda coluna não padrão",
               "C09-SKOS: semantic_relation = predicate_id (exact↔exactMatch, broad↔broadMatch…)",
               "C09-GUARD: guarda na gramática tipada (bo.semantics.guards.typecheck)",
               "C09-IDS: claim_version_id = <claim_id>@n; claim_version_id e event_id únicos no arquivo; supersedes "
               "aponta para versão anterior da MESMA alegação",
               "C09-FN: translation_fn só com funções do núcleo (bo.semantics.transforms) ou do registro do C10",
               "C09-GROUP: grupo com variáveis nomeadas, ligadas e únicas, argumentos = assinatura, ocorrências ligadas "
               "por junção (G-VARS, G-ARITY, G-OCC); bo_group_id da coluna = do grupo",
               "C09-PROJ: projeção em bloco repetido tem chave de ocorrência que não é posição; extrator roda nos "
               "testes; sobreposição declarada (P-OCC, P-EXEC, P-OVERLAP)",
               "C09-ALT: alternativas são mútuas, do mesmo subject_id, com guarda; ProvenExclusive só se a interseção "
               "das guardas é UNSAT; senão Ambiguous (A-EXCL)"])


# ------------------------------------------------------------------------------------------------- C10
def c10() -> dict:
    guard = _strip(adopted("C10_guard"))
    comp = _strip(adopted("C10_composition_table"))
    comp["properties"]["contract_version"] = const("3.0.0")
    comp["properties"]["module"] = c00("stable_id")
    comp["properties"]["reading"] = text(10)
    for k in ("guard", "domain", "evidence", "verdict", "closure"):
        comp["properties"][k] = obj({"rule": text(10)}, ["rule"], extra=True)
    sr = comp["properties"]["semantic_relation"]["items"]
    sr["properties"]["why"] = text(3)
    sr["properties"]["predicate"] = enum(*SKOS_PREDICATES, None)
    sr["properties"]["rcc5"] = arr(enum(*VDR[:5]), 1, unique=True)
    sr["allOf"] = [{"if": {"properties": {"result": {"type": "null"}}}, "then": {"properties": {"predicate": {"type": "null"}}},
                    "else": {"required": ["predicate"]}}]
    vdr_row = obj({"r1": enum(*VDR[:5]), "r2": enum(*VDR[:5]), "result": enum(*VDR),
                   "possible": arr(enum(*VDR[:5]), 1, unique=True)}, ["r1", "r2", "result", "possible"])
    comp["properties"]["value_domain_relation"]["properties"]["rows"]["items"] = vdr_row
    fid_row = obj({"f1": enum(*FIDELITIES), "f2": enum(*FIDELITIES), "result": enum(*FIDELITIES)},
                  ["f1", "f2", "result"])
    comp["properties"]["transport_fidelity"]["properties"]["rows"]["items"] = fid_row
    gram = adopted("C10_conditions_grammar")
    grammar = obj({"schema": const("bo.conditions_grammar/1"), "contract": const("C10"),
                   "contract_version": const("3.0.0"), "form": text(10), "roles": const(["subject", "object"]),
                   "operators": obj({op: text(5) for op in GUARD_OPS}, list(GUARD_OPS)),
                   "satisfiability": text(10), "evaluation": text(10), "composition": text(10),
                   "schema_ref": text(3),
                   "sat_tests": arr(obj({"test_id": string(r"^SAT-[A-Za-z0-9_\-]+$"), "guard": local("guard"),
                                         "expected": enum("SAT", "UNSAT", "UNKNOWN")},
                                        ["test_id", "guard", "expected"]), 3)},
                  ["schema", "contract", "contract_version", "form", "roles", "operators", "satisfiability",
                   "evaluation", "composition", "sat_tests"])
    assert set(gram["operators"]) == set(GUARD_OPS)
    side = obj({"datatype": enum(*SCALARS, "tuple", "number", "any"), "quantity_kind": c00("quantity_kind"),
                "unit": c00("unit_qudt")}, ["datatype", "quantity_kind"])
    scalar = obj({"name": string(r"^[a-z][a-z0-9_]*$"), "kind": const("scalar"), "domain": side, "codomain": side,
                  "precondition": text(3), "error": text(3), "loss": text(3),
                  "inverse": obj({"name": nullable(string(r"^[a-z][a-z0-9_]*$")), "partial": boolean()},
                                 ["name", "partial"]),
                  "params": obj({}, extra={"type": "object"}),
                  "context_required": arr(enum("calendar", "region", "edition", "provider_version"), unique=True),
                  "duration_calendar": enum("forbidden", "with_context",
                                            description="duração com mês/ano: recusada ou só com contexto de calendário")},
                 ["name", "kind", "domain", "codomain", "precondition", "error", "loss", "inverse"])
    port = obj({"name": string(r"^[a-z][a-z0-9_]*$"), "datatype": enum(*SCALARS, "tuple", "number", "any")},
               ["name", "datatype"])
    comb = obj({"name": string(r"^[a-z][a-z0-9_]*$"), "kind": const("tuple"), "inputs": arr(port, 1),
                "outputs": arr(port, 1), "precondition": text(3), "error": text(3), "loss": text(3),
                "inverse": obj({"name": nullable(string(r"^[a-z][a-z0-9_]*$")), "partial": boolean()},
                               ["name", "partial"])},
               ["name", "kind", "inputs", "outputs", "precondition", "error", "loss", "inverse"])
    hp, hr = header("bo.transforms/1", "C10", "3.0.0", module=True)
    tdoc = obj({**hp, "scalar": arr(local("scalar_transform"), 1), "combinators": arr(local("combinator"))},
               hr + ["scalar", "combinators"])
    defs = {"guard": guard, "composition_table": comp, "conditions_grammar": grammar, "transforms": tdoc,
            "scalar_transform": scalar, "combinator": comb}
    return contract_schema(
        "C10", "transforms", "3.0.0", "transformações, gramática de guarda e tabela de composição", status="changed_v3",
        description="Transformação escalar (grandeza de entrada = de saída) separada de combinador de tupla; domínio e "
                    "codomínio, pré-condições, erro, perda, inversa parcial; durações com mês/ano só com contexto; "
                    "gramática de guarda tipada e decidível (eq, in, present, refers_to_kind, region_in, edition_in, "
                    "version_range) com teste de satisfatibilidade; tabela de composição.",
        files=[file_kind("transforms", "transforms.yaml", "yaml", "transforms", "document"),
               file_kind("conditions_grammar", "conditions.grammar.json", "json", "conditions_grammar", "document"),
               file_kind("composition_table", "composition_table.json", "json", "composition_table", "document"),
               file_kind("guard", "guard.json", "json", "guard", "document", "uma guarda solta (stub e testes)")],
        defs=defs, producers=["SEMANTICS", "TRANSFORMS"],
        adopted=["results/SEMANTICS/C10_proposta/guard.schema.json",
                 "results/SEMANTICS/C10_proposta/composition_table.schema.json",
                 "results/SEMANTICS/C10_proposta/conditions.grammar.json"],
        rules=["C10-KIND: transformação escalar tem a mesma grandeza na entrada e na saída (kind_in = kind_out só vale "
               "para escalar); tupla vai em combinators",
               "C10-CAL: duração com mês/ano (P…M, P…Y) só com context_required ∋ calendar",
               "C10-INV: inverse.name, quando há, é transformação declarada no mesmo documento",
               "C10-SAT: cada sat_test dá o resultado esperado em bo.semantics.guards.satisfiable",
               "C10-TABLE: semantic_relation e value_domain_relation cobrem os 25 pares (r1, r2) uma vez cada; "
               "transport_fidelity os 16 pares (f1, f2)",
               "C10-GUARD: guarda passa no typecheck da gramática"])


# ------------------------------------------------------------------------------------------------- C11
def c11() -> dict:
    case = obj({
        "case_id": string(r"^CASE-[A-Za-z0-9_\-]+$"), "group_id": string(r"^(GRP|G)-[A-Za-z0-9_\-]+$"),
        "claim_id": c00("claim_id"), "claim_version_id": c00("claim_version_id"),
        "stratum": obj({"pair": c00("pair"), "domain": c00("domain"),
                        "cardinality": enum("1:1", "1:N", "N:1", "N:M"),
                        "relation": enum(*SEMANTIC_RELATIONS), "direction": enum("forward", "inverse")},
                       ["pair", "domain", "cardinality", "relation", "direction"]),
        "frame_ref": c00("file_ref"), "weight": number(exclusiveMinimum=0),
        "origin": enum("sample", "blocked", "dispute", "cq"), "cq_id": string(r"^CQ-[A-Z]{3,4}-\d{2}$"),
        "side": enum("subject", "object", "both"),
        "lowering_plan": obj({"plan_id": string(r"^LP-[A-Za-z0-9_\-]+$"), "graph_id": string(r"^GIR-[A-Za-z0-9_\-]+$")},
                             ["plan_id", "graph_id"]),
        "values": arr(obj({"var": string(r"^(\?[a-z][a-z0-9_]*|[a-z][a-z0-9_]*:\S+)$"), "term": c00("term")},
                          ["var", "term"]), 1),
        "comparator": obj({"name": enum("exact", "numeric_tolerance", "set_equal", "normalized_string",
                                        "duration_equal", "cidr_equal"),
                           "tolerance": number(minimum=0)}, ["name"]),
        "cost_class": enum("free", "low", "medium", "high"), "guard": C10_GUARD},
        ["case_id", "group_id", "claim_id", "claim_version_id", "stratum", "frame_ref", "weight", "origin", "side",
         "lowering_plan", "values", "comparator", "cost_class"],
        allOf=[{"if": {"properties": {"origin": const("cq")}}, "then": {"required": ["cq_id"]}},
               {"if": {"properties": {"comparator": {"properties": {"name": const("numeric_tolerance")}}}},
                "then": {"properties": {"comparator": {"required": ["tolerance"]}}}}])
    return contract_schema(
        "C11", "cases", "3.0.1", "casos de implantação", status="amended",
        description="case_id, group_id, claim_id, estrato (par, domínio, cardinalidade, relação, direção), frame_ref e "
                    "peso, origin (sample | blocked | dispute | cq), lado, plano de lowering (C26) em vez de lista de "
                    "caminhos, valores, comparador, classe de custo.",
        files=[file_kind("cases", "cases*.jsonl", "jsonl", "case", "record")], defs={"case": case},
        producers=["DEPSAMPLE", "DISPUTE-SAMPLE"],
        rules=["C11-UNIQ: case_id único", "C11-CQ: origin=cq exige cq_id",
               "C11-VER: claim_version_id é versão do claim_id do caso",
               "C11-NOPATHS: o caso aponta para um plano de lowering (C26), nunca para lista de caminhos"])


# ------------------------------------------------------------------------------------------------- C12
def c12() -> dict:
    field = obj({"path": string(r"^[A-Za-z0-9_]+(\.[A-Za-z0-9_]+|\[[0-9]+\])*$"),
                 "node_id": string(r"^[rc][0-9]+$", description="nó do graph_ir/plano (C26) dono do campo, quando o "
                                                                  "caso tem vários recursos (emenda 3.1.0)"),
                 "state": enum("read", "absent", "not_read", "withheld"), "value": {},
                 "redaction": obj({"rule_id": c00("rule_id"), "at_source": const(True)}, ["rule_id", "at_source"])},
                ["path", "state"],
                allOf=[{"if": {"properties": {"state": const("read")}}, "then": {"required": ["value"]}},
                       {"if": {"properties": {"state": {"enum": ["absent", "not_read", "withheld"]}}},
                        "then": {"not": {"required": ["value"]}}},
                       {"if": {"properties": {"state": const("withheld")}}, "then": {"required": ["redaction"]}}],
                description="Withheld nunca tem valor nem hash; a redação acontece na origem")
    rb = obj({"readback_id": string(r"^RB-[A-Za-z0-9_\-]+$"), "case_id": string(r"^CASE-[A-Za-z0-9_\-]+$"),
              "group_id": string(r"^(GRP|G)-[A-Za-z0-9_\-]+$"), "claim_id": c00("claim_id"), "side": c00("side"),
              "provider": c00("provider"), "read_at": c00("datetime"), "protocol_version": c00("semver"),
              "fields": arr(field, 1)},
             ["readback_id", "case_id", "group_id", "claim_id", "side", "provider", "read_at", "protocol_version",
              "fields"])
    persistence = {"allOf": [c00("outcome"), {"properties": {"axis": const("persistence")}}]}
    oc = obj({"outcome_id": string(r"^OUT-[A-Za-z0-9_\-]+$"), "case_id": string(r"^CASE-[A-Za-z0-9_\-]+$"),
              "group_id": string(r"^(GRP|G)-[A-Za-z0-9_\-]+$"), "claim_id": c00("claim_id"), "side": c00("side"),
              "outcome": persistence, "evidence_state_before": c00("evidence_state"),
              "evidence_state_after": c00("evidence_state"), "readback_id": string(r"^RB-[A-Za-z0-9_\-]+$"),
              "rule_id": c00("rule_id"), "decided_at": c00("datetime")},
             ["outcome_id", "case_id", "group_id", "claim_id", "side", "outcome", "evidence_state_before",
              "evidence_state_after", "rule_id", "decided_at"])
    return contract_schema(
        "C12", "readback_outcomes", "3.1.0", "leitura e desfecho de persistência", status="amended",
        description="Leitura com redação na origem; desfecho como união discriminada {axis: persistence, value: "
                    "PERSISTED | ALTERED | REJECTED_BY_API | NOT_READABLE | INFRA_ERROR | UNKNOWN}, a mesma do C22 "
                    "(C00 #/$defs/outcome); case_id e group_id; estado de evidência antes e depois.",
        files=[file_kind("readback", "readback.jsonl", "jsonl", "readback", "record"),
               file_kind("outcomes", "outcomes.jsonl", "jsonl", "outcome_record", "record")],
        defs={"readback": rb, "outcome_record": oc}, producers=["DEP-{provider}-A", "DEP-{provider}-B", "JUDGE",
                                                                  "SMOKE-{provider}"],
        rules=["C12-UNION: outcome é a união do C00 com axis = persistence",
               "C12-LADDER: o estado de evidência só sobe com PERSISTED; com os demais desfechos after <= before",
               "C12-READ: desfecho PERSISTED/ALTERED exige readback_id (a leitura que o sustenta)",
               "C12-WITHHELD: campo withheld não tem valor (nem hash)",
               "C12-NODE: (node_id, path) único no registro; sem node_id o caminho é do único recurso do caso "
               "(o prefixo '<nó>.' no path continua aceito)"])


# ------------------------------------------------------------------------------------------------- C13
def c13() -> dict:
    V = "3.1.0"
    hp, hr = header("bo.pins/1", "C13", V, module=True)
    pins = obj({**hp,
                "terraform": obj({"version": c00("semver"), "sha256": c00("sha256")}, ["version", "sha256"]),
                "providers": arr(obj({"provider": c00("provider"),
                                      "source": string(r"^registry\.terraform\.io/[a-z0-9-]+/[a-z0-9-]+$"),
                                      "version": c00("semver"), "shasums_sha256": c00("sha256"),
                                      "schema_sha256": c00("sha256")},
                                     ["provider", "source", "version", "schema_sha256"]), 1)},
               hr + ["terraform", "providers"])
    vp, vr = header("bo.versions/1", "C13", V, module=True)
    versions = obj({**vp, "provider": c00("provider"),
                    "versions": arr(obj({"version": c00("semver"), "released_at": c00("date"),
                                         "schema_sha256": c00("sha256")}, ["version", "released_at"]), 1)},
                   vr + ["provider", "versions"])
    interval = obj({"after": c00("semver"), "until": c00("semver")}, ["after", "until"],
                   description="o evento ocorreu em (after, until]: after = última versão sem a mudança, until = "
                               "primeira com ela")
    ev = obj({"event_id": c00("event_id"), "provider": c00("provider"), "resource_type": c00("resource_type"),
              "event_type": enum("addition", "rename", "removal", "contract_change"), "atom_id": c00("atom_id"),
              "from_atom": c00("atom_id"), "to_atom": c00("atom_id"),
              "change": obj({"field": text(1), "before": {}, "after": {}}, ["field", "before", "after"]),
              "version_interval": interval, "evidence": arr(c00("evidence_item"), 1)},
             ["event_id", "provider", "resource_type", "event_type", "version_interval", "evidence"],
             allOf=[{"if": {"properties": {"event_type": {"enum": ["addition", "removal"]}}},
                     "then": {"required": ["atom_id"]}},
                    {"if": {"properties": {"event_type": const("rename")}}, "then": {"required": ["from_atom", "to_atom"]}},
                    {"if": {"properties": {"event_type": const("contract_change")}},
                     "then": {"required": ["atom_id", "change"]}}])
    utc = string(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$", description="carimbo UTC do Registry, como veio")
    reason = string(r"^(quarter_end:\d{4}Q[1-4]|major_first:\d+|index_first|cutoff:\d{4}-\d{2}-\d{2})$")
    hhp, hhr = header("bo.history_versions/1", "C13", V, module=True)
    sel = obj({"version": c00("semver"), "published_at": utc, "released_at": c00("date"), "reasons": arr(reason, 1,
                                                                                                        unique=True),
               "index_sha256": c00("sha256"), "protocols": arr(string(r"^\d+\.\d+$"), 1),
               "darwin_arm64": boolean(), "linux_amd64": boolean()},
              ["version", "published_at", "released_at", "reasons", "index_sha256", "protocols", "darwin_arm64",
               "linux_amd64"])
    hprov = obj({"provider": c00("provider"), "source": string(r"^registry\.terraform\.io/[a-z0-9-]+/[a-z0-9-]+$"),
                 "pin": c00("semver"),
                 "index_files": obj({"registry_v1": c00("file_ref"), "registry_v2": c00("file_ref")},
                                    ["registry_v1", "registry_v2"]),
                 "versions_doc": local("versions"), "selection": arr(sel, 1),
                 "left_truncation": obj({"at": c00("datetime"), "version_in_force": nullable(c00("semver")),
                                         "major_in_force": nullable(integer(0)), "index_first_version": c00("semver"),
                                         "index_first_published_at": utc},
                                        ["at", "version_in_force", "major_in_force", "index_first_version",
                                         "index_first_published_at"])},
                ["provider", "source", "pin", "index_files", "versions_doc", "selection", "left_truncation"])
    hist = obj({**hhp,
                "cutoff": obj({"date": c00("date"), "timezone": const("America/Recife"), "end_exclusive": c00("datetime"),
                               "rule": text(10)}, ["date", "timezone", "end_exclusive", "rule"]),
                "window": obj({"start": c00("date"), "rule": text(10)}, ["start", "rule"]),
                "index": obj({"path": c00("portable_path"), "sha256": c00("sha256"), "fetched_at": c00("datetime")},
                             ["path", "sha256", "fetched_at"]),
                "providers": arr(hprov, 1), "note": text(3)},
               hhr + ["cutoff", "window", "index", "providers"])
    step = obj({"version": c00("semver"), "state": enum("present", "absent"), "tf_type": {"type": ["string", "array"]},
                "required": boolean(), "optional": boolean(), "computed": boolean(), "force_new": boolean(),
                "sensitive": boolean(), "deprecated": boolean(), "write_only": boolean(), "default": {}},
               ["version", "state"],
               allOf=[{"if": {"properties": {"state": const("absent")}},
                       "then": {"not": {"anyOf": [{"required": [k]} for k in
                                                  ("tf_type", "required", "optional", "computed", "force_new",
                                                   "default")]}}},
                      {"if": {"properties": {"state": const("present")}},
                       "then": {"required": ["tf_type", "required", "optional", "computed"]}}])
    ah = obj({"atom_id": c00("atom_id"), "provider": c00("provider"), "resource_type": c00("resource_type"),
              "path": string(r"^[A-Za-z0-9_]+(\.[A-Za-z0-9_]+)*$"), "history": arr(step, 1),
              "first_seen": nullable(c00("semver")), "last_seen": nullable(c00("semver")),
              "events": arr(c00("event_id"), unique=True)},
             ["atom_id", "provider", "resource_type", "path", "history", "first_seen", "last_seen", "events"],
             description="estado de um átomo em cada versão amostrada (DRIFT); os eventos ficam em events.jsonl")
    return contract_schema(
        "C13", "versions", V, "pins, versões e eventos", status="amended",
        description="Pins do Terraform e dos providers; versões por provider; eventos tipados (adição, renome, remoção, "
                    "mudança de contrato) com o intervalo de versão em que podem ter ocorrido.",
        files=[file_kind("pins", "pins.json", "json", "pins", "document"),
               file_kind("versions", "versions.json", "json", "versions", "document"),
               file_kind("events", "events.jsonl", "jsonl", "event", "record"),
               file_kind("history_versions", "history_versions.json", "json", "history_versions", "document",
                         "lista histórica dos 4 providers (PINS); cada versions_doc é um documento versions completo"),
               file_kind("atom_history", "atom_history.jsonl", "jsonl", "atom_history", "record",
                         "estado de cada átomo por versão amostrada (DRIFT)")],
        defs={"pins": pins, "versions": versions, "event": ev, "history_versions": hist, "history_selection": sel,
              "atom_history": ah},
        producers=["PINS", "HIST-{provider}", "DRIFT", "SCHEMA-POST"],
        rules=["C13-INTERVAL: after < until (ordem semver)", "C13-RENAME: from_atom ≠ to_atom, mesmo provider e tipo",
               "C13-UNIQ: event_id único; versões únicas e em ordem crescente (também dentro de cada versions_doc)",
               "C13-HIST-PIN: a última versão de cada versions_doc é o pin do provider (e o pin do pins.json irmão, "
               "com schema_sha256 igual quando os dois têm)",
               "C13-HIST-SEL: selection e versions_doc listam as mesmas versões, na mesma ordem e com o mesmo released_at",
               "C13-ATOMHIST: history em ordem semver sem repetição; first_seen/last_seen = primeira/última versão "
               "present (nulos se nunca); atom_id = provider:resource_type:path; required e optional se excluem"])


# ------------------------------------------------------------------------------------------------- C14
def realization() -> dict:
    base = _strip(adopted("C14_realization"))
    p = base["properties"]
    p["provider"] = c00("provider")
    p["guards"] = arr({"anyOf": [text(3), C14_GUARDED]})
    p["references"] = arr(obj({"from_artifact": text(1), "to_artifact": text(1), "via_field": text(1)},
                              ["from_artifact", "to_artifact", "via_field"]))
    p["exclusivity_proof"] = obj({"method": enum("guard_intersection_unsat", "documented_exclusive"),
                                  "evidence": arr(c00("evidence_item"), 1)}, ["method", "evidence"])
    base["allOf"].append({"if": {"required": ["alternative_to"], "properties": {"exclusivity": const("ProvenExclusive"),
                                                                                "alternative_to": {"minItems": 1}}},
                          "then": {"required": ["exclusivity_proof"]}})
    base["title"] = "C14 realizations.jsonl (padrão de descritor; proposta do ONTPAT + referências e prova)"
    return base


def c14() -> dict:
    parent = obj({"iri": c00("iri"), "kind": enum("nested", "orthogonal", "conditional"),
                  "axis": text(2), "guard": C10_GUARD}, ["iri", "kind"],
                 allOf=[{"if": {"properties": {"kind": const("orthogonal")}}, "then": {"required": ["axis"]}},
                        {"if": {"properties": {"kind": const("conditional")}}, "then": {"required": ["guard"]}}])
    cls = obj({"class_id": c00("iri"), "label": text(2), "definition": text(10), "parents": arr(parent),
               "model_role": enum("Resource", "ConfigurationDescription", "ObservedState", "Observation", "Other"),
               "identity": obj({"fields": arr(enum("synthetic_account", "provider", "location", "type", "local_key"), 1,
                                               unique=True), "composite": boolean()}, ["fields", "composite"]),
               "status": enum("active", "deprecated", "merged", "split"), "replaced_by": arr(c00("iri")),
               "evidence_state": c00("evidence_state")},
              ["class_id", "label", "definition", "parents", "model_role", "status", "evidence_state"],
              allOf=[{"if": {"properties": {"status": {"enum": ["merged", "split", "deprecated"]}}},
                      "then": {"required": ["replaced_by"]}},
                     {"if": {"properties": {"model_role": const("Resource")}}, "then": {"required": ["identity"]}}])
    dom = {"oneOf": [obj({"kind": const("single"), "class": c00("iri")}, ["kind", "class"]),
                     obj({"kind": const("union"), "classes": arr(c00("iri"), 2, unique=True)}, ["kind", "classes"]),
                     obj({"kind": const("local_restriction"), "class": c00("iri"),
                          "restriction": enum("some", "only", "exactly", "max", "min"), "cardinality": integer(0)},
                         ["kind", "class", "restriction"])],
           "description": "nunca vários rdfs:domain (seriam conjunção): união ou restrição local"}
    prop = obj({"property_id": c00("iri"), "label": text(2), "kind": enum("object", "datatype", "annotation"),
                "domain": dom, "range": c00("iri"), "definition": text(10),
                "value_marks": arr(c00("value_mark"), 1, unique=True),
                "unknown_marks": arr(c00("unknown_mark"), 1, unique=True),
                "status": enum("active", "deprecated", "merged", "split"), "evidence_state": c00("evidence_state")},
               ["property_id", "label", "kind", "domain", "range", "definition", "value_marks", "unknown_marks",
                "status", "evidence_state"])
    return contract_schema(
        "C14", "ontology_tables", "3.0.0", "classes, propriedades, realizações e TTL", status="changed_v3",
        description="Classe com vários pais (aninhados, ortogonais declarados, condicionais com guarda). Propriedade com "
                    "domínio como união ou restrição local (nunca vários rdfs:domain). Realização pelo padrão de "
                    "descritor (sem punning): recursos criados, referências, condições, projeções, perdas, realizações "
                    "alternativas guardadas com prova de exclusividade ou Ambiguous; sem injetividade global. Modelo "
                    "Resource / ConfigurationDescription / ObservedState / Observation; identidade composta; marcas "
                    "configurado/inferido/default/observado e desconhecido/ausente/não lido/retido.",
        files=[file_kind("classes", "classes.jsonl", "jsonl", "class", "record"),
               file_kind("properties", "properties.jsonl", "jsonl", "property", "record"),
               file_kind("realizations", "realizations*.jsonl", "jsonl", "realization", "record"),
               file_kind("ttl", "*.ttl", "turtle", None, "graph",
                         "Turtle que parseia, sem punning e sem propriedade com mais de um rdfs:domain")],
        defs={"class": cls, "property": prop, "realization": realization()},
        adopted=["results/ONTPAT/C14_proposta/realization_row.schema.json"],
        producers=["ONTPAT", "CLASS", "PROP", "OWL", "AXIOMS", "NAMING", "REPAIR", "SHACL", "CQRUN", "BASELINE-ADAPT"],
        rules=["C14-PARENTS: ortogonal declara o eixo; condicional tem guarda",
               "C14-DOMAIN: domínio é single, union (>= 2) ou restrição local; no TTL nenhuma propriedade tem dois "
               "rdfs:domain",
               "C14-PUN: nenhum IRI do TTL é ao mesmo tempo classe/propriedade e indivíduo (padrão de descritor)",
               "C14-ALT: alternativas mútuas, mesmo descritor e provedor, mesma exclusividade; ProvenExclusive entre "
               "alternativas exige prova",
               "C14-LOSS: fidelidade com perda declarada ou parcial exige losses",
               "C14-UNIQ: class_id, property_id e realization_id únicos"])


SPECS = {"C09": c09, "C10": c10, "C11": c11, "C12": c12, "C13": c13, "C14": c14}
