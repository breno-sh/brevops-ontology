"""Conta o uso dos átomos aws no TerraDS e grava as saídas em staging.

  python -I -m bo.corpus_aws.build [--workers N] [--out DIR] [--resources P] [--symbolic P] [--index P]
                                   [--atoms P] [--chunk-bytes B]

Saídas em DIR (padrão $BO_DATA/CORPUS-AWS/.staging): usage.jsonl (C06 usage, por repositório e família),
atom_totals.jsonl (um registro por átomo do schema, inclusive os nunca usados), build_report.json (entradas com
sha256, regras, diagnósticos) e counts.json (números do resumo, vão para results/CORPUS-AWS/). Tudo determinístico:
a mesma entrada dá os mesmos bytes (o tempo de execução fica em run.json, fora da comparação).
"""

from __future__ import annotations

import argparse
import multiprocessing as mp
import os
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

from . import common as K
from .core import RULES_VERSION, AtomIndex, RepoAgg, dumps, is_data_address, module_of, usage_row

_IX: AtomIndex | None = None
_FH = None
_PROVIDER = K.PROVIDER


def _init(atoms_path: str, symbolic_path: str, provider: str) -> None:
    global _IX, _FH, _PROVIDER
    _PROVIDER = provider
    _IX = AtomIndex.load(atoms_path, provider)
    _FH = open(symbolic_path, "rb")  # noqa: SIM115 - um por processo, fechado na saída


def _run_chunk(chunk):
    import json
    needle = f'"provider":"{_PROVIDER}"'.encode()
    out = []
    for rid, start, end, resources in chunk:
        agg = RepoAgg(_IX, rid, resources)
        _FH.seek(start)
        buf = _FH.read(end - start)
        for line in buf.split(b"\n"):
            if not line or needle not in line:
                continue
            r = json.loads(line)
            if r["provider"] != _PROVIDER:
                continue
            agg.add(r)
        out.append(agg.finish())
    return out


def load_resources(path: Path, provider: str):
    """repo -> {(file, addr): (tipo, n_attrs, is_data)}, família por repo e contagens do parquet."""
    import pyarrow.compute as pc
    import pyarrow.parquet as pq
    t = pq.read_table(path, columns=["repo_id", "family_id", "file", "resource_address", "resource_type",
                                     "provider", "n_attrs"])
    t = t.filter(pc.equal(t["provider"], provider))
    cols = {c: t[c].to_pylist() for c in ("repo_id", "family_id", "file", "resource_address", "resource_type",
                                          "n_attrs")}
    repos: dict[str, dict] = defaultdict(dict)
    fam: dict[str, str] = {}
    diag = Counter()
    for rid, fid, f, a, ty, na in zip(cols["repo_id"], cols["family_id"], cols["file"], cols["resource_address"],
                                      cols["resource_type"], cols["n_attrs"]):
        if fam.setdefault(rid, fid) != fid:
            raise SystemExit(f"repositório com duas famílias no parquet: {rid}")
        key = (f, a)
        if key in repos[rid]:
            diag["parquet_duplicate_resource"] += 1
            continue
        d = is_data_address(a)
        repos[rid][key] = (ty, int(na), d)
        diag["parquet_rows"] += 1
        diag["parquet_data" if d else "parquet_managed"] += 1
    return repos, fam, diag


def make_chunks(repos: dict, index: dict, chunk_bytes: int):
    """Tarefas em ordem de byte no jsonl (leitura quase sequencial), cortadas por volume."""
    have = sorted((index[r][0], index[r][1], r) for r in repos if r in index)
    chunks, cur, size = [], [], 0
    for s, e, r in have:
        cur.append((r, s, e, repos[r]))
        size += e - s
        if size >= chunk_bytes:
            chunks.append(cur)
            cur, size = [], 0
    if cur:
        chunks.append(cur)
    return chunks


