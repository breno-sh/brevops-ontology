"""Regeneração idêntica do SCHEMA-AZURE: duas execuções, mesmo sha256.

  python -I -m bo.tools.regen_check SCHEMA-AZURE      (pelo despachante do coordenador)
  python -I -m bo.schema_azure.regen_check [--no-schema] [--out ARQ]

  1. o schema guardado: schema.json.gz descomprime no sha256 de schema.json.sha256, que é o do pins.json;
  2. duas execuções independentes de átomos e tipos (bo.schema.build, que já grava write_only) em
     $BO_TMP/regen/run1 e run2: os sha256 de atoms.jsonl e types.jsonl batem entre si e com os publicados;
  3. (a menos de --no-schema) o schema cru é refeito SEM rede a partir do binário fixado no plugin_cache/
     (bo.schema_azure.offline, que também roda o validate offline) e o sha256 bate com o do pins.json.
Sai 0 só se tudo bate. Relatório em $BO_DATA/SCHEMA-AZURE/regen_check.json.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

from . import atoms, common, offline, pipeline


def check(schema: bool = True) -> dict:
    from bo.repo.core import now
    pin = common.read_pin()
    out = common.out_dir()
    sdir = common.tfschema_dir(pin.version)
    gz = sdir / "schema.json.gz"
    rep: dict = {"module": common.MODULE, "provider": common.PROVIDER, "version": pin.version,
                 "started_at": now(), "falhas": []}

    pub_sha = (out / "schema.json.sha256").read_text(encoding="utf-8").split()[0]
    gz_sha = pipeline.gz_sha256(gz)
    rep["schema"] = {"publicado": pub_sha, "gz_descomprimido": gz_sha, "pins": pin.schema_sha256}
    if not (pub_sha == gz_sha == pin.schema_sha256):
        rep["falhas"].append("schema guardado diverge do pins.json")

    published = {n: common.sha256_file(out / n) for n in ("atoms.jsonl", "types.jsonl")}
    runs = []
    root = common.bo_tmp() / "regen"
    for i in (1, 2):
        d = root / f"run{i}"
        if d.exists():
            shutil.rmtree(d)
        d.mkdir(parents=True)
        atoms.make(gz, pin.version, d / "atoms.jsonl", d / "types.jsonl")
        runs.append({n: common.sha256_file(d / n) for n in ("atoms.jsonl", "types.jsonl")})
    shutil.rmtree(root, ignore_errors=True)
    rep["build"] = {"publicado": published, "run1": runs[0], "run2": runs[1]}
    if not (runs[0] == runs[1] == published):
        rep["falhas"].append("átomos/tipos regenerados diferem entre execuções ou do publicado")

    if schema:
        off = offline.run()
        ok = next(c for c in off["cases"] if c["case"] == "valida")
        rep["schema_offline"] = {"sha256": ok.get("schema_sha256"), "igual_ao_pin": ok.get("schema_igual_ao_pin"),
                                 "validate_offline": off["veredito"], "network": off["network"]}
        if off["veredito"] != "PASS":
            rep["falhas"].append("schema refeito offline / validate offline reprovou")
    rep["finished_at"] = now()
    rep["veredito"] = "PASS" if not rep["falhas"] else "FAIL"
    return rep


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="bo.schema_azure.regen_check", description=__doc__.split("\n")[0])
    ap.add_argument("module", nargs="?", default=common.MODULE)
    ap.add_argument("--no-schema", action="store_true", help="não refaz o schema cru pelo binário fixado")
    ap.add_argument("--out", type=Path)
    a = ap.parse_args(argv)
    if a.module != common.MODULE:
        print(f"regen_check: este pacote é do {common.MODULE}, não do {a.module}", file=sys.stderr)
        return 2
    rep = check(not a.no_schema)
    outp = a.out or common.out_dir() / "regen_check.json"
    outp.write_text(json.dumps(rep, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    b = rep["build"]
    print(f"regen_check {common.MODULE}: schema {rep['schema']['publicado'][:12]} (pins igual: "
          f"{rep['schema']['publicado'] == rep['schema']['pins']}); atoms {b['run1']['atoms.jsonl'][:12]} = "
          f"{b['run2']['atoms.jsonl'][:12]} = {b['publicado']['atoms.jsonl'][:12]}; types "
          f"{b['run1']['types.jsonl'][:12]} = {b['run2']['types.jsonl'][:12]} = {b['publicado']['types.jsonl'][:12]}"
          + (f"; schema offline igual: {rep['schema_offline']['igual_ao_pin']}" if "schema_offline" in rep else "")
          + f" -> {rep['veredito']}")
    for f in rep["falhas"]:
        print(f"  FALHA: {f}", file=sys.stderr)
    return 0 if rep["veredito"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
