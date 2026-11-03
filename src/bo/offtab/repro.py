"""Gate do OFFTAB: as 223 linhas do Google e as 205 da Microsoft saem de novo do HTML, idênticas aos CSVs publicados
em tabelas_oficiais/, e o sha256 de cada HTML confere com o fixado no código, com o SOURCE.txt da pasta e com a
coluna source_html_sha256 de cada linha. A Oracle (160 linhas) é conferida do mesmo jeito contra o SOURCE.txt da
coleta. Por fim, toda alegação de services.sssom.tsv cita URL, data, sha256 conhecido e uma linha que existe.

  python -I -m bo.offtab.repro      sai 0 se tudo confere; relatório em $BO_DATA/OFFTAB/repro_report.json
"""

from __future__ import annotations

import csv
import json
import sys

from . import google as G
from . import microsoft as M
from . import oracle as O
from . import sources as S
from .build import now


def _csv(path) -> list[dict]:
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _cmp_rows(name: str, got: list[dict], ref: list[dict], expect: int, errs: list) -> dict:
    same = sum(1 for a, b in zip(got, ref) if a == b)
    if len(ref) != expect:
        errs.append(f"{name}: CSV publicado tem {len(ref)} linhas, esperava {expect}")
    if len(got) != expect:
        errs.append(f"{name}: HTML reparseado dá {len(got)} linhas, esperava {expect}")
    if same != len(ref) or len(got) != len(ref):
        first = next((i for i, (a, b) in enumerate(zip(got, ref)) if a != b), min(len(got), len(ref)))
        errs.append(f"{name}: {same} de {len(ref)} linhas idênticas; primeira divergência na posição {first + 1}")
    return {"expected": expect, "csv_rows": len(ref), "reparsed_rows": len(got), "identical_rows": same}


