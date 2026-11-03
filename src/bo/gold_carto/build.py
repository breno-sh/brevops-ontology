"""Gera o ouro do Cartography (C09) e os artefatos de apoio, ou confere que a regeneração é idêntica.

  python -I -m bo.gold_carto.build            grava as saídas
  python -I -m bo.gold_carto.build --check    regenera em memória e compara byte a byte (relatório: menos o carimbo)

Saídas
  $BO_DATA/GOLD-CARTO/cartography.sssom.tsv     C09 3.0.0: publicadas + derivadas (AWS, GCP, Azure)
  $BO_DATA/GOLD-CARTO/field_mappings.jsonl      os OntologyFieldMapping em escopo, como lidos (arquivo:linha)
  $BO_DATA/GOLD-CARTO/api_fields.jsonl          registro de campos de API (PropertyRef) dos rótulos citados
  $BO_REPO/results/GOLD-CARTO/conversion_report.json   contagens, regras e estatística da derivação
  $BO_REPO/results/GOLD-CARTO/MANIFEST.sha256          C17
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

from bo.contracts.sssom import write_tsv
from bo.semantics import sssom_io as SIO

from . import (LICENSE_URI, MODULE_ID, PROVIDERS, SOURCE_COMMIT, SOURCE_COMMIT_DATE, SOURCE_REPO, SOURCE_TAG,
               TARBALL, TARBALL_SHA256)
from . import convert as C
from . import extract as X
from .resolve import Index

DEFAULT_BO_DATA = "/Users/breno/doutorado/brevops-data"


def bo_data() -> Path:
    return Path(os.environ.get("BO_DATA") or DEFAULT_BO_DATA)


def bo_repo() -> Path:
    v = os.environ.get("BO_REPO")
    return Path(v) if v else Path(__file__).resolve().parents[3]


def data_dir() -> Path:
    return bo_data() / MODULE_ID


def download_dir() -> Path:
    return bo_data() / "downloads" / "cartography"


def results_dir() -> Path:
    return bo_repo() / "results" / MODULE_ID


def now() -> str:
    import datetime as dt
    from zoneinfo import ZoneInfo
    return dt.datetime.now(ZoneInfo("America/Recife")).isoformat(timespec="seconds")


def _jsonl(rows) -> str:
    return "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in rows)


def generate() -> dict:
    """Tudo em memória: {nome: texto} + o relatório (sem carimbo)."""
    src = X.Source(download_dir() / TARBALL)
    fm = X.field_mappings(src)
    registry = X.api_field_registry(src)
    idx = Index(registry)
    pub = []
    for r in fm["in_scope"]:
        pub.extend(C.published(r, idx.resolve))
    ids = [r["claim_id"] for r in pub]
    dup = sorted({i for i in ids if ids.count(i) > 1})
    if dup:
        raise ValueError(f"claim_id publicado repetido: {dup[:5]}")
    der, dstats = C.derived(pub)
    records = sorted(pub, key=lambda r: r["claim_id"]) + der
    cited = {(r["node_label"]) for r in fm["in_scope"]}
    reg_cited = [r for r in registry if r["node_label"] in cited]
    prefixes = dict(SIO.PREFIXES) | C.PREFIXES
    tsv = write_tsv(records, C.MAPPING_SET_ID, prefixes)
    cc0 = f"# license: {SIO.LICENSE}\n"
    if tsv.count(cc0) != 1:
        raise ValueError("cabeçalho SSSOM sem a linha de licença esperada")
    tsv = tsv.replace(cc0, f"# license: {LICENSE_URI}\n")

    def count(rows, key):
        out = {}
        for r in rows:
            k = key(r)
            out[k] = out.get(k, 0) + 1
        return dict(sorted(out.items()))

    pub_other = [json.loads(r["other"]) for r in pub]
    res_status = {}
    for o in pub_other:
        st = o["resolution"][0]["status"]
        res_status[st] = res_status.get(st, 0) + 1
    report = {
        "schema": "bo.gold_carto.report/1", "module": MODULE_ID,
        "source": {"repo": SOURCE_REPO, "tag": SOURCE_TAG, "commit": SOURCE_COMMIT,
                   "commit_date": SOURCE_COMMIT_DATE, "tarball": f"$BO_DATA/downloads/cartography/{TARBALL}",
                   "tarball_sha256": TARBALL_SHA256, "license": LICENSE_URI,
                   "read_as": "texto (ast.parse), sem import e sem execução"},
        "scope": {"providers": list(PROVIDERS),
                  "field_mappings_all_modules": len(fm["rows"]),
                  "field_mappings_per_module": fm["per_module"],
                  "field_mappings_in_scope": len(fm["in_scope"]),
                  "out_of_scope_note": "só aws, gcp e azure (brief); oci tem "
                                       f"{fm['per_module'].get('oci', 0)} OntologyFieldMapping no mesmo commit, fora "
                                       "do escopo deste módulo"},
        "rules": {str(k): {"semantic_relation": v[0], "transport_fidelity": v[1], "why": v[2]}
                  for k, v in C.RULES.items()},
        "field_mappings_in_scope": {
            "by_provider": count(fm["in_scope"], lambda r: r["module"]),
            "by_special_handling": count(fm["in_scope"], lambda r: str(r["special_handling"])),
            "by_category": count(fm["in_scope"], lambda r: r["category"]),
            "by_registry": count(fm["in_scope"], lambda r: r["registry"]),
        },
        "published_rows": {
            "total": len(pub), "by_provider": count(pub, C.pa_of),
            "by_semantic_relation": count(pub, lambda r: r["semantic_relation"]),
            "by_evidence_state": count(pub, lambda r: r["evidence_state"]),
            "subject_field_resolution": dict(sorted(res_status.items())),
        },
        "derived_rows": {
            "total": len(der),
            "by_pair": count(der, lambda r: f"{C.pa_of(r)}->{r['object_id'].split(':', 1)[0][6:]}"),
            "by_semantic_relation": count(der, lambda r: r["semantic_relation"]),
            "by_evidence_state": count(der, lambda r: r["evidence_state"]),
            "derivation": dstats,
        },
        "api_field_registry": {"node_schemas_entries_all": len(registry),
                               "node_labels_all": len({r["node_label"] for r in registry}),
                               "entries_for_cited_labels": len(reg_cited),
                               "cited_node_labels": len(cited),
                               "cited_labels_without_schema": sorted(l for l in cited if l not in idx.by)},
        "total_rows": len(records),
        "notes": [
            "Âncoras e derivadas são de API (campos de nó do Cartography), não de Terraform: a ponte "
            "API->Terraform é do SERVICE-EVIDENCE e é avaliada no GOLD-AUDIT.",
            "Estado de evidência máximo aqui é STRUCTURALLY_VALID (campo resolvido no registro do próprio "
            "Cartography); nenhuma linha tem testes de valor, logo o árbitro deve dar UNPROVEN às transportadoras.",
            "Derivadas: relação pela tabela formal (compose com K-LEGS e K-DOMAIN desligados); o resultado do "
            "hub sem desligar regras vai em other.hub_outcome.",
            "Silêncio do Cartography (campo sem mapeamento) não é negativo.",
        ],
    }
    files = {
        "cartography.sssom.tsv": tsv,
        "field_mappings.jsonl": _jsonl(fm["in_scope"]),
        "api_fields.jsonl": _jsonl(reg_cited),
    }
    return {"files": files, "report": report, "records": records}


def _report_text(report: dict, stamp: str) -> str:
    return json.dumps({"generated_at": stamp, **report}, ensure_ascii=False, indent=1, sort_keys=False) + "\n"


def write(out: dict) -> list[Path]:
    d, rd = data_dir(), results_dir()
    d.mkdir(parents=True, exist_ok=True)
    rd.mkdir(parents=True, exist_ok=True)
    written = []
    for name, text in out["files"].items():
        p = d / name
        p.write_text(text, encoding="utf-8")
        written.append(p)
    rp = rd / "conversion_report.json"
    rp.write_text(_report_text(out["report"], now()), encoding="utf-8")
    written.append(rp)
    lines = []
    for p in [download_dir() / TARBALL, download_dir() / "SOURCE.txt"] + written:
        lines.append(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {portable(p)}")
    (rd / "MANIFEST.sha256").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return written


def portable(p: Path) -> str:
    s = str(p)
    for var, base in (("$BO_DATA", str(bo_data())), ("$BO_REPO", str(bo_repo()))):
        if s.startswith(base + "/"):
            return var + s[len(base):]
    return s


def check(out: dict) -> list[str]:
    probs = []
    for name, text in out["files"].items():
        p = data_dir() / name
        if not p.is_file():
            probs.append(f"{p} ausente")
        elif p.read_text(encoding="utf-8") != text:
            probs.append(f"{p} difere da regeneração")
    rp = results_dir() / "conversion_report.json"
    if not rp.is_file():
        probs.append(f"{rp} ausente")
    else:
        cur = json.loads(rp.read_text(encoding="utf-8"))
        stamp = cur.pop("generated_at", None)
        if not stamp:
            probs.append("conversion_report.json sem generated_at")
        if json.dumps(cur, sort_keys=True, ensure_ascii=False) != json.dumps(
                json.loads(json.dumps(out["report"], ensure_ascii=False)), sort_keys=True, ensure_ascii=False):
            probs.append("conversion_report.json difere da regeneração")
    return probs


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    out = generate()
    r = out["report"]
    msg = (f"{MODULE_ID}: {r['scope']['field_mappings_in_scope']} OntologyFieldMapping em escopo -> "
           f"{r['published_rows']['total']} publicadas + {r['derived_rows']['total']} derivadas = {r['total_rows']}")
    if "--check" in argv:
        probs = check(out)
        for p in probs:
            print("FAIL", p)
        print(msg, "| regeneração", "idêntica" if not probs else "DIFERENTE")
        return 1 if probs else 0
    for p in write(out):
        print("gravado", portable(p))
    print(msg)
    return 0


if __name__ == "__main__":
    sys.exit(main())
