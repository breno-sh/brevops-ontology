"""bo.docs.coverage DOCS-AZURE (via despachante): % de átomos com descrição, enum e unidade. Relatado, sem meta.

  python -I -m bo.docs.coverage DOCS-AZURE        (ou python -I -m bo.docs_azure.coverage DOCS-AZURE)

Lê $BO_DATA/DOCS-AZURE/docs_facts.jsonl e os átomos do schema fixado (bo.schema.core) e grava
results/DOCS-AZURE/coverage.json (C15 result 3.0.0). É um censo (todos os átomos de resource_schemas do pin),
não uma amostra: lower = upper = est e joint_uncertainty.method = exact. O arquivo só é regravado quando o
conteúdo muda (o carimbo generated_at acompanha a última mudança). Sai 0 sempre que mede; sai 1 só quando a
medida não pode ser feita (arquivo ausente, fato de átomo fora do schema, versão diferente do pin).
"""

from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from datetime import datetime
from zoneinfo import ZoneInfo

from bo.schema import core as schema_core

from . import extract as X
from . import source as SRC

MODULE = "DOCS-AZURE"


def _sha(p) -> str:
    return SRC.sha256(p)


def measure() -> dict:
    facts_p = SRC.bo_data() / MODULE / "docs_facts.jsonl"
    if not facts_p.is_file():
        raise SystemExit(f"{facts_p} ausente; rode python -I -m bo.docs_azure.build")
    doc = schema_core.load(SRC.schema_path())
    ps = schema_core.providers(doc)[SRC.PROVIDER]
    atoms = {}
    for ts in schema_core.iter_types(ps, SRC.PROVIDER, SRC.version()):
        for a in ts.atoms:
            atoms[a["atom_id"]] = a
    have = defaultdict(set)          # kind -> átomos com fato stated
    have_pub = defaultdict(set)      # kind -> átomos com fato stated published
    unknown = Counter()
    for ln in open(facts_p, encoding="utf-8"):
        r = json.loads(ln)
        if r["atom_id"] not in atoms:
            raise SystemExit(f"fato {r['fact_id']} cita átomo fora do schema fixado: {r['atom_id']}")
        if r["provider_version"] != SRC.version():
            raise SystemExit(f"fato {r['fact_id']} com provider_version {r['provider_version']} != {SRC.version()}")
        if r["status"] == "stated":
            have[r["fact_kind"]].add(r["atom_id"])
            if r["evidence_level"] == "published":
                have_pub[r["fact_kind"]].add(r["atom_id"])
        else:
            unknown[f"{r['fact_kind']}:{r['unknown_reason']}"] += 1
    n = len(atoms)
    conf = {k for k, a in atoms.items() if a["configurable"]}
    num = {k for k, a in atoms.items() if X.is_numeric(a["tf_type"])}
    strs = {k for k, a in atoms.items() if a["tf_type"] == "string"}

    def frac(s, base):
        return {"k": len(s & base), "n": len(base), "frac": round(len(s & base) / len(base), 6) if base else None}

    allk = set(atoms)
    kinds = ["description", "default", "allowed_values", "range", "unit", "format", "forces_replacement",
             "deprecation", "conflicts_with", "required_when", "example", "behavior"]
    return {
        "n_atoms": n, "facts_sha256": _sha(facts_p), "facts_path": "$BO_DATA/DOCS-AZURE/docs_facts.jsonl",
        "main": {"description": frac(have["description"], allk), "allowed_values": frac(have["allowed_values"], allk),
                 "unit": frac(have["unit"], allk)},
        "by_kind_all_atoms": {k: frac(have[k], allk) for k in kinds},
        "by_kind_configurable_atoms": {k: frac(have[k], conf) for k in kinds},
        "allowed_values_string_atoms": frac(have["allowed_values"], strs),
        "unit_numeric_atoms": frac(have["unit"], num),
        "unit_numeric_atoms_published_only": frac(have_pub["unit"], num),
        "unknown_facts": dict(sorted(unknown.items())),
    }


def document(m: dict, generated_at: str) -> dict:
    ref = {"path": m["facts_path"], "sha256": m["facts_sha256"]}

    def metric(mid, name, key):
        x = m["main"][key]
        return {"metric_id": mid, "name": name, "reading": "field", "axis": "representability",
                "quantifier": "observed_fraction",
                "operational_coverage": {"lower": x["frac"], "upper": x["frac"], "est": x["frac"], "n": x["n"]},
                "frame": {"ref": ref, "description": "todos os átomos (C01) de resource_schemas do azurerm "
                                                     f"{SRC.version()} fixado; censo, não amostra"},
                "inclusion": {"rule_id": f"INC-DOCAZ-{key.upper().replace('_', '')}",
                              "text": f"átomo com pelo menos um fato {key} status=stated (published ou derived)"},
                "weights": {"scheme": "uniform"},
                "joint_uncertainty": {"method": "exact"}}

    return {
        "schema": "bo.result/1", "contract": "C15", "contract_version": "3.0.0", "module": MODULE,
        "generated_at": generated_at,
        "metrics": [metric("M-DOCAZ-DESC", "átomos com descrição na documentação", "description"),
                    metric("M-DOCAZ-ENUM", "átomos com valores válidos (enum) na documentação", "allowed_values"),
                    metric("M-DOCAZ-UNIT", "átomos com unidade (texto ou sufixo do nome)", "unit")],
        "notes": ("Relatado, sem meta (brief do DOCS-AZURE). Censo dos átomos do pin; lower = upper = est. "
                  "Os denominadores alternativos (configuráveis, string para enum, numéricos para unidade) e a "
                  "unidade só publicada (sem o sufixo do nome) estão em data."),
        "data": {k: v for k, v in m.items() if k not in ("main", "facts_path", "facts_sha256")},
    }


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] != MODULE:
        print(f"coverage: módulo {argv[0]!r} não é {MODULE}")
        return 2
    m = measure()
    out = SRC.bo_repo() / "results" / MODULE / "coverage.json"
    now = datetime.now(ZoneInfo("America/Recife")).isoformat(timespec="seconds")
    new = document(m, now)
    if out.is_file():
        old = json.loads(out.read_text(encoding="utf-8"))
        if {k: v for k, v in old.items() if k != "generated_at"} == {k: v for k, v in new.items()
                                                                       if k != "generated_at"}:
            new = old
    out.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(new, indent=1, ensure_ascii=False) + "\n"
    if not out.is_file() or out.read_text(encoding="utf-8") != text:
        out.write_text(text, encoding="utf-8")
    for mt in new["metrics"]:
        c = mt["operational_coverage"]
        print(f"{mt['metric_id']}: {c['est']:.4f} de {c['n']} átomos  ({mt['name']})")
    d = new["data"]
    print(f"enum entre átomos string: {d['allowed_values_string_atoms']['frac']}; unidade entre numéricos: "
          f"{d['unit_numeric_atoms']['frac']} (só publicada: {d['unit_numeric_atoms_published_only']['frac']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