def build(args) -> int:
    t0 = time.time()
    inp = K.inputs()
    paths = {"resources": Path(args.resources or inp["resources"]),
             "symbolic_config": Path(args.symbolic or inp["symbolic_config"]),
             "symbolic_index": Path(args.index or inp["symbolic_index"]),
             "atoms": Path(args.atoms or inp["atoms"])}
    for k, p in paths.items():
        if not p.is_file():
            print(f"entrada ausente ({k}): {p}", file=sys.stderr)
            return 2
    prov = args.provider
    out = Path(args.out) if args.out else K.staging_dir()
    out.mkdir(parents=True, exist_ok=True)
    import json
    print(f"[{K.now()}] lendo átomos, parquet e índice", flush=True)
    ix = AtomIndex.load(paths["atoms"], prov)
    repos, fam, pdiag = load_resources(paths["resources"], prov)
    index = json.loads(paths["symbolic_index"].read_text(encoding="utf-8"))["repos"]
    chunks = make_chunks(repos, index, args.chunk_bytes)
    print(f"[{K.now()}] {len(repos)} repositórios {prov}, {len(chunks)} tarefas, {args.workers} processos",
          flush=True)

    results: dict[str, dict] = {}
    initargs = (str(paths["atoms"]), str(paths["symbolic_config"]), prov)
    if args.workers <= 1:
        _init(*initargs)
        for ch in chunks:
            for r in _run_chunk(ch):
                results[r["repo_id"]] = r
    else:
        ctx = mp.get_context("spawn")
        with ctx.Pool(args.workers, initializer=_init, initargs=initargs) as pool:
            for i, rs in enumerate(pool.imap_unordered(_run_chunk, chunks), 1):
                for r in rs:
                    results[r["repo_id"]] = r
                if i % 50 == 0 or i == len(chunks):
                    print(f"[{K.now()}]   {i}/{len(chunks)} tarefas", flush=True)

    # repositórios com recurso aws e nenhum registro no índice: só linhas de tipo (n_attrs tem de ser 0)
    diag = Counter(pdiag)
    for rid, res in repos.items():
        if rid not in results:
            agg = RepoAgg(ix, rid, res)
            results[rid] = agg.finish()
            diag["repos_without_records"] += 1

    # ------------------------------------------------------------------------------------ linhas de uso
    type_n = defaultdict(Counter)        # repo -> tipo -> recursos gerenciados
    type_mods = defaultdict(lambda: defaultdict(set))
    for rid, res in repos.items():
        for (f, _a), (ty, _na, d) in res.items():
            if d:
                continue
            type_n[rid][ty] += 1
            type_mods[rid][ty].add(module_of(f))

    unattr, unmatched, unknown_types = Counter(), Counter(), Counter()
    unattr_f, unmatched_f, unknown_f = defaultdict(set), defaultdict(set), defaultdict(set)
    tot = defaultdict(lambda: [0, 0, 0, 0, 0, 0, set()])  # atom -> [repos, mods, set, lit, sym, wh, famílias]
    typ = defaultdict(lambda: [0, 0, 0, set()])            # tipo -> [repos, mods, recursos, famílias]
    n_rows_type = n_rows_atom = 0
    cls_cells = Counter()
    type_cls = Counter()
    upath = out / "usage.jsonl"
    with open(str(upath) + ".part", "w", encoding="utf-8") as fo:
        for rid in sorted(repos):
            r = results[rid]
            fid = fam[rid]
            if r["family_id"] is not None and r["family_id"] != fid:
                raise SystemExit(f"família do jsonl diverge do parquet em {rid}")
            for k, v in r["diag"].items():
                diag[k] += v
            for k, v in r["unattributed_blocks"].items():
                unattr[tuple(k)] += v
                unattr_f[tuple(k)].add(fid)
            for k, v in r["unmatched_paths"].items():
                unmatched[tuple(k)] += v
                unmatched_f[tuple(k)].add(fid)
            for k, v in r["unknown_types"].items():
                unknown_types[k] += v
                unknown_f[k].add(fid)
            rows_by_type = defaultdict(list)
            for (ty, p), vals in r["rows"].items():
                rows_by_type[ty].append((p, vals))
            for ty in sorted(type_n[rid]):
                nres = type_n[rid][ty]
                ts, tl, tsy, tw = r["type_rows"].get(ty, (0, 0, 0, 0))
                fo.write(dumps(usage_row(prov, rid, fid, ty, nres, None, ts, tl, tsy, tw)) + "\n")
                type_cls["set"] += ts
                type_cls["literal"] += tl
                type_cls["symbolic"] += tsy
                type_cls["withheld"] += tw
                n_rows_type += 1
                tt = typ[ty]
                tt[0] += 1
                tt[1] += len(type_mods[rid][ty])
                tt[2] += nres
                tt[3].add(fid)
                for p, (n_set, n_lit, n_sym, n_wh, n_mod) in sorted(rows_by_type.get(ty, ())):
                    aid = ix.atom_id(ty, p)
                    fo.write(dumps(usage_row(prov, rid, fid, ty, nres, aid, n_set, n_lit, n_sym, n_wh)) + "\n")
                    n_rows_atom += 1
                    a = tot[aid]
                    a[0] += 1
                    a[1] += n_mod
                    a[2] += n_set
                    a[3] += n_lit
                    a[4] += n_sym
                    a[5] += n_wh
                    a[6].add(fid)
                    cls_cells["literal"] += n_lit
                    cls_cells["symbolic"] += n_sym
                    cls_cells["withheld"] += n_wh
            extra = set(t for t, _ in r["rows"]) - set(type_n[rid])
            if extra:
                raise SystemExit(f"linha de átomo sem recurso gerenciado do tipo em {rid}")
    os.replace(str(upath) + ".part", upath)

    # ------------------------------------------------------------------------------------ totais por átomo
    apath = out / "atom_totals.jsonl"
    used = Counter()
    with open(str(apath) + ".part", "w", encoding="utf-8") as fo:
        for ty in sorted(ix.paths):
            tt = typ.get(ty, [0, 0, 0, set()])
            for p in sorted(ix.paths[ty]):
                aid = ix.atom_id(ty, p)
                a = tot.get(aid, [0, 0, 0, 0, 0, 0, set()])
                m = ix.meta[(ty, p)]
                rec = {"atom_id": aid, "provider": prov, "resource_type": ty, "path": p,
                       "configurable": m["configurable"], "computed": m["computed"], "required": m["required"],
                       "n_repos": a[0], "n_families": len(a[6]), "n_modules": a[1], "n_resources": a[2],
                       "n_literal": a[3], "n_symbolic": a[4], "n_withheld": a[5],
                       "type_n_repos": tt[0], "type_n_families": len(tt[3]), "type_n_modules": tt[1],
                       "type_n_resources": tt[2]}
                fo.write(dumps(rec) + "\n")
                used["atoms"] += 1
                if a[0]:
                    used["atoms_used"] += 1
                    used["atoms_used_configurable" if m["configurable"] else "atoms_used_not_configurable"] += 1
                    if len(a[6]) >= K.NAME_MIN_FAMILIES:
                        used["atoms_used_ge5_families"] += 1
                if m["configurable"]:
                    used["atoms_configurable"] += 1
                if tt[0]:
                    used["atoms_of_present_types"] += 1
    os.replace(str(apath) + ".part", apath)
    missing = set(tot) - {ix.atom_id(t, p) for t in ix.paths for p in ix.paths[t]}
    if missing:
        raise SystemExit(f"{len(missing)} átomo(s) contado(s) fora do schema")

    # ------------------------------------------------------------------------------------ relatório
    def top(c: Counter, fams: dict, label):
        named = [(k, v, len(fams[k])) for k, v in c.items() if len(fams[k]) >= K.NAME_MIN_FAMILIES]
        named.sort(key=lambda x: (-x[2], -x[1], str(x[0])))
        hidden = sum(v for k, v in c.items() if len(fams[k]) < K.NAME_MIN_FAMILIES)
        return {"distinct": len(c), "records": sum(c.values()), "records_not_named": hidden,
                "top": [dict(zip(label, (list(k) if isinstance(k, tuple) else [k]))) |
                        {"records": v, "families": f} for k, v, f in named[:K.TOP_N]]}

    managed_types = {ty for rid in type_n for ty in type_n[rid]}
    in_schema = {ty for ty in managed_types if ix.has_type(ty)}
    n_res_managed = sum(sum(c.values()) for c in type_n.values())
    n_res_known = sum(typ[ty][2] for ty in in_schema)
    n_mod = sum(len({module_of(f) for (f, _a), v in res.items() if not v[2]}) for res in repos.values())
    counts = {
        "module": K.MODULE, "provider": prov, "rules_version": RULES_VERSION,
        "corpus": {"repos": sum(1 for r in type_n if type_n[r]),
                   "repos_any_block": len(repos),
                   "families": len({fam[r] for r in type_n if type_n[r]}),
                   "modules": n_mod,
                   "managed_resources": n_res_managed,
                   "managed_resources_type_in_schema": n_res_known,
                   "data_blocks_excluded": diag["parquet_data"],
                   "managed_types_present": len(managed_types),
                   "managed_types_present_in_schema": len(in_schema),
                   "managed_types_present_not_in_schema": len(managed_types - in_schema)},
        "schema": {"types": len(ix.paths), "atoms": used["atoms"], "atoms_configurable": used["atoms_configurable"],
                   "types_present_in_corpus": len(in_schema),
                   "atoms_of_present_types": used["atoms_of_present_types"]},
        "atoms_used": {"any": used["atoms_used"], "configurable": used["atoms_used_configurable"],
                       "not_configurable": used["atoms_used_not_configurable"],
                       "in_ge5_families": used["atoms_used_ge5_families"]},
        "resources_with_atom": {"total": type_cls["set"], **{k: type_cls[k] for k in
                                                             ("literal", "symbolic", "withheld")}},
        "cells_resource_atom": {"total": sum(cls_cells.values()), **{k: cls_cells[k] for k in
                                                                     ("literal", "symbolic", "withheld")}},
        "records": {k: diag[k] for k in sorted(diag) if k.startswith("records_")},
        "consistency": {"records_without_resource": diag["records_without_resource"],
                        "records_type_mismatch": diag["records_type_mismatch"],
                        "resources_n_attrs_mismatch": diag["resources_n_attrs_mismatch"],
                        "parquet_duplicate_resource": diag["parquet_duplicate_resource"]},
        "usage_rows": {"total": n_rows_type + n_rows_atom, "type_rows": n_rows_type, "atom_rows": n_rows_atom},
        "withheld_blocks_unattributed": top(unattr, unattr_f, ("resource_type", "block")),
        "unmatched_paths": top(unmatched, unmatched_f, ("resource_type", "path")),
        "types_not_in_schema": top(unknown_types, unknown_f, ("resource_type",)),
        "name_min_families": K.NAME_MIN_FAMILIES,
        "alignment": K.ALIGNMENT,
    }
    report = {"module": K.MODULE, "provider": prov, "rules_version": RULES_VERSION,
              "inputs": [{"name": k, "path": K.portable(p), "sha256": K.sha256_file(p)} for k, p in
                         sorted(paths.items())],
              "params": {"provider": prov, "name_min_families": K.NAME_MIN_FAMILIES, "top_n": K.TOP_N,
                         "alignment": K.ALIGNMENT},
              "diag": {k: diag[k] for k in sorted(diag)},
              "outputs": {n: K.sha256_file(out / n) for n in ("usage.jsonl", "atom_totals.jsonl")},
              "counts_ref": "counts.json"}
    K.write_json(out / "counts.json", counts)
    K.write_json(out / "build_report.json", report)
    K.write_json(out / "run.json", {"finished_at": K.now(), "seconds": round(time.time() - t0, 1),
                                    "workers": args.workers, "chunks": len(chunks)})
    print(f"[{K.now()}] pronto em {time.time() - t0:.0f} s: {n_rows_atom} linhas de átomo, {n_rows_type} de tipo; "
          f"{used['atoms_used']} átomos usados de {used['atoms']}", flush=True)
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="bo.corpus_aws.build")
    ap.add_argument("--workers", type=int, default=max(1, min(12, (os.cpu_count() or 2) - 2)))
    ap.add_argument("--out")
    ap.add_argument("--provider", default=K.PROVIDER)
    ap.add_argument("--resources")
    ap.add_argument("--symbolic")
    ap.add_argument("--index")
    ap.add_argument("--atoms")
    ap.add_argument("--chunk-bytes", type=int, default=32 << 20)
    return build(ap.parse_args(argv))


if __name__ == "__main__":
    sys.exit(main())
