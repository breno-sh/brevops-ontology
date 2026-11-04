"""Regeneração idêntica, sem rede e sem binário: a partir dos schemas guardados, refaz em $BO_TMP os átomos de
cada versão extraída (C01 validado) e confere byte a byte com atoms_<v>.jsonl.gz; varre o texto DESCOMPRIMIDO
dos átomos com as regras do privacy_lint (bo.repo.privacy.scan_large_text); refaz versions.json e report.json
e confere o conteúdo (fora generated_at).

  python -I -m bo.hist_aws.regen_check [--only V ...] [--jobs N]

As versões rodam em paralelo (processos; padrão: metade dos núcleos, no máximo 6).
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from concurrent.futures import ProcessPoolExecutor

from . import atoms, common, pipeline


def _strip(d: dict) -> dict:
    return {k: v for k, v in d.items() if k != "generated_at"}


def one(version: str, rec: dict) -> list[str]:
    """Regenera uma versão em $BO_TMP/regen/<v>/ e devolve os problemas."""
    from bo.repo import privacy
    errs = []
    work = common.bo_tmp() / "regen" / version
    shutil.rmtree(work, ignore_errors=True)
    dest = work / f"atoms_{version}.jsonl.gz"
    try:
        br = atoms.make(common.schema_dir(version) / "schema.json.gz", version, work / "build", dest)
        if br["atoms_gz_sha256"] != common.sha256_file(common.atoms_path(version)):
            errs.append(f"{version}: átomos regenerados diferem de {common.atoms_path(version).name}")
        if br["atoms"] != rec["atoms"] or br["types"] != rec["types"]:
            errs.append(f"{version}: contagens regeneradas {br['atoms']}/{br['types']} != "
                        f"{rec['atoms']}/{rec['types']}")
        found = privacy.scan_large_text(work / "build" / "atoms.jsonl", privacy.load_lists()[0])
        for x in found[:5]:
            errs.append(f"{version}: privacidade no texto descomprimido: {x.rule} linha {x.line}")
    except Exception as e:   # noqa: BLE001 - o problema vira linha do relatório
        errs.append(f"{version}: regeneração falhou: {type(e).__name__}: {str(e)[:300]}")
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return errs


def run(only: list[str] | None = None, jobs: int | None = None) -> list[str]:
    hist = common.read_history()
    ext = pipeline.load_extraction()
    todo = [(it.version, ext["versions"][it.version]) for it in hist.versions
            if (ext["versions"].get(it.version) or {}).get("status") == "EXTRACTED"
            and (not only or it.version in only)]
    jobs = jobs or max(1, min(6, (os.cpu_count() or 2) // 2))
    errs: list[str] = []
    with ProcessPoolExecutor(max_workers=jobs) as ex:
        for e in ex.map(one, [v for v, _ in todo], [r for _, r in todo]):
            errs.extend(e)
    if not only:
        vd = json.loads((common.out_dir() / "versions.json").read_text(encoding="utf-8"))
        if _strip(vd) != _strip(pipeline.versions_doc(hist, ext)):
            errs.append("versions.json regenerado difere (fora generated_at)")
        rp = common.bo_repo() / "results" / common.MODULE / "report.json"
        if _strip(json.loads(rp.read_text(encoding="utf-8"))) != _strip(pipeline.report(hist, ext)):
            errs.append("results/HIST-AWS/report.json regenerado difere (fora generated_at)")
    shutil.rmtree(common.bo_tmp() / "regen", ignore_errors=True)
    print(f"regen_check: {len(todo)} versão(ões) regenerada(s) dos schemas guardados ({jobs} processo(s)), "
          f"texto descomprimido varrido pelo privacy_lint; {len(errs)} problema(s)")
    return errs


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="bo.hist_aws.regen_check", description=__doc__.split("\n")[0])
    ap.add_argument("--only", action="append")
    ap.add_argument("--jobs", type=int)
    a = ap.parse_args(argv)
    errs = run(a.only, a.jobs)
    for e in errs:
        print(f"  FAIL {e}")
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
