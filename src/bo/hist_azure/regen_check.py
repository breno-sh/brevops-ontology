"""Regeneração idêntica dos átomos e tipos de toda versão extraída, sem rede e sem binário.

  python -I -m bo.hist_azure.regen_check [--only V ...]

Para cada versão EXTRACTED do extract_report.json: confere que o schema.json.gz guardado descomprime no
schema_sha256, gera átomos e tipos DUAS vezes em $BO_TMP/regen/ pela mesma rota da pipeline
(bo.schema.build + write_only + gzip determinístico) e exige os mesmos sha256 nas duas e nos publicados.
Relatório em $BO_TMP/regen_check.json (volátil, fora do manifesto). Sai 0 só se todas conferem.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys

from . import atoms, common


def run(only: list[str] | None = None) -> dict:
    from bo.repo.core import now
    rep = json.loads(common.report_path().read_text(encoding="utf-8"))
    base = common.bo_tmp() / "regen"
    out = {"schema": "bo.hist_azure.regen_check/1", "started_at": now(), "versions": {}, "ok": True}
    for r in rep["versions"]:
        if r.get("status") != "EXTRACTED" or (only and r["version"] not in only):
            continue
        v = r["version"]
        gz = common.schema_dir(v) / "schema.json.gz"
        e = {"schema_ok": common.gz_sha256(gz) == r["schema"]["sha256"], "runs": []}
        for k in (1, 2):
            d = base / v / f"run{k}"
            if d.exists():
                shutil.rmtree(d)
            b = atoms.make(gz, v, d / "work", d / f"atoms_{v}.jsonl.gz", d / f"types_{v}.jsonl.gz",
                           validate=False)
            e["runs"].append({"atoms_gz_sha256": b["atoms_gz_sha256"], "types_gz_sha256": b["types_gz_sha256"],
                              "atoms": b["atoms"], "types": b["types"]})
        want = {"atoms_gz_sha256": r["atoms"]["gz_sha256"], "types_gz_sha256": r["types"]["gz_sha256"],
                "atoms": r["atoms"]["count"], "types": r["types"]["count"]}
        e["ok"] = e["schema_ok"] and all(x == want for x in e["runs"])
        out["versions"][v] = e
        out["ok"] &= e["ok"]
        shutil.rmtree(base / v, ignore_errors=True)
    out["finished_at"] = now()
    out["checked"] = len(out["versions"])
    out["ok"] = out["ok"] and out["checked"] > 0
    common.write_json(common.bo_tmp() / "regen_check.json", out)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="bo.hist_azure.regen_check", description=__doc__.split("\n")[0])
    ap.add_argument("--only", nargs="*")
    a = ap.parse_args(argv)
    r = run(a.only)
    bad = [v for v, e in r["versions"].items() if not e["ok"]]
    print(f"regen_check: {r['checked']} versão(ões), {len(bad)} divergente(s) {bad[:5]}")
    return 0 if r["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
