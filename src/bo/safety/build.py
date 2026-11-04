"""Gera as saídas de dados do SAFETY a partir do código e das entradas; --check regera em memória e compara.

  python -I -m bo.safety.build           grava
  python -I -m bo.safety.build --check   sai 1 se algum arquivo difere do que o código geraria

Saídas: deploy/safety/allowlist_skus.yaml (política + SERVICE-EVIDENCE), deploy/safety/EXPECTED_RESIDUE.json,
results/SAFETY/sku_table_summary.json (contagens de tag/TTL/rastreio por provedor) e
results/SAFETY/sweep_coverage.json (fonte de varredura de cada tipo da allowlist, por provedor).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from . import residue, skus
from .common import PROVIDERS, deploy_dir, results_dir
from .providers import coverage


def _dump(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=1, sort_keys=True) + "\n"


def outputs() -> dict[Path, str]:
    table = skus.build_table()
    out = {deploy_dir() / "allowlist_skus.yaml": skus.render(table),
           deploy_dir() / "EXPECTED_RESIDUE.json": _dump(residue.build(table))}
    summ = {"schema": "bo.safety.sku_table_summary/1", "providers": {}}
    for p in PROVIDERS:
        ts = table["providers"][p]["types"]
        summ["providers"][p] = {
            "types": len(ts),
            "tag_supported": sum(1 for e in ts.values() if e["tag"]["supported"]),
            "tag_no_evidence": sorted(t for t, e in ts.items() if e["tag"]["status"] == "no_evidence"),
            "ttl_attribute_stated": sum(1 for e in ts.values() if e["ttl"]["supported"]),
            "native_resource_destruction": sum(1 for e in ts.values() if e["ttl"]["native_resource_destruction"]),
            "trace": {k: sum(1 for e in ts.values() if e["trace"] == k) for k in ("tag", "name", "ref")},
            "trace_downgraded_by_evidence": sorted(t for t, e in ts.items() if e["trace_reason"] != "política"),
            "removal_modes": {m: sum(1 for e in ts.values() if e["removal"]["mode"] == m)
                              for m in sorted({e["removal"]["mode"] for e in ts.values()})},
            "class_c_patterns": len(table["providers"][p]["class_c"]),
            "regions_allowed": table["providers"][p]["regions_allowed"],
        }
    summ["budget"] = table["budget"]
    summ["generated_from"] = table["generated_from"]
    out[results_dir() / "sku_table_summary.json"] = _dump(summ)
    cov = coverage(table)
    out[results_dir() / "sweep_coverage.json"] = _dump({
        "schema": "bo.safety.sweep_coverage/1", "providers": cov,
        "holes": {p: sorted(t for t, v in cov[p].items() if not v) for p in PROVIDERS}})
    return out


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    outs = outputs()
    if "--check" in argv:
        diff = [str(p) for p, txt in outs.items() if not p.exists() or p.read_text(encoding="utf-8") != txt]
        if diff:
            print("build --check: difere do que o código gera: " + ", ".join(Path(d).name for d in diff))
            return 1
        print(f"build --check: {len(outs)} arquivo(s) idênticos à regeração")
        return 0
    for p, txt in outs.items():
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(txt, encoding="utf-8")
    print(f"build: {len(outs)} arquivo(s) gravados")
    return 0


if __name__ == "__main__":
    sys.exit(main())
