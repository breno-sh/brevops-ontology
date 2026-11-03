"""Comparadores da leitura de volta (C11 'comparator'), com tolerância declarada.

Cada comparador decide se o valor LIDO DE VOLTA (observed) confere com o valor PLANEJADO (expected). São
combinadores de tupla no registro (expected, observed[, tolerance] -> match) e têm os nomes do C11:

  exact              igualdade de valor JSON: número por valor exato (1 = 1.0), texto por texto ('1' ≠ 1),
                     booleano só com booleano, lista na ordem, objeto chave a chave; ABSENT só confere com ABSENT
  numeric_tolerance  |observed − expected| ≤ tolerance, ABSOLUTA, na unidade do expected; com tipos de unidade
                     declarados dos dois lados, o observed é convertido para o tipo do expected (janela de taxa e
                     convenção de byte incluídas) antes da conta; tolerância é obrigatória (≥ 0, finita)
  set_equal          igualdade de conjuntos (ordem e repetição não contam; a repetição é perda declarada)
  normalized_string  texto em NFC, sem espaço nas pontas e com espaço interno colapsado; caixa preservada
  duration_equal     xsd:duration pelo espaço de valores do XSD 1.1: (meses, segundos) iguais (P12M = P1Y,
                     PT60M = PT1H, P1M ≠ P30D); com contexto de calendário, compara segundos na âncora
  cidr_equal         mesma rede (endereço de rede e prefixo), forma textual livre (maiúsculas, compressão IPv6);
                     bits de host ligados = TRANSFORM_OUT_OF_DOMAIN (não é rede)

Tolerância diferente de 0 fora de numeric_tolerance é erro de declaração: só a comparação numérica tem folga.
Comparação exata é a tolerância 0 declarada pelo próprio nome.
"""

from __future__ import annotations

import ipaddress
import json
import unicodedata
from fractions import Fraction

from . import units as U
from .errors import DeclarationError, OutOfDomain, SymbolicInput, UnknownInput
from .markers import is_absent, is_not_read, is_symbolic

C11_COMPARATORS = ("exact", "numeric_tolerance", "set_equal", "normalized_string", "duration_equal", "cidr_equal")


def _guard_markers(*vs):
    for v in vs:
        if is_not_read(v):
            raise UnknownInput("valor não lido não se compara")
        if is_symbolic(v):
            raise SymbolicInput("valor simbólico não se compara antes de resolvido")


def _is_num(v) -> bool:
    return isinstance(v, (int, float, Fraction)) and not isinstance(v, bool)


def value_equal(a, b) -> bool:
    if is_absent(a) or is_absent(b):
        return is_absent(a) and is_absent(b)
    if isinstance(a, bool) or isinstance(b, bool):
        return isinstance(a, bool) and isinstance(b, bool) and a == b
    if _is_num(a) and _is_num(b):
        return U.frac(a) == U.frac(b)
    if isinstance(a, str) and isinstance(b, str):
        return a == b
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(value_equal(x, y) for x, y in zip(a, b))
    if isinstance(a, dict) and isinstance(b, dict):
        return set(a) == set(b) and all(value_equal(a[k], b[k]) for k in a)
    if a is None and b is None:
        return True
    return False


def _canon(v):
    """Forma canônica hasheável de um valor JSON (para conjuntos)."""
    if isinstance(v, bool) or v is None or isinstance(v, str):
        return json.dumps(v)
    if _is_num(v):
        f = U.frac(v)
        return f"n:{f.numerator}/{f.denominator}"
    if isinstance(v, list):
        return "[" + ",".join(_canon(x) for x in v) + "]"
    if isinstance(v, dict):
        return "{" + ",".join(f"{json.dumps(k)}:{_canon(v[k])}" for k in sorted(v)) + "}"
    raise OutOfDomain(f"valor não é JSON: {v!r}")


def _no_tolerance(name, tolerance):
    if tolerance not in (None, 0):
        raise DeclarationError(f"{name}: tolerância só vale em numeric_tolerance (declarada {tolerance!r})")


def _tolerance(tolerance) -> Fraction:
    if tolerance is None:
        raise DeclarationError("numeric_tolerance sem tolerância declarada")
    t = U.frac(tolerance)
    if t < 0:
        raise DeclarationError(f"tolerância negativa: {tolerance!r}")
    return t


def compare_exact(expected, observed, tolerance=None, ctx=None) -> bool:
    _no_tolerance("exact", tolerance)
    _guard_markers(expected, observed)
    return value_equal(expected, observed)


