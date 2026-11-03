"""Conferências offline das saídas do SCHEMA-GCP (chamado por gates/SCHEMA-GCP.sh).

  python -I -m bo.schema_gcp.check

  1. pin: SHA256SUMS da pré-busca = pins.json; schema.json.sha256 = schema_sha256 do pin = sha da saída guardada;
  2. biblioteca: types.jsonl é byte a byte o do bo.schema.build; atoms.jsonl só difere dele por "write_only": true,
     e só nos átomos cujo atributo traz write_only no schema;
  3. build_report.json bate com os arquivos (contagens e sha256);
  4. crosscheck_beta_google-<versão>.json regenera com os mesmos bytes (análise de causa, sem data).
Sai 0 se tudo confere.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import sys

from . import atoms as A
from . import beta_check as B
from . import common as C


def main(argv=None) -> int:
    from bo.schema import build as LB
    pin = C.read_pin()
    v = pin["version"]
    out = C.out_dir()
    fails = []
    C.signed_inputs(pin)
    sdir = C.tfschema_dir(v)
    with gzip.open(sdir / "schema.json.gz", "rb") as g:
        raw_sha = hashlib.sha256(g.read()).hexdigest()
    if not (raw_sha == C.read_sha_file(out / "schema.json.sha256") == pin["schema_sha256"]):
        fails.append("sha256 do schema: saída guardada, schema.json.sha256 e pin não são iguais")

    work = C.bo_tmp() / "check"
    work.mkdir(parents=True, exist_ok=True)
    LB.build(sdir / "schema.json.gz", "google", v, work / "lib_atoms.jsonl", work / "lib_types.jsonl")
    if (work / "lib_types.jsonl").read_bytes() != (out / "types.jsonl").read_bytes():
        fails.append("types.jsonl difere do bo.schema.build")
    mine = (out / "atoms.jsonl").read_text(encoding="utf-8").splitlines()
    lib = (work / "lib_atoms.jsonl").read_text(encoding="utf-8").splitlines()
    n_wo = 0
    if len(mine) != len(lib):
        fails.append(f"atoms.jsonl com {len(mine)} linhas, biblioteca {len(lib)}")
    for m, b in zip(mine, lib):
        if m == b:
            continue
        mm = json.loads(m)
        if mm.pop("write_only", None) is not True or mm != json.loads(b):
            fails.append(f"átomo difere da biblioteca além do write_only: {json.loads(b)['atom_id']}")
            break
        n_wo += 1
    A.build(sdir / "schema.json.gz", v, work / "a.jsonl", work / "t.jsonl")
    if C.sha256_file(work / "a.jsonl") != C.sha256_file(out / "atoms.jsonl"):
        fails.append("atoms.jsonl não regenera igual pelo bo.schema_gcp.atoms")

    rep = json.loads((out / "build_report.json").read_text(encoding="utf-8"))
    b = rep["build"]
    if (b["atoms"], b["types"], b["write_only"]) != (len(mine), sum(1 for _ in open(out / "types.jsonl")), n_wo):
        fails.append("build_report.json não bate com atoms/types/write_only")
    if rep["extract"]["schema_json_sha256"] != raw_sha or rep["pin"]["schema_sha256"] != pin["schema_sha256"]:
        fails.append("build_report.json com sha256 de schema diferente")

    bpath = out / f"crosscheck_beta_{C.PROVIDER}-{v}.json"
    before = bpath.read_bytes()
    B.main([])
    if bpath.read_bytes() != before:
        bpath.write_bytes(before)
        fails.append("crosscheck_beta não regenera com os mesmos bytes")

    print(f"check {C.ID} google {v}: schema {raw_sha[:12]}… = pin; {len(mine)} átomos, {b['types']} tipos; "
          f"{n_wo} write_only (único acréscimo à biblioteca) -> {'OK' if not fails else 'FAIL'}")
    for f in fails:
        print(f"  FAIL {f}")
    return 0 if not fails else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
