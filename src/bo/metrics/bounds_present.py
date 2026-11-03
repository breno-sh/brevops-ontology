"""python -I -m bo.metrics.bounds_present ID

Toda célula de todo documento C15 (result ou summary com results) em $BO_REPO/results/<ID>/ tem limite
inferior e superior, n inteiro, 0 <= lower <= upper <= 1 e, quando est existe, lower <= est <= upper. As células
sem est com n > 0 (data.est_undefined) também têm de trazer os dois limites. Nenhum documento C15 = reprova
(nada passa por vacuidade). Saída 0 = conforme; 1 = defeito; 2 = uso.
"""
from __future__ import annotations

import json
import sys

from ._cli import catalog, results_dir, say


def _check_cov(mid: str, c: dict, errs: list):
    for k in ("lower", "upper", "n"):
        if k not in c or c[k] is None:
            errs.append(f"{mid}: sem {k}")
            return
    lo, up, n, est = c["lower"], c["upper"], c["n"], c.get("est")
    if not (isinstance(n, int) and n >= 0):
        errs.append(f"{mid}: n inválido {n!r}")
    if not (0 <= lo <= up <= 1):
        errs.append(f"{mid}: limites fora de 0 <= lower <= upper <= 1 ({lo}, {up})")
    if est is not None and not (lo - 1e-12 <= est <= up + 1e-12):
        errs.append(f"{mid}: est {est} fora de [{lo}, {up}]")


def check_dir(d) -> tuple[int, list[str]]:
    n_cells, errs = 0, []
    for p in sorted(d.glob("*.json")):
        try:
            doc = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(doc, dict) or doc.get("contract") not in ("C15", "C17"):
            continue
        ms = doc.get("metrics") if doc.get("schema") == "bo.result/1" else doc.get("results")
        if not isinstance(ms, list):
            continue
        for m in ms:
            n_cells += 1
            _check_cov(f"{p.name}:{m.get('metric_id')}", m.get("operational_coverage") or {}, errs)
        for u in (doc.get("data") or {}).get("est_undefined", []):
            n_cells += 1
            _check_cov(f"{p.name}:{u.get('metric_id')}", {**u, "est": None}, errs)
    return n_cells, errs


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) != 1:
        print(__doc__)
        return 2
    mid = argv[0]
    if mid not in catalog():
        print(f"módulo {mid} fora do catálogo")
        return 2
    d = results_dir(mid)
    if not d.is_dir():
        say(f"bounds_present {mid}: {d} não existe")
        return 1
    n, errs = check_dir(d)
    for e in errs:
        print("  FAIL " + e)
    if n == 0:
        say(f"bounds_present {mid}: nenhuma célula C15 em results/{mid}/ (nada passa por vacuidade)")
        return 1
    say(f"bounds_present {mid}: {n} célula(s), {len(errs)} defeito(s) -> {'OK' if not errs else 'REPROVADO'}")
    return 0 if not errs else 1


if __name__ == "__main__":
    sys.exit(main())
