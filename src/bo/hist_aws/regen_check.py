"""Regeneração idêntica, sem rede e sem binário: a partir dos schemas guardados, refaz em $BO_TMP os átomos de
cada versão extraída e confere byte a byte com atoms_<v>.jsonl.gz; refaz versions.json e report.json e confere
o conteúdo (fora generated_at).

  python -I -m bo.hist_aws.regen_check [--only V ...]
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys

from . import atoms, common, pipeline


def _strip(d: dict) -> dict:
    return {k: v for k, v in d.items() if k != "generated_at"}


def run(only: list[str] | None = None) -> list[str]:
    hist = common.read_history()
    ext = pipeline.load_extraction()
    errs = []
    work = common.bo_tmp() / "regen"
    shutil.rmtree(work, ignore_errors=True)
    n = 0
    for it in hist.versions:
        r = ext["versions"].get(it.version) or {}
        if r.get("status") != "EXTRACTED" or (only and it.version not in only):
            continue
        dest = work / f"atoms_{it.version}.jsonl.gz"
        br = atoms.make(common.schema_dir(it.version) / "schema.json.gz", it.version, work / it.version, dest)
        if br["atoms_gz_sha256"] != common.sha256_file(common.atoms_path(it.version)):
            errs.append(f"{it.version}: átomos regenerados diferem de {common.atoms_path(it.version).name}")
        if br["atoms"] != r["atoms"] or br["types"] != r["types"]:
            errs.append(f"{it.version}: contagens regeneradas {br['atoms']}/{br['types']} != {r['atoms']}/{r['types']}")
        shutil.rmtree(work / it.version, ignore_errors=True)
        dest.unlink()
        n += 1
    if not only:
        vd = json.loads((common.out_dir() / "versions.json").read_text(encoding="utf-8"))
        if _strip(vd) != _strip(pipeline.versions_doc(hist, ext)):
            errs.append("versions.json regenerado difere (fora generated_at)")
        rp = common.bo_repo() / "results" / common.MODULE / "report.json"
        if _strip(json.loads(rp.read_text(encoding="utf-8"))) != _strip(pipeline.report(hist, ext)):
            errs.append("results/HIST-AWS/report.json regenerado difere (fora generated_at)")
    shutil.rmtree(work, ignore_errors=True)
    print(f"regen_check: {n} versão(ões) regenerada(s) dos schemas guardados; {len(errs)} problema(s)")
    return errs


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="bo.hist_aws.regen_check", description=__doc__.split("\n")[0])
    ap.add_argument("--only", action="append")
    a = ap.parse_args(argv)
    errs = run(a.only)
    for e in errs:
        print(f"  FAIL {e}")
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
