"""Execução dos exemplos declarados no registro (positivos, de erro e de ida e volta pela inversa parcial)."""

from __future__ import annotations

from . import comparators as CMP
from . import registry as R
from .errors import TransformError


def _same(a, b, dt: str | None = None) -> bool:
    """Igualdade de valor; duração compara no espaço de valores do XSD (PT90S = PT1M30S)."""
    from . import units as U
    if dt == "duration" and isinstance(a, str) and isinstance(b, str):
        try:
            x, y = U.parse_duration(a), U.parse_duration(b)
            return (x.months, x.seconds) == (y.months, y.seconds)
        except TransformError:
            return a == b
    return CMP.value_equal(a, b)


def same_input(t, a, b) -> bool:
    """A volta pela inversa confere com a entrada, porta a porta, pelo datatype declarado."""
    if isinstance(t, R.Scalar):
        return _same(a, b, t.domain["datatype"])
    if not (isinstance(a, dict) and isinstance(b, dict)):
        return False
    if t.inv_inputs is not None:
        # a inversa devolve só as portas de dados (fn e params são da instância, não do valor)
        b = {k: b[k] for k in a if k in b}
    if set(a) != set(b):
        return False
    types = {n: dt for n, dt, _ in t.inputs}
    coll = dict(t.collection)
    for k in a:
        if coll.get(k) == "set" and isinstance(a[k], list) and isinstance(b[k], list):
            if {CMP._canon(x) for x in a[k]} != {CMP._canon(x) for x in b[k]} or len(a[k]) != len(b[k]):
                return False
        elif not _same(a[k], b[k], types.get(k)):
            return False
    return True


def run_example(t, ex) -> tuple[bool, str]:
    """(passou, detalhe)."""
    scalar = isinstance(t, R.Scalar)
    try:
        got = (R.apply_scalar(t.name, ex.value, ex.params, ex.ctx) if scalar
               else R.apply_combinator(t.name, ex.value, ex.ctx))
    except TransformError as e:
        if ex.err is None:
            return False, f"erro inesperado {e}"
        if e.code != ex.err:
            return False, f"erro {e.code}, esperado {ex.err}: {e}"
        return True, f"erro {e.code} como declarado"
    if ex.err is not None:
        return False, f"esperado erro {ex.err}, saiu {got!r}"
    if ex.out is not R._NO and not _same(got, ex.out):
        return False, f"saída {got!r}, esperado {ex.out!r}"
    if ex.roundtrip:
        inv = R.invert(t.name, ex.params, ex.value, got)
        if inv is None:
            return False, "ida e volta pedida, mas a instância não tem inversa"
        name, p = inv
        try:
            back = R.apply_scalar(name, got, p, ex.ctx) if scalar else R.apply_combinator(name, p, ex.ctx)
        except TransformError as e:
            return False, f"inversa {name} falhou: {e}"
        if not same_input(t, back, ex.value):
            return False, f"ida e volta: {ex.value!r} -> {got!r} -> {back!r}"
        return True, f"ida e volta por {name}"
    return True, "saída confere"


def run_all() -> list[dict]:
    rows = []
    for t in list(R.SCALARS) + list(R.COMBINATORS):
        for i, ex in enumerate(t.examples):
            ok, why = run_example(t, ex)
            kind = "error" if ex.err else "roundtrip" if ex.roundtrip else "positive"
            rows.append({"name": t.name, "i": i, "kind": kind, "ok": ok, "detail": why})
    return rows
