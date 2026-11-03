"""Gate 'python -I -m bo.docs.coverage DOCS-OCI' (o despachante chama este main).

Relata, sem meta, a % de átomos do oci com descrição, valores válidos (enum) e unidade, recontando direto
de $BO_DATA/DOCS-OCI/docs_facts.jsonl contra os átomos do schema fixado, e confere que o
results/DOCS-OCI/coverage.json (C15) diz o mesmo. Sai 1 só se faltar arquivo ou se o relatório divergir
da recontagem; o número em si nunca reprova.
"""

from __future__ import annotations

import json
import sys

from bo.schema import core as schema_core

from . import build, source

KINDS = {"description": "M-DOCS-OCI-DESC", "allowed_values": "M-DOCS-OCI-ENUM", "unit": "M-DOCS-OCI-UNIT"}


def recount() -> dict:
    ver = source.version()
    ps = build.load_schema(ver)
    atoms = {a["atom_id"]: a for ts in schema_core.iter_types(ps, "oci", ver) for a in ts.atoms}
    has = {k: set() for k in KINDS}
    pub_unit = set()
    stray = 0
    with open(build.out_dir() / "docs_facts.jsonl", encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            if r["atom_id"] not in atoms:
                stray += 1
                continue
            if r["status"] == "stated" and r["fact_kind"] in has:
                has[r["fact_kind"]].add(r["atom_id"])
                if r["fact_kind"] == "unit" and r["evidence_level"] == "published":
                    pub_unit.add(r["atom_id"])
    cfg = {a for a, x in atoms.items() if x["configurable"]}
    return {"n": len(atoms), "has": has, "pub_unit": pub_unit, "cfg": cfg, "stray": stray}


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    covp = build.results_dir() / "coverage.json"
    if not covp.exists() or not (build.out_dir() / "docs_facts.jsonl").exists():
        print("coverage DOCS-OCI: falta coverage.json ou docs_facts.jsonl (rode python -I -m bo.docs_oci.build)")
        return 1
    rc = recount()
    cov = json.loads(covp.read_text(encoding="utf-8"))
    by_id = {m["metric_id"]: m for m in cov["metrics"]}
    problems = []
    if rc["stray"]:
        problems.append(f"{rc['stray']} fato(s) com atom_id fora dos átomos do schema fixado")
    n = rc["n"]
    print(f"coverage DOCS-OCI (oci {source.version()}, {n} átomos, {len(rc['cfg'])} configuráveis) — relatado, sem meta")
    for k, mid in KINDS.items():
        got = len(rc["has"][k])
        est = round(got / n, 6) if n else 0.0
        m = by_id.get(mid)
        if m is None:
            problems.append(f"{mid} ausente no coverage.json")
        elif m["operational_coverage"]["est"] != est or m["operational_coverage"]["n"] != n:
            problems.append(f"{mid}: relatório diz {m['operational_coverage']}, recontagem dá est={est} n={n}")
        pc = 100 * len(rc["has"][k] & rc["cfg"]) / len(rc["cfg"]) if rc["cfg"] else 0.0
        print(f"  {k:15s} {got:6d}/{n} = {100 * est:6.2f}%   (configuráveis: {pc:6.2f}%)")
    pu = len(rc["pub_unit"])
    print(f"  unit (só publicada) {pu:6d}/{n} = {100 * pu / n:6.2f}%")
    if cov["data"]["atoms_with"] != {k: len(v) for k, v in rc["has"].items()}:
        problems.append("data.atoms_with diverge da recontagem")
    if problems:
        print("DIVERGÊNCIA: " + "; ".join(problems))
        return 1
    print("coverage.json confere com a recontagem")
    return 0


if __name__ == "__main__":
    sys.exit(main())
