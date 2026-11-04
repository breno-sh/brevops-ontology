"""Gera as saídas do DRIFT a partir dos HIST-* (somente leitura), um processo por provider.

  python -I -m bo.drift.build [--out DIR] [--providers aws,google,...] [--jobs N]

Padrão de --out: $BO_DATA/DRIFT/.staging (a troca pelas saídas finais é do bo.drift.promote, com a trava).
Escreve em DIR: events.jsonl, atom_history.jsonl (C13), rename_candidates.jsonl e churn.json (C15).
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from . import churn, common, core, guides


def run_provider(provider: str, parts: str, data: str | None = None) -> dict:
    """Analisa um provider e grava as partes em `parts/<provider>.*`. Devolve as estatísticas."""
    data_p = Path(data) if data else common.bo_data()
    pin = common.load_provider(provider, data_p)
    obs = pin.observed
    snaps, metas, counts = [], [], {}
    for v in obs:
        s, m = core.snapshot(common.read_atoms(v.atoms_path, v.atoms_sha256), provider)
        snaps.append(s)
        metas.append(m)
        counts[v.version] = len(s)
    sents, gfiles = guides.load(provider, data_p)
    res = core.analyze(provider, [v.version for v in obs], snaps, metas, sents)
    del snaps, metas
    pdir = Path(parts)
    with open(pdir / f"{provider}.events.jsonl", "w", encoding="utf-8") as f:
        for e in res.events:
            f.write(common.dumps(e) + "\n")
    n_hist = 0
    with open(pdir / f"{provider}.atom_history.jsonl", "w", encoding="utf-8") as f:
        for r in core.atom_history_records(res):
            f.write(common.dumps(r) + "\n")
            n_hist += 1
    with open(pdir / f"{provider}.rename_candidates.jsonl", "w", encoding="utf-8") as f:
        for c in res.candidates:
            f.write(common.dumps(c) + "\n")
    return churn.provider_stats(pin, res, counts, sents, gfiles, n_hist)


def build(out: Path, providers: list[str] | None = None, jobs: int = 4) -> dict:
    providers = providers or common.ORDER
    out.mkdir(parents=True, exist_ok=True)
    parts = out / ".parts"
    if parts.exists():
        shutil.rmtree(parts)
    parts.mkdir()
    data = str(common.bo_data())
    if jobs > 1 and len(providers) > 1:
        with ProcessPoolExecutor(max_workers=min(jobs, len(providers))) as ex:
            futs = {p: ex.submit(run_provider, p, str(parts), data) for p in providers}
            stats = {p: futs[p].result() for p in providers}
    else:
        stats = {p: run_provider(p, str(parts), data) for p in providers}
    for kind in ("events", "atom_history", "rename_candidates"):
        with open(out / f"{kind}.jsonl", "wb") as f:
            for p in providers:
                with open(parts / f"{p}.{kind}.jsonl", "rb") as g:
                    shutil.copyfileobj(g, f, 1 << 20)
    shutil.rmtree(parts)
    doc = churn.document(stats, out)
    (out / "churn.json").write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return doc


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="bo.drift.build")
    ap.add_argument("--out", default=None)
    ap.add_argument("--providers", default=",".join(common.ORDER))
    ap.add_argument("--jobs", type=int, default=4)
    a = ap.parse_args(argv)
    out = Path(a.out) if a.out else common.staging_dir()
    provs = [p for p in a.providers.split(",") if p]
    bad = [p for p in provs if p not in common.PROVIDERS]
    if bad:
        print(f"provider desconhecido: {bad}", file=sys.stderr)
        return 2
    t = common.now()
    doc = build(out, provs, a.jobs)
    tot = doc["data"]["totals"]
    print(f"[{common.now()}] bo.drift.build: {out} (início {t})")
    print(f"  eventos {tot['events']}  átomos {tot['atoms']}  candidatos {tot['rename_candidates']}")
    return 0


if __name__ == "__main__":
    os.environ.setdefault("BO_TMP", str(common.bo_tmp()))
    sys.exit(main())
