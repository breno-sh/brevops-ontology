"""Predicado de pertença ao subconjunto (obrigação de broad/narrow): linguagem fechada e executável.

membership_predicate = {"subset": "subject" | "object", "expr": EXPR, "tests": {"members": [...], "non_members": [...]}}
O predicado é a função característica do lado MAIS ESTREITO, avaliada sobre valores do lado MAIS AMPLO, no
espaço de valores do lado mais amplo (depois da normalização declarada). Orientação: em 'a broadMatch b' o
subconjunto é o sujeito (a ⊂ b); em 'a narrowMatch b', o objeto (b ⊂ a). Texto livre não é predicado.

EXPR := {"op": "in", "values": [...]} | {"op": "eq", "value": v} | {"op": "range", "min"?: n, "max"?: n}
      | {"op": "and"|"or", "args": [EXPR, ...]} | {"op": "not", "arg": EXPR}
      | {"op": "field", "name": componente, "pred": EXPR}     (valor de tupla)
"""

from __future__ import annotations

from .valuetypes import frac, _is_num

PRED_OPS = ("in", "eq", "range", "and", "or", "not", "field")


class PredicateError(ValueError):
    pass


def check(expr) -> None:
    if not isinstance(expr, dict) or expr.get("op") not in PRED_OPS:
        raise PredicateError(f"predicado não executável (operador fora de {PRED_OPS}): {expr!r}")
    op = expr["op"]
    need = {"in": {"values"}, "eq": {"value"}, "range": set(), "and": {"args"}, "or": {"args"}, "not": {"arg"},
            "field": {"name", "pred"}}[op]
    if not need <= set(expr):
        raise PredicateError(f"{op} exige {sorted(need)}")
    if op == "range":
        if not ({"min", "max"} & set(expr)):
            raise PredicateError("range exige min ou max")
        for k in ("min", "max"):
            if k in expr:
                frac(expr[k])
    if op == "in" and (not isinstance(expr["values"], list) or not expr["values"]):
        raise PredicateError("in exige lista não vazia")
    if op in ("and", "or"):
        if not isinstance(expr["args"], list) or not expr["args"]:
            raise PredicateError(f"{op} exige argumentos")
        for a in expr["args"]:
            check(a)
    if op == "not":
        check(expr["arg"])
    if op == "field":
        check(expr["pred"])


def evaluate(expr: dict, v) -> bool:
    op = expr["op"]
    if op == "in":
        return any(_eq(v, x) for x in expr["values"])
    if op == "eq":
        return _eq(v, expr["value"])
    if op == "range":
        if not _is_num(v):
            return False
        x = frac(v)
        return ("min" not in expr or x >= frac(expr["min"])) and ("max" not in expr or x <= frac(expr["max"]))
    if op == "and":
        return all(evaluate(a, v) for a in expr["args"])
    if op == "or":
        return any(evaluate(a, v) for a in expr["args"])
    if op == "not":
        return not evaluate(expr["arg"], v)
    if op == "field":
        return isinstance(v, dict) and expr["name"] in v and evaluate(expr["pred"], v[expr["name"]])
    raise PredicateError(op)


def _eq(a, b) -> bool:
    if isinstance(a, bool) or isinstance(b, bool):
        return a is b or (isinstance(a, bool) and isinstance(b, bool) and a == b)
    if _is_num(a) and _is_num(b) and not (isinstance(a, str) and isinstance(b, str)):
        return frac(a) == frac(b)
    return a == b


def conj(p1: dict, p2: dict) -> dict:
    return {"op": "and", "args": [p1, p2]}
