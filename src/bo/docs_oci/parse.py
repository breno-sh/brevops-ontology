"""Leitura das páginas Markdown do website/docs/ do provider oci (só texto; nada é executado).

Uma página r/<x>.html.markdown tem: front matter (subcategory, page_title, ...), título '# oci_<tipo>',
'## Supported Aliases', '## Argument Reference', '## Attributes Reference', '## Timeouts' e '## Import'.
Cada argumento/atributo é um item de lista '* `nome` - (marcadores) texto'; o aninhamento é dado pela
indentação (tab ou espaços), relativo ao item anterior. O caminho do item é o dos nomes até ele; na seção
Timeouts o caminho começa em 'timeouts' (bloco do schema). Linhas indentadas e listas sem nome logo abaixo
do item são continuação dele; um parágrafo sem indentação depois de linha em branco encerra a lista.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

NAMED = re.compile(r"^(?P<ind>[ \t]*)[*-][ \t]+`(?P<name>[^`]+)`[ \t]*-[ \t]?(?P<rest>.*)$")
HEADING = re.compile(r"^(?P<h>#{1,6})[ \t]*(?P<t>.*?)[ \t#]*$")
FENCE = re.compile(r"^[ \t]*(```|~~~)")
MARKER = re.compile(r"^[ \t]*\((?P<m>(?:Required|Optional|Updatable|Applicable|Defaults? to|\*\*Deprecated\*\*|Deprecated)"
                    r"[^()]*(?:\([^()]*\)[^()]*)*)\)")
IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
ENUM_NAME = re.compile(r"^[A-Z][A-Z0-9_]*$")     # nomes de atributo do oci são snake_case minúsculo
IMPORTANT = re.compile(r"force the destruction and recreation of the resource", re.I)
IMPORT_CMD = re.compile(r"terraform import[ \t]+(?P<addr>\S+)[ \t]+(?P<id>.+?)[ \t]*$")

SECTION_KEYS = {
    "argument reference": "arguments",
    "arguments reference": "arguments",
    "attributes reference": "attributes",
    "attribute reference": "attributes",
    "timeouts": "timeouts",
    "import": "import",
    "supported aliases": "aliases",
    "example usage": "example",
}


@dataclass
class Item:
    section: str            # arguments | attributes | timeouts
    path: tuple             # nomes do topo até o item
    line: int               # linha (1-based) do item
    raw: str                # a linha do item, crua (sem a quebra)
    markers: list           # textos dos parênteses iniciais, na ordem
    head: str               # texto da linha do item depois dos marcadores
    cont: list = field(default_factory=list)   # [(linha, texto)] de continuação

    @property
    def name(self) -> str:
        return self.path[-1]

    def lines(self) -> list:
        """[(linha, texto)]: a linha do item (só o texto depois dos marcadores) e as de continuação."""
        return [(self.line, self.head)] + list(self.cont)

    def body(self) -> str:
        parts = [self.head.strip()] + [t.strip() for _, t in self.cont]
        return "\n".join(p for p in parts if p).strip()


@dataclass
class Page:
    file: str                       # caminho no repositório (website/docs/r/x.html.markdown)
    kind: str                       # r | d | outro
    front: dict                     # chave -> (valor, linha)
    title: tuple | None             # (texto, linha) do primeiro '# '
    items: list                     # [Item]
    aliases: list                   # [(nome, linha)]
    important_line: int | None      # linha da nota "Any change to a property that does not support update ..."
    important_text: str | None
    import_cmds: list               # [(linha, endereço, id cru)]
    import_text: list               # [(linha, texto)] fora de bloco de código na seção Import
    sections: dict                  # chave -> linha do cabeçalho


def parse_front(lines: list[str]) -> tuple[dict, int]:
    """Front matter YAML simples (chave: valor numa linha; '|-' junta as linhas indentadas seguintes)."""
    front: dict = {}
    if not lines or lines[0].strip() != "---":
        return front, 0
    i = 1
    key = None
    while i < len(lines):
        s = lines[i]
        if s.strip() == "---":
            return front, i + 1
        m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*):[ \t]*(.*)$", s)
        if m:
            key, val = m.group(1), m.group(2).strip()
            if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
                val = val[1:-1]
            front[key] = (val, i + 1)
        elif key and s.strip() and front[key][0] in ("|-", "|", ">", ">-"):
            front[key] = (s.strip(), front[key][1])
        i += 1
    return front, i


def width(ind: str) -> int:
    return len(ind.expandtabs(4))


def split_markers(rest: str) -> tuple[list, str]:
    marks = []
    s = rest
    while True:
        m = MARKER.match(s)
        if not m:
            break
        marks.append(m.group("m").strip())
        s = s[m.end():]
    return marks, s.strip()


def page_kind(rel: str) -> str:
    parts = rel.split("/")
    if len(parts) >= 3 and parts[-2] in ("r", "d"):
        return parts[-2]
    return "outro"


def parse(text: str, rel: str) -> Page:
    lines = text.splitlines()
    front, start = parse_front(lines)
    title = None
    items: list[Item] = []
    aliases: list = []
    important_line = important_text = None
    import_cmds: list = []
    import_text: list = []
    sections: dict = {}
    section = None
    in_code = False
    stack: list = []          # [(largura, nome)]
    cur: Item | None = None
    blank = False
    for idx in range(start, len(lines)):
        n = idx + 1
        s = lines[idx]
        if FENCE.match(s):
            in_code = not in_code
            cur = None
            continue
        if in_code:
            if section == "import":
                m = IMPORT_CMD.search(s)
                if m:
                    import_cmds.append((n, m.group("addr"), m.group("id")))
            continue
        if IMPORTANT.search(s) and important_line is None:
            important_line, important_text = n, s.strip()
        h = HEADING.match(s)
        if h:
            level = len(h.group("h"))
            t = h.group("t").strip()
            if level == 1 and title is None:
                title = (t, n)
            if level == 2:
                section = SECTION_KEYS.get(t.lower())
                if section:
                    sections.setdefault(section, n)
            stack, cur, blank = [], None, False
            continue
        if not s.strip():
            blank = True
            continue
        if section == "import":
            import_text.append((n, s.strip()))
            continue
        if section == "aliases":
            m = re.match(r"^[ \t]*[*-][ \t]+`([^`]+)`", s)
            if m:
                aliases.append((m.group(1).strip(), n))
            continue
        if section not in ("arguments", "attributes", "timeouts"):
            continue
        m = NAMED.match(s)
        if m and ENUM_NAME.match(m.group("name").strip()) and cur is not None:
            # '* `VALOR` - explicação' abaixo de um item: lista de valores do item, não atributo filho
            cur.cont.append((n, s.rstrip()))
            blank = False
            continue
        if m and IDENT.match(m.group("name").strip()):
            w = width(m.group("ind"))
            while stack and stack[-1][0] >= w:
                stack.pop()
            name = m.group("name").strip()
            path = tuple(x for _, x in stack) + (name,)
            if section == "timeouts":
                path = ("timeouts",) + path
            marks, head = split_markers(m.group("rest"))
            cur = Item(section, path, n, s.rstrip("\n"), marks, head)
            items.append(cur)
            stack.append((w, name))
            blank = False
            continue
        indented = s[:1] in (" ", "\t")
        if cur is not None and (indented or not blank):
            cur.cont.append((n, s.rstrip()))
            blank = False
            continue
        # parágrafo sem indentação depois de linha em branco: a lista acabou
        stack, cur, blank = [], None, False
    return Page(rel, page_kind(rel), front, title, items, aliases, important_line, important_text,
                import_cmds, import_text, sections)


def resource_type_of(page: Page, known: set | None = None) -> str | None:
    """Tipo documentado: 'oci_' + nome do arquivo quando é um tipo conhecido (é assim que o repositório nomeia
    as páginas); senão o título '# oci_x'; senão o nome do arquivo. O título pode estar errado (cópia de outra
    página), o nome do arquivo não."""
    base = page.file.rsplit("/", 1)[-1].split(".", 1)[0]
    fname = "oci_" + base if base else None
    if known is not None and fname in known:
        return fname
    if page.title and re.match(r"^oci_[a-z0-9_]+$", page.title[0]):
        return page.title[0]
    return fname


def title_mismatch(page: Page) -> bool:
    base = page.file.rsplit("/", 1)[-1].split(".", 1)[0]
    return bool(page.title and re.match(r"^oci_[a-z0-9_]+$", page.title[0]) and page.title[0] != "oci_" + base)
