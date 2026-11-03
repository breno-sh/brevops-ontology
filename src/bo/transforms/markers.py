"""Marcadores de valor na entrada de um transporte (os mesmos do SEMANTICS, bo.semantics.vocab).

ABSENT    sabidamente sem valor (leitura completa)
NOT_READ  fora do que a leitura cobriu            -> UNKNOWN_INPUT
SYMBOLIC  conhecido só depois da criação          -> UNKNOWN_SYMBOLIC_INPUT (identity o deixa passar)
"""

from __future__ import annotations

ABSENT = {"$absent": True}
NOT_READ = {"$not_read": True}
SYMBOLIC = {"$symbolic": True}


def is_marker(v, m) -> bool:
    return isinstance(v, dict) and next(iter(m)) in v


def is_absent(v) -> bool:
    return is_marker(v, ABSENT)


def is_not_read(v) -> bool:
    return is_marker(v, NOT_READ)


def is_symbolic(v) -> bool:
    return is_marker(v, SYMBOLIC)


def is_any_marker(v) -> bool:
    return is_absent(v) or is_not_read(v) or is_symbolic(v)
