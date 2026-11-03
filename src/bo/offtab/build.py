"""Gera as saídas do OFFTAB a partir do HTML (e do pacote da Oracle), nunca dos CSVs publicados.

  python -I -m bo.offtab.build            grava tudo
  python -I -m bo.offtab.build --check    regenera em memória e compara com o que está gravado (sai 1 se diverge)

Saídas ($BO_DATA/OFFTAB/): table_rows.jsonl (linhas normalizadas das três tabelas), services.sssom.tsv (C09),
correspondences.jsonl (C09, mesma coisa decodificada), service_catalog.json, aws_centrality.json.
Saídas ($BO_REPO/results/OFFTAB/): summary.json (bloco results C15 e notas; a proveniência do agente é gravada por
tools/provenance.py record e preservada aqui), MANIFEST.sha256 (C17).
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

from . import audit as A
from . import claims as C
from . import google as G
from . import mentions as MN
from . import microsoft as M
from . import oracle as O
from . import sources as S

TZ = ZoneInfo("America/Recife")
MAPPING_SET_ID = "https://w3id.org/brevops/offtab/mapping-set/services-2026-11-03"
# O escritor do C09 grava CC0 por padrão; aqui não serve: as linhas vêm de documentação CC BY 4.0 (Google, Microsoft)
# e de nomes de serviço da página da Oracle (termos de uso da Oracle). A licença do conjunto é a mais restritiva
# das abertas (CC BY 4.0, com atribuição a cada fornecedor em author_label/mapping_provider).
LICENSE_CC0 = "# license: https://creativecommons.org/publicdomain/zero/1.0/\n"
LICENSE = "# license: https://creativecommons.org/licenses/by/4.0/\n"
CODE_FILES = ("__init__.py", "sources.py", "htmltables.py", "google.py", "microsoft.py", "oracle.py", "mentions.py",
              "claims.py", "audit.py", "build.py", "repro.py")


def now() -> str:
    return dt.datetime.now(TZ).replace(microsecond=0).isoformat()


def repo_root() -> Path:
    return Path(os.environ.get("BO_REPO") or Path(__file__).resolve().parents[3])


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def jdump(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=1, sort_keys=False) + "\n"


def collect() -> dict:
    g_rows, g_sha = G.parse_file()
    m_rows, m_shas = M.parse_dir()
    m_sup = M.supplement()
    o_rows, o_meta = O.parse_dir()
    rows = C.table_rows(g_rows, m_rows, m_sup, o_rows)
    return {"google": g_rows, "google_sha": g_sha, "ms": m_rows, "ms_shas": m_shas, "ms_sup": m_sup,
            "oracle": o_rows, "oracle_meta": o_meta, "rows": rows}


def render(d: dict, generated_at: str) -> dict:
    """{nome: bytes} das saídas determinísticas, mais os blocos que levam data (aws_centrality, summary)."""
    from bo.contracts import sssom as CS
    rows = d["rows"]
    recs = C.correspondences(rows)
    prefixes = {**MN.CURIE_MAP, "bo": "https://w3id.org/brevops/ontology#",
                "semapv": "https://w3id.org/semapv/vocab/", "skos": "http://www.w3.org/2004/02/skos/core#"}
    tsv = CS.write_tsv(recs, MAPPING_SET_ID, prefixes)
    if tsv.count(LICENSE_CC0) != 1:
        raise RuntimeError("cabeçalho SSSOM sem a linha de licença esperada (mudou o escritor do C09?)")
    tsv = tsv.replace(LICENSE_CC0, LICENSE, 1)
    rows_b = "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in rows).encode()
    jsonl_b = "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in recs).encode()
    cat = C.catalog(rows)
    tables = {
        "google": {"title": S.GOOGLE["title"], "url": S.GOOGLE["url"], "retrieved_utc": S.GOOGLE["retrieved_utc"],
                   "html": {"page.html": d["google_sha"]}, "rows_main": len(d["google"]), "pivot": "gcp",
                   "columns": ["gcp", "aws", "azure"]},
        "microsoft": {"title": S.MICROSOFT["title"], "url": S.MICROSOFT["url"],
                      "retrieved_utc": S.MICROSOFT["retrieved_utc"],
                      "html": {f"{p}.html": s for p, s in d["ms_shas"].items()}, "rows_main": len(d["ms"]),
                      "rows_supplement": len(d["ms_sup"]), "pivot": "aws", "columns": ["aws", "azure"]},
        "oracle": {"title": S.ORACLE["title"], "url": S.ORACLE["url"], "retrieved_utc": S.ORACLE["retrieved_utc"],
                   "html": {k: v["sha256"] for k, v in S.ORACLE_FILES.items()},
                   "build_date": d["oracle_meta"]["build_date"], "rows_main": len(d["oracle"]), "pivot": "oci",
                   "columns": ["oci", "aws", "azure", "gcp"]},
    }
    catalog = {
        "schema": "bo.offtab.service_catalog/1", "module": "OFFTAB",
        "scope": "só auditoria: serviços como os fornecedores os nomeiam nas tabelas de comparação; não define "
                 "universo nem classe; id = prefixo do provedor + slug do rótulo (sem resolver sinônimo)",
        "split_rule": "célula -> menções: ' ; ' (quebra da página), ', ' fora de parênteses, tira 'or '/'and ' "
                      "após vírgula; 'A or B' sem vírgula fica uma menção (compound=true)",
        "curie_map": MN.CURIE_MAP, "tables": tables, "n_services": len(cat),
        "n_services_by_provider": C.provider_counts(cat), "n_claims": len(recs), "services": cat,
    }
    cat_b = jdump(catalog).encode()
    rows_ref = {"path": "$BO_DATA/OFFTAB/table_rows.jsonl", "sha256": sha(rows_b)}
    gaps, rch = A.row_gaps(rows), A.reach(rows)
    mets = A.metrics(gaps, rch, rows_ref)
    centr = {"schema": "bo.offtab.aws_centrality/1", "module": "OFFTAB", "generated_at": generated_at,
             "frame": rows_ref, "reading": A.__doc__.strip(), "row_gaps": gaps, "reach": rch,
             "verdict": A.verdict(gaps, rch)}
    return {"files": {"table_rows.jsonl": rows_b, "services.sssom.tsv": tsv.encode(),
                      "correspondences.jsonl": jsonl_b, "service_catalog.json": cat_b},
            "centrality": centr, "metrics": mets, "recs": recs, "catalog": catalog, "gaps": gaps, "reach": rch}


def notes(out: dict, d: dict) -> str:
    v = out["centrality"]["verdict"]
    return ("OFFTAB (só auditoria; não define universo nem classes). Tabelas: Google 223 linhas (pivô GCP), "
            f"Microsoft 205 (pivô AWS) + {len(d['ms_sup'])} linhas de suplemento fora das 205 (lado 'Microsoft "
            "service'), Oracle 160 (pivô OCI; JSON embutido no pacote da página, buildDate "
            f"{d['oracle_meta']['build_date']}). {len(out['recs'])} alegações skos:relatedMatch sem transporte. "
            "Leitura: " + "; ".join(v) + ".")


def summary_obj(existing: dict, out: dict, d: dict, generated_at: str) -> dict:
    s = dict(existing or {})
    s.update({"schema": "bo.summary/1", "contract": "C17", "contract_version": "3.0.0", "module": "OFFTAB",
              "generated_at": generated_at})
    s.setdefault("sources", [])
    s["results"] = out["metrics"]
    s["notes"] = notes(out, d)
    order = ("schema", "contract", "contract_version", "module", "generated_at", "agent_provenance", "sources",
             "results", "notes")
    return {k: s[k] for k in order if k in s} | {k: v for k, v in s.items() if k not in order}


def manifest(repo: Path, data_files: dict) -> str:
    lines = []
    for rel in ["gates/OFFTAB.sh"] + [f"src/bo/offtab/{f}" for f in CODE_FILES]:
        p = repo / rel
        if p.is_file():
            lines.append(f"{S.sha256_file(p)}  {rel}")
    for name in sorted(data_files):
        lines.append(f"{sha(data_files[name])}  $BO_DATA/OFFTAB/{name}")
    return "\n".join(lines) + "\n"


def _strip_ts(o: dict) -> dict:
    return {k: v for k, v in o.items() if k != "generated_at"}


def write_all() -> int:
    d = collect()
    ts = now()
    out = render(d, ts)
    od = S.out_dir()
    od.mkdir(parents=True, exist_ok=True)
    for name, b in out["files"].items():
        (od / name).write_bytes(b)
    (od / "aws_centrality.json").write_text(jdump(out["centrality"]), encoding="utf-8")
    repo = repo_root()
    rd = repo / "results" / "OFFTAB"
    rd.mkdir(parents=True, exist_ok=True)
    sp = rd / "summary.json"
    existing = json.loads(sp.read_text(encoding="utf-8")) if sp.is_file() else {}
    sp.write_text(jdump(summary_obj(existing, out, d, ts)), encoding="utf-8")
    (rd / "MANIFEST.sha256").write_text(manifest(repo, out["files"]), encoding="utf-8")
    print(f"[{ts}] OFFTAB: {len(d['google'])} Google, {len(d['ms'])}+{len(d['ms_sup'])} Microsoft, "
          f"{len(d['oracle'])} Oracle; {len(out['recs'])} alegações; {out['catalog']['n_services']} serviços")
    for line in out["centrality"]["verdict"]:
        print("  " + line)
    return 0


def check() -> int:
    d = collect()
    ts = now()
    out = render(d, ts)
    od = S.out_dir()
    bad = []
    for name, b in out["files"].items():
        p = od / name
        if not p.is_file() or p.read_bytes() != b:
            bad.append(str(p))
    p = od / "aws_centrality.json"
    if not p.is_file() or _strip_ts(json.loads(p.read_text(encoding="utf-8"))) != _strip_ts(
            json.loads(jdump(out["centrality"]))):
        bad.append(str(p))
    repo = repo_root()
    sp = repo / "results" / "OFFTAB" / "summary.json"
    if sp.is_file():
        s = json.loads(sp.read_text(encoding="utf-8"))
        want = json.loads(jdump(summary_obj(s, out, d, ts)))
        if s.get("results") != want["results"] or s.get("notes") != want["notes"]:
            bad.append(str(sp))
    else:
        bad.append(str(sp))
    mp = repo / "results" / "OFFTAB" / "MANIFEST.sha256"
    if not mp.is_file() or mp.read_text(encoding="utf-8") != manifest(repo, out["files"]):
        bad.append(str(mp))
    print(f"[{ts}] OFFTAB build --check: " + ("idêntico" if not bad else "DIVERGE: " + ", ".join(bad)))
    return 1 if bad else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="bo.offtab.build")
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)
    return check() if a.check else write_all()


if __name__ == "__main__":
    sys.exit(main())
