"""JSON Schema (draft 2020-12) propostos pelo SEMANTICS para o C09 e a parte do C10 que é dele.
O dono dos schemas publicados é o CONTRACTS; estes vão em results/SEMANTICS/C09_proposta e C10_proposta."""

from __future__ import annotations

from . import guards as G
from . import predicates as PR
from . import transforms as TR
from .valuetypes import DATATYPES
from .vocab import (EVIDENCE_STATES, FIDELITIES, LOSS_KINDS, SEMANTIC_RELATIONS, SKOS_PREDICATE,
                    VALUE_DOMAIN_RELATIONS)

D = "https://json-schema.org/draft/2020-12/schema"

VALUE_TYPE = {
    "type": "object", "required": ["datatype"],
    "properties": {
        "datatype": {"enum": list(DATATYPES)},
        "quantity_kind": {"type": "string", "description": "IRI QUDT (quantitykind:...) | NOT_APPLICABLE | UNKNOWN"},
        "unit": {"type": "string", "description": "IRI QUDT (unit:...) | NOT_APPLICABLE | UNKNOWN"},
        "rate_window": {"type": ["string", "null"], "description": "xsd:duration fixa (parte do tipo, N4)"},
        "byte_convention": {"enum": ["SI", "IEC", None]},
        "enum": {"type": "array"}, "range": {"type": "object"}, "step": {"type": ["string", "integer"]},
        "sentinels": {"type": "object"}, "components": {"type": "array"}, "required": {"type": "boolean"}},
}

GUARD = {
    "$schema": D, "$id": "https://w3id.org/brevops/schema/C10/guard.schema.json",
    "title": "Guarda tipada (conjunção de átomos)", "type": "object", "required": ["all"],
    "additionalProperties": False,
    "properties": {
        "all": {"type": "array", "items": {
            "type": "object", "required": ["term", "op", "value"], "additionalProperties": False,
            "properties": {"term": {"type": "string", "pattern": r"^(subject|object)\.[A-Za-z0-9_.\[\]]+$"},
                           "op": {"enum": list(G.OPS)}, "value": {}}}},
        "term_types": {"type": "object", "additionalProperties": {"type": "object", "required": ["datatype"],
                                                                   "properties": {"datatype": {"enum": list(G.SCALAR_TYPES)}}}},
        "kind_disjoint": {"type": "array", "items": {"type": "array", "minItems": 2, "maxItems": 2,
                                                       "items": {"type": "string"}}}},
}

FN = {"type": "object", "required": ["name"], "properties": {"name": {"enum": sorted(TR.REGISTRY)},
                                                               "params": {"type": "object"}}}

C09_RECORD = {
    "$schema": D, "$id": "https://w3id.org/brevops/schema/C09/correspondence.schema.json",
    "title": "C09 3.0.0: alegação de correspondência (linha SSSOM com as colunas próprias já decodificadas)",
    "type": "object",
    "required": ["claim_id", "claim_version_id", "event_id", "subject_id", "predicate_id", "object_id",
                 "mapping_justification", "semantic_relation", "value_domain_relation", "transport_fidelity",
                 "guard", "evidence_state", "proof", "subject_concept", "object_concept"],
    "properties": {
        "claim_id": {"type": "string", "minLength": 1}, "claim_version_id": {"type": "string"},
        "event_id": {"type": "string"},
        "subject_id": {"type": "string"}, "object_id": {"type": "string"},
        "predicate_id": {"enum": list(SKOS_PREDICATE.values())},
        "mapping_justification": {"type": "string", "pattern": "^semapv:"},
        "semantic_relation": {"enum": list(SEMANTIC_RELATIONS)},
        "value_domain_relation": {"type": "object", "required": ["relation", "orientation"],
                                  "properties": {"relation": {"enum": list(VALUE_DOMAIN_RELATIONS)},
                                                 "orientation": {"const": "subject_to_object"}}},
        "transport_fidelity": {"enum": list(FIDELITIES)},
        "guard": {"$ref": "#/$defs/guard"},
        "translation_fn": {"oneOf": [{"type": "null"}, FN, {"type": "array", "items": FN}]},
        "loss_contract": {"type": "array", "items": {"type": "object", "required": ["kind"],
                                                     "properties": {"kind": {"enum": list(LOSS_KINDS)}}}},
        "membership_predicate": {"type": "object", "required": ["subset", "expr", "tests"],
                                 "properties": {"subset": {"enum": ["subject", "object"]},
                                                "expr": {"type": "object", "properties": {"op": {"enum": list(PR.PRED_OPS)}}},
                                                "tests": {"type": "object", "required": ["members", "non_members"]}}},
        "fixed_default": {"type": "object", "required": ["kind", "value", "context", "evidence"],
                          "properties": {"kind": {"enum": ["fixed", "default"]},
                                         "evidence": {"type": "object", "required": ["date", "source"]}}},
        "projection": {"type": "array"}, "bo_group_id": {"type": "string"}, "group": {"type": "object"},
        "proof": {"type": "object", "required": ["type"],
                  "properties": {"type": {"type": "string"}, "evidence": {"type": "array"}, "tests": {"type": "array"}}},
        "evidence_state": {"enum": list(EVIDENCE_STATES)},
        "basis": {"enum": ["direct", "shared_concept", "composition", "inverse"]},
        "anchors": {"type": "array"},
        "subject_concept": {"type": "string"}, "object_concept": {"type": "string"},
        "subject_value_type": VALUE_TYPE, "object_value_type": VALUE_TYPE,
        "preserved_observations": {"type": "array", "items": {"type": "string"}},
    },
    "$defs": {"guard": {k: v for k, v in GUARD.items() if k not in ("$schema", "$id")}},
}

