"""Resultados do HIST-GCP no repositório: contagens por versão e manifesto de results/HIST-GCP/.

  python -I -m bo.hist_gcp.results counts      grava results/HIST-GCP/history_counts.json do extraction.json
  python -I -m bo.hist_gcp.results manifest    grava results/HIST-GCP/MANIFEST.sha256 (gate, contagens, summary)

As contagens são do schema, por versão (tipos, átomos, flags); a diferença entre versões consecutivas é só de
contagem: eventos tipados (adição, renome, remoção, mudança de contrato) são do DRIFT, não daqui.
"""

from __future__ import annotations

import json
import sys

from . import common as C

COUNT_KEYS = ("types", "atoms", "required", "optional", "computed", "configurable", "sensitive", "deprecated",
              "write_only", "data_sources")


def counts_doc(xd: dict, generated_at: str) -> dict:
    rows, prev = [], None
    for r in xd["versions"]:
        row = {"version": r["version"], "released_at": r["released_at"], "status": r["status"]}
        if r["status"] == "extracted":
            row.update({k: r["counts"][k] for k in COUNT_KEYS})
            if prev is not None:
                row["delta_vs_previous_extracted"] = {"from": prev["version"],
                                                      "types": r["counts"]["types"] - prev["counts"]["types"],
                                                      "atoms": r["counts"]["atoms"] - prev["counts"]["atoms"]}
            prev = r
        else:
            row["reason"] = r["reason"]
        rows.append(row)
    ex = [r for r in xd["versions"] if r["status"] == "extracted"]
    return {"schema": "bo.hist_gcp.history_counts/1", "module": C.ID, "generated_at": generated_at,
            "provider": C.PROVIDER, "source": "$BO_DATA/HIST-GCP/extraction.json",
            "totals": xd["totals"],
            "span": {"first_extracted": ex[0]["version"] if ex else None,
                     "last_extracted": ex[-1]["version"] if ex else None,
                     "types": [ex[0]["counts"]["types"], ex[-1]["counts"]["types"]] if ex else None,
                     "atoms": [ex[0]["counts"]["atoms"], ex[-1]["counts"]["atoms"]] if ex else None},
            "versions": rows,
            "note": ("Contagens da superfície do provider Terraform (schema do plugin), não da nuvem. Deltas são "
                     "diferenças de contagem entre versões amostradas consecutivas; eventos tipados ficam no DRIFT.")}


def write_counts() -> dict:
    xd = json.loads((C.out_dir() / "extraction.json").read_text(encoding="utf-8"))
    p = C.results_dir() / "history_counts.json"
    old = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    doc = counts_doc(xd, old.get("generated_at") or C.now())
    if doc != old:
        doc = counts_doc(xd, C.now())
    C.write_json(p, doc)
    return doc


def manifest_text() -> str:
    files = [C.bo_repo() / "gates" / f"{C.ID}.sh"] + sorted(
        p for p in C.results_dir().iterdir() if p.is_file() and p.name != "MANIFEST.sha256")
    return "".join(f"{C.sha256_file(p)}  {p.relative_to(C.bo_repo()).as_posix()}\n" for p in files)


def main(argv=None) -> int:
    args = [a for a in (argv or []) if a != C.ID]
    if args == ["counts"]:
        d = write_counts()
        print(json.dumps({"totals": d["totals"], "span": d["span"]}, ensure_ascii=False))
        return 0
    if args == ["manifest"]:
        (C.results_dir() / "MANIFEST.sha256").write_text(manifest_text(), encoding="utf-8")
        print(manifest_text(), end="")
        return 0
    print("uso: python -I -m bo.hist_gcp.results counts|manifest", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
