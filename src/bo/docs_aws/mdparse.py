"""Leitura linha a linha de uma página de documentação do provider aws (markdown do website/docs).

Nada de renderização: o markdown é lido como texto, com número de linha (1-based) preservado. Produz:
  * frontmatter: {chave: (valor, linha)} (subcategory, page_title, layout, ...)
  * title: (texto de '# Resource: aws_x' ou '# Data Source: aws_x', linha)
  * items: cada item de lista '* `nome` - texto' fora de cerca de código, com a seção (nível 2), o contexto de
    bloco vigente (cabeçalho com `nome`, cabeçalho em texto, frase 'The `x` block supports the following'),
    a indentação, as linhas de continuação e o item-pai pela indentação
  * import_lines: as linhas da seção '## Import' (texto e código separados)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

FENCE = re.compile(r"^\s*(```|~~~)")
HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
ITEM = re.compile(r"^(\s*)[*-]\s+`([^`]+)`(.*)$")
OTHER_ITEM = re.compile(r"^\s*([*-]|\d+\.)\s+")
TICK = re.compile(r"`([^`]+)`")
# frase que abre a lista de um bloco: 'The `x` [configuration] block supports the following [arguments]:'
BLOCK_INTRO = re.compile(
    r"^(?:(?:The|Each|A|An|This|Every)\s+)?`([^`]+)`\s+(?:\w+\s+){0,3}?"
    r"(?:supports?|exports?|takes?|contains?|has|accepts?|includes?)\b.*\bfollowing\b", re.I)
GENERIC_INTRO = re.compile(r"^(?:This|The)\s+(?:configuration\s+)?(?:block|object)\s+supports\s+the\s+following", re.I)

ALIAS = re.compile(r"`(aws_[a-z0-9_]+)`\s+is\s+known\s+as\s+`(aws_[a-z0-9_]+)`")

ARG_SECTIONS = ("argument reference", "arguments reference")
ATTR_SECTIONS = ("attribute reference", "attributes reference")


@dataclass
class Item:
    name: str               # o nome entre crases, como escrito
    line: int               # linha do item
    indent: int
    section: str            # 'argument' | 'attribute' | 'timeouts' | 'identity' | 'other'
    hint: str | None        # contexto de bloco vigente (nome ou caminho pontuado), None = topo
    hint_line: int | None
    hint_kind: str          # 'top' | 'tick_heading' | 'text_heading' | 'intro' | 'generic'
    text: str               # texto depois do nome (sem o separador ' - '), com as continuações
    lines: list = field(default_factory=list)   # [(linha, texto bruto)] do item e das continuações
    parent: int | None = None                   # índice do item-pai pela indentação


@dataclass
class Page:
    file: str
    frontmatter: dict
    title: tuple | None
    items: list
    import_text: list       # [(linha, texto)] fora de cerca, na seção Import
    import_code: list       # [(linha, texto)] dentro de cerca, na seção Import
    sections: list          # [(linha, título nível 2)]
    aliases: list = field(default_factory=list)   # [(linha, sentença, apelido, nome)] de '`a` is known as `b`'


def _section_of(title: str) -> str:
    t = title.strip().lower()
    if t.startswith(ARG_SECTIONS):
        return "argument"
    if t.startswith(ATTR_SECTIONS):
        return "attribute"
    if t.startswith("timeouts"):
        return "timeouts"
    if t.startswith("import"):
        return "import"
    return "other"


def _frontmatter(lines: list[str]) -> tuple[dict, int]:
    fm = {}
    if not lines or lines[0].strip() != "---":
        return fm, 0
    for i in range(1, len(lines)):
        s = lines[i]
        if s.strip() == "---":
            return fm, i + 1
        m = re.match(r"^([A-Za-z_]+):\s*(.*)$", s)
        if m:
            v = m.group(2).strip()
            if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
                v = v[1:-1]
            fm[m.group(1)] = (v, i + 1)
    return fm, 0


def strip_sep(rest: str) -> str:
    """'` - texto' / '` – texto' / '`: texto' / '` (texto' -> texto."""
    r = rest.lstrip()
    for sep in ("- ", "– ", "— ", ": ", "-", ":"):
        if r.startswith(sep):
            return r[len(sep):].lstrip()
    return r


def parse(text: str, file: str) -> Page:
    raw = text.splitlines()
    fm, start = _frontmatter(raw)
    title = None
    items: list[Item] = []
    sections = []
    imp_text, imp_code = [], []
    aliases = []
    section = "other"
    hint, hint_line, hint_kind = None, None, "top"
    in_fence = False
    identity = False
    last_item: Item | None = None
    stack: list[int] = []   # índices de itens abertos (indentação crescente)
    for i in range(start, len(raw)):
        n = i + 1
        s = raw[i]
        if FENCE.match(s):
            in_fence = not in_fence
            last_item = None
            if section == "import":
                imp_code.append((n, s))
            continue
        if in_fence:
            if section == "import":
                imp_code.append((n, s))
            continue
        h = HEADING.match(s)
        if h:
            level, htxt = len(h.group(1)), h.group(2)
            last_item, stack = None, []
            if level == 1:
                title = (htxt, n)
                continue
            if level == 2:
                section = _section_of(htxt)
                sections.append((n, htxt))
                identity = False
                hint, hint_line, hint_kind = (("timeouts", n, "text_heading") if section == "timeouts"
                                              else (None, None, "top"))
                continue
            if section == "import":
                imp_text.append((n, s))
                identity = htxt.strip().lower().startswith("identity schema") or (
                    identity and level > 3)
                continue
            if htxt.strip().lower().startswith("identity schema"):
                identity = True
                continue
            if identity and level > 3:
                continue
            identity = False
            ticks = TICK.findall(htxt)
            if ticks:
                hint, hint_line, hint_kind = ticks[0].strip(), n, "tick_heading"
            else:
                hint, hint_line, hint_kind = htxt.strip(), n, "text_heading"
            continue
        if section == "import":
            imp_text.append((n, s))
        for a in ALIAS.finditer(s):
            aliases.append((n, s.strip(), a.group(1), a.group(2)))
        m = ITEM.match(s)
        if m and section in ("argument", "attribute", "timeouts", "import"):
            indent = len(m.group(1).replace("\t", "    "))
            sec = "identity" if (identity or section == "import") else section
            while stack and items[stack[-1]].indent >= indent:
                stack.pop()
            it = Item(name=m.group(2).strip(), line=n, indent=indent, section=sec, hint=hint, hint_line=hint_line,
                      hint_kind=hint_kind, text=strip_sep(m.group(3)), lines=[(n, s)],
                      parent=stack[-1] if stack else None)
            items.append(it)
            stack.append(len(items) - 1)
            last_item = it
            continue
        if not s.strip():
            last_item = None
            continue
        if last_item is not None and not OTHER_ITEM.match(s) and s.startswith((" ", "\t")):
            last_item.text = (last_item.text + " " + s.strip()).strip()
            last_item.lines.append((n, s))
            continue
        last_item = None
        if OTHER_ITEM.match(s):
            continue
        if section in ("argument", "attribute", "timeouts"):
            stack = []
            b = BLOCK_INTRO.match(s.strip())
            if b:
                hint, hint_line, hint_kind = b.group(1).strip(), n, "intro"
            elif GENERIC_INTRO.match(s.strip()) and hint_kind == "text_heading":
                hint_kind = "generic"
    return Page(file=file, frontmatter=fm, title=title, items=items, import_text=imp_text,
                import_code=imp_code, sections=sections, aliases=aliases)
