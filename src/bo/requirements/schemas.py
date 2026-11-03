"""JSON Schema (draft 2020-12) proposto para o C24 1.0.0, um por arquivo JSONL (um registro por linha).

O CONTRACTS é o dono de $BO_REPO/contracts/C24_requirements.schema.json; estes schemas são a proposta do
produtor, gravados em results/REQUIREMENTS/C24_proposta/ pelo build. As regras que um schema não exprime
(polaridade x checagem, UNKNOWN em fixture incompleta, referências cruzadas, termos declarados) ficam em
model.validate_*.
"""

from . import model, terms

_TXT = {"type": "string", "minLength": 10}
_OBJ_IDS = {"type": "array", "minItems": 1, "items": {"type": "string", "pattern": model.OBJECTION_RE.pattern}}
_MODS = {"type": "array", "items": {"type": "string", "pattern": model.MODULE_RE.pattern}}
_HEAD = {
    "schema": {"type": "string"},
    "contract": {"const": "C24"},
    "contract_version": {"const": "1.0.0"},
}

FIXTURE = {
    "type": "object",
    "required": ["fixture_id", "summary", "entities", "relations", "attributes", "read"],
    "additionalProperties": False,
    "properties": {
        "fixture_id": {"type": "string", "pattern": model.FX_ID_RE.pattern},
        "summary": {"type": "string", "minLength": 5},
        "entities": {"type": "array", "minItems": 1, "items": {
            "type": "object", "required": ["id", "kind"], "additionalProperties": False,
            "properties": {"id": {"type": "string", "pattern": model.LOCAL_ID_RE.pattern},
                           "kind": {"enum": sorted(terms.KINDS)},
                           "also_kinds": {"type": "array", "minItems": 1, "items": {"enum": sorted(terms.KINDS)}}}}},
        "relations": {"type": "array", "items": {
            "type": "object", "required": ["from", "rel", "to"], "additionalProperties": False,
            "properties": {"from": {"type": "string"}, "rel": {"enum": sorted(terms.RELATIONS)},
                           "to": {"type": "string"}}}},
        "attributes": {"type": "array", "items": {
            "type": "object", "required": ["of", "attr", "value"], "additionalProperties": False,
            "properties": {"of": {"type": "string"}, "attr": {"enum": sorted(terms.ATTRIBUTES)},
                           "value": {"type": ["string", "integer", "boolean"]}}}},
        "read": {"type": "object", "required": ["completeness", "not_read", "withheld"], "additionalProperties": False,
                 "properties": {
                     "completeness": {"enum": list(terms.COMPLETENESS)},
                     "not_read": {"type": "array", "items": {
                         "type": "object", "required": ["of", "what"], "additionalProperties": False,
                         "properties": {"of": {"type": "string"}, "what": {"enum": sorted(terms.NOT_READ_WHAT)}}}},
                     "withheld": {"type": "array", "items": {
                         "type": "object", "required": ["of", "attr"], "additionalProperties": False,
                         "properties": {"of": {"type": "string"}, "attr": {"type": "string"}}}}}},
    },
}

REQUIREMENT = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "C24 requirements.jsonl (registro)",
    "type": "object",
    "additionalProperties": False,
    "required": ["schema", "contract", "contract_version", "req_id", "area", "priority", "statement", "rationale",
                 "answers", "consumers"],
    "properties": {**_HEAD, "schema": {"const": model.SCHEMAS["requirements"]},
                   "req_id": {"type": "string", "pattern": model.REQ_ID_RE.pattern},
                   "area": {"enum": sorted(model.AREAS)},
                   "priority": {"enum": ["MUST", "SHOULD"]},
                   "statement": {"type": "string", "minLength": 20},
                   "rationale": {"type": "string", "minLength": 20},
                   "answers": _OBJ_IDS, "consumers": _MODS},
}

_EXPECTED = {"type": "object", "required": ["value", "why"], "additionalProperties": False,
             "properties": {"value": {"type": ["string", "integer", "boolean"]}, "why": _TXT,
                            "code": {"enum": list(model.CODES)}}}

