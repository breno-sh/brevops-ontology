"""SemVer 2.0.0 mínimo: análise, ordem e pré-lançamento (sem dependência externa)."""

from __future__ import annotations

import re

SEMVER_RE = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-((?:0|[1-9]\d*|\d*[A-Za-z-][0-9A-Za-z-]*)(?:\.(?:0|[1-9]\d*|\d*[A-Za-z-][0-9A-Za-z-]*))*))?"
    r"(?:\+([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?$"
)


class SemverError(ValueError):
    pass


def parse(v: str) -> tuple[int, int, int, tuple, str]:
    m = SEMVER_RE.match(v)
    if not m:
        raise SemverError(f"versão fora de SemVer: {v!r}")
    pre = tuple(int(p) if p.isdigit() else p for p in m.group(4).split(".")) if m.group(4) else ()
    return int(m.group(1)), int(m.group(2)), int(m.group(3)), pre, m.group(5) or ""


def is_prerelease(v: str) -> bool:
    return bool(parse(v)[3])


def major(v: str) -> int:
    return parse(v)[0]


def key(v: str) -> tuple:
    """Chave de ordem SemVer: pré-lançamento vem antes do lançamento; build é ignorado."""
    ma, mi, pa, pre, _ = parse(v)
    if not pre:
        return (ma, mi, pa, 1, ())
    ids = tuple((0, p, "") if isinstance(p, int) else (1, 0, p) for p in pre)
    return (ma, mi, pa, 0, ids)
