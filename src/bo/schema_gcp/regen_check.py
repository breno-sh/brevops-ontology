"""Regeneração do SCHEMA-GCP duas vezes, do zero e offline, com o mesmo sha256 (gate G2).

  python -I -m bo.tools.regen_check SCHEMA-GCP      (despachante do coordenador -> este main)
  python -I -m bo.schema_gcp.regen_check

Cada execução, numa pasta nova em $BO_TMP, sem rede e sem credenciais:
  1. o plugin_cache guardado vira filesystem_mirror; init -lockfile=readonly confere o h1; validate passa;
  2. 'terraform providers schema -json' de novo -> sha256 da saída crua tem de ser o schema_sha256 do pin;
  3. átomos e tipos pela biblioteca a partir dessa saída.
Passa (sai 0) se as duas execuções derem os mesmos sha256 entre si E iguais aos de $BO_DATA/SCHEMA-GCP
(atoms.jsonl, types.jsonl, schema.json.sha256), e se o h1 recalculado da pasta do provider for o do lock.
"""

from __future__ import annotations

import gzip
import json
import sys

from bo.schema import lockfile

from . import atoms as A
from . import common as C
from . import offline


def one(i: int, version: str) -> dict:
    work = C.bo_tmp() / "regen" / f"run{i}"
    off = offline.run(work / "tf")
    raw = work / "schema.json.gz"
    with open(raw, "wb") as f:
        with gzip.GzipFile(filename="schema.json", mode="wb", fileobj=f, mtime=0, compresslevel=9) as g:
            g.write(off["raw"])
    b = A.build(raw, version, work / "atoms.jsonl", work / "types.jsonl")
    return {"schema_json": off["sha256"], "atoms.jsonl": C.sha256_file(work / "atoms.jsonl"),
            "types.jsonl": C.sha256_file(work / "types.jsonl"), "atoms": b["atoms"], "types": b["types"],
            "write_only": b["write_only"], "validate": off["validate"]}


def main(argv=None) -> int:
    args = [a for a in (argv or []) if a != C.ID]
    if args:
        print(f"regen_check: argumentos desconhecidos: {args}", file=sys.stderr)
        return 2
    pin = C.read_pin()
    v = pin["version"]
    sig = C.signed_inputs(pin)
    lock = lockfile.find(lockfile.read(C.lock_path()), C.SOURCE)
    want_lock = C.locked_provider(pin, sig)
    problems = []
    if lock != want_lock:
        problems.append("lock do plugin_cache difere do derivado do pin + SHA256SUMS")
    h1 = C.dirhash_h1(C.provider_dir(C.plugin_cache(), v))
    if h1 not in lock.hashes:
        problems.append(f"h1 da pasta do provider ({h1}) fora do lock")
    out = C.out_dir()
    stored = {"schema_json": C.read_sha_file(out / "schema.json.sha256"),
              "atoms.jsonl": C.sha256_file(out / "atoms.jsonl"), "types.jsonl": C.sha256_file(out / "types.jsonl")}
    if stored["schema_json"] != pin["schema_sha256"]:
        problems.append("schema.json.sha256 guardado != schema_sha256 do pin")
    runs = [one(i, v) for i in (1, 2)]
    for k in ("schema_json", "atoms.jsonl", "types.jsonl"):
        if runs[0][k] != runs[1][k]:
            problems.append(f"{k}: as duas execuções divergem")
        if runs[0][k] != stored[k]:
            problems.append(f"{k}: regenerado != guardado em {C.portable(out)}")
    rep = {"module": C.ID, "provider_version": v, "h1": h1, "stored": stored, "runs": runs,
           "verdict": "PASS" if not problems else "FAIL", "problems": problems}
    (C.bo_tmp() / "regen" / "regen_check.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1) + "\n",
                                                             encoding="utf-8")
    print(f"regen_check {C.ID} google {v}: 2 execuções offline; schema {runs[0]['schema_json'][:12]}…, "
          f"atoms {runs[0]['atoms.jsonl'][:12]}… ({runs[0]['atoms']}), types {runs[0]['types.jsonl'][:12]}… "
          f"({runs[0]['types']}), h1 ok={h1 in lock.hashes} -> {rep['verdict']}")
    for p in problems:
        print(f"  FAIL {p}")
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
