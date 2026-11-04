"""Avalia o texto de pass_rule do prereg/pilot_exit.yaml TAL COMO ESTÁ ESCRITO, sem reescrever a regra.

Gramática aceita (a do arquivo pré-registrado): nomes, inteiros, True/False, ==, !=, <, <=, >, >=, and, or, not e
parênteses. Nome sem medida é erro (MissingMeasure): critério sem medida não passa por omissão.
"""
from __future__ import annotations

import ast
import operator

_CMP = {ast.Eq: operator.eq, ast.NotEq: operator.ne, ast.Lt: operator.lt, ast.LtE: operator.le,
        ast.Gt: operator.gt, ast.GtE: operator.ge}


class RuleError(ValueError):
    pass


class MissingMeasure(RuleError):
    pass


def names(rule: str) -> list[str]:
    return sorted({n.id for n in ast.walk(_parse(rule)) if isinstance(n, ast.Name)})


def _parse(rule: str) -> ast.AST:
    try:
        return ast.parse(rule, mode="eval").body
    except SyntaxError as e:
        raise RuleError(f"regra ilegível: {rule!r}: {e.msg}")


def evaluate(rule: str, measures: dict) -> bool:
    def ev(n):
        if isinstance(n, ast.BoolOp):
            vals = (ev(v) for v in n.values)
            return all(vals) if isinstance(n.op, ast.And) else any(vals)
        if isinstance(n, ast.UnaryOp) and isinstance(n.op, ast.Not):
            return not ev(n.operand)
        if isinstance(n, ast.Compare):
            left = ev(n.left)
            for op, right in zip(n.ops, n.comparators):
                if type(op) not in _CMP:
                    raise RuleError(f"operador não aceito: {type(op).__name__}")
                r = ev(right)
                if left is None or r is None:
                    raise MissingMeasure("medida nula numa comparação")
                if not _CMP[type(op)](left, r):
                    return False
                left = r
            return True
        if isinstance(n, ast.Name):
            if n.id not in measures:
                raise MissingMeasure(f"medida ausente: {n.id}")
            v = measures[n.id]
            if v is None:
                raise MissingMeasure(f"medida nula: {n.id}")
            return v
        if isinstance(n, ast.Constant) and isinstance(n.value, (bool, int)):
            return n.value
        raise RuleError(f"construção não aceita na regra: {type(n).__name__}")
    return bool(ev(_parse(rule)))