COMMITMENT = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "C24 commitments.jsonl (registro)",
    "type": "object",
    "additionalProperties": False,
    "required": ["schema", "contract", "contract_version", "commitment_id", "case", "polarity", "check", "statement",
                 "fixtures", "expected_answer", "protects", "layer", "upper_axes", "requirement_ids", "answers",
                 "provider_grounding", "consumers"],
    "properties": {
        **_HEAD, "schema": {"const": model.SCHEMAS["commitments"]},
        "commitment_id": {"type": "string", "pattern": model.CMT_ID_RE.pattern},
        "case": {"enum": list(model.ALL_CASES)},
        "polarity": {"enum": list(model.POLARITIES)},
        "check": {"type": "object", "required": ["kind", "assertion"], "additionalProperties": False,
                  "properties": {"kind": {"enum": sorted({k for v in model.CHECKS.values() for k in v})},
                                 "assertion": _TXT}},
        "statement": {"type": "string", "minLength": 20},
        "fixtures": {"type": "array", "minItems": 1, "items": FIXTURE},
        "expected_answer": _EXPECTED,
        "protects": _TXT,
        "layer": {"enum": list(model.LAYERS)},
        "upper_axes": {"type": "array", "items": {"enum": list(model.UPPER_AXES)}},
        "requirement_ids": {"type": "array", "minItems": 1, "items": {"type": "string", "pattern": model.REQ_ID_RE.pattern}},
        "answers": _OBJ_IDS,
        "provider_grounding": {"type": "array", "items": {
            "type": "object", "required": ["provider", "note", "evidence_state", "verify_in"], "additionalProperties": False,
            "properties": {"provider": {"enum": list(model.PROVIDERS)}, "note": _TXT,
                           "evidence_state": {"enum": list(model.EVIDENCE_STATES)}, "verify_in": {"type": "string"}}}},
        "consumers": _MODS,
    },
    "allOf": [
        {"if": {"properties": {"polarity": {"const": "positive"}}},
         "then": {"properties": {"check": {"properties": {"kind": {"enum": list(model.CHECKS["positive"])}}}}}},
        {"if": {"properties": {"polarity": {"const": "negative"}}},
         "then": {"properties": {"check": {"properties": {"kind": {"enum": list(model.CHECKS["negative"])}}}}}},
        {"if": {"properties": {"polarity": {"const": "unknown"}}},
         "then": {"properties": {"check": {"properties": {"kind": {"const": "unknown"}}},
                                 "expected_answer": {"properties": {"value": {"const": "UNKNOWN"}}}}}},
    ],
}

_SIDE = {"type": "object", "required": ["fixture", "expected"], "additionalProperties": False,
         "properties": {"fixture": FIXTURE, "expected": _EXPECTED}}

CQ_SPEC = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "C24 cq_spec.jsonl (registro)",
    "type": "object",
    "additionalProperties": False,
    "required": ["schema", "contract", "contract_version", "cq_id", "family", "question", "criterion", "answer_form",
                 "fixtures", "closed_world", "applicability", "reasoning_needs", "requirement_ids", "commitment_ids",
                 "cases", "answers"],
    "properties": {
        **_HEAD, "schema": {"const": model.SCHEMAS["cq_spec"]},
        "cq_id": {"type": "string", "pattern": model.CQ_ID_RE.pattern},
        "family": {"enum": list(model.FAMILIES)},
        "question": {"type": "string", "minLength": 15},
        "criterion": {"type": "string", "minLength": 15},
        "answer_form": {"enum": list(model.ANSWER_FORMS)},
        "fixtures": {"type": "object", "required": ["conforming", "nonconforming", "incomplete"],
                     "additionalProperties": False,
                     "properties": {"conforming": _SIDE, "nonconforming": _SIDE,
                                    "incomplete": {**_SIDE, "properties": {
                                        "fixture": FIXTURE,
                                        "expected": {**_EXPECTED, "properties": {
                                            **_EXPECTED["properties"], "value": {"const": "UNKNOWN"}}}}}}},
        "closed_world": {"type": "object", "required": ["uses_negation", "negation_requires_complete_read"],
                         "additionalProperties": False,
                         "properties": {"uses_negation": {"type": "boolean"},
                                        "negation_requires_complete_read": {"const": True}}},
        "applicability": {"type": "string", "minLength": 15},
        "reasoning_needs": {"type": "string", "minLength": 15},
        "requirement_ids": {"type": "array", "minItems": 1, "items": {"type": "string", "pattern": model.REQ_ID_RE.pattern}},
        "commitment_ids": {"type": "array", "items": {"type": "string", "pattern": model.CMT_ID_RE.pattern}},
        "cases": {"type": "array", "items": {"enum": list(model.ADVERSARIAL_CASES)}},
        "answers": _OBJ_IDS,
    },
}

BY_KIND = {"requirements": REQUIREMENT, "commitments": COMMITMENT, "cq_spec": CQ_SPEC}
