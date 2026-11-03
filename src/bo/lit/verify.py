"""Conferência offline de cada entrada do .bib contra o livro de resolução (results/LIT/id_resolution.json).

Uma entrada passa quando:
- tem author, title e year (4 dígitos);
- todo identificador declarado tem formato certo e registro "ok" no livro (nenhum id quebrado);
- tem DOI que resolve no Crossref, com título, ano e autores batendo com o registro (diferença
  de autores só passa se declarada em crossref_mismatch); OU, sem DOI Crossref, ao menos um
  identificador alternativo verificável (isbn, wayback, commit, arxiv). Uma norma (std:) só vale
  junto com um wayback da mesma entrada.
"""
from __future__ import annotations

import difflib
from dataclasses import dataclass, field

from . import bib, ids

TITLE_MIN = 0.85


@dataclass
class Verdict:
    key: str
    ok: bool = True
    basis: str = ""            # "doi_crossref" | "altid" | ""
    verified_ids: list[str] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def bad(self, msg: str) -> None:
        self.ok = False
        self.problems.append(msg)


def title_ratio(a: str, b: str) -> float:
    na, nb = ids.norm_text(a), ids.norm_text(b)
    if not na or not nb:
        return 0.0
    if na == nb or (len(nb) >= 8 and (na.startswith(nb) or nb.startswith(na))):
        return 1.0
    return difflib.SequenceMatcher(None, na, nb).ratio()


def author_found(bib_author: str, cr_authors: list[dict]) -> bool:
    want = ids.tokens(bib.family(bib_author))
    if not want:
        return True
    for a in cr_authors:
        have = ids.tokens(a.get("family", "") + " " + a.get("given", ""))
        if want <= have:
            return True
    return False


def check_entry(e: dict, ledger: dict) -> Verdict:
    f = e["fields"]
    v = Verdict(e["key"])
    recs = (ledger or {}).get("records", {})
    for req in ("author", "title", "year"):
        if not f.get(req):
            v.bad(f"campo obrigatório ausente: {req}")
    if f.get("year") and not (len(f["year"]) == 4 and f["year"].isdigit()):
        v.bad(f"year inválido: {f['year']!r}")

    try:
        alts = bib.split_altids(f.get("altid"))
    except bib.BibError as ex:
        v.bad(str(ex))
        alts = []

    crossref_ok = False
    if f.get("doi"):
        bad = ids.validate_format("doi", f["doi"])
        k = ids.id_key("doi", f["doi"])
        rec = recs.get(k)
        if bad:
            v.bad(f"{k}: {bad}")
        elif not rec:
            v.bad(f"{k}: sem registro no livro de resolução (rode python -I -m bo.lit.resolve)")
        elif rec.get("ra") == "Crossref" and rec.get("status") == "ok":
            mism = f.get("crossref_mismatch", "")
            r = title_ratio(f.get("title", ""), rec.get("title", ""))
            if r < TITLE_MIN:
                v.bad(f"{k}: título difere do Crossref (semelhança {r:.2f})")
            if f.get("year", "").isdigit() and int(f["year"]) not in rec.get("years", []):
                v.bad(f"{k}: ano {f['year']} fora dos anos do Crossref {rec.get('years')}")
            auth = [a for a in bib.authors(f.get("author")) if a.lower() != "others" and not a.startswith("{")]
            missing = [bib.family(a) for a in auth if not author_found(a, rec.get("authors", []))]
            if auth and not author_found(auth[0], rec.get("authors", [])) and "authors:" not in mism:
                v.bad(f"{k}: primeiro autor {bib.family(auth[0])!r} não está no registro do Crossref")
            if missing:
                if "authors:" in mism:
                    v.notes.append(f"{k}: autores fora do Crossref, diferença declarada: {', '.join(missing)}")
                else:
                    v.bad(f"{k}: autores fora do registro do Crossref sem crossref_mismatch: {', '.join(missing)}")
            if not v.problems:
                crossref_ok = True
                v.verified_ids.append(k)
        elif rec.get("status") == "not_crossref":
            v.notes.append(f"{k}: DOI registrado na {rec.get('ra')}, não no Crossref; precisa de altid")
            if not alts:
                v.bad(f"{k}: DOI fora do Crossref ({rec.get('ra')}) e nenhum identificador alternativo declarado")
        else:
            v.bad(f"{k}: DOI não resolveu (status {rec.get('status')})")

    alt_ok = []
    schemes = {s for s, _ in alts}
    for scheme, value in alts:
        k = ids.id_key(scheme, value)
        bad = ids.validate_format(scheme, value)
        if bad:
            v.bad(f"{k[:80]}: {bad}")
            continue
        rec = recs.get(k)
        if not rec:
            v.bad(f"{k[:80]}: sem registro no livro de resolução")
            continue
        if rec.get("status") != "ok":
            v.bad(f"{k[:80]}: não verificou (status {rec.get('status')})")
            continue
        if scheme == "std" and "wayback" not in schemes:
            v.bad(f"{k[:80]}: norma sem cópia arquivada (wayback) na mesma entrada")
            continue
        v.verified_ids.append(k)
        if scheme in ("isbn", "wayback", "commit", "arxiv"):
            alt_ok.append(k)
    if f.get("isbn") and not ids.isbn13_ok(f["isbn"]):
        v.bad("campo isbn com dígito verificador errado")

    if v.ok:
        if crossref_ok:
            v.basis = "doi_crossref"
        elif alt_ok:
            v.basis = "altid"
        else:
            v.bad("nem DOI que resolve no Crossref nem identificador alternativo verificável")
    return v


def check_all(entries: list[dict], ledger: dict) -> list[Verdict]:
    return [check_entry(e, ledger) for e in entries]


def entry_ids(e: dict) -> set[str]:
    f = e["fields"]
    out = set()
    if f.get("doi"):
        out.add(ids.id_key("doi", f["doi"]))
    for s, val in bib.split_altids(f.get("altid")):
        out.add(ids.id_key(s, val))
    return out
