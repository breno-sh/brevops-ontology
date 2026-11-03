"""Leitura de uma página r/*.html.markdown do azurerm em seções e itens, com a linha de cada pedaço.

Só texto: nada da página é interpretado como código. Estrutura reconhecida (a do lint de docs do azurerm):
  front matter (subcategory, page_title), '# azurerm_x', '## Arguments Reference', '## Attributes Reference',
  '## Timeouts', '## Import'. Dentro de argumentos/atributos: itens '* `nome` - (Optional) texto', com linhas
  de continuação e marcadores recuados; notas '-> ', '~> ', '!> '; '---' fecha a seção do bloco;
  'A|An|The `bloco` block supports|exports ...:' abre a seção de um bloco (com dica de pai 'within/for `pai`').
  'When `x` contains ...:' não abre seção (o texto continua na seção corrente).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

H2 = re.compile(r"^(##+)\s+(.*?)\s*$")
H1 = re.compile(r"^#\s+(\S+)\s*$")
ITEM = re.compile(r"^[*-]\s+`([^`]+)`\s*(?:[-–—:]+)?\s*(.*)$")
SUBITEM = re.compile(r"^\s+[*-]\s+\S")
NOTE = re.compile(r"^\s*(->|~>|!>)\s*(.*)$")
FENCE = re.compile(r"^\s*```")
INTRO = re.compile(
    r"^(?:[Aa]n?|[Tt]he|[Ee]ach)\s+((?:`[^`]+`(?:\s*,\s*|\s+or\s+|\s+and\s+)?)+)\s*(.*?)"
    r"\b(supports?|exports?|contains?|takes|accepts|has|have|includes?|blocks?)\b(.*)$")
HINT = re.compile(r"\b(?:within|for|under|inside|in|of)\s+(?:the\s+|an?\s+)?`([^`]+)`")
IMPORT_CMD = re.compile(r"^\s*(?:\$\s*)?terraform\s+import\s+(\S+)\s+(.+?)\s*$")
FRONT_KEY = re.compile(r'^([a-z_]+):\s*"?(.*?)"?\s*$')
MARKER = re.compile(r"^\(([^)]*)\)\s*")


@dataclass
class Note:
    line: int
    text: str
    after_item: "Item | None"


@dataclass
class Item:
    name: str
    line: int
    parts: list = field(default_factory=list)      # [(linha, texto)]
    notes: list = field(default_factory=list)      # Note anexadas por posição (logo depois do item)

    @property
    def text(self) -> str:
        return "\n".join(t for _, t in self.parts)

    @property
    def marker(self) -> str:
        m = MARKER.match(self.parts[0][1]) if self.parts else None
        return m.group(1) if m else ""

    def line_at(self, offset: int) -> int:
        """Linha do arquivo onde está o caractere 'offset' de self.text."""
        pos = 0
        for ln, t in self.parts:
            if offset <= pos + len(t):
                return ln
            pos += len(t) + 1
        return self.parts[-1][0]


@dataclass
class Section:
    kind: str                 # arg | attr | timeouts
    blocks: list              # [] = raiz do tipo; senão nomes de bloco da linha de abertura
    hint: str | None          # pai citado na abertura ('within `pai`')
    line: int                 # linha da abertura (ou do '##')
    intro: str = ""
    items: list = field(default_factory=list)
    notes: list = field(default_factory=list)


@dataclass
class ImportCmd:
    line: int
    address: str
    id: str


@dataclass
class Page:
    file: str                 # caminho no repositório (website/docs/r/x.html.markdown)
    lines: list
    front: dict = field(default_factory=dict)      # chave -> (valor, linha)
    h1: tuple | None = None                         # (nome, linha)
    sections: list = field(default_factory=list)
    imports: list = field(default_factory=list)
    has_import_section: bool = False
    import_line: int | None = None
    import_text: list = field(default_factory=list)  # [(linha, texto)] fora do código, na seção Import


def _h2_kind(title: str) -> str:
    t = title.lower()
    if t.startswith("argument"):
        return "arg"
    if t.startswith("attribute"):
        return "attr"
    if t.startswith("timeout"):
        return "timeouts"
    if t.startswith("import"):
        return "import"
    return "other"


def parse(path: Path, repo_rel: str) -> Page:
    lines = path.read_text(encoding="utf-8").splitlines()
    pg = Page(repo_rel, lines)
    i = 0
    if lines and lines[0].strip() == "---":
        i = 1
        while i < len(lines) and lines[i].strip() != "---":
            m = FRONT_KEY.match(lines[i])
            if m and m.group(1) not in pg.front:
                pg.front[m.group(1)] = (m.group(2), i + 1)
            i += 1
        i += 1
    kind = "other"
    sec: Section | None = None
    item: Item | None = None
    note: Note | None = None
    in_code = False
    blank_since_item = False
    for n in range(i, len(lines)):
        ln = n + 1
        raw = lines[n]
        s = raw.rstrip()
        if FENCE.match(s):
            in_code = not in_code
            item = None
            note = None
            continue
        if in_code:
            if kind == "import":
                m = IMPORT_CMD.match(s)
                if m:
                    pg.imports.append(ImportCmd(ln, m.group(1), m.group(2).strip().strip("'\"")))
            continue
        m = H2.match(s)
        if m and (len(m.group(1)) == 2 or _h2_kind(m.group(2)) in ("arg", "attr", "timeouts", "import")):
            kind = _h2_kind(m.group(2))
            item = note = None
            sec = None
            if kind in ("arg", "attr", "timeouts"):
                sec = Section(kind, ["timeouts"] if kind == "timeouts" else [], None, ln, s)
                pg.sections.append(sec)
            elif kind == "import":
                pg.has_import_section = True
                pg.import_line = ln
            continue
        if m:                                    # '### outro título' dentro de uma seção: fecha o item
            item = note = None
            continue
        if pg.h1 is None:
            m = H1.match(s)
            if m:
                pg.h1 = (m.group(1), ln)
                continue
        if kind == "import":
            if s.strip():
                pg.import_text.append((ln, s.strip()))
            continue
        if sec is None:
            continue
        if not s.strip():
            if item is not None:
                blank_since_item = True
            note = None
            continue
        if s.strip() == "---":
            item = note = None
            continue
        mi = INTRO.match(s.strip())
        if mi and kind in ("arg", "attr") and (s.strip().endswith(":") or s.strip().endswith(":.")
                                                or "following" in s):
            names = re.findall(r"`([^`]+)`", mi.group(1))
            hint = HINT.search(mi.group(2) + " " + mi.group(4))
            sec = Section(kind, names, hint.group(1) if hint else None, ln, s.strip())
            pg.sections.append(sec)
            item = note = None
            continue
        mn = NOTE.match(s)
        if mn:
            note = Note(ln, mn.group(2).strip(), item)
            sec.notes.append(note)
            if item is not None:
                item.notes.append(note)
            continue
        mt = ITEM.match(s)
        if mt and not raw.startswith((" ", "\t")):
            item = Item(mt.group(1).strip(), ln, [(ln, mt.group(2).strip())])
            sec.items.append(item)
            note = None
            blank_since_item = False
            continue
        if note is not None:
            note.text += " " + s.strip()
            continue
        if item is not None and (not blank_since_item or SUBITEM.match(raw)):
            item.parts.append((ln, s.strip()))
            continue
        # texto solto na seção (parágrafo): fecha o item corrente
        item = None
    return pg
