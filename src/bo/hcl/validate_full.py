"""Validação C06 do symbolic_config.jsonl INTEIRO, em paralelo, com o validador oficial (bo.contracts.validate).

  python -I -m bo.hcl.validate_full

Corta o jsonl em pedaços alinhados por repositório (pelo índice), grava cada pedaço como
$BO_TMP/c06_full/<n>/symbolic_config.jsonl e roda `python -I -m bo.contracts.validate C06` em cada um, em
paralelo. Grava $BO_DATA/HCL/contract_report.json com o sha256 do jsonl validado; o gates/HCL.sh confere que o
relatório é deste jsonl (mesmo sha) e que não houve erro. O resources.parquet é validado inteiro no gate.
"""

from __future__ import annotations

import concurrent.futures as cf
import json
import re
import shutil
import subprocess
import sys

from .common import now, out_dir, sha256_file, tmp_dir, write_json

PIECE = 400_000  # registros por pedaço


def main(argv=None) -> int:
    import argparse
    from pathlib import Path
    ap = argparse.ArgumentParser(prog="bo.hcl.validate_full")
    ap.add_argument("--data", default=None, help="pasta das saídas (padrão $BO_DATA/HCL; ex.: a .staging)")
    a = ap.parse_args(argv)
    d = out_dir() if a.data is None else Path(a.data)
    idx = json.load(open(d / "symbolic_config.index.json", encoding="utf-8"))["repos"]
    spans = sorted(idx.values())
    pieces, cur, n = [], None, 0
    for s, e, k in spans:
        if cur is None:
            cur = [s, e]
        cur[1] = e
        n += k
        if n >= PIECE:
            pieces.append(tuple(cur))
            cur, n = None, 0
    if cur:
        pieces.append(tuple(cur))
    root = tmp_dir() / "c06_full"
    shutil.rmtree(root, ignore_errors=True)
    src = d / "symbolic_config.jsonl"
    paths = []
    with open(src, "rb") as f:
        for i, (s, e) in enumerate(pieces):
            p = root / f"{i:04d}" / "symbolic_config.jsonl"
            p.parent.mkdir(parents=True, exist_ok=True)
            f.seek(s)
            p.write_bytes(f.read(e - s))
            paths.append(p)

    def run(p):
        r = subprocess.run([sys.executable, "-I", "-m", "bo.contracts.validate", "C06", str(p)],
                           capture_output=True, text=True)
        out = (r.stdout + r.stderr).splitlines()
        errs = [ln for ln in out if "ERRO" in ln]
        if errs:  # só em $BO_TMP, para depuração local; nunca vai para $BO_DATA/HCL
            (p.parent / "erros.txt").write_text("\n".join(errs) + "\n", encoding="utf-8")
        last = [ln for ln in out if "item(ns)" in ln]
        m = re.search(r"(\d+) item\(ns\), (\d+) erro", last[-1]) if last else None
        return r.returncode, (int(m.group(1)), int(m.group(2))) if m else (0, -1)

    with cf.ThreadPoolExecutor(max_workers=14) as ex:
        res = list(ex.map(run, paths))
    items = sum(x[1][0] for x in res)
    errors = sum(max(x[1][1], 0) for x in res)
    bad = [i for i, x in enumerate(res) if x[0] != 0 or x[1][1] != 0]
    rep = {"at": now(), "validator": "python -I -m bo.contracts.validate C06", "file": "$BO_DATA/HCL/symbolic_config.jsonl",
           "sha256": sha256_file(src), "pieces": len(paths), "items": items, "errors": errors,
           "failed_pieces": bad, "result": "PASS" if not bad and items > 0 else "FAIL"}
    write_json(d / "contract_report.json", rep)
    if not bad:
        shutil.rmtree(root, ignore_errors=True)
    print(f"[{now()}] validate_full: {items} registros em {len(paths)} pedaços, {errors} erro(s) -> {rep['result']}")
    return 0 if rep["result"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