def compare_numeric_tolerance(expected, observed, tolerance=None, ctx=None, expected_type=None,
                              observed_type=None) -> bool:
    t = _tolerance(tolerance)
    _guard_markers(expected, observed)
    if is_absent(expected) or is_absent(observed):
        return is_absent(expected) and is_absent(observed)
    if not (_is_num(expected) or isinstance(expected, str)) or not (_is_num(observed) or isinstance(observed, str)):
        raise OutOfDomain(f"numeric_tolerance compara números: {expected!r} x {observed!r}")
    e, o = U.frac(expected), U.frac(observed)
    if (expected_type is None) != (observed_type is None):
        raise DeclarationError("tipo de unidade declarado de um lado só: declare os dois ou nenhum")
    if expected_type is not None:
        o = U.frac(U.convert(o, observed_type, expected_type, ctx))
    return abs(o - e) <= t


def compare_set_equal(expected, observed, tolerance=None, ctx=None) -> bool:
    _no_tolerance("set_equal", tolerance)
    _guard_markers(expected, observed)
    if is_absent(expected) or is_absent(observed):
        return is_absent(expected) and is_absent(observed)
    if not isinstance(expected, list) or not isinstance(observed, list):
        raise OutOfDomain("set_equal compara listas")
    _guard_markers(*expected, *observed)
    return {_canon(x) for x in expected} == {_canon(x) for x in observed}


def normalize_string(s: str) -> str:
    if not isinstance(s, str):
        raise OutOfDomain(f"não é texto: {s!r}")
    return " ".join(unicodedata.normalize("NFC", s).split())


def compare_normalized_string(expected, observed, tolerance=None, ctx=None) -> bool:
    _no_tolerance("normalized_string", tolerance)
    _guard_markers(expected, observed)
    if is_absent(expected) or is_absent(observed):
        return is_absent(expected) and is_absent(observed)
    return normalize_string(expected) == normalize_string(observed)


def compare_duration_equal(expected, observed, tolerance=None, ctx=None) -> bool:
    _no_tolerance("duration_equal", tolerance)
    _guard_markers(expected, observed)
    if is_absent(expected) or is_absent(observed):
        return is_absent(expected) and is_absent(observed)
    a, b = U.parse_duration(expected), U.parse_duration(observed)
    if U.calendar_of(ctx) is not None:
        return U.duration_seconds(expected, ctx) == U.duration_seconds(observed, ctx)
    return (a.months, a.seconds) == (b.months, b.seconds)


def network(v):
    if not isinstance(v, str):
        raise OutOfDomain(f"CIDR não é texto: {v!r}")
    try:
        return ipaddress.ip_network(v.strip(), strict=True)
    except ValueError:
        raise OutOfDomain(f"não é rede CIDR (ou tem bits de host): {v!r}")


def compare_cidr_equal(expected, observed, tolerance=None, ctx=None) -> bool:
    _no_tolerance("cidr_equal", tolerance)
    _guard_markers(expected, observed)
    if is_absent(expected) or is_absent(observed):
        return is_absent(expected) and is_absent(observed)
    return network(expected) == network(observed)


IMPLEMENTATIONS = {
    "exact": compare_exact,
    "numeric_tolerance": compare_numeric_tolerance,
    "set_equal": compare_set_equal,
    "normalized_string": compare_normalized_string,
    "duration_equal": compare_duration_equal,
    "cidr_equal": compare_cidr_equal,
}
REGISTRY_NAME = {c: f"compare_{c}" for c in C11_COMPARATORS}


def compare(comparator: dict, expected, observed, ctx: dict | None = None, expected_type=None,
            observed_type=None) -> bool:
    """Aplica um comparador do C11 ({name, tolerance?}). Tipos de unidade só para numeric_tolerance."""
    if not isinstance(comparator, dict) or set(comparator) - {"name", "tolerance"} or "name" not in comparator:
        raise DeclarationError(f"comparador do C11 é {{name, tolerance?}}: {comparator!r}")
    name = comparator["name"]
    if name not in IMPLEMENTATIONS:
        raise DeclarationError(f"comparador fora do registro: {name!r} (só {C11_COMPARATORS})")
    tol = comparator.get("tolerance")
    if name == "numeric_tolerance":
        return compare_numeric_tolerance(expected, observed, tol, ctx, expected_type, observed_type)
    if expected_type is not None or observed_type is not None:
        raise DeclarationError(f"{name}: tipo de unidade só vale em numeric_tolerance")
    return IMPLEMENTATIONS[name](expected, observed, tol, ctx)
