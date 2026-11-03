"""Política do desconhecido (PREREG §4) e classe de desfecho por métrica.

Toda unidade termina em exatamente uma classe:
  success  sucesso nos dois limites
  failure  falha nos dois limites
  bounded  falha no limite inferior, sucesso no superior; sai do denominador de est

A tabela de cada eixo vem do PREREG §4 (enumerações do C00/C12/C22/C23). Cada métrica do metrics_spec.yaml
tem a sua tabela (BINDINGS em spec.py): os códigos bounded de cada uma são exatamente os que a cláusula
"Desconhecido" da definição nomeia (o teste confere contra o texto do pré-registro).

Uma unidade com vários desfechos (uma decisão com vários valores, um grafo com várias decisões e referências,
um recurso com vários campos) combina por `combine`: qualquer falha definida reprova nos dois limites; senão,
qualquer desconhecido deixa a unidade no intervalo; senão é sucesso. Unidade sem desfecho é erro, nunca
sucesso por vacuidade.
"""
from __future__ import annotations

SUCCESS, FAILURE, BOUNDED = "success", "failure", "bounded"
CLASSES = (SUCCESS, FAILURE, BOUNDED)

# enumerações dos contratos (C00 block_code, C23 result, C12 persistence, C22 behavior)
BLOCK_CODES = ("OUT_OF_SUBSET", "UNKNOWN_SYMBOLIC_INPUT", "TRANSFORM_OUT_OF_DOMAIN", "NO_UNIT", "NO_REALIZATION",
               "SHACL_VIOLATION", "CONDITION_FALSE", "CONDITION_INDETERMINATE", "RELATED_ONLY", "REPAIR_EXCLUDED",
               "AMBIGUOUS_TARGET", "UNPROVEN", "INFRA_ERROR", "UNKNOWN_INPUT", "REFUTED_BY_RULE")
TRACE_RESULTS = ("carried", "omitted", "blocked")
PERSISTENCE_OUTCOMES = ("PERSISTED", "ALTERED", "REJECTED_BY_API", "NOT_READABLE", "INFRA_ERROR", "UNKNOWN")
BEHAVIOR_OUTCOMES = ("OBSERVATIONS_MATCH_UNDER_PROTOCOL", "OBSERVATIONS_DIFFER_UNDER_PROTOCOL",
                     "NOT_OBSERVED_IN_WINDOW", "PROTOCOL_UNSUPPORTED", "INFRA_ERROR", "UNKNOWN")

# códigos próprios da biblioteca para desfechos que nenhum contrato enumera (lifting, transporte, unidade
# completa, grafo, CQ, auditoria de ausências). Cada um tem classe fixa; nenhum é decidido depois do desfecho.
REPR_CODES = {"REPRESENTED": SUCCESS, "UNGLOSSED": FAILURE, "NEW_CLASS_REQUIRED": FAILURE,
              "NOT_REPRESENTED": FAILURE}
TRANSPORT_CODES = {"TRANSPORTS": SUCCESS, "PREDICATE_FALSE": FAILURE, "FUNCTION_UNDEFINED": FAILURE,
                   "EVIDENCE_BELOW_DOC_SUPPORTED": FAILURE, "KIND_UNKNOWN": FAILURE, "CONDITION_FALSE": FAILURE,
                   "RELATED_ONLY": FAILURE, "REPAIR_EXCLUDED": FAILURE, "REFUTED_BY_RULE": FAILURE,
                   "UNPROVEN": FAILURE, "CONTESTED": FAILURE, "AMBIGUOUS": FAILURE}
UNIT_CODES = {"COMPLETE": SUCCESS, "DEPENDENCY_OPEN": FAILURE, "REQUIRED_MISSING": FAILURE,
              "VALIDATE_FAILED": FAILURE}
GRAPH_REF_CODES = {"REF_SAME_TARGET": SUCCESS, "REF_OTHER_TARGET": FAILURE, "REF_DROPPED": FAILURE}
CQ_CODES = {"CORRECT": SUCCESS, "WRONG": FAILURE, "UNKNOWN_WHEN_DEFINED": FAILURE, "TIMEOUT": BOUNDED}
NONE_AUDIT_CODES = {"FALSE_NONE": SUCCESS, "TRUE_NONE": FAILURE, "UNDECIDED": BOUNDED}

