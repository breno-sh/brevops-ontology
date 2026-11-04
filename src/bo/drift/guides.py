"""Frases dos guias de atualização (upgrade guides) do provider que citam um renome ou uma substituição.

Os guias são texto publicado pelo mantenedor do provider, copiados e conferidos pelos DOCS-* na tag fixada
($BO_DATA/downloads/docs-*). Aqui são só lidos como texto (dado não confiável, nada é executado). Uma frase
vira evidência `published` de renome quando: está fora de bloco de código, na seção de um tipo de recurso
(título com o nome do tipo; seções de data source não contam), cita pelo menos dois nomes entre crases e traz
uma pista de renome ("renamed", "rename") ou de substituição ("in favor of", "instead of", "replaced by",
"change `a` to `b`", ...). O guia da major N só vale para intervalos que cruzam a fronteira N.0.0.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from . import common

RENAME_CUE = re.compile(r"\brenam(?:e|ed|es|ing)\b", re.I)
REPLACE_CUE = re.compile(
    r"in\s+favou?r\s+of|replaced\s+(?:by|with)|\binstead\b|superseded\s+by|moved\s+to|migrated?\s+to"
    r"|\bchange[sd]?\s+`[^`]+`\s+to\s+`", re.I)
MENTION = re.compile(r"`([A-Za-z_][A-Za-z0-9_.\[\]*]*)`")
HEADING = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")
FENCE = re.compile(r"^\s*(```|~~~)")
DATA_SOURCE = re.compile(r"data[\s_-]?source|^d/", re.I)
GUIDE_NAME = (re.compile(r"^version[-_](\d+)[-_]upgrade\.html\.markdown$"),
              re.compile(r"^(\d+)\.0-upgrade-guide\.html\.markdown$"))
MAX_SENTENCE = 400


@dataclass(frozen=True)
class Sentence:
    provider: str
    major: int
    repo: str
    tag: str
    file: str          # caminho no repositório do provider (website/docs/guides/...)
    line: int
    text: str
    resources: frozenset
    mentions: tuple
    cue: str           # "rename" | "replace"


def guide_major(name: str) -> int | None:
    for rx in GUIDE_NAME:
        m = rx.match(name)
        if m:
            return int(m.group(1))
    return None


def _norm_mention(m: str, resources: frozenset) -> str:
    m = re.sub(r"\[[^\]]*\]", "", m).strip(".")
    for rt in resources:
        if m.startswith(rt + "."):
            return m[len(rt) + 1:]
    return m


def parse_guide(provider: str, path: Path, major: int, repo: str, tag: str, rel: str) -> list[Sentence]:
    rt_rx = re.compile(rf"\b{re.escape(provider)}_[a-z0-9_]+\b")
    out: list[Sentence] = []
    stack: list[tuple[int, frozenset | None]] = []   # (nível do título, tipos da seção | None = data source)
    fenced = False
    for n, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
        if FENCE.match(line):
            fenced = not fenced
            continue
        if fenced:
            continue
        h = HEADING.match(line)
        text = line
        if h:
            level, title = len(h.group(1)), h.group(2)
            while stack and stack[-1][0] >= level:
                stack.pop()
            rts = frozenset(rt_rx.findall(title))
            if DATA_SOURCE.search(title) and rts:
                stack.append((level, None))
            elif rts:
                stack.append((level, rts))
                continue      # o título do tipo não é frase de renome
            text = title
        ctx = stack[-1][1] if stack else None   # seção de tipo mais interna; None = data source
        if not ctx:
            continue
        cue = "rename" if RENAME_CUE.search(text) else ("replace" if REPLACE_CUE.search(text) else None)
        if not cue:
            continue
        ms = []
        for m in MENTION.findall(text):
            nm = _norm_mention(m, ctx)
            if nm and nm not in ctx and not rt_rx.fullmatch(nm) and nm not in ms:
                ms.append(nm)
        if len(ms) < 2:
            continue
        out.append(Sentence(provider, major, repo, tag, rel, n, " ".join(text.split())[:MAX_SENTENCE],
                            ctx, tuple(ms), cue))
    return out


def load(provider: str, data: Path | None = None) -> tuple[list[Sentence], list[Path]]:
    """Frases de todos os guias de atualização do provider e os arquivos lidos (para a proveniência)."""
    data = data or common.bo_data()
    _, repo, tag, rel_dir = common.PROVIDERS[provider]
    d = data / rel_dir
    sents, files = [], []
    if not d.is_dir():
        return sents, files
    for p in sorted(d.iterdir()):
        mj = guide_major(p.name)
        if mj is None or not p.is_file():
            continue
        files.append(p)
        sents += parse_guide(provider, p, mj, repo, tag, f"website/docs/guides/{p.name}")
    return sents, files
