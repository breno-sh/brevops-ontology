"""Duas passadas sobre o TerraDS e escrita das saídas do C06.

  python -I -m bo.hcl.extract [--limit N] [--workers W] [--out DIR]

Passada 1 (vocabulário): percorre tudo e registra, por repositório, as chaves (contexto, valor) das cadeias
candidatas; agrega por família e fixa o conjunto mantido (valor comum em contexto de enumeração).
Passada 2 (termos): percorre de novo com o vocabulário fixo e grava symbolic_config.jsonl, resources.parquet,
parse_stats.json, licenses.json e vocab_keep.u64 (só chaves de 64 bits, nenhum texto).
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import multiprocessing as mp
import os
import posixpath
import re
import sys
import time
from pathlib import Path

import numpy as np

from . import hclast, source
from .common import (MODULE, PARAMS, dumps, family_id, key64, now, out_dir, provider_of, repo_id, sha256_file, tmp_dir,
                     write_json)
from .symbolize import Symbolizer, Vocab

_KEEP = None
TYPE_RX = re.compile(r"^[a-z][a-z0-9_]*$")


def _init(keep_path):
    global _KEEP
    if keep_path:
        arr = np.fromfile(keep_path, dtype=">u8")
        _KEEP = set(int(x) for x in arr)


# ------------------------------------------------------------------------------------------------ por repositório
def parse_files(files, stats):
    parsed = []
    for rel, b in files:
        stats["files_total"] += 1
        if len(b) > PARAMS["max_file_bytes"]:
            stats["files_fail:too_large"] += 1
            parsed.append((rel, None))
            continue
        try:
            text = b.decode("utf-8")
        except UnicodeDecodeError:
            stats["files_decode_replaced"] += 1
            text = b.decode("utf-8", errors="replace")
        if text.startswith("﻿"):
            text = text[1:]
        try:
            body = hclast.parse_json_file(text) if rel.endswith(".json") else \
                hclast.parse_file(text, PARAMS["file_timeout_s"])
            stats["files_ok"] += 1
            parsed.append((rel, body))
        except hclast.ParseTimeout:
            stats["files_fail:timeout"] += 1
            parsed.append((rel, None))
        except RecursionError:
            stats["files_fail:recursion"] += 1
            parsed.append((rel, None))
        except Exception as e:  # noqa: BLE001 - erro do parser = arquivo não lido, contado por classe
            stats[f"files_fail:{type(e).__name__}"] += 1
            parsed.append((rel, None))
    return parsed


def module_graph(parsed):
    """Chamadas de módulo locais (source ./ ou ../): profundidade e cadeia de nomes de chamada por diretório."""
    dirs = sorted({posixpath.dirname(rel) or "." for rel, _ in parsed})
    calls = collections.defaultdict(list)  # alvo -> [(chamador, nome)]
    for rel, body in parsed:
        if body is None:
            continue
        d = posixpath.dirname(rel) or "."
        for b in body.blocks:
            if b.type != "module" or not b.labels:
                continue
            src = [v for k, v in b.body.attrs if k == "source"]
            if not src or src[0][0] != "str" or len(src[0][1]) != 1 or src[0][1][0][0] != "t":
                continue
            s = src[0][1][0][1]
            if not (s.startswith("./") or s.startswith("../")):
                continue
            tgt = posixpath.normpath(posixpath.join(d, s))
            if tgt.startswith("..") or tgt == d:
                continue
            calls[tgt or "."].append((d, b.labels[0]))
    roots = [d for d in dirs if not any(c != d for c, _ in calls.get(d, []))]
    depth, chain = {}, {}
    q = collections.deque()
    for r in roots:
        depth[r], chain[r] = 0, []
        q.append(r)
    callees = collections.defaultdict(list)
    for tgt, cs in calls.items():
        for c, name in cs:
            callees[c].append((name, tgt))
    while q:
        d = q.popleft()
        for name, tgt in sorted(callees.get(d, [])):
            if tgt not in depth:
                depth[tgt], chain[tgt] = depth[d] + 1, chain[d] + [name]
                q.append(tgt)
    for d in dirs:
        if d not in depth:
            depth[d], chain[d] = 0, []
    return depth, chain


def safe_path(rel: str, sz: Symbolizer) -> str:
    segs = rel.split("/")
    out = []
    for i, s in enumerate(segs):
        last = i == len(segs) - 1
        if last:
            stem = s[:-3] if s.endswith(".tf") else s[:-8]
            suf = s[len(stem):]
            ok = stem and ".." not in stem and stem != "." and \
                sz.vocab.literal_ok("path:file", stem) and all(c.isalnum() or c in "_.-" for c in stem)
            out.append((stem if ok else sz.tab.get("path", stem)) + suf)
        else:
            ok = s not in (".", "") and ".." not in s and all(c.isalnum() or c in "_.-" for c in s) and \
                sz.vocab.literal_ok("path:dir", s)
            out.append(s if ok else sz.tab.get("path", s))
    return "/".join(out)


def process_repo(args):
    tid, data = args
    return repo_core(tid, data, _KEEP)


def repo_core(tid, data, keep, reveal=False):
    """Um repositório inteiro, na ordem canônica. reveal=True (só roundtrip) guarda a tabela privada e as ASTs."""
    stats = collections.Counter()
    by_type = collections.Counter()
    files, other = source.repo_files(tid, data, stats)
    stats["other_files"] += other
    dig = hashlib.sha256()
    for h in sorted(hashlib.sha256(b).hexdigest() for _, b in files):
        dig.update(h.encode())
    fam_digest = dig.hexdigest()
    rid, fid = repo_id(tid), family_id(fam_digest)
    vocab = Vocab(keep)
    sz = Symbolizer(rid, vocab, reveal=reveal)
    trace = [] if reveal else None
    parsed = parse_files(files, stats)
    depth, chain = module_graph(parsed)
    rows, lines = [], []
    seen_addr = set()
    for rel, body in parsed:
        if body is None:
            continue
        d = posixpath.dirname(rel) or "."
        blocks = [b for b in body.blocks if b.type in ("resource", "data") and len(b.labels) == 2]
        for b in blocks:
            kind = "Managed" if b.type == "resource" else "Data"
            by_type[f"{kind}:{b.labels[0]}"] += 1
        if not any(provider_of(b.labels[0]) for b in blocks):
            continue
        frel = safe_path(rel, sz)
        prefix = "".join(f"module.{sz.tab.get('module', n)}." for n in chain.get(d, []))
        for b in blocks:
            rtype, rname = b.labels
            prov = provider_of(rtype)
            if prov is None:
                continue
            if not TYPE_RX.match(rtype):
                stats["invalid_type_label"] += 1  # rótulo que não é tipo do Terraform (ex.: com espaço)
                continue
            addr = prefix + ("data." if b.type == "data" else "") + f"{rtype}.{sz.tab.get('res', rname)}"
            key = (addr, frel)
            if key in seen_addr:
                stats["dup_address_same_file"] += 1
                continue
            seen_addr.add(key)
            if reveal:
                sz.ast_log = []
            recs = sz.resource_records(rtype, b.body)
            if reveal:
                trace.append({"rel": rel, "frel": frel, "addr": addr, "rtype": rtype, "label": rname,
                              "chain": list(chain.get(d, [])), "recs": recs, "log": sz.ast_log})
            top = {n for n, _ in b.body.attrs}
            rows.append((rid, fid, frel, addr, rtype, prov, len(recs), "count" in top, "for_each" in top,
                         depth.get(d, 0)))
            stats[f"blocks:{prov}"] += 1
            for path, term in recs:
                stats["records"] += 1
                stats[f"term:{term['kind']}"] += 1
                lines.append(dumps({"repo_id": rid, "family_id": fid, "file": frel, "resource_address": addr,
                                    "resource_type": rtype, "provider": prov, "attr_path": path, "term": term}))
    for k, v in sz.counts.items():
        if isinstance(v, dict):
            for r, n in v.items():
                stats[f"withheld:{r}"] += n
        else:
            stats[f"sym:{k}"] += v
    stats["symbols"] += sz.tab.n
    pairs = None
    if vocab.collecting and vocab.seen:
        arr = np.array(sorted(vocab.seen), dtype=np.uint64)
        pairs = arr.tobytes()
    res = {"tid": tid, "rid": rid, "fid": fid, "fam": int(fam_digest[:16], 16), "stats": stats,
           "by_type": by_type, "rows": rows, "lines": lines, "pairs": pairs, "n_files": len(files)}
    if reveal:
        res["trace"], res["reveal"], res["sz"] = trace, sz.tab.reveal, sz
    return res


# ------------------------------------------------------------------------------------------------ vocabulário
ALWAYS_ENUM_CTX = ("path:file", "path:dir")


def build_vocab(ctx_arr, key_arr, fam_arr, kmin: int, share: float):
    """Chaves mantidas: valor em >= kmin famílias, num contexto onde >= share das ocorrências são comuns.

    Segmentos de caminho (path:file, path:dir) não são valores de configuração: basta serem comuns."""
    order = np.lexsort((fam_arr, key_arr))
    k, f, c = key_arr[order], fam_arr[order], ctx_arr[order]
    new_pair = np.ones(len(k), dtype=bool)
    new_pair[1:] = (k[1:] != k[:-1]) | (f[1:] != f[:-1])
    uk, idx = np.unique(k, return_index=True)
    nfam = np.add.reduceat(new_pair.astype(np.int64), idx) if len(k) else np.array([], dtype=np.int64)
    nocc = np.diff(np.append(idx, len(k)))
    kctx = c[idx]
    common = nfam >= kmin
    uc, inv = np.unique(kctx, return_inverse=True)
    tot = np.bincount(inv, weights=nocc)
    com = np.bincount(inv, weights=nocc * common)
    enum_ctx = (com / np.maximum(tot, 1)) >= share
    always = np.array([key64(c) for c in ALWAYS_ENUM_CTX], dtype=np.uint64)
    enum_ctx |= np.isin(uc, always)
    keep = uk[common & enum_ctx[inv]]
    info = {"distinct_keys": int(len(uk)), "common_keys": int(common.sum()), "contexts": int(len(uc)),
            "enum_contexts": int(enum_ctx.sum()), "kept_keys": int(len(keep)),
            "occurrences": int(len(k))}
    return np.sort(keep).astype(">u8"), info


# ------------------------------------------------------------------------------------------------ principal
def run_pass(keep_path, limit, workers, consume):
    ctx = mp.get_context("spawn")
    with ctx.Pool(workers, initializer=_init, initargs=(keep_path,), maxtasksperchild=2000) as pool:
        it = pool.imap(process_repo, source.iter_repos(limit=limit), chunksize=8)
        for r in it:
            consume(r)


def write_parquet(rows, path: Path):
    import pyarrow as pa
    import pyarrow.parquet as pq
    cols = list(zip(*rows)) if rows else [[]] * 10
    names = ["repo_id", "family_id", "file", "resource_address", "resource_type", "provider", "n_attrs",
             "has_count", "has_for_each", "module_depth"]
    types = [pa.string()] * 6 + [pa.int64(), pa.bool_(), pa.bool_(), pa.int64()]
    t = pa.table({n: pa.array(list(c), type=ty) for n, c, ty in zip(names, cols, types)})
    pq.write_table(t, path, compression="zstd")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="bo.hcl.extract")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--workers", type=int, default=PARAMS["workers"])
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)
    out = Path(a.out) if a.out else out_dir()
    out.mkdir(parents=True, exist_ok=True)
    tmp = tmp_dir()
    t0 = time.time()
    print(f"[{now()}] passada 1 (vocabulário), workers={a.workers}, limit={a.limit}", flush=True)
    ctxs, keys, fams = [], [], []
    n1 = [0]

    def c1(r):
        n1[0] += 1
        if r["pairs"]:
            arr = np.frombuffer(r["pairs"], dtype=np.uint64).reshape(-1, 2)
            ctxs.append(arr[:, 0])
            keys.append(arr[:, 1])
            fams.append(np.full(len(arr), r["fam"], dtype=np.uint64))
        if n1[0] % 5000 == 0:
            print(f"  [{now()}] p1 {n1[0]} repos", flush=True)

    run_pass(None, a.limit, a.workers, c1)
    cat = lambda xs: np.concatenate(xs) if xs else np.array([], dtype=np.uint64)  # noqa: E731
    keep, vinfo = build_vocab(cat(ctxs), cat(keys), cat(fams), PARAMS["vocab_min_families"],
                              PARAMS["vocab_enum_share"])
    del ctxs, keys, fams
    keep_path = out / "vocab_keep.u64"
    keep.tofile(keep_path)
    print(f"[{now()}] vocabulário: {vinfo} ({time.time() - t0:.0f}s)", flush=True)

    print(f"[{now()}] passada 2 (termos)", flush=True)
    stats = collections.Counter()
    by_type = collections.Counter()
    rows, repos = [], []
    jpath = out / "symbolic_config.jsonl"
    part = tmp / "symbolic_config.jsonl.part"
    fh = open(part, "wb")
    n2 = [0]
    pos = [0]
    index = {}

    def c2(r):
        n2[0] += 1
        stats.update(r["stats"])
        stats["repos"] += 1
        by_type.update(r["by_type"])
        rows.extend(r["rows"])
        if r["rows"]:
            repos.append((r["tid"], r["rid"]))
        if r["lines"]:
            data = ("\n".join(r["lines"]) + "\n").encode("utf-8")
            fh.write(data)
            index[r["rid"]] = [pos[0], pos[0] + len(data), len(r["lines"])]
            pos[0] += len(data)
        if n2[0] % 5000 == 0:
            print(f"  [{now()}] p2 {n2[0]} repos, {len(rows)} recursos", flush=True)

    try:
        run_pass(str(keep_path), a.limit, a.workers, c2)
    finally:
        fh.close()
    os.replace(part, jpath)
    write_json(out / "symbolic_config.index.json", {
        "module": MODULE, "note": "repo_id -> [byte inicial, byte final, nº de registros] em symbolic_config.jsonl",
        "repos": index})
    write_parquet(rows, out / "resources.parquet")
    # licenças por repositório emitido
    con = source.sqlite_conn()
    lic = dict(con.execute("select Id, coalesce(License, 'NONE') from Repositories").fetchall())
    per = collections.Counter()
    lrows = []
    for tid, rid in repos:
        lv = lic.get(int(tid), "MISSING")
        per[lv] += 1
        lrows.append({"repo_id": rid, "license": lv})
    write_json(out / "licenses.json", {
        "module": MODULE, "generated_at": now(),
        "source": "TerraDS (Zenodo 10.5281/zenodo.20339474), Repositories.License; só repositórios com recurso emitido",
        "policy": "publicar só agregados, ids sintéticos e termos simbólicos; texto dos repositórios nunca é gravado",
        "n_repos": len(lrows), "by_license": dict(sorted(per.items())), "repos": sorted(lrows, key=lambda x: x["repo_id"])})
    files_total = stats["files_total"]
    write_json(out / "parse_stats.json", {
        "module": MODULE, "generated_at": now(), "params": PARAMS, "limit": a.limit,
        "parser": {"name": "python-hcl2", "version": _ver("python-hcl2"), "lark": _ver("lark"),
                   "mode": "parses_to_tree (LALR), nada avaliado; AST própria (bo.hcl.hclast)"},
        "inputs": {"tar_sha256": sha256_file(source.TAR), "sqlite_sha256": sha256_file(source.SQLITE)},
        "repos": stats["repos"], "files_total": files_total, "files_ok": stats["files_ok"],
        "parse_rate": round(stats["files_ok"] / files_total, 6) if files_total else 0.0,
        "failures": {k.split(":", 1)[1]: v for k, v in sorted(stats.items()) if k.startswith("files_fail:")},
        "files_decode_replaced": stats["files_decode_replaced"], "other_files": stats["other_files"],
        "resources_emitted": len(rows), "records": stats["records"],
        "blocks_by_provider": {k.split(":", 1)[1]: v for k, v in sorted(stats.items()) if k.startswith("blocks:")},
        "dup_address_same_file": stats["dup_address_same_file"],
        "invalid_type_label": stats["invalid_type_label"],
        "symlinks": {"resolved": stats["symlink_resolved"], "unresolved": stats["symlink_unresolved"]},
        "terms_by_kind": {k.split(":", 1)[1]: v for k, v in sorted(stats.items()) if k.startswith("term:")},
        "withheld_by_reason": {"n_" + k.split(":", 1)[1]: v for k, v in sorted(stats.items())
                               if k.startswith("withheld:")},
        "strings": {k.split(":", 1)[1]: v for k, v in sorted(stats.items()) if k.startswith("sym:")},
        "symbols": stats["symbols"], "vocab": vinfo,
        "blocks_by_type": dict(sorted(by_type.items())),
        "seconds": round(time.time() - t0, 1)})
    print(f"[{now()}] fim: {stats['repos']} repos, {files_total} arquivos, {stats['files_ok']} ok, "
          f"{len(rows)} recursos, {stats['records']} registros ({time.time() - t0:.0f}s)", flush=True)
    return 0


def _ver(dist):
    import importlib.metadata as md
    try:
        return md.version(dist)
    except md.PackageNotFoundError:
        return "?"


if __name__ == "__main__":
    sys.exit(main())
