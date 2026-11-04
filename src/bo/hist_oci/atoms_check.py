"""Contrato C01 e privacidade DENTRO de cada atoms_<versão>.jsonl.gz.

  python -I -m bo.hist_oci.atoms_check [--only V ...]

O validador oficial e o privacy_lint leem texto: num .gz eles veriam só bytes comprimidos (o lint --strict varre
as sequências imprimíveis do binário, o que não prova nada sobre o conteúdo). Aqui cada arquivo é descomprimido
em $BO_TMP e passa (1) por bo.contracts.validate C01_atoms e (2) pelas regras do privacy_lint
(bo.repo.privacy.scan_large_text, as mesmas do tools/privacy_lint.py), linha a linha. Sai 1 se algum reprovar.
O valor achado nunca é impresso inteiro (máscara do próprio lint).
"""

from __future__ import annotations

import argparse
import gzip
import json
import shutil
import sys

from . import common


def main(argv=None) -> int:
    from bo.contracts import validate as V
    from bo.repo import privacy
    ap = argparse.ArgumentParser(prog="bo.hist_oci.atoms_check", description=__doc__.split("\n")[0])
    ap.add_argument("--only", nargs="+")
    a = ap.parse_args([x for x in (argv or []) if x != common.MODULE])
    vdoc = json.loads((common.out_dir() / "versions.json").read_text(encoding="utf-8"))
    todo = [v["version"] for v in vdoc["versions"] if "schema_sha256" in v and (not a.only or v["version"] in a.only)]
    lists, _ = privacy.load_lists()
    work = common.bo_tmp() / "atoms_check"
    work.mkdir(parents=True, exist_ok=True)
    ok = bool(todo)
    for v in todo:
        p = work / f"atoms_{v}.jsonl"
        with gzip.open(common.atoms_path(v), "rb") as fi, open(p, "wb") as fo:
            shutil.copyfileobj(fi, fo, 1 << 20)
        res = V.validate("C01_atoms", p)
        found = privacy.scan_large_text(p, lists)
        good = res.ok and not found
        ok &= good
        print(f"  {'OK  ' if good else 'FAIL'} {v}: C01 {res.n} registros {'OK' if res.ok else res.errors[:3]}; "
              f"privacidade {len(found)} achado(s) {[str(x) for x in found[:3]]}", flush=True)
        p.unlink()
    shutil.rmtree(work, ignore_errors=True)
    print(f"atoms_check {common.MODULE}: {len(todo)} arquivo(s) {'OK' if ok else 'com falha'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
