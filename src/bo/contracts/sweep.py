"""Varredura dos gates do catálogo: para CADA comando 'bo.contracts.validate <alias> <caminho>' dos módulos do
modulos.json, o alias e o nome do arquivo resolvem num tipo (a) do contrato que o artifact_catalog dá ao caminho e
(b) cujo padrão de arquivo casa com o nome (sem cair no tipo homônimo por falta de padrão).

  python -I -m bo.contracts.sweep      sai 1 se algum gate não resolve no tipo pretendido; relatório em
                                       $BO_DATA/CONTRACTS/sweep.json
"""

from __future__ import annotations

import fnmatch
import json
import os
import re
import sys
from pathlib import Path

from . import _base, catalog

CALL = re.compile(r"bo\.contracts\.validate\s+([^\s#;&|]+)\s+([^\s#;&|]+)")
DEFAULT_MODULES = "/Users/breno/doutorado/pesquisa/superficie/reports/brevops_ontology/modulos.json"


def sweep(modules_path: str | None = None) -> dict:
    cat = json.loads(Path(modules_path or os.environ.get("BO_MODULES") or DEFAULT_MODULES).read_text(encoding="utf-8"))
    art = {a["path"]: a for a in cat["artifact_catalog"]["artifacts"]}
    rows = []
    for m in cat["modules"]:
        for g in m["gates"]:
            for alias, p in CALL.findall(g):
                if alias.startswith("--"):
                    continue
                path = Path(p)
                row = {"module": m["stable_id"], "alias": alias, "path": p,
                       "catalog_contract": (art.get(p) or {}).get("contract")}
                try:
                    fk = catalog.resolve(alias, path)
                except KeyError as e:
                    row.update(ok=False, problem=f"não resolve: {e.args[0]}")
                    rows.append(row)
                    continue
                row["resolved"] = f"{fk.cid}:{fk.kind}"
                probs = []
                if not (fnmatch.fnmatchcase(path.name, fk.file) or
                        fnmatch.fnmatchcase("/".join(path.parts[-2:]), fk.file)):
                    probs.append(f"nome não casa com o padrão {fk.file} do tipo resolvido")
                if row["catalog_contract"] and row["catalog_contract"] != fk.cid:
                    probs.append(f"artifact_catalog diz {row['catalog_contract']}")
                if p.startswith("$BO_REPO/contracts/stubs/"):
                    pass
                elif row["catalog_contract"] is None:
                    row["note"] = "caminho sem contrato no artifact_catalog (conferido só o padrão)"
                row.update(ok=not probs, problem="; ".join(probs))
                rows.append(row)
    return {"at": _base.now(), "gates": len(rows), "ok": sum(r["ok"] for r in rows),
            "failed": [r for r in rows if not r["ok"]], "rows": rows}


def main(argv=None) -> int:
    rep = sweep()
    d = _base.data_dir()
    d.mkdir(parents=True, exist_ok=True)
    (d / "sweep.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    for r in rep["failed"]:
        print(f"  FAIL {r['module']}: validate {r['alias']} {r['path']} -> {r.get('resolved')} ({r['problem']})")
    for r in rep["rows"]:
        if r.get("note"):
            print(f"  nota {r['module']}: {r['path']}: {r['note']}")
    print(f"[{_base.now()}] sweep: {rep['ok']}/{rep['gates']} gates 'bo.contracts.validate' resolvem no tipo pretendido")
    return 0 if rep["ok"] == rep["gates"] else 1


if __name__ == "__main__":
    sys.exit(main())