def check() -> tuple[dict, list[str]]:
    errs: list[str] = []
    rep: dict = {}

    # Google
    src = S.read_source_txt(S.GOOGLE_DIR)
    rows, sha = G.parse_file()
    ref = _csv(S.GOOGLE_CSV)
    if sha != S.GOOGLE["html_sha256"]:
        errs.append(f"google: sha256 do page.html {sha[:12]}… != fixado {S.GOOGLE['html_sha256'][:12]}…")
    if src.get("page.html") != sha:
        errs.append("google: sha256 do page.html não confere com o SOURCE.txt")
    bad = [r["row"] for r in ref if r["source_html_sha256"] != sha]
    if bad:
        errs.append(f"google: {len(bad)} linha(s) do CSV com source_html_sha256 diferente do HTML")
    rep["google"] = _cmp_rows("google", rows, ref, S.GOOGLE["rows"], errs) | {
        "html_sha256": sha, "source_txt": src.get("page.html") == sha, "csv_sha_column_ok": not bad}

    # Microsoft
    src = S.read_source_txt(S.MS_DIR)
    rows, shas = M.parse_dir()
    ref = _csv(S.MS_CSV)
    for page, s in shas.items():
        if s != S.MS_PAGES[page]:
            errs.append(f"microsoft: sha256 de {page}.html não é o fixado")
        if src.get(f"{page}.html") != s:
            errs.append(f"microsoft: sha256 de {page}.html não confere com o SOURCE.txt")
    bad = [r["row"] for r in ref if r["source_html_sha256"] != shas.get(r["page"])]
    if bad:
        errs.append(f"microsoft: {len(bad)} linha(s) do CSV com source_html_sha256 diferente do HTML da página")
    parsed = _csv(S.MS_DIR / "parsed.csv")
    if parsed != ref:
        errs.append("microsoft: parsed.csv da coleta difere do CSV de tabelas_oficiais/")
    sup = M.supplement()
    rep["microsoft"] = _cmp_rows("microsoft", rows, ref, S.MICROSOFT["rows"], errs) | {
        "html_sha256": shas, "source_txt": all(src.get(f"{p}.html") == s for p, s in shas.items()),
        "csv_sha_column_ok": not bad, "parsed_csv_equal": parsed == ref, "supplement_rows": len(sup)}

    # Oracle
    od = S.oracle_dir()
    src = S.read_source_txt(od)
    files = {}
    for name, meta in S.ORACLE_FILES.items():
        s = S.sha256_file(od / name)
        files[name] = s
        if s != meta["sha256"]:
            errs.append(f"oracle: sha256 de {name} não é o fixado")
        if src.get(name) != s:
            errs.append(f"oracle: sha256 de {name} não confere com o SOURCE.txt")
    errs += [f"oracle: {e}" for e in O.chain_ok(od)]
    orows, ometa = O.parse_dir(od)
    if len(orows) != S.ORACLE["rows"]:
        errs.append(f"oracle: {len(orows)} linhas, esperava {S.ORACLE['rows']}")
    if ometa["build_date"] != S.ORACLE["build_date"]:
        errs.append(f"oracle: buildDate {ometa['build_date']} != {S.ORACLE['build_date']}")
    rep["oracle"] = {"expected": S.ORACLE["rows"], "rows": len(orows), "build_date": ometa["build_date"],
                     "files_sha256": files, "source_txt": all(src.get(n) == s for n, s in files.items())}

    # Alegações: toda evidência cita fonte, data, sha256 conhecido e linha existente
    known = {S.GOOGLE["html_sha256"], *S.MS_PAGES.values(), S.ORACLE["html_sha256"]}
    rows_of = {("google", "main"): {r["row"] for r in G.parse_file()[0]},
               ("microsoft", "main"): {r["row"] for r in rows}, ("microsoft", "supplement"): {r["row"] for r in sup},
               ("oracle", "main"): {r["row"] for r in orows}}
    vendor_of = {"G": "google", "M": "microsoft", "O": "oracle"}
    tsv = S.out_dir() / "services.sssom.tsv"
    n = nbad = 0
    if not tsv.is_file():
        errs.append(f"{tsv} não existe (rode python -I -m bo.offtab.build)")
    else:
        from bo.contracts import sssom as CS
        _, recs, _ = CS.read_tsv(tsv.read_text(encoding="utf-8"))
        for r in recs:
            n += 1
            code = r["claim_id"].split("-")[1]
            vendor = vendor_of[code[0]]
            ev = (r.get("proof") or {}).get("evidence") or [{}]
            e = ev[0]
            ok = (e.get("source", "").startswith("https://") and len(e.get("date", "")) == 10
                  and e.get("html_sha256") in known and e.get("row") in rows_of.get((vendor, e.get("table_set")), ())
                  and r.get("predicate_id") == "skos:relatedMatch" and r.get("transport_fidelity") == "none")
            if not ok:
                nbad += 1
        if nbad:
            errs.append(f"alegações: {nbad} de {n} sem citação completa (URL, data, sha256 conhecido, linha)")
    rep["claims"] = {"n": n, "bad_citation": nbad}
    return rep, errs


def main(argv=None) -> int:
    ts = now()
    rep, errs = check()
    out = {"schema": "bo.offtab.repro_report/1", "module": "OFFTAB", "generated_at": ts, "report": rep,
           "errors": errs, "result": "OK" if not errs else "REPROVADO"}
    od = S.out_dir()
    od.mkdir(parents=True, exist_ok=True)
    (od / "repro_report.json").write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    g, m, o = rep["google"], rep["microsoft"], rep["oracle"]
    print(f"[{ts}] OFFTAB repro")
    print(f"  google    {g['identical_rows']}/{g['expected']} linhas idênticas ao CSV; sha256 HTML "
          f"{'confere' if g['source_txt'] and g['csv_sha_column_ok'] else 'NÃO confere'}")
    print(f"  microsoft {m['identical_rows']}/{m['expected']} linhas idênticas ao CSV; sha256 HTML "
          f"{'confere' if m['source_txt'] and m['csv_sha_column_ok'] else 'NÃO confere'} ({len(m["html_sha256"])} páginas); "
          f"suplemento fora das 205: {m['supplement_rows']}")
    print(f"  oracle    {o['rows']}/{o['expected']} linhas; buildDate {o['build_date']}; sha256 "
          f"{'confere' if o['source_txt'] else 'NÃO confere'}")
    print(f"  alegações {rep['claims']['n']} com citação; {rep['claims']['bad_citation']} incompletas")
    for e in errs:
        print("  FAIL " + e)
    print("RESULTADO: " + ("OK" if not errs else "REPROVADO"))
    return 0 if not errs else 1


if __name__ == "__main__":
    sys.exit(main())
