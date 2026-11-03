"""Resolução ao vivo dos identificadores do related.bib e livro de evidência.

  python -I -m bo.lit.resolve [--bib ARQ] [--out ARQ]

Para cada DOI: agência de registro (doi.org/ra) e, se Crossref, o registro (api.crossref.org).
Para cada identificador alternativo: wayback (a cópia arquivada responde 200), commit (a API do
GitHub devolve o mesmo sha), arxiv (a API do arXiv devolve a entrada), isbn (dígito verificador),
std (só formato; vale junto com um wayback da mesma entrada).

Grava results/LIT/id_resolution.json: só metadados bibliográficos públicos e o sha256 da resposta
bruta (a resposta bruta não é guardada). O check_ids confere o .bib contra este livro sem rede;
check_ids --live refaz a resolução e compara.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from bo.repo import core

from . import bib, ids

UA = "brevops-ontology-lit/1.0 (pesquisa academica; resolucao de identificadores)"
SCHEMA = "bo.lit.id_resolution/1"


def http_get(url: str, accept: str | None = None, limit: int | None = None, tries: int = 3) -> tuple[int, bytes, str]:
    hdr = {"User-Agent": UA}
    if accept:
        hdr["Accept"] = accept
    last = None
    for k in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=hdr), timeout=60) as r:
                body = r.read(limit) if limit else r.read()
                return r.status, body, r.geturl()
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504) and k < tries - 1:
                time.sleep(3 * (k + 1))
                last = e
                continue
            return e.code, b"", url
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            last = e
            time.sleep(5 * (k + 1))
    raise core.BoError(f"rede: {url}: {last}")


def years_of(m: dict) -> list[int]:
    out = set()
    for k in ("issued", "published-print", "published-online", "published"):
        dp = (m.get(k) or {}).get("date-parts") or [[None]]
        if dp and dp[0] and dp[0][0]:
            out.add(int(dp[0][0]))
    return sorted(out)


def resolve_doi(doi: str) -> dict:
    d = ids.norm_doi(doi)
    st, body, _ = http_get("https://doi.org/ra/" + urllib.parse.quote(d, safe="/"))
    ra = None
    if st == 200:
        try:
            ra = (json.loads(body)[0] or {}).get("RA")
        except (ValueError, IndexError, KeyError):
            ra = None
    rec = {"scheme": "doi", "value": d, "ra": ra, "ra_http": st}
    if ra == "Crossref":
        st, body, _ = http_get("https://api.crossref.org/works/" + urllib.parse.quote(d, safe="/"))
        rec["crossref_http"] = st
        if st == 200:
            m = json.loads(body)["message"]
            rec.update({
                "status": "ok",
                "response_sha256": hashlib.sha256(body).hexdigest(),
                "title": (m.get("title") or [""])[0],
                "container": (m.get("container-title") or [""])[0],
                "type": m.get("type"),
                "publisher": m.get("publisher"),
                "years": years_of(m),
                "volume": m.get("volume"), "issue": m.get("issue"), "page": m.get("page"),
                "authors": [{"family": a.get("family") or a.get("name") or "", "given": a.get("given") or ""}
                            for a in m.get("author", [])],
            })
        else:
            rec["status"] = "fail"
        time.sleep(0.3)
    else:
        rec["status"] = "not_crossref" if ra else "fail"
    return rec


def resolve_alt(scheme: str, value: str) -> dict:
    rec = {"scheme": scheme, "value": value}
    bad = ids.validate_format(scheme, value)
    if bad:
        rec.update(status="fail", reason=bad)
        return rec
    if scheme == "isbn":
        rec.update(status="ok", method="dígito verificador ISBN-13")
    elif scheme == "std":
        rec.update(status="ok", method="formato; vale só com wayback na mesma entrada")
    elif scheme == "wayback":
        time.sleep(4)  # o Wayback recusa conexão quando as consultas vêm em rajada
        st, body, final = http_get(value.replace("http://web.archive.org/", "https://web.archive.org/", 1), limit=4096)
        rec.update(status="ok" if st == 200 else "fail", http=st,
                   snapshot=ids.WAYBACK_RX.match(value).group(1),
                   final_host=urllib.parse.urlparse(final).netloc)
    elif scheme == "commit":
        o, r, sha = ids.COMMIT_RX.match(value).groups()
        st, body, _ = http_get(f"https://api.github.com/repos/{o}/{r}/commits/{sha}",
                               accept="application/vnd.github+json")
        if st == 200:
            j = json.loads(body)
            ok = j.get("sha") == sha
            rec.update(status="ok" if ok else "fail", http=st, sha=j.get("sha"),
                       committed_at=((j.get("commit") or {}).get("committer") or {}).get("date"),
                       response_sha256=hashlib.sha256(body).hexdigest())
        else:
            rec.update(status="fail", http=st)
    elif scheme == "arxiv":
        st, body, _ = http_get("https://export.arxiv.org/api/query?id_list=" + value)
        t = body.decode("utf-8", "replace")
        entry = t[t.find("<entry>"):] if "<entry>" in t else ""
        title = re.findall(r"<title>(.*?)</title>", entry, flags=re.S)
        doi = re.findall(r"<arxiv:doi[^>]*>(.*?)<", entry)
        rec.update(status="ok" if st == 200 and title else "fail", http=st,
                   title=re.sub(r"\s+", " ", title[0]).strip() if title else "",
                   published_doi=doi[0] if doi else None,
                   response_sha256=hashlib.sha256(body).hexdigest())
    return rec


def run(bib_path: Path, out: Path, reuse_ok: dict | None = None) -> dict:
    """reuse_ok: registros "ok" de um livro anterior que não precisam ser refeitos (--only-failed);
    cada registro mantém o próprio checked_at, então o livro diz quando cada id foi conferido."""
    entries = bib.parse(bib_path.read_text(encoding="utf-8"))
    records: dict[str, dict] = {}
    reuse_ok = reuse_ok or {}
    for e in entries:
        f = e["fields"]
        todo = []
        if f.get("doi"):
            todo.append(("doi", f["doi"]))
        todo += bib.split_altids(f.get("altid"))
        for scheme, value in todo:
            key = ids.id_key(scheme, value)
            if key in records:
                continue
            if reuse_ok.get(key, {}).get("status") == "ok":
                records[key] = reuse_ok[key]
                continue
            try:
                rec = resolve_doi(value) if scheme == "doi" else resolve_alt(scheme, value)
            except core.BoError as ex:
                rec = {"scheme": scheme, "value": value, "status": "fail", "reason": str(ex)[:200]}
            rec["checked_at"] = core.now()
            records[key] = rec
            core.emit(f"  {rec['status']:<12} {key[:110]}")
    ledger = {
        "schema": SCHEMA, "module": "LIT", "resolved_at": core.now(),
        "bib": "$BO_REPO/lit/related.bib", "bib_content_sha256": bib.content_sha256(bib_path.read_text(encoding="utf-8")),
        "sources": {
            "doi_ra": "https://doi.org/ra/<doi>", "crossref": "https://api.crossref.org/works/<doi>",
            "github": "https://api.github.com/repos/<dono>/<repo>/commits/<sha>",
            "arxiv": "https://export.arxiv.org/api/query?id_list=<id>", "wayback": "GET da cópia arquivada",
        },
        "note": "Só metadados bibliográficos públicos e sha256 da resposta bruta; a resposta bruta não é guardada.",
        "records": dict(sorted(records.items())),
    }
    core.write_json(out, ledger)
    n = {s: sum(r["status"] == s for r in records.values()) for s in ("ok", "not_crossref", "fail")}
    log = core.bo_data() / "LIT" / "resolve_runs.jsonl"
    log.parent.mkdir(parents=True, exist_ok=True)
    with open(log, "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"at": ledger["resolved_at"], "ids": len(records), **n}, ensure_ascii=False) + "\n")
    return ledger


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -I -m bo.lit.resolve", description=__doc__.split("\n\n")[0])
    ap.add_argument("--bib", default=None)
    ap.add_argument("--out", default=None)
    ap.add_argument("--only-failed", action="store_true",
                    help="refaz só o que não está ok no livro atual (os ok mantêm o checked_at original)")
    a = ap.parse_args(argv)
    root = ids.repo_root()
    bib_path = Path(a.bib) if a.bib else root / "lit" / "related.bib"
    out = Path(a.out) if a.out else root / ids.LEDGER_REL
    core.emit(f"[{core.now()}] resolvendo identificadores de {bib_path}")
    reuse = {}
    if a.only_failed and out.is_file():
        reuse = json.loads(out.read_text(encoding="utf-8")).get("records", {})
    led = run(bib_path, out, reuse)
    bad = [k for k, r in led["records"].items() if r["status"] == "fail"]
    core.emit(f"[{core.now()}] {len(led['records'])} identificadores; {len(bad)} falha(s) -> {out}")
    for k in bad:
        core.emit(f"  FALHA {k}")
    return 1 if bad else 0


if __name__ == "__main__":
    core.run_main(main)