# códigos desconhecidos por eixo (PREREG §4, cláusula Desconhecido de cada métrica)
UNK_REPR = frozenset({"UNKNOWN_SYMBOLIC_INPUT", "UNKNOWN_INPUT"})
UNK_TRANS_SCHEMA = frozenset({"CONDITION_INDETERMINATE"})
UNK_TRANS_OBS = frozenset({"CONDITION_INDETERMINATE", "UNKNOWN_SYMBOLIC_INPUT"})
UNK_OP = frozenset({"UNKNOWN_SYMBOLIC_INPUT", "UNKNOWN_INPUT", "CONDITION_INDETERMINATE", "INFRA_ERROR"})
UNK_UNIT = frozenset({"UNKNOWN_SYMBOLIC_INPUT", "CONDITION_INDETERMINATE", "INFRA_ERROR"})
UNK_PERS = frozenset({"NOT_READABLE", "INFRA_ERROR", "UNKNOWN"})
UNK_BEHAV = frozenset({"NOT_OBSERVED_IN_WINDOW", "PROTOCOL_UNSUPPORTED", "INFRA_ERROR", "UNKNOWN"})
UNK_CQ = frozenset({"INFRA_ERROR", "TIMEOUT", "UNKNOWN_INPUT", "UNKNOWN_SYMBOLIC_INPUT"})


class OutcomeError(ValueError):
    """Código desconhecido para a tabela da métrica, ou unidade sem desfecho."""


def _table(success: dict, unknown: frozenset, extra_fail: tuple = ()) -> dict:
    t = dict(success)
    for c in extra_fail:
        t.setdefault(c, FAILURE)
    for c in unknown:
        t[c] = BOUNDED
    return t


def operational_table(unknown: frozenset = UNK_OP) -> dict:
    """carried = sucesso; omitted e todo código de bloqueio fora de `unknown` = falha."""
    return _table({"carried": SUCCESS, "omitted": FAILURE}, unknown, BLOCK_CODES)


def representability_table() -> dict:
    return _table(REPR_CODES, UNK_REPR)


def transport_table(observed: bool) -> dict:
    return _table(TRANSPORT_CODES, UNK_TRANS_OBS if observed else UNK_TRANS_SCHEMA)


def unit_table() -> dict:
    # UNKNOWN_INPUT é falha definida na unidade completa (a unidade não é completa sem o valor)
    return _table(UNIT_CODES, UNK_UNIT, BLOCK_CODES + ("omitted",)) | {"carried": SUCCESS}


def graph_table() -> dict:
    return _table(GRAPH_REF_CODES, UNK_OP, BLOCK_CODES + ("omitted",)) | {"carried": SUCCESS}


def persistence_table() -> dict:
    return _table({"PERSISTED": SUCCESS, "ALTERED": FAILURE, "REJECTED_BY_API": FAILURE}, UNK_PERS)


def behavior_table() -> dict:
    return _table({"OBSERVATIONS_MATCH_UNDER_PROTOCOL": SUCCESS, "OBSERVATIONS_DIFFER_UNDER_PROTOCOL": FAILURE},
                  UNK_BEHAV)


def cq_table() -> dict:
    return _table(CQ_CODES, UNK_CQ)


def none_audit_table() -> dict:
    return dict(NONE_AUDIT_CODES)


def classify(code: str, table: dict) -> str:
    try:
        return table[code]
    except KeyError:
        raise OutcomeError(f"código {code!r} fora da tabela da métrica") from None


def combine(classes) -> str:
    cls = list(classes)
    if not cls:
        raise OutcomeError("unidade sem desfecho: não vira sucesso por vacuidade")
    for c in cls:
        if c not in CLASSES:
            raise OutcomeError(f"classe {c!r} inválida")
    if FAILURE in cls:
        return FAILURE
    if BOUNDED in cls:
        return BOUNDED
    return SUCCESS


def classify_all(codes, table: dict) -> str:
    return combine(classify(c, table) for c in codes)
