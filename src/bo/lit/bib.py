"""BibTeX mínimo (só biblioteca padrão): escrever as entradas do data.py e ler o .bib de volta.

O leitor aceita @tipo{chave, campo = {valor com {chaves} aninhadas}, campo = "valor", campo = 123}.
Comentários (% ...) e @comment são ignorados. Chave repetida é erro.
"""
from __future__ import annotations

import re

HEADER = ("% related.bib -- trabalhos relacionados do BrevOps Ontology (módulo LIT).\n"
          "% Gerado por python -I -m bo.lit.build a partir de src/bo/lit/data.py; não editar à mão.\n"
          "% Campos próprios: altid (identificadores alternativos esquema:valor, separados por ' ; '),\n"
          "% crossref_mismatch (diferença declarada frente ao registro do Crossref).\n")


class BibError(ValueError):
    pass


def render_entry(e: dict) -> str:
    keys = [k for k, _ in e["fields"]]
    if len(keys) != len(set(keys)):
        raise BibError(f"{e['key']}: campo repetido")
    width = max(len(k) for k in keys)
    lines = [f"@{e['type']}{{{e['key']},"]
    for i, (k, v) in enumerate(e["fields"]):
        if v.count("{") != v.count("}"):
            raise BibError(f"{e['key']}.{k}: chaves desbalanceadas")
        sep = "," if i < len(e["fields"]) - 1 else ""
        lines.append(f"  {k.ljust(width)} = {{{v}}}{sep}")
    lines.append("}")
    return "\n".join(lines)


def render(entries: list[dict], edited_at: str) -> str:
    seen = set()
    for e in entries:
        if e["key"] in seen:
            raise BibError(f"chave repetida: {e['key']}")
        seen.add(e["key"])
    body = "\n\n".join(render_entry(e) for e in entries)
    return HEADER + f"% Conteúdo editado em {edited_at} (America/Recife).\n\n" + body + "\n"


def _read_value(s: str, i: int) -> tuple[str, int]:
    while i < len(s) and s[i].isspace():
        i += 1
    if i >= len(s):
        raise BibError("valor ausente no fim do arquivo")
    c = s[i]
    if c == "{":
        depth, j = 0, i
        while j < len(s):
            if s[j] == "{":
                depth += 1
            elif s[j] == "}":
                depth -= 1
                if depth == 0:
                    return s[i + 1:j], j + 1
            j += 1
        raise BibError("chave sem fechamento")
    if c == '"':
        j = s.find('"', i + 1)
        if j < 0:
            raise BibError("aspas sem fechamento")
        return s[i + 1:j], j + 1
    m = re.match(r"[A-Za-z0-9_.:-]+", s[i:])
    if not m:
        raise BibError(f"valor inválido perto de {s[i:i + 20]!r}")
    return m.group(0), i + m.end()


def parse(text: str) -> list[dict]:
    """Devolve [{'type','key','fields': {campo: valor}, 'line'}]; campos em minúsculas."""
    out, keys = [], set()
    i = 0
    clean = "\n".join("" if ln.lstrip().startswith("%") else ln for ln in text.splitlines())
    while True:
        at = clean.find("@", i)
        if at < 0:
            break
        m = re.match(r"@([A-Za-z]+)\s*\{", clean[at:])
        if not m:
            raise BibError(f"entrada malformada na posição {at}")
        typ = m.group(1).lower()
        j = at + m.end()
        line = clean.count("\n", 0, at) + 1
        if typ in ("comment", "preamble", "string"):
            _, i = _read_value(clean, j - 1)
            continue
        km = re.match(r"\s*([^,\s]+)\s*,", clean[j:])
        if not km:
            raise BibError(f"linha {line}: entrada sem chave")
        key = km.group(1)
        if key in keys:
            raise BibError(f"linha {line}: chave repetida {key}")
        keys.add(key)
        j += km.end()
        fields = {}
        while True:
            while j < len(clean) and (clean[j].isspace() or clean[j] == ","):
                j += 1
            if j >= len(clean):
                raise BibError(f"{key}: entrada sem fechamento")
            if clean[j] == "}":
                j += 1
                break
            fm = re.match(r"([A-Za-z_][A-Za-z0-9_-]*)\s*=", clean[j:])
            if not fm:
                raise BibError(f"{key}: campo malformado perto de {clean[j:j + 30]!r}")
            name = fm.group(1).lower()
            val, j = _read_value(clean, j + fm.end())
            if name in fields:
                raise BibError(f"{key}: campo repetido {name}")
            fields[name] = re.sub(r"\s+", " ", val).strip()
        out.append({"type": typ, "key": key, "fields": fields, "line": line})
        i = j
    return out


def split_altids(v: str | None) -> list[tuple[str, str]]:
    out = []
    for part in (v or "").split(" ; "):
        part = part.strip()
        if not part:
            continue
        scheme, sep, val = part.partition(":")
        if not sep or not val.strip():
            raise BibError(f"altid sem esquema:valor: {part!r}")
        out.append((scheme.strip().lower(), val.strip()))
    return out


def authors(v: str | None) -> list[str]:
    """Lista de autores como no .bib ('Sobrenome, Nome' ou '{Instituição}')."""
    return [a.strip() for a in re.split(r"\s+and\s+", v or "") if a.strip()]


def family(a: str) -> str:
    a = a.strip()
    if a.startswith("{") and a.endswith("}"):
        return a[1:-1]
    return a.split(",", 1)[0].strip() if "," in a else a.split()[-1]
