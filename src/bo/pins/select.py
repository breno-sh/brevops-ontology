"""Regras de escolha, puras e testáveis: versão estável num instante, amostra trimestral, primeira de cada major.

Uma versão publicada no instante t pertence ao estado "até o dia D" se t < início do dia D+1 em America/Recife.
"Estável" = sem sufixo de pré-lançamento SemVer; "a estável num instante" = a MAIOR em ordem SemVer entre as
estáveis publicadas antes do instante (um backport de linha antiga publicado depois de uma major nova não vira
o estado, porque o estado é a linha principal)."""

from __future__ import annotations

import datetime as _dt
import json
from dataclasses import dataclass, field
from pathlib import Path

from . import config, semver


@dataclass(frozen=True)
class Release:
    version: str
    published_at: _dt.datetime  # UTC, do Registry v2 (published-at)
    protocols: tuple = ()
    platforms: tuple = ()

    @property
    def stable(self) -> bool:
        return not semver.is_prerelease(self.version)

    @property
    def date_recife(self) -> str:
        return self.published_at.astimezone(config.TZ).date().isoformat()

    @property
    def published_iso(self) -> str:
        return self.published_at.astimezone(config.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class Pick:
    release: Release
    reasons: list = field(default_factory=list)


def parse_ts(s: str) -> _dt.datetime:
    t = _dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
    if t.tzinfo is None:
        raise ValueError(f"instante sem fuso: {s!r}")
    return t.astimezone(config.UTC)


def releases_from_registry(v1: dict, v2: dict) -> tuple[list[Release], list[str]]:
    """Junta v1 (protocolos, plataformas) e v2 (published-at). Devolve (versões, divergências entre v1 e v2)."""
    meta = {}
    for v in v1.get("versions", []):
        plats = sorted(f"{p['os']}_{p['arch']}" for p in v.get("platforms", []))
        meta[v["version"]] = (tuple(sorted(v.get("protocols", []))), tuple(plats))
    dated = {}
    for inc in v2.get("included", []):
        if inc.get("type") != "provider-versions":
            continue
        a = inc["attributes"]
        dated[a["version"]] = parse_ts(a["published-at"])
    issues = []
    only1 = sorted(set(meta) - set(dated), key=semver.key)
    only2 = sorted(set(dated) - set(meta), key=semver.key)
    if only1:
        issues.append(f"{len(only1)} versão(ões) só no v1 (sem data): {', '.join(only1[:5])}")
    if only2:
        issues.append(f"{len(only2)} versão(ões) só no v2 (sem plataformas): {', '.join(only2[:5])}")
    out = [Release(v, dated[v], *meta.get(v, ((), ()))) for v in dated]
    out.sort(key=lambda r: semver.key(r.version))
    return out, issues


def stable_before(rels: list[Release], instant: _dt.datetime) -> Release | None:
    cands = [r for r in rels if r.stable and r.published_at < instant]
    return max(cands, key=lambda r: semver.key(r.version)) if cands else None


def quarters(start: _dt.date, end_exclusive: _dt.datetime) -> list[tuple[str, _dt.datetime]]:
    """Trimestres completos de `start` até o fim de corte: [(rótulo AAAAQn, início do trimestre seguinte)]."""
    out = []
    y, q = start.year, (start.month - 1) // 3 + 1
    while True:
        ny, nq = (y, q + 1) if q < 4 else (y + 1, 1)
        nxt = config.day_start(_dt.date(ny, 3 * (nq - 1) + 1, 1))
        if nxt > end_exclusive:
            break
        out.append((f"{y}Q{q}", nxt))
        y, q = ny, nq
    return out


def first_of_each_major(rels: list[Release], start: _dt.datetime, end: _dt.datetime) -> list[tuple[Release, str]]:
    """Primeira estável (menor SemVer) de cada major, se publicada em [start, end). Rótulo major_first:M quando
    ela é M.0.0; quando não é (o índice começa no meio da major, ex. troca de namespace), o rótulo é index_first:
    é o primeiro estado observável, não o começo da major."""
    firsts: dict[int, Release] = {}
    for r in rels:
        if not r.stable:
            continue
        m = semver.major(r.version)
        if m not in firsts or semver.key(r.version) < semver.key(firsts[m].version):
            firsts[m] = r
    out = []
    for m, r in sorted(firsts.items()):
        if not start <= r.published_at < end:
            continue
        ma, mi, pa, _, _ = semver.parse(r.version)
        out.append((r, f"major_first:{m}" if (mi, pa) == (0, 0) else "index_first"))
    return out


def history(rels: list[Release]) -> tuple[Release, list[Pick], dict]:
    """(pin no corte, lista histórica em ordem SemVer, detalhes). A lista = estado ao fim de cada trimestre
    completo desde HISTORY_START + primeira estável de cada major publicada na janela + o próprio pin."""
    start, end = config.day_start(config.HISTORY_START), config.cutoff_end()
    pin = stable_before(rels, end)
    if pin is None:
        raise ValueError("nenhuma versão estável até a data de corte")
    picks: dict[str, Pick] = {}

    def add(r: Release, why: str):
        picks.setdefault(r.version, Pick(r)).reasons.append(why)

    qs = quarters(config.HISTORY_START, end)
    empty = []
    for label, nxt in qs:
        r = stable_before(rels, nxt)
        if r is None:
            empty.append(label)
            continue
        add(r, f"quarter_end:{label}")
    for r, why in first_of_each_major(rels, start, end):
        add(r, why)
    add(pin, f"cutoff:{config.CUTOFF_DATE.isoformat()}")
    out = sorted(picks.values(), key=lambda p: semver.key(p.release.version))
    in_force = stable_before(rels, start)
    first = min((r for r in rels if r.stable), key=lambda r: r.published_at)
    det = {
        "quarters": [q for q, _ in qs],
        "quarters_without_release": empty,
        "left_truncation": {
            "at": start.isoformat(),
            "version_in_force": in_force.version if in_force else None,
            "major_in_force": semver.major(in_force.version) if in_force else None,
            "index_first_version": first.version,
            "index_first_published_at": first.published_iso,
        },
        "stable_in_window": sum(1 for r in rels if r.stable and start <= r.published_at < end),
        "prerelease_total": sum(1 for r in rels if not r.stable),
        "published_after_cutoff": sorted((r.version for r in rels if r.published_at >= end), key=semver.key),
    }
    return pin, out, det


def load_json(p: Path) -> dict:
    return json.loads(Path(p).read_bytes())
