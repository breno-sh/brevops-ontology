"""Extrator de tabelas HTML com o contexto de títulos (h2/h3), só com html.parser da biblioteca padrão.

Cada célula guarda segmentos: <br>, <li>, <p> e <div> quebram segmento (é assim que as páginas separam vários
serviços numa célula). O texto de cada segmento tem os espaços colapsados; segmentos vazios somem. Nada da página
é executado: <script> e <style> são ignorados.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from html.parser import HTMLParser

_WS = re.compile(r"\s+")
BREAKS = {"br", "li", "p", "div", "ul", "ol"}
SKIP = {"script", "style", "template", "noscript"}


def norm(s: str) -> str:
    return _WS.sub(" ", s).strip()


@dataclass
class Cell:
    segments: list = field(default_factory=list)
    header: bool = False

    def text(self, sep: str = " ; ") -> str:
        return sep.join(self.segments)


@dataclass
class Table:
    index: int
    h2: str
    h3: str
    rows: list = field(default_factory=list)   # [[Cell]]

    def header(self) -> list[str]:
        for r in self.rows:
            if r and all(c.header for c in r):
                return [c.text() for c in r]
        return []

    def body(self) -> list[list[Cell]]:
        return [r for r in self.rows if r and not all(c.header for c in r)]


class _Parser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tables: list[Table] = []
        self.h2 = self.h3 = ""
        self._heading = None       # (tag, [texto])
        self._skip = 0
        self._depth = 0            # profundidade de <table>
        self._row = None
        self._cell = None
        self._buf: list[str] = []

    # -- segmentos da célula
    def _flush(self):
        if self._cell is not None:
            t = norm("".join(self._buf))
            if t:
                self._cell.segments.append(t)
        self._buf = []

    def handle_starttag(self, tag, attrs):
        if tag in SKIP:
            self._skip += 1
            return
        if self._skip:
            return
        if tag in ("h1", "h2", "h3", "h4") and self._depth == 0:
            self._heading = (tag, [])
            return
        if tag == "table":
            self._depth += 1
            if self._depth == 1:
                self.tables.append(Table(len(self.tables), self.h2, self.h3))
            return
        if self._depth != 1:
            return
        if tag == "tr":
            self._row = []
            self.tables[-1].rows.append(self._row)
        elif tag in ("td", "th") and self._row is not None:
            self._cell = Cell(header=(tag == "th"))
            self._buf = []
            self._row.append(self._cell)
        elif tag in BREAKS and self._cell is not None:
            self._flush()

    def handle_startendtag(self, tag, attrs):
        if tag == "br" and self._depth == 1 and self._cell is not None and not self._skip:
            self._flush()
        else:
            self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
        if tag in SKIP:
            self._skip = max(0, self._skip - 1)
            return
        if self._skip:
            return
        if self._heading and tag == self._heading[0]:
            text = norm("".join(self._heading[1]))
            if tag == "h2":
                self.h2, self.h3 = text, ""
            elif tag == "h3":
                self.h3 = text
            self._heading = None
            return
        if tag == "table":
            if self._depth == 1:
                self._flush()
                self._cell = self._row = None
            self._depth = max(0, self._depth - 1)
            return
        if self._depth != 1:
            return
        if tag in ("td", "th"):
            self._flush()
            self._cell = None
        elif tag == "tr":
            self._flush()
            self._cell = None
            self._row = None
        elif tag in BREAKS and self._cell is not None:
            self._flush()

    def handle_data(self, data):
        if self._skip:
            return
        if self._heading is not None:
            self._heading[1].append(data)
        elif self._cell is not None and self._depth == 1:
            self._buf.append(data)


def tables(html: str) -> list[Table]:
    p = _Parser()
    p.feed(html)
    p.close()
    return p.tables
