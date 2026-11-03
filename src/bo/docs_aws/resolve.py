"""Item da documentação -> átomo(s) do schema da mesma versão (C01: atom_id = provider:tipo:caminho.de.blocos).

Regras, em ordem (a primeira que decide vale; o nível de evidência sai da regra):
  R0 nome pontuado ou com índice ('a.0.b', 'a[0].b', 'a.*.b') é normalizado para 'a.b'.
  R1 item aninhado por indentação sob um item que resolveu num bloco B: B.nome é átomo -> published.
  R2 sem contexto de bloco (topo da seção): 'nome' é átomo de topo -> published.
  R3 contexto H (cabeçalho com crase, frase 'The `H` block supports', cabeçalho em texto normalizado):
       H.nome é átomo -> published;
       senão, blocos cujo caminho termina em H e têm o átomo 'nome': 1 -> published, vários -> derived
       (a página descreve uma vez um bloco que o schema repete em vários caminhos; o fato vale para todos).
  R4 contexto que não é bloco do schema (ex.: '### Block Devices') ou topo sem átomo de topo:
       'nome' é átomo de topo -> published; senão, átomos cujo último segmento é 'nome' e cujo bloco-pai
       aparece no contexto: 1 -> derived; senão, único átomo no tipo com esse último segmento -> derived.
  Fora disso: não resolvido, com motivo (block = o nome é bloco, não atributo; nested_child = filho de atributo
  com nested_type, que o C01 não atomiza; ambiguous = vários candidatos sem critério; not_in_schema).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

IDX = re.compile(r"\[(?:\d+|\*)\]")


def norm_path(s: str) -> str:
    s = IDX.sub("", s.strip().strip("`").strip())
    parts = [p for p in s.split(".") if p and not p.isdigit() and p not in ("*", "#", "%")]
    return ".".join(parts)


def norm_heading(s: str) -> str:
    """'CPU Options' -> 'cpu_options' (cabeçalho em texto como candidato a nome de bloco)."""
    s = re.sub(r"[^A-Za-z0-9]+", "_", s.strip().lower()).strip("_")
    for suf in ("_configuration_blocks", "_configuration_block", "_blocks", "_block", "_arguments", "_argument_reference", "_attributes"):
        if s.endswith(suf) and len(s) > len(suf):
            s = s[: -len(suf)]
    return s


@dataclass
class TypeIndex:
    atoms: dict          # caminho -> átomo C01
    blocks: set          # caminhos de blocos
    by_last: dict        # último segmento -> [caminhos de átomo]
    nested_attrs: set    # caminhos de átomos com nested_type (objeto)

    @classmethod
    def build(cls, atoms: list[dict], blocks: list) -> "TypeIndex":
        a = {x["path"]: x for x in atoms}
        bl = {".".join(b.path) for b in blocks}
        by_last: dict = {}
        for p in a:
            by_last.setdefault(p.rsplit(".", 1)[-1], []).append(p)
        nested = {p for p, x in a.items() if isinstance(x["tf_type"], list) and _has_object(x["tf_type"])}
        return cls(a, bl, by_last, nested)


def _has_object(t) -> bool:
    if isinstance(t, list):
        if t and t[0] == "object":
            return True
        return any(_has_object(x) for x in t[1:])
    return False


@dataclass
class Resolution:
    paths: list          # caminhos de átomo
    level: str | None    # 'published' | 'derived' | None
    rule: str            # R1..R4 ou motivo
    block: str | None = None   # caminho de bloco quando o item é um bloco


def _blocks_ending(ix: TypeIndex, h: str) -> list[str]:
    return sorted(b for b in ix.blocks if b == h or b.endswith("." + h))


def resolve(ix: TypeIndex, name: str, hint: str | None, hint_kind: str, parent_block: str | None,
            parent_atom: str | None) -> Resolution:
    n = norm_path(name)
    if not n:
        return Resolution([], None, "empty")
    if parent_atom is not None:
        return Resolution([], None, "nested_child")
    # R1: pai por indentação
    if parent_block is not None:
        p = f"{parent_block}.{n}"
        if p in ix.atoms:
            return Resolution([p], "published", "R1")
        if p in ix.blocks:
            return Resolution([], None, "block", block=p)
    h = None
    if hint is not None:
        h = norm_path(hint) if hint_kind in ("tick_heading", "intro") else norm_heading(hint)
        if hint_kind == "text_heading" and h == "timeouts":
            h = "timeouts"
    # R2: topo
    if h is None:
        if n in ix.atoms:
            return Resolution([n], "published", "R2")
        if n in ix.blocks:
            return Resolution([], None, "block", block=n)
        return _fallback(ix, n, None)
    # R3: contexto de bloco do schema
    hb = _blocks_ending(ix, h)
    if hb:
        exact = f"{h}.{n}"
        if exact in ix.atoms:
            return Resolution([exact], "published", "R3")
        if exact in ix.blocks:
            return Resolution([], None, "block", block=exact)
        cands = [f"{b}.{n}" for b in hb if f"{b}.{n}" in ix.atoms]
        if len(cands) == 1:
            return Resolution(cands, "published", "R3")
        if cands:
            return Resolution(sorted(cands), "derived", "R3-shared")
        blks = [f"{b}.{n}" for b in hb if f"{b}.{n}" in ix.blocks]
        if blks:
            return Resolution([], None, "block", block=blks[0])
        if any(f"{b}" in ix.nested_attrs for b in hb):
            return Resolution([], None, "nested_child")
    # contexto H como atributo com nested_type: os filhos não são átomos
    if h in ix.nested_attrs or any(p.endswith("." + h) for p in ix.nested_attrs):
        return Resolution([], None, "nested_child")
    if hb:
        # contexto é bloco do schema, mas o nome não está nele: tenta o topo e o sufixo
        return _fallback(ix, n, h, strict_ctx=True)
    return _fallback(ix, n, h)


def _fallback(ix: TypeIndex, n: str, h: str | None, strict_ctx: bool = False) -> Resolution:
    # R4
    if "." in n:
        cands = [p for p in ix.atoms if p == n or p.endswith("." + n)]
        if len(cands) == 1:
            return Resolution(cands, "published" if cands[0] == n else "derived", "R4-dotted")
        if len(cands) > 1:
            return Resolution([], None, "ambiguous")
        if any(b == n or b.endswith("." + n) for b in ix.blocks):
            return Resolution([], None, "block", block=n)
        return Resolution([], None, "not_in_schema")
    if not strict_ctx and n in ix.atoms:
        return Resolution([n], "published", "R4-top")
    cands = ix.by_last.get(n, [])
    if h:
        hs = set(h.split("_")) | {h}
        ctx = [c for c in cands if "." in c and c.rsplit(".", 2)[-2] in hs | {h}]
        if len(ctx) == 1:
            return Resolution(ctx, "derived", "R4-ctx")
    deep = [c for c in cands if "." in c]
    if strict_ctx and n in ix.atoms and not deep:
        return Resolution([n], "derived", "R4-top-ctx")
    if len(cands) == 1:
        return Resolution(cands, "derived", "R4-unique")
    if n in ix.blocks or any(b.endswith("." + n) for b in ix.blocks):
        return Resolution([], None, "block", block=n)
    if cands:
        return Resolution([], None, "ambiguous")
    return Resolution([], None, "not_in_schema")
