"""python -I -m bo.metrics.recompute ID

Recalcula do zero, duas vezes, as saídas do módulo e confere que dão o mesmo sha256 entre si e que batem com
o que está gravado. Protocolo: o pacote do módulo (o primeiro src/bo/<pkg>/ do owns que tem build.py) expõe
bo.<pkg>.build com main(argv) aceitando --out DIR, que grava os mesmos caminhos relativos à raiz do
repositório (como bo.metrics.build). Cada execução vai para uma pasta nova em $BO_TMP/recompute/. Saída 0 =
mesmo sha; 1 = diverge; 2 = uso; 3 = o módulo não implementa o protocolo.
"""
from __future__ import annotations

import hashlib
import importlib
import os
import shutil
import sys
from pathlib import Path

from ._cli import catalog, packages_of, say
from .spec import repo_root


def _tree(d: Path) -> dict[str, str]:
    return {str(p.relative_to(d)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(d.rglob("*")) if p.is_file()}


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) != 1:
        print(__doc__)
        return 2
    mid = argv[0]
    cat = catalog()
    if mid not in cat:
        print(f"módulo {mid} fora do catálogo")
        return 2
    mod = None
    names = [f"bo.{p}.build" for p in packages_of(mid, cat)]
    for name in names:   # o primeiro pacote do owns que tem build
        if (repo_root() / "src" / Path(*name.split("."))).with_suffix(".py").is_file():
            mod = importlib.import_module(name)
            break
    if mod is None:
        say(f"recompute {mid}: nenhum de {', '.join(names)} existe (protocolo: main(argv) com --out DIR)")
        return 3
    tmp = Path(os.environ.get("BO_TMP") or (Path(os.environ.get("BO_DATA", "/Users/breno/doutorado/brevops-data"))
                                             / "tmp" / mid)) / "recompute"
    runs = []
    for i in (1, 2):
        d = tmp / f"run{i}"
        if d.exists():
            shutil.rmtree(d)
        d.mkdir(parents=True)
        rc = mod.main(["--out", str(d)])
        if rc:
            say(f"recompute {mid}: execução {i} saiu {rc}")
            return 1
        runs.append(_tree(d))
    if runs[0] != runs[1] or not runs[0]:
        say(f"recompute {mid}: as duas execuções divergem (ou não gravaram nada)")
        return 1
    root = repo_root()
    bad = [k for k, h in runs[0].items()
           if not (root / k).is_file() or hashlib.sha256((root / k).read_bytes()).hexdigest() != h]
    for k in bad:
        print(f"  FAIL {k}: gravado difere do recalculado")
    say(f"recompute {mid}: {len(runs[0])} arquivo(s), {len(bad)} divergente(s) -> {'OK' if not bad else 'REPROVADO'}")
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
