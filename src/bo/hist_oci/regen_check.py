"""Regeneração idêntica dos átomos do HIST-OCI: duas execuções, mesmo sha256, igual ao publicado.

  python -I -m bo.hist_oci.regen_check [--only V ...]

Para cada versão extraída, gera DUAS vezes, em pastas separadas de $BO_TMP/regen/, o atoms_<versão>.jsonl.gz a
partir do schema extraído guardado (conferido contra o schema_sha256 do versions.json), com a mesma biblioteca
e o mesmo gzip determinístico. Sai 0 só se as duas execuções dão o mesmo sha256 E ele é o do arquivo publicado.
Não baixa nada e não executa binário (o binário já foi apagado; o schema é dado lido como JSON).
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys

from . import atoms, common


def one(version: str, run: int) -> str:
    d = common.bo_tmp() / "regen" / f"{version}-run{run}"
    if d.exists():
        shutil.rmtree(d)
    d.mkdir(parents=True)
    atoms.make(common.tfschema_dir(version) / "schema.json.gz", version, d / "atoms.jsonl", d / "types.jsonl")
    gz = d / f"atoms_{version}.jsonl.gz"
    common.write_gz(d / "atoms.jsonl", gz, f"atoms_{version}.jsonl")
    sha = common.sha256_file(gz)
    shutil.rmtree(d, ignore_errors=True)
    return sha


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="bo.hist_oci.regen_check", description=__doc__.split("\n")[0])
    ap.add_argument("--only", nargs="+")
    a = ap.parse_args([x for x in (argv or []) if x != common.MODULE])
    vdoc = json.loads((common.out_dir() / "versions.json").read_text(encoding="utf-8"))
    todo = [v for v in vdoc["versions"] if "schema_sha256" in v and (not a.only or v["version"] in a.only)]
    if not todo:
        print("regen_check: nenhuma versão extraída para conferir", file=sys.stderr)
        return 1
    ok = True
    for e in todo:
        v = e["version"]
        gz = common.tfschema_dir(v) / "schema.json.gz"
        if common.gz_sha256(gz) != e["schema_sha256"]:
            print(f"  DIFF {v}: schema guardado não confere com o versions.json")
            ok = False
            continue
        r1, r2 = one(v, 1), one(v, 2)
        pub = common.sha256_file(common.atoms_path(v))
        same = r1 == r2 == pub
        ok &= same
        print(f"  {'OK  ' if same else 'DIFF'} {v}: run1 {r1[:16]} run2 {r2[:16]} publicado {pub[:16]}", flush=True)
    shutil.rmtree(common.bo_tmp() / "regen", ignore_errors=True)
    print(f"regen_check {common.MODULE}: {len(todo)} versão(ões) {'idênticas' if ok else 'DIVERGEM'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
