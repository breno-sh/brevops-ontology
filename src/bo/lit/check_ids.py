"""Gate G1 do LIT: todo item do related.bib tem DOI que resolve no Crossref ou identificador
alternativo declarado e verificado.

  python -I -m bo.lit.check_ids [$BO_REPO/lit/related.bib] [--ledger ARQ] [--live]

Sem --live, confere contra o livro results/LIT/id_resolution.json (gravado por bo.lit.resolve) e
exige que o livro seja do .bib atual (mesmo sha256). Com --live, resolve tudo de novo pela rede
num livro temporário e confere contra ele; diferença frente ao livro gravado é relatada.
Saída 0 só se todas as entradas passam.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from bo.repo import core

from . import bib, ids, verify


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -I -m bo.lit.check_ids")
    ap.add_argument("bib", nargs="?", default=None)
    ap.add_argument("--ledger", default=None)
    ap.add_argument("--live", action="store_true")
    a = ap.parse_args(argv)
    root = ids.repo_root()
    bib_path = Path(a.bib) if a.bib else root / "lit" / "related.bib"
    led_path = Path(a.ledger) if a.ledger else root / ids.LEDGER_REL
    if not bib_path.is_file():
        raise core.BoError(f"bib não encontrado: {bib_path}")
    entries = bib.parse(bib_path.read_text(encoding="utf-8"))
    if not entries:
        raise core.BoError("bib sem entradas")
    if not led_path.is_file():
        raise core.BoError(f"livro de resolução ausente: {led_path} (rode python -I -m bo.lit.resolve)")
    ledger = json.loads(led_path.read_text(encoding="utf-8"))
    problems = 0
    if ledger.get("bib_sha256") != core.sha256_file(bib_path):
        core.emit("FALHA livro de resolução é de outra versão do .bib (sha256 diferente); rode bo.lit.resolve")
        problems += 1
    if a.live:
        from . import resolve
        tmp = core.bo_tmp("LIT") / "id_resolution.live.json"
        live = resolve.run(bib_path, tmp)
        for k, rec in ledger.get("records", {}).items():
            lv = live["records"].get(k)
            if not lv or lv.get("status") != rec.get("status") or lv.get("title", "") != rec.get("title", ""):
                core.emit(f"DERIVA {k[:100]}: gravado={rec.get('status')} ao vivo={lv and lv.get('status')}")
        ledger = live
    verdicts = verify.check_all(entries, ledger)
    for vd in verdicts:
        if vd.ok:
            core.emit(f"ok    {vd.key:<28} {vd.basis:<13} {len(vd.verified_ids)} id(s)")
        else:
            problems += 1
            core.emit(f"FALHA {vd.key}")
            for p in vd.problems:
                core.emit(f"      - {p}")
        for n in vd.notes:
            core.emit(f"      nota: {n}")
    n_doi = sum(v.ok and v.basis == "doi_crossref" for v in verdicts)
    n_alt = sum(v.ok and v.basis == "altid" for v in verdicts)
    core.emit(f"[{core.now()}] {len(verdicts)} entradas: {n_doi} com DOI no Crossref, {n_alt} só com "
              f"identificador alternativo, {sum(not v.ok for v in verdicts)} reprovada(s)"
              + (" (ao vivo)" if a.live else f" (livro de {ledger.get('resolved_at')})"))
    return 1 if problems else 0


if __name__ == "__main__":
    core.run_main(main)
