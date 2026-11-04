"""Constrói o uso do google no TerraDS em $BO_DATA/CORPUS-GCP/.staging (ou --out).

  python -I -m bo.corpus_gcp.build [--out DIR] [--workers N] [--sample-mod M]

1. resources.parquet: blocos do provider google (gerenciados e data), agrupados por repositório;
2. symbolic_config.jsonl: para cada repositório com bloco google, só o trecho dele (pelo
   symbolic_config.index.json), filtrando os registros do google;
3. bo.corpus_gcp.count.count_repo por repositório, em paralelo; saída em ordem canônica (repo_id).

Saídas (DIR): usage.jsonl (C06 usage), atom_totals.jsonl (todos os átomos do schema, com zeros),
type_totals.jsonl, coverage.json, build_report.json, MANIFEST.sha256. O build não troca nada no lugar: a troca da
.staging pela pasta do módulo é do bo.corpus_gcp.promote, dentro da trava.
"""

from __future__ import annotations

import argparse
import collections
import concurrent.futures as cf
import hashlib
import json
import sys
import time
from pathlib import Path

from . import common as C
from .count import KINDS, count_repo, load_atoms

DETERMINISTIC = ("usage.jsonl", "atom_totals.jsonl", "type_totals.jsonl", "coverage.json")
UNMATCHED_MIN_REPOS = 5  # caminho sem átomo só é listado pelo nome se aparece em >= 5 repositórios

_ATOMS = None
_SRC = None


def _init(atoms_file: str, src: str) -> None:
    global _ATOMS, _SRC
    with open(atoms_file, encoding="utf-8") as f:
        _ATOMS = load_atoms(f)
    _SRC = src


def read_repo_records(fh, span, repo_id: str) -> list[dict]:
    """Registros do google no trecho do repositório; confere que o trecho é todo do repositório."""
    s, e, n = span
    fh.seek(s)
    buf = fh.read(e - s)
    lines = buf.split(b"\n")
    if lines and lines[-1] == b"":
        lines.pop()
    if len(lines) != n:
        raise ValueError(f"{repo_id}: índice diz {n} registros, trecho tem {len(lines)}")
    out = []
    needle = f'"repo_id":"{repo_id}"'.encode()
    for ln in lines:
        if needle not in ln:
            raise ValueError(f"{repo_id}: registro de outro repositório no trecho do índice")
        if b'"provider":"google"' not in ln:
            continue
        d = json.loads(ln)
        if d.get("provider") != "google":
            continue
        if d.get("repo_id") != repo_id:
            raise ValueError(f"{repo_id}: registro de outro repositório no trecho do índice")
        out.append(d)
    return out


def _work(batch):
    res = []
    with open(_SRC, "rb") as fh:
        for repo_id, family_id, resources, span in batch:
            recs = read_repo_records(fh, span, repo_id) if span else []
            r = count_repo(repo_id, family_id, resources, recs, _ATOMS)
            r["repo_id"], r["family_id"], r["n_records"] = repo_id, family_id, len(recs)
            res.append(r)
    return res


def google_resources(parquet: Path) -> dict[str, tuple[str, list]]:
    import pyarrow.compute as pc
    import pyarrow.parquet as pq
    t = pq.read_table(parquet, columns=["repo_id", "family_id", "file", "resource_address", "resource_type",
                                        "provider", "n_attrs"])
    t = t.filter(pc.equal(t["provider"], "google"))
    cols = {k: t[k].to_pylist() for k in ("repo_id", "family_id", "file", "resource_address", "resource_type",
                                         "n_attrs")}
    by: dict[str, tuple[str, list]] = {}
    for i, rid in enumerate(cols["repo_id"]):
        fid = cols["family_id"][i]
        ent = by.get(rid)
        if ent is None:
            ent = by[rid] = (fid, [])
        elif ent[0] != fid:
            raise ValueError(f"{rid}: mais de uma família no mesmo repositório")
        ent[1].append((cols["file"][i], cols["resource_address"][i], cols["resource_type"][i], cols["n_attrs"][i]))
    return by


def pick(repo_id: str, mod: int) -> bool:
    return mod <= 1 or int(hashlib.sha256(repo_id.encode()).hexdigest(), 16) % mod == 0