COMPOSITION_TABLE = {
    "$schema": D, "$id": "https://w3id.org/brevops/schema/C10/composition_table.schema.json",
    "title": "C10 3.0.0: tabela formal de composição", "type": "object",
    "required": ["schema", "contract", "contract_version", "semantic_relation", "value_domain_relation",
                 "transport_fidelity", "guard", "domain", "evidence", "verdict", "closure"],
    "properties": {
        "schema": {"const": "bo.composition_table/1"}, "contract": {"const": "C10"},
        "semantic_relation": {"type": "array", "minItems": 25, "maxItems": 25, "items": {
            "type": "object", "required": ["r1", "r2", "result", "derivation", "why"],
            "properties": {"r1": {"enum": list(SEMANTIC_RELATIONS)}, "r2": {"enum": list(SEMANTIC_RELATIONS)},
                           "result": {"enum": list(SEMANTIC_RELATIONS) + [None]},
                           "derivation": {"enum": ["rcc5", "policy"]}}}},
        "value_domain_relation": {"type": "object", "required": ["rows"],
                                  "properties": {"rows": {"type": "array", "minItems": 25, "maxItems": 25}}},
        "transport_fidelity": {"type": "object", "required": ["rows"],
                               "properties": {"rows": {"type": "array", "minItems": 16, "maxItems": 16}}},
    },
}

COUNTEREXAMPLE = {
    "$schema": D, "$id": "https://w3id.org/brevops/schema/SEMANTICS/counterexample.schema.json",
    "title": "Contraexemplo por regra (par mínimo)", "type": "object",
    "required": ["ce_id", "rule_id", "kind", "why", "input", "control", "mutation"],
    "properties": {"ce_id": {"type": "string", "pattern": "^CE-"}, "rule_id": {"type": "string"},
                   "kind": {"enum": ["claim", "set", "trace", "compose", "hub", "projections", "alternatives", "group"]},
                   "mutation": {"enum": ["strict", "rule_only"]}, "why": {"type": "string", "minLength": 10}},
}

BY_KIND = {"c09": C09_RECORD, "guard": GUARD, "composition_table": COMPOSITION_TABLE, "counterexample": COUNTEREXAMPLE}


def grammar_document() -> dict:
    """Proposta ao TRANSFORMS para transforms/conditions.grammar.json (o SEMANTICS fixa a semântica)."""
    return {"schema": "bo.conditions_grammar/1", "contract": "C10", "contract_version": "3.0.0",
            "form": "conjunção de átomos <term, op, value>; sem negação nem disjunção (decidível termo a termo)",
            "roles": list(G.ROLES), "operators": {
                "eq": "termo vizinho tipado (term_types) = valor", "in": "termo vizinho ∈ lista",
                "present": "termo presente (true) ou sabidamente ausente (false)",
                "refers_to_kind": "a referência aponta para unidade do tipo; tipos distintos só incompatíveis com kind_disjoint",
                "region_in": "<papel>.region ∈ lista", "edition_in": "<papel>.edition ∈ lista",
                "version_range": "<papel>.provider_version em [min, max_exclusive)"},
            "satisfiability": "SAT (com testemunha) | UNSAT | UNKNOWN; UNKNOWN só por tipos de referência sem disjunção declarada",
            "evaluation": "TRUE | FALSE | INDETERMINATE (termo não lido, NOT_READ ou simbólico)",
            "composition": "papéis renomeados (n0 sujeito, n1 meio, n2 objeto), conjunção, eliminação existencial de n1",
            "schema_ref": "guard.schema.json"}
