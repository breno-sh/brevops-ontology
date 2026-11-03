"""Gate G3 do LIT: as duas entradas CoCoOn registradas com autores, ano e venue.

  python -I -m bo.lit.cocoon_disambiguation [--bib ARQ] [--json ARQ] [--csv ARQ] [--html ARQ] [--ledger ARQ]

O PDF de Kalinin e Skvortsov (referência [16]) e a revisão R4 citam entradas distintas para o CoCoOn.
Confere que o related.bib tem as duas, cada uma com autores, ano, venue (booktitle) e DOI que resolve no
Crossref; que são obras distintas (DOI, ano e primeiro autor diferentes); que o registro
results/LIT/cocoon_disambiguation.json bate com o .bib e diz quem cita qual (uma o artigo de Kalinin, a
outra a R4); que a matriz tem linha para cada uma; e que o RELATED_WORK.html explica a resolução.
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from bo.repo import core

from . import bib, ids, verify
from .matrix_check import html_section, plain


def check(bib_path: Path, js_path: Path, csv_path: Path, html_path: Path, led_path: Path) -> tuple[list[str], list[dict]]:
    errs: list[str] = []
    E = errs.append
    entries = bib.parse(bib_path.read_text(encoding="utf-8"))
    ledger = json.loads(led_path.read_text(encoding="utf-8"))
    coc = [e for e in entries if "cocoon" in (e["fields"].get("title", "") + " " + e["fields"].get("note", "")).lower()]
    if len(coc) < 2:
        E(f"esperadas 2 entradas CoCoOn no .bib, achadas {len(coc)}")
        return errs, coc
    info = []
    for e in coc:
        f = e["fields"]
        au = bib.authors(f.get("author"))
        for fld, ok in (("author", bool(au)), ("year", bool(f.get("year"))), ("booktitle", bool(f.get("booktitle"))),
                        ("doi", bool(f.get("doi")))):
            if not ok:
                E(f"{e['key']}: campo {fld} ausente")
        vd = verify.check_entry(e, ledger)
        if not vd.ok or vd.basis != "doi_crossref":
            E(f"{e['key']}: DOI não confirmado no Crossref: {'; '.join(vd.problems)[:200]}")
        info.append((e["key"], ids.norm_doi(f.get("doi", "")), f.get("year"), au[0] if au else ""))
    if len({i[1] for i in info}) != len(info):
        E("entradas CoCoOn com o mesmo DOI")
    if len({i[2] for i in info}) != len(info):
        E("entradas CoCoOn com o mesmo ano (não desambigua)")
    if len({i[3] for i in info}) != len(info):
        E("entradas CoCoOn com o mesmo primeiro autor (não desambigua)")

    if not js_path.is_file():
        E(f"registro ausente: {js_path}")
    else:
        js = json.loads(js_path.read_text(encoding="utf-8"))
        jkeys = {x["bibkey"]: x for x in js.get("entries", [])}
        if set(jkeys) != {e["key"] for e in coc}:
            E(f"registro e .bib divergem nas chaves: {sorted(jkeys)} x {sorted(e['key'] for e in coc)}")
        for e in coc:
            j, f = jkeys.get(e["key"]), e["fields"]
            if not j:
                continue
            if j.get("authors") != bib.authors(f.get("author")) or j.get("year") != f.get("year") \
                    or j.get("venue") != f.get("booktitle") or ids.norm_doi(j.get("doi", "")) != ids.norm_doi(f.get("doi", "")):
                E(f"{e['key']}: registro diverge do .bib (autores, ano, venue ou DOI)")
            if not j.get("cited_by"):
                E(f"{e['key']}: registro sem cited_by")
        cites = " | ".join(x.get("cited_by", "") for x in js.get("entries", []))
        if "Kalinin" not in cites or "R4" not in cites:
            E("registro não diz qual entrada o artigo de Kalinin cita e qual a R4 cita")
        if not js.get("resolution"):
            E("registro sem a resolução escrita")

    with open(csv_path, encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    for e in coc:
        if not any(e["key"] in (r.get("bibkeys") or "").split(";") for r in rows):
            E(f"{e['key']}: sem linha na matriz")
    sec = plain(html_section(html_path.read_text(encoding="utf-8"), "cocoon"))
    if not sec:
        E("RELATED_WORK.html sem a seção id=cocoon")
    else:
        for e in coc:
            if e["fields"].get("doi", "") not in sec:
                E(f"seção CoCoOn do RELATED_WORK.html não cita o DOI de {e['key']}")
    return errs, coc


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -I -m bo.lit.cocoon_disambiguation")
    for k in ("bib", "json", "csv", "html", "ledger"):
        ap.add_argument("--" + k, default=None)
    a = ap.parse_args(argv)
    root = ids.repo_root()
    p = {
        "bib": Path(a.bib) if a.bib else root / "lit" / "related.bib",
        "json": Path(a.json) if a.json else root / "results" / "LIT" / "cocoon_disambiguation.json",
        "csv": Path(a.csv) if a.csv else root / "lit" / "positioning_matrix.csv",
        "html": Path(a.html) if a.html else root / "lit" / "RELATED_WORK.html",
        "ledger": Path(a.ledger) if a.ledger else root / ids.LEDGER_REL,
    }
    for k in ("bib", "csv", "html", "ledger"):
        if not p[k].is_file():
            raise core.BoError(f"{k} ausente: {p[k]}")
    errs, coc = check(p["bib"], p["json"], p["csv"], p["html"], p["ledger"])
    for e in errs:
        core.emit(f"FALHA {e}")
    for e in coc:
        f = e["fields"]
        core.emit(f"  {e['key']}: {bib.authors(f.get('author'))[0] if f.get('author') else '?'} et al., "
                  f"{f.get('year')}, {f.get('booktitle', '?')[:70]}, doi:{f.get('doi')}")
    core.emit(f"[{core.now()}] CoCoOn: {len(coc)} entradas, {len(errs)} problema(s)")
    return 1 if errs else 0


if __name__ == "__main__":
    core.run_main(main)
