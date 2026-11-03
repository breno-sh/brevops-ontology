"""Cobertura da documentação sobre os átomos do schema fixado (relatada, sem meta).

  python -I -m bo.docs.coverage DOCS-GCP     (despachante do coordenador -> bo.docs_gcp.coverage.main)

Recalcula, a partir de $BO_DATA/DOCS-GCP/docs_facts.jsonl e do schema fixado, a fração de átomos com descrição,
com valores válidos (enum) e com unidade declarados (status stated), confere com results/DOCS-GCP/coverage.json
(sem generated_at) e valida o arquivo como C15 result. Sai 0 se confere; não há limiar: o número é relatado.

É censo, não amostra: o quadro são TODOS os átomos dos tipos de recurso do schema (C01), então o intervalo é
degenerado (lower = est = upper, método exact). Ausência de fato não é auditada aqui (absence_audit fica para os
consumidores).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from . import sources as S

KINDS = ("description", "default", "allowed_values", "range", "unit", "format", "forces_replacement",
         "deprecation", "conflicts_with")
HEAD = (("M-DOCS-GCP-DESC", "description", "átomos com descrição na documentação"),
        ("M-DOCS-GCP-ENUM", "allowed_values", "átomos com valores válidos (enum) na documentação"),
        ("M-DOCS-GCP-UNIT", "unit", "átomos com unidade na documentação"))


def _frac(k: int, n: int):
    return round(k / n, 6) if n else None


def compute(out_dir: Path, types: dict, at: str) -> dict:
    atoms = [a for t in sorted(types) for a in types[t].atoms]
    cfg = {a["atom_id"] for a in atoms if a["configurable"]}
    all_ids = {a["atom_id"] for a in atoms}
    stated: dict = {k: set() for k in KINDS}
    unknown: dict = {}
    n_facts = 0
    with open(out_dir / "docs_facts.jsonl", encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            n_facts += 1
            if r["status"] == "stated":
                stated.setdefault(r["fact_kind"], set()).add(r["atom_id"])
            else:
                key = f"{r['fact_kind']}:{r['unknown_reason']}"
                unknown[key] = unknown.get(key, 0) + 1
    outside = sorted(set().union(*stated.values()) - all_ids)
    n = len(all_ids)
    frame = {"ref": {"path": f"$BO_DATA/downloads/prefetch/{S.PROVIDER}/{S.version()}/providers-schema.json",
                     "sha256": S.pin()["schema_sha256"]},
             "description": f"todos os átomos (atributos em toda profundidade) dos {len(types)} tipos de recurso do "
                            f"schema {S.PROVIDER} {S.version()} fixado no pins.json"}
    metrics = []
    for mid, kind, name in HEAD:
        k = len(stated.get(kind, set()) & all_ids)
        est = _frac(k, n)
        metrics.append({
            "metric_id": mid, "name": name, "reading": "field", "axis": "representability",
            "quantifier": "observed_fraction",
            "operational_coverage": {"lower": est if est is not None else 0.0,
                                     "upper": est if est is not None else 1.0, "est": est, "n": n},
            "frame": frame,
            "inclusion": {"rule_id": "INC-DOCS-ATOM", "text": f"átomo com ao menos um fato {kind} stated "
                                                              f"(extraído de página da tag {S.tag()})"},
            "weights": {"scheme": "uniform"},
            "joint_uncertainty": {"method": "exact"},
        })
    by_kind = {kind: {"atoms": len(stated.get(kind, set()) & all_ids),
                      "frac_all": _frac(len(stated.get(kind, set()) & all_ids), n),
                      "atoms_configurable": len(stated.get(kind, set()) & cfg),
                      "frac_configurable": _frac(len(stated.get(kind, set()) & cfg), len(cfg))} for kind in KINDS}
    three = stated["description"] & stated["allowed_values"] & stated["unit"] & all_ids
    data = {"n_atoms": n, "n_atoms_configurable": len(cfg), "n_types": len(types), "n_facts": n_facts,
            "by_kind": by_kind, "unknown_facts": dict(sorted(unknown.items())),
            "atoms_with_description_enum_and_unit": len(three),
            "stated_atom_ids_outside_schema": len(outside),
            "docs": {"repo": S.REPO, "tag": S.tag()}}
    st = out_dir / "build_stats.json"
    if st.exists():
        b = json.loads(st.read_text(encoding="utf-8"))
        data["pages"] = b["pages"]
        data["pages_without_schema_type"] = len(b["pages_without_type"])
        data["bullets"] = b["bullets"]
        data["bullet_resolution"] = b["bullet_resolution"]
        data["context_methods"] = b["context_methods"]
        data["contradictions"] = b["contradictions"]
        data["redactions"] = b["redactions"]
        data["flag_required_vs_schema"] = b["flag_required_vs_schema"]
    sub = out_dir / "type_subcategory.jsonl"
    if sub.exists():
        recs = [json.loads(x) for x in sub.read_text(encoding="utf-8").splitlines()]
        data["types_with_page"] = sum("doc_pages" in r for r in recs)
        data["types_with_subcategory"] = sum(r["status"] == "stated" for r in recs)
        data["subcategories"] = len({r["subcategory"] for r in recs if r["status"] == "stated"})
    return {"schema": "bo.result/1", "contract": "C15", "contract_version": "3.0.0", "module": S.MODULE,
            "generated_at": at, "metrics": metrics,
            "notes": "censo dos átomos do schema fixado (sem amostragem; intervalo degenerado, método exact); "
                     "fato = extração por analisador e regex declarados sobre a documentação da tag; relatado, "
                     "sem meta; ausência de fato não é prova de ausência na documentação",
            "data": data}


def main(argv=None) -> int:
    from bo.contracts import validate as V
    from bo.repo import core
    at = core.now()
    out_dir, res = S.out_dir(), S.results_dir() / "coverage.json"
    for p in (out_dir / "docs_facts.jsonl", res):
        if not p.exists():
            print(f"falta {p}")
            return 1
    new = compute(out_dir, S.load_types(), at)
    old = json.loads(res.read_text(encoding="utf-8"))
    o = {k: v for k, v in old.items() if k != "generated_at"}
    nn = {k: v for k, v in new.items() if k != "generated_at"}
    ok = o == nn
    r = V.validate("C15_result", res)
    print(f"[{at}] cobertura da documentação {S.PROVIDER} {S.version()} ({new['data']['n_atoms']} átomos, "
          f"{new['data']['n_types']} tipos):")
    for m in new["metrics"]:
        c = m["operational_coverage"]
        print(f"  {m['metric_id']}: {100 * c['est']:.2f}%  ({m['name']})")
    print(f"  coverage.json {'confere com o recálculo' if ok else 'DIVERGE do recálculo'}; "
          f"C15 {'OK' if r.ok else 'REPROVADO: ' + '; '.join(r.errors[:3])}")
    return 0 if ok and r.ok else 1


if __name__ == "__main__":
    sys.exit(main())
