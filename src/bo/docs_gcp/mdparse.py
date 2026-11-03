"""Página markdown da documentação (r/*.html.markdown) -> estrutura, sem interpretar o texto.

Regras do analisador (declaradas, as mesmas para toda página):
  * front matter entre as duas primeiras linhas '---': 'subcategory: "..."' (com a linha) e 'description:'.
  * tipos documentados: títulos '# google_x' / '## google_x' (fora de bloco de código).
  * seção = título '## '; tipo da seção pelo começo do título: argument -> args, attribute -> attrs,
    timeouts -> timeouts, import -> import; o resto é other (exemplos, notas) e não gera item.
  * bloco aninhado: linha 'The `x` block supports|contains ...' (com ou sem '<a name="nested_x"></a>' antes, na
    mesma linha ou na anterior) abre um contexto; um título '## ' volta ao topo da seção.
  * item: linha '* `nome` ...' ou '- `nome` ...' (até 4 espaços de recuo) nas seções args/attrs/timeouts.
    O corpo segue até o próximo item de recuo menor ou igual, título, abertura de bloco, '- - -', cerca de código,
    ou linha em branco seguida de linha sem recuo que não é item. Item com recuo maior dentro do corpo é
    subitem (filho do item de cima) e também fica no texto do pai.
  * links '(#nested_x)' no corpo de um item ligam o item ao contexto de âncora nested_x.
  * import: itens com '{{' ou '/' no texto entre crases (formatos aceitos) e a frase que os introduz; nos blocos de
    código da seção, 'identity = {' (atributos '<-required value->'/'<-optional value->'), 'id = "' e
    'terraform import' dão os métodos; 'does not support import' marca importação não suportada.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

TYPE_HEAD = re.compile(r"^#{1,3}\s+(google_[a-z0-9_]+)\s*$")
SECTION = re.compile(r"^##\s+(.+?)\s*$")
ANCHOR_ONLY = re.compile(r'^\s*<a\s+name="([^"]+)"\s*>\s*</a>\s*$')
BLOCK_OPEN = re.compile(r'^\s*(?:<a\s+name="(?P<anchor>[^"]+)"\s*>\s*</a>)?\s*The\s+`(?P<name>[^`]+)`(?P<rest>[^\n]*)$')
BULLET = re.compile(r"^(?P<ind>[ \t]{0,4})[*-][ \t]+`(?P<name>[A-Za-z0-9_.*/\[\]{}-]+)`(?P<rest>.*)$")
SEP = re.compile(r"^\s*-\s+-\s+-\s*$")
FENCE = re.compile(r"^\s*(```|~~~)")
LINK_NESTED = re.compile(r"\(#(nested_[A-Za-z0-9_\-]+)\)")
IMPORT_FMT = re.compile(r"^\s*[*-]\s+`?(?P<fmt>[^`\s]*(?:\{\{|/)[^`\s]*)`?\s*$")
SUBCAT = re.compile(r'^subcategory:\s*"?(?P<v>[^"]*?)"?\s*$')
NAME_OK = re.compile(r"^[A-Za-z0-9_]+(?:\.(?:[A-Za-z0-9_]+|\*|\d+))*(?:/[A-Za-z0-9_]+)*$")


def section_kind(title: str) -> str:
    t = title.strip().lower()
    for prefix, kind in (("argument", "args"), ("attribute", "attrs"), ("timeouts", "timeouts"), ("import", "import")):
        if t.startswith(prefix):
            return kind
    return "other"


@dataclass
class Context:
    idx: int
    section: str
    line: int
    anchor: str | None = None      # 'nested_x' ou None (topo da seção)
    name: str | None = None        # nome entre crases em 'The `x` block'


@dataclass
class Bullet:
    name: str
    line: int
    indent: int
    section: str
    ctx: int
    lines: list = field(default_factory=list)       # [(nº da linha, texto)] do item, ele incluído
    links: list = field(default_factory=list)       # âncoras nested_ citadas no corpo
    parent: int | None = None                       # índice do item pai (subitem)


@dataclass
class ImportInfo:
    line: int | None = None
    sentence: str | None = None
    formats: list = field(default_factory=list)     # [(nº da linha, formato)]
    section_line: int | None = None                 # título '## Import'
    methods: list = field(default_factory=list)     # import_block_identity | import_block_id | terraform_import_cli
    identity: dict = field(default_factory=lambda: {"required": [], "optional": []})
    identity_line: int | None = None
    unsupported: tuple | None = None                # (linha, frase) 'does not support import'


@dataclass
class Page:
    rel: str                                        # caminho no repositório (website/docs/r/x.html.markdown)
    lines: list
    subcategory: str | None = None
    subcategory_line: int | None = None
    types: list = field(default_factory=list)       # [(tipo, nº da linha do título)]
    contexts: list = field(default_factory=list)
    bullets: list = field(default_factory=list)
    imports: ImportInfo = field(default_factory=ImportInfo)


def _ind(s: str) -> int:
    return len(s.expandtabs(4)) - len(s.expandtabs(4).lstrip(" "))


def parse_text(text: str, rel: str) -> Page:
    lines = text.splitlines()
    pg = Page(rel=rel, lines=lines)
    n = len(lines)
    i = 0
    # front matter
    if n and lines[0].strip() == "---":
        j = 1
        while j < n and lines[j].strip() != "---":
            m = SUBCAT.match(lines[j])
            if m and pg.subcategory is None:
                pg.subcategory, pg.subcategory_line = m.group("v").strip(), j + 1
            j += 1
        i = j + 1
    section = "other"
    ctx = None
    pending_anchor = None
    in_code = False
    import_intro = None
    in_identity = False
    while i < n:
        raw = lines[i]
        ln = i + 1
        if FENCE.match(raw):
            in_code = not in_code
            in_identity = False
            i += 1
            continue
        if in_code:
            if section == "import":
                _import_code(pg.imports, raw, ln, in_identity)
                if IDENTITY_OPEN.match(raw):
                    in_identity = True
                elif in_identity and raw.strip().startswith("}"):
                    in_identity = False
            i += 1
            continue
        m = TYPE_HEAD.match(raw)
        if m:
            pg.types.append((m.group(1), ln))
        m = SECTION.match(raw)
        if m:
            section = section_kind(m.group(1))
            if section == "import" and pg.imports.section_line is None:
                pg.imports.section_line = ln
            ctx = Context(len(pg.contexts), section, ln)
            pg.contexts.append(ctx)
            pending_anchor = None
            i += 1
            continue
        if section == "import":
            mf = IMPORT_FMT.match(raw)
            if mf and ("{{" in mf.group("fmt") or "/" in mf.group("fmt")):
                if pg.imports.line is None:
                    pg.imports.line = import_intro[0] if import_intro else ln
                    pg.imports.sentence = import_intro[1] if import_intro else raw.strip()
                pg.imports.formats.append((ln, mf.group("fmt")))
            elif "imported using" in raw or "can be imported" in raw:
                if import_intro is None:
                    import_intro = (ln, raw.strip())
            elif NO_IMPORT.search(raw) and pg.imports.unsupported is None:
                pg.imports.unsupported = (ln, raw.strip())
            i += 1
            continue
        if section not in ("args", "attrs", "timeouts"):
            i += 1
            continue
        ma = ANCHOR_ONLY.match(raw)
        if ma:
            pending_anchor = ma.group(1)
            i += 1
            continue
        mb = BLOCK_OPEN.match(raw)
        if mb and re.search(r"\b(block|supports|contains|exports)\b", mb.group("rest")):
            anchor = mb.group("anchor") or pending_anchor
            ctx = Context(len(pg.contexts), section, ln, anchor=anchor, name=mb.group("name"))
            pg.contexts.append(ctx)
            pending_anchor = None
            i += 1
            continue
        if raw.strip() and not BULLET.match(raw):
            pending_anchor = None
        mbul = BULLET.match(raw)
        if mbul and ctx is not None and NAME_OK.match(mbul.group("name")):
            i = _read_bullet(pg, lines, i, ctx, section, None)
            continue
        i += 1
    return pg


IDENTITY_OPEN = re.compile(r"^\s*identity\s*=\s*\{")
IDENTITY_ATTR = re.compile(r'^\s*([A-Za-z0-9_]+)\s*=\s*"<-(required|optional) value->"')
NO_IMPORT = re.compile(r"\b(?:does\s+not|doesn't)\s+support\s+import|\bcannot\s+be\s+imported\b|"
                       r"\bimport\s+is\s+not\s+supported\b", re.I)


def _add_method(imp: ImportInfo, m: str) -> None:
    if m not in imp.methods:
        imp.methods.append(m)


def _import_code(imp: ImportInfo, raw: str, ln: int, in_identity: bool) -> None:
    """Linha de bloco de código na seção Import: métodos de importação e atributos de identidade."""
    if IDENTITY_OPEN.match(raw):
        _add_method(imp, "import_block_identity")
        imp.identity_line = imp.identity_line or ln
        return
    if in_identity:
        m = IDENTITY_ATTR.match(raw)
        if m and m.group(1) not in imp.identity[m.group(2)]:
            imp.identity[m.group(2)].append(m.group(1))
        return
    if re.match(r'^\s*id\s*=\s*"', raw):
        _add_method(imp, "import_block_id")
    elif re.match(r"^\s*\$?\s*terraform\s+import\s", raw):
        _add_method(imp, "terraform_import_cli")


def _is_stop(line: str) -> bool:
    return bool(SECTION.match(line) or ANCHOR_ONLY.match(line) or SEP.match(line) or FENCE.match(line)
                or (BLOCK_OPEN.match(line) and re.search(r"\b(block|supports|contains|exports)\b",
                                                         BLOCK_OPEN.match(line).group("rest"))))


def _read_bullet(pg: Page, lines: list, i: int, ctx: Context, section: str, parent: int | None) -> int:
    """Lê o item que começa em lines[i]; devolve o índice da primeira linha depois dele."""
    m = BULLET.match(lines[i])
    ind = _ind(m.group("ind"))
    b = Bullet(name=m.group("name"), line=i + 1, indent=ind, section=section, ctx=ctx.idx, parent=parent)
    b.lines.append((i + 1, lines[i]))
    me = len(pg.bullets)
    pg.bullets.append(b)
    j = i + 1
    n = len(lines)
    while j < n:
        s = lines[j]
        if _is_stop(s):
            break
        mb = BULLET.match(s) if _ind(s) <= 4 else None
        if mb and NAME_OK.match(mb.group("name")):
            if _ind(s) <= ind:
                break
            # subitem: entra no texto do pai e vira item filho
            k = _read_bullet(pg, lines, j, ctx, section, me)
            b.lines.extend((x + 1, lines[x]) for x in range(j, k) if lines[x].strip())
            j = k
            continue
        if not s.strip():
            # linha em branco: continua só se a próxima não vazia tem recuo e não é item de mesmo nível
            k = j + 1
            while k < n and not lines[k].strip():
                k += 1
            if k >= n:
                j = k
                break
            nxt = lines[k]
            mbn = BULLET.match(nxt) if _ind(nxt) <= 4 else None
            if _ind(nxt) == 0 or _is_stop(nxt) or (mbn and _ind(nxt) <= ind):
                j = k
                break
            j = k
            continue
        if _ind(s) == 0 and s.lstrip().startswith(("->", "~>", "!>")):
            break
        b.lines.append((j + 1, s))
        j += 1
    text = " ".join(t for _, t in b.lines)
    b.links = LINK_NESTED.findall(text)
    return j


def parse_file(path: Path, rel: str) -> Page:
    return parse_text(path.read_text(encoding="utf-8", errors="replace"), rel)
