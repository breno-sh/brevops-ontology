#!/usr/bin/env python3
"""Validação no consumo: todo módulo roda ao começar (e de novo no gate).

  consume_check.py ID [--no-record] [--reset] [--json]

Reprova se: o módulo ou alguma dep transitiva está STALE; alguma dep não foi mergeada em
bo/base; alguma entrada não existe; algum comprovante de congelamento relevante diverge
(hash mudou, arquivo sumiu ou o próprio comprovante foi editado); algum manifesto
transitivo (MANIFEST.sha256 ou entradas do summary.json das deps) não bate; ou alguma
entrada mudou desde o primeiro consumo (livro em $BO_DATA/ID/consume_ledger.json).
"""
import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import argparse  # noqa: E402
import json  # noqa: E402

from bo.repo import catalog, core, receipts  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(prog="consume_check.py")
    ap.add_argument("module")
    ap.add_argument("--no-record", action="store_true", help="não grava o livro de consumo")
    ap.add_argument("--reset", action="store_true", help="recomeça o livro (depois de refazer o módulo)")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    repo = core.bo_repo()
    cat = catalog.load(repo)
    rep = receipts.consume_check(cat, a.module, repo, record=not a.no_record, reset=a.reset)
    if a.json:
        print(json.dumps(rep, ensure_ascii=False, indent=1))
    else:
        core.emit(f"[{rep['at']}] consume_check {a.module} (catálogo: {cat.source})")
        for c in rep["checks"]:
            core.emit(f"  {c['status']:<4} {c['check']}: {c['detail']}")
        core.emit(f"  livro: {rep['ledger']}")
        core.emit("RESULTADO: " + ("OK" if rep["ok"] else "REPROVADO"))
    return 0 if rep["ok"] else 1


if __name__ == "__main__":
    core.run_main(main)
