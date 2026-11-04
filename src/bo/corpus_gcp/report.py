"""Números do módulo, re-medidos das saídas em $BO_DATA/CORPUS-GCP, para results/CORPUS-GCP/counts.json.

  python -I -m bo.corpus_gcp.report

Também grava results/CORPUS-GCP/MANIFEST.sha256 (counts.json, summary.json e as saídas de dado, com caminho
portátil). Rode depois do provenance.py record (o summary.json entra no manifesto).
"""

from __future__ import annotations

import json
import sys

from . import common as C

TOP = 25


def measure() -> dict:
    d = C.out_dir()
    cov = json.load(open(d / "coverage.json", encoding="utf-8"))
    atoms = [json.loads(x) for x in open(d / "atom_totals.jsonl", encoding="utf-8")]
    repos, fams = set(), set()
    n_rows = 0
    for ln in open(d / "usage.jsonl", encoding="utf-8"):
        u = json.loads(ln)
        n_rows += 1
        repos.add(u["repo_id"])
        fams.add(u["family_id"])
    seen = [a for a in atoms if a["n_repos"] > 0]
    n_set = sum(a["n_resources"] for a in atoms)
    lit = sum(a["n_literal"] for a in atoms)
    sym = sum(a["n_symbolic"] for a in atoms)
    wh = sum(a["n_withheld"] for a in atoms)
    kinds: dict[str, int] = {}
    for a in atoms:
        for k, v in a["records_by_kind"].items():
            kinds[k] = kinds.get(k, 0) + v
    c = cov["counters"]
    rec_total = sum(v for k, v in c.items() if k.startswith("records:"))
    top = sorted(seen, key=lambda a: (-a["n_repos"], a["atom_id"]))[:TOP]
    out = {
        "schema": "bo.corpus_gcp.counts/1", "module": C.MODULE, "provider": "google",
        "provider_versions": cov["provider_versions"],
        "repos_with_google_block": cov["n_repos"], "repos_with_managed_google": len(repos),
        "families_with_managed_google": len(fams), "usage_rows": n_rows,
        "modules_with_managed_google": c.get("modules_managed", 0),
        "managed_resources": c.get("resources_managed", 0),
        "managed_resources_type_in_schema": c.get("resources_schema_type", 0),
        "managed_resources_type_not_in_schema": c.get("resources_unknown_type", 0),
        "data_source_blocks_excluded": c.get("data_source_blocks", 0),
        "corpus_types": cov["corpus_types"], "corpus_types_not_in_schema": cov["corpus_types_unknown"],
        "schema_types": cov["schema_types"], "schema_types_seen": cov["schema_types_seen"],
        "schema_atoms": cov["schema_atoms"], "schema_atoms_seen": len(seen),
        "schema_atoms_seen_ge5_repos": sum(1 for a in seen if a["n_repos"] >= 5),
        "schema_atoms_seen_ge5_families": sum(1 for a in seen if a["n_families"] >= 5),
        "atom_resource_pairs_set": n_set,
        "atom_resource_pairs_class": {"literal": lit, "symbolic": sym, "withheld": wh},
        "records_google_managed_by_category": {k.split(":", 1)[1]: v for k, v in sorted(c.items())
                                               if k.startswith("records:")},
        "records_google_managed_total": rec_total,
        "records_on_atoms_by_term_kind": dict(sorted(kinds.items())),
        "checks": cov["checks"],
        "top_atoms_by_repos": [{k: a[k] for k in ("atom_id", "n_repos", "n_families", "n_modules", "n_resources",
                                                  "n_literal", "n_symbolic", "n_withheld")} for a in top],
        "top_types_not_in_schema": cov["unknown_types"][:10],
        "top_unmatched_paths": cov["unmatched_paths"][:10],
    }
    return out


def main(argv=None) -> int:
    res = C.results_dir()
    out = measure()
    C.write_json(res / "counts.json", out)
    names = [res / "counts.json", res / "summary.json"] + \
        [C.out_dir() / n for n in ("usage.jsonl", "atom_totals.jsonl", "type_totals.jsonl", "coverage.json",
                                   "build_report.json")]
    lines = [f"{C.sha256_file(p)}  {C.portable(p)}\n" for p in names if p.is_file()]
    (res / "MANIFEST.sha256").write_text("".join(lines), encoding="utf-8")
    print(f"[{C.now()}] corpus_gcp.report: {out['repos_with_managed_google']} repositórios, "
          f"{out['managed_resources']} blocos, {out['schema_atoms_seen']}/{out['schema_atoms']} átomos vistos; "
          f"manifesto com {len(lines)} arquivo(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