def run(out: Path, workers: int, sample_mod: int = 1) -> dict:
    t0 = time.time()
    ins = C.inputs()
    for p in ins.values():
        if not p.is_file():
            raise FileNotFoundError(p)
    in_sha = {k: C.sha256_file(p) for k, p in ins.items()}
    with open(ins["$BO_DATA/SCHEMA-GCP/atoms.jsonl"], encoding="utf-8") as f:
        atom_lines = f.readlines()
    atoms = load_atoms(atom_lines)
    atom_rows = [json.loads(x) for x in atom_lines if x.strip()]
    atom_rows = [a for a in atom_rows if a.get("provider") == "google"]
    versions = sorted({a["provider_version"] for a in atom_rows})
    by_repo = google_resources(ins["$BO_DATA/HCL/resources.parquet"])
    idx = json.load(open(ins["$BO_DATA/HCL/symbolic_config.index.json"], encoding="utf-8"))["repos"]
    repos = sorted(r for r in by_repo if pick(r, sample_mod))
    jobs = [(r, by_repo[r][0], by_repo[r][1], idx.get(r)) for r in repos]
    # lotes pelo tamanho do trecho (repositório grande sozinho), ordem estável
    batches, cur, size = [], [], 0
    for j in jobs:
        w = (j[3][1] - j[3][0]) if j[3] else 0
        cur.append(j)
        size += w + 2000
        if size >= 8_000_000 or len(cur) >= 200:
            batches.append(cur)
            cur, size = [], 0
    if cur:
        batches.append(cur)
    results = {}
    with cf.ProcessPoolExecutor(max_workers=workers, initializer=_init,
                                initargs=(str(ins["$BO_DATA/SCHEMA-GCP/atoms.jsonl"]),
                                          str(ins["$BO_DATA/HCL/symbolic_config.jsonl"]))) as ex:
        for res in ex.map(_work, batches):
            for r in res:
                results[r["repo_id"]] = r
    t_count = time.time() - t0

    out.mkdir(parents=True, exist_ok=True)
    cov, chk = collections.Counter(), collections.Counter()
    atom_acc: dict[str, list] = {}
    atom_repos: dict[str, int] = collections.Counter()
    atom_fams: dict[str, set] = collections.defaultdict(set)
    type_acc: dict[str, list] = {}
    unmatched_repos: collections.Counter = collections.Counter()
    n_rows = n_records = 0
    families = set()
    with open(out / "usage.jsonl.part", "w", encoding="utf-8") as fu:
        for rid in repos:
            r = results[rid]
            families.add(r["family_id"])
            n_records += r["n_records"]
            cov.update(r["cov"])
            chk.update(r["check"])
            for row in r["rows"]:
                fu.write(C.dumps(row) + "\n")
                n_rows += 1
            for aid, v in r["atoms"].items():
                a = atom_acc.setdefault(aid, [0] * len(v))
                for i, x in enumerate(v):
                    a[i] += x
                atom_repos[aid] += 1
                atom_fams[aid].add(r["family_id"])
            for rt, v in r["types"].items():
                t = type_acc.setdefault(rt, [0, 0, 0, 0, 0, set(), v[4]])
                t[0] += v[0]
                t[1] += v[1]
                t[2] += v[2]
                t[3] += v[3]
                t[4] += 1
                t[5].add(r["family_id"])
            for u in r["unmatched"]:
                unmatched_repos[tuple(u)] += 1
    (out / "usage.jsonl.part").replace(out / "usage.jsonl")

    with open(out / "atom_totals.jsonl.part", "w", encoding="utf-8") as fa:
        for a in sorted(atom_rows, key=lambda x: x["atom_id"]):
            aid, rt = a["atom_id"], a["resource_type"]
            v = atom_acc.get(aid, [0] * (5 + len(KINDS)))
            t = type_acc.get(rt)
            fa.write(C.dumps({
                "atom_id": aid, "resource_type": rt, "path": a["path"],
                "n_repos": atom_repos.get(aid, 0), "n_families": len(atom_fams.get(aid, ())),
                "n_modules": v[4], "n_resources": v[0], "n_literal": v[1], "n_symbolic": v[2], "n_withheld": v[3],
                "records_by_kind": dict(zip(KINDS, v[5:])),
                "type_n_repos": t[4] if t else 0, "type_n_families": len(t[5]) if t else 0,
                "type_n_modules": t[1] if t else 0, "type_n_resources": t[0] if t else 0,
            }) + "\n")
    (out / "atom_totals.jsonl.part").replace(out / "atom_totals.jsonl")
    seen_atoms = set(atom_acc)
    schema_ids = {a["atom_id"] for a in atom_rows}

    with open(out / "type_totals.jsonl.part", "w", encoding="utf-8") as ft:
        for rt in sorted(type_acc):
            t = type_acc[rt]
            ft.write(C.dumps({"resource_type": rt, "in_schema": bool(t[6]), "n_repos": t[4],
                              "n_families": len(t[5]), "n_modules": t[1], "n_resources": t[0],
                              "n_resources_with_atom": t[2], "n_modules_with_atom": t[3]}) + "\n")
    (out / "type_totals.jsonl.part").replace(out / "type_totals.jsonl")

    schema_types = {a["resource_type"] for a in atom_rows}
    unknown = sorted(((rt, t) for rt, t in type_acc.items() if not t[6]), key=lambda x: (-x[1][4], x[0]))
    unm = sorted(((k, n) for k, n in unmatched_repos.items() if n >= UNMATCHED_MIN_REPOS),
                 key=lambda x: (-x[1], x[0]))
    coverage = {
        "schema": "bo.corpus_gcp.coverage/1", "module": C.MODULE, "provider": "google",
        "provider_versions": versions,
        "n_repos": len(repos), "n_families": len(families), "n_records_google": n_records,
        "n_usage_rows": n_rows, "counters": dict(sorted(cov.items())), "checks": dict(sorted(chk.items())),
        "schema_atoms": len(schema_ids), "schema_atoms_seen": len(seen_atoms & schema_ids),
        "atoms_outside_schema": len(seen_atoms - schema_ids),
        "schema_types": len(schema_types),
        "schema_types_seen": sum(1 for rt, t in type_acc.items() if t[6]),
        "corpus_types": len(type_acc), "corpus_types_unknown": len(unknown),
        "unknown_types": [{"resource_type": rt, "n_repos": t[4], "n_resources": t[0]} for rt, t in unknown],
        "unmatched_paths_min_repos": UNMATCHED_MIN_REPOS,
        "unmatched_paths": [{"resource_type": k[0], "path": k[1], "n_repos": n} for k, n in unm],
        "unmatched_paths_distinct": len(unmatched_repos),
        "sample_mod": sample_mod,
    }
    C.write_json(out / "coverage.json", coverage)
    report = {
        "schema": "bo.corpus_gcp.build_report/1", "module": C.MODULE, "finished_at": C.now(),
        "params": C.PARAMS | {"workers": workers, "sample_mod": sample_mod},
        "inputs": [{"path": k, "sha256": v} for k, v in sorted(in_sha.items())],
        "seconds": {"count": round(t_count, 1), "total": round(time.time() - t0, 1)},
        "outputs": {n: C.sha256_file(out / n) for n in DETERMINISTIC},
        "n_repos": len(repos), "n_usage_rows": n_rows, "checks": dict(sorted(chk.items())),
    }
    C.write_json(out / "build_report.json", report)
    names = list(DETERMINISTIC) + ["build_report.json"]
    (out / "MANIFEST.sha256").write_text("".join(f"{C.sha256_file(out / n)}  {n}\n" for n in names), encoding="utf-8")
    return report


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="bo.corpus_gcp.build")
    ap.add_argument("--out", default=None, help="pasta de saída (padrão $BO_DATA/CORPUS-GCP/.staging)")
    ap.add_argument("--workers", type=int, default=C.PARAMS["workers"])
    ap.add_argument("--sample-mod", type=int, default=1, help="só repositórios com sha256(repo_id) %% M == 0")
    a = ap.parse_args(argv)
    out = Path(a.out) if a.out else C.staging_dir()
    rep = run(out, a.workers, a.sample_mod)
    bad = {k: v for k, v in rep["checks"].items() if v}
    print(f"[{C.now()}] corpus_gcp.build: {rep['n_repos']} repositórios, {rep['n_usage_rows']} linhas de uso em "
          f"{rep['seconds']['total']} s -> {C.portable(out)}; checagens {bad or 'zeradas'}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
