"""Varredura do C06 (symbolic_config.jsonl): variantes por provedor e famílias de módulos no mesmo repositório.

  python -I -m bo.gold_mods.scan [--workers W] [--limit N] [--out ARQ]

Unidade de variante = diretório de módulo (dirname do arquivo .tf, símbolo estável dentro do repositório).
Regras (fixadas antes de olhar os números; vão para families.json e summary.json):
  V1  variante = diretório cujos blocos resource/data são de UM só dos 4 provedores; diretório com dois ou
      mais provedores é 'misto' (configuração multi-nuvem simultânea, não variante) e fica fora;
  V2  interface da variante = conjunto das variáveis (raiz var.<x>) que chegam a algum atributo de bloco
      resource ou data (meta-argumentos fora); linhas SSSOM só para recurso gerenciado (data source fica no
      rastro com categoria data_source: o átomo do C01 é de recurso);
  V3  par de variantes = dois diretórios do MESMO repositório (mesmo mantenedor), provedores diferentes,
      |interseção| >= MIN_SHARED e Jaccard >= MIN_JACCARD;
  V3b contraparte mútua: das variantes que passam V3, cada uma fica só com a(s) de melhor posto em cada outro
      provedor (Jaccard maior; empate -> prefixo de diretório comum mais longo) e o par só entra se a escolha é
      mútua. Acrescentada DEPOIS da 1ª rodada completa: só com V3, um repositório gerado com 200 projetos
      (X/aws, X/gcp, X/azure, mesma interface) cruzava todo X/gcp com todo Y/azure (40 000 dos 40 697 pares);
      a contagem só com V3 fica registrada (n_threshold_pairs);
  V4  família = componente conexo dos pares de um repositório;
  V5  repositórios com o mesmo family_id do C06 (conteúdo idêntico: cópia/fork) contam uma vez (o menor repo_id);
      as cópias entram só como contagem.
Por que só no mesmo repositório: o C06 simboliza nomes POR repositório (C06-SYM); var.x em dois repositórios dá
símbolos diferentes, então a interface só é comparável dentro de um repositório. Famílias espalhadas em vários
repositórios do mesmo dono ficam fora (limite declarado, não silêncio do ouro).
"""
from __future__ import annotations

import argparse
import json
import multiprocessing as mp
import posixpath
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

from . import terms
from .paths import now_iso, symbolic_config, symbolic_index, tmp_dir

PROVIDERS = ("aws", "google", "azurerm", "oci")
PARAMS = {"min_shared_vars": 2, "min_jaccard": 0.5, "unit": "diretório do arquivo .tf",
          "counterpart": "mútua: Jaccard maior, empate pelo prefixo de diretório comum mais longo (V3b)",
          "dedupe": "um repositório por family_id do C06 (menor repo_id)", "identity": "ops == () (valor = var)"}
FAMILY = re.compile(r'"family_id":"(F-[0-9a-f]{12})"')
HEAD = re.compile(r'"file":"((?:[^"\\]|\\.)*)","provider":"([a-z]+)","repo_id":"(R-[0-9a-f]{12})",'
                  r'"resource_address":"((?:[^"\\]|\\.)*)"')
DATA_ADDR = re.compile(r"(^|\.)data\.[a-z]")
BATCH_BYTES = 48 << 20


def _root(pivot: str) -> str:
    return re.split(r"[.\[]", pivot, maxsplit=1)[0]


ATTR = re.compile(r'^\{"attr_path":"((?:[^"\\]|\\.)*)"')
RTYPE = re.compile(r'"resource_type":"([a-z][a-z0-9_]*)","term":')


def repo_scan(lines, norm_cache=None):
    """Linhas (bytes) de UM repositório -> resumo por diretório, usos de variáveis e átomos do repositório."""
    norm_cache = {} if norm_cache is None else norm_cache
    dirs: dict = {}
    uses = defaultdict(list)
    atoms: set = set()
    rid = fid = None
    for raw in lines:
        if not raw.strip():
            continue
        s = raw.decode("utf-8")
        m = HEAD.search(s, 0, 2000)
        ma = ATTR.match(s)
        mt = RTYPE.search(s, m.end() if m else 0) if ma else None
        rec = None
        if m and ma and mt:
            file, prov, rid = json.loads('"' + m.group(1) + '"'), m.group(2), m.group(3)
            apath, rtype, addr = json.loads('"' + ma.group(1) + '"'), mt.group(1), json.loads('"' + m.group(4) + '"')
        else:
            rec = json.loads(s)
            file, prov, rid = rec["file"], rec["provider"], rec["repo_id"]
            apath, rtype, addr = rec["attr_path"], rec["resource_type"], rec["resource_address"]
        if fid is None:
            fm = FAMILY.search(s, 0, 2000)
            fid = fm.group(1) if fm else (rec or json.loads(s))["family_id"]
        na = norm_cache.get(apath)
        if na is None:
            na = norm_cache[apath] = terms.norm_attr(apath)
        cat, atom = na
        if cat == "attribute" and DATA_ADDR.search(addr):
            cat, atom = "data_source", None    # átomo do C01 é de recurso gerenciado; data source fica no rastro
        if cat == "attribute":
            atoms.add(f"{rtype}:{atom}")
        d = posixpath.dirname(file) or "."
        info = dirs.get(d)
        if info is None:
            info = dirs[d] = {"providers": Counter(), "n_records": 0, "vars": set()}
        info["providers"][prov] += 1
        info["n_records"] += 1
        if '"name_class":"variable"' not in s:
            continue
        if rec is None:
            rec = json.loads(s)
        for pivot, ops in terms.var_uses(rec["term"]):
            if cat in ("attribute", "data_source"):
                info["vars"].add(_root(pivot))
            uses[d].append((pivot, prov, rtype, addr, apath, cat, atom, list(ops), file))
    return rid, fid, dirs, uses, atoms


def common_depth(a: str, b: str) -> int:
    n = 0
    for x, y in zip(a.split("/"), b.split("/")):
        if x != y:
            break
        n += 1
    return n


def find_pairs(dirs, uses, min_shared, min_jaccard):
    """Pares V3 (limiar) filtrados por V3b (contraparte mútua): cada variante fica só com as contrapartes de
    outro provedor de melhor posto (Jaccard maior; empate -> prefixo de diretório comum mais longo), e o par só
    entra se a escolha é mútua. Devolve também o nº de pares que passavam só no limiar (V3)."""
    variants = {d: next(iter(i["providers"])) for d, i in dirs.items() if len(i["providers"]) == 1}
    mixed = sum(1 for i in dirs.values() if len(i["providers"]) > 1)
    vlist = sorted(d for d in variants if dirs[d]["vars"])
    cand = []
    for i, a in enumerate(vlist):
        for b in vlist[i + 1:]:
            pa, pb = variants[a], variants[b]
            if pa == pb:
                continue
            ia, ib = dirs[a]["vars"], dirs[b]["vars"]
            inter = ia & ib
            if len(inter) < min_shared:
                continue
            jac = len(inter) / len(ia | ib)
            if jac < min_jaccard:
                continue
            cand.append((a, b, jac))
    best: dict = {}
    for a, b, jac in cand:
        rank = (jac, common_depth(a, b))
        for x, y in ((a, b), (b, a)):
            k = (x, variants[y])
            cur = best.get(k)
            if cur is None or rank > cur[0]:
                best[k] = (rank, {y})
            elif rank == cur[0]:
                cur[1].add(y)
    pairs = []
    for a, b, jac in cand:
        if b not in best[(a, variants[b])][1] or a not in best[(b, variants[a])][1]:
            continue
        pa, pb = variants[a], variants[b]
        if PROVIDERS.index(pa) > PROVIDERS.index(pb):
            a, b, pa, pb = b, a, pb, pa
        ia, ib = dirs[a]["vars"], dirs[b]["vars"]
        inter = ia & ib
        ua = defaultdict(list)
        ub = defaultdict(list)
        for u in uses[a]:
            if _root(u[0]) in inter:
                ua[u[0]].append(u)
        for u in uses[b]:
            if _root(u[0]) in inter:
                ub[u[0]].append(u)
        feeds = {}
        for piv in sorted(set(ua) & set(ub)):
            feeds[piv] = {"a": [_use(u) for u in ua[piv]], "b": [_use(u) for u in ub[piv]]}
        pairs.append({"dir_a": a, "dir_b": b, "provider_a": pa, "provider_b": pb, "n_vars_a": len(ia),
                      "n_vars_b": len(ib), "n_shared": len(inter), "jaccard": round(jac, 6),
                      "common_dir_depth": common_depth(a, b), "equal_interface": ia == ib, "feeds": feeds})
    pairs.sort(key=lambda p: (p["dir_a"], p["dir_b"]))
    return variants, mixed, pairs, len(cand)


def _use(u):
    pivot, prov, rtype, addr, apath, cat, atom, ops, file = u
    return {"resource_type": rtype, "address": addr, "attr_path": apath, "category": cat, "atom": atom,
            "ops": ops, "mode": terms.mode_of(tuple(ops)), "file": file}


def components(pairs):
    parent: dict = {}

    def f(x):
        while parent.setdefault(x, x) != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for p in pairs:
        ra, rb = f(p["dir_a"]), f(p["dir_b"])
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)
    comp = defaultdict(set)
    for p in pairs:
        comp[f(p["dir_a"])].update((p["dir_a"], p["dir_b"]))
    return [sorted(v) for _, v in sorted(comp.items())]


def _work(args):
    path, start, end, repos, min_shared, min_jaccard = args
    out, fam_atoms = [], []
    cache: dict = {}
    with open(path, "rb") as f:
        f.seek(start)
        buf = f.read(end - start)
    for rid, s, e in repos:
        lines = buf[s - start:e - start].split(b"\n")
        r_id, fid, dirs, uses, atoms = repo_scan(lines, cache)
        if r_id is not None and r_id != rid:
            raise RuntimeError(f"índice e arquivo divergem em {rid}")
        variants, mixed, pairs, n_cand = find_pairs(dirs, uses, min_shared, min_jaccard)
        comps = components(pairs)
        out.append({"repo_id": rid, "family_id": fid, "n_dirs": len(dirs), "n_variant_dirs": len(variants),
                    "n_threshold_pairs": n_cand, "n_mixed_dirs": mixed,
                    "variant_providers": dict(sorted(Counter(variants.values()).items())),
                    "multi_provider_variants": len(set(variants.values())) >= 2,
                    "pairs": pairs, "families": comps,
                    "variants": {d: variants[d] for c in comps for d in c}})
        fam_atoms.append((rid, fid, sorted(atoms)))
    return out, fam_atoms


def batches(index: dict, limit=None):
    items = sorted((v[0], v[1], rid) for rid, v in index.items())
    if limit:
        items = items[:limit]
    cur, cs, ce = [], None, None
    for s, e, rid in items:
        if cs is None:
            cs = s
        if cur and (e - cs > BATCH_BYTES or s != ce):
            yield cs, ce, cur
            cur, cs = [], s
        cur.append((rid, s, e))
        ce = e
    if cur:
        yield cs, ce, cur


def scan(workers=14, limit=None, min_shared=PARAMS["min_shared_vars"], min_jaccard=PARAMS["min_jaccard"]):
    """-> (resumo por repositório em ordem de repo_id, nº de famílias C06 distintas por átomo 'tipo:caminho')."""
    index = json.loads(symbolic_index().read_text(encoding="utf-8"))["repos"]
    path = str(symbolic_config())
    jobs = [(path, s, e, reps, min_shared, min_jaccard) for s, e, reps in batches(index, limit)]
    res, fam_atoms = [], []
    ctx = mp.get_context("spawn")
    with ctx.Pool(workers) as pool:
        for chunk, fa in pool.imap_unordered(_work, jobs, chunksize=1):
            res.extend(chunk)
            fam_atoms.extend(fa)
    res.sort(key=lambda r: r["repo_id"])
    fam_atoms.sort()
    seen, atom_families = set(), Counter()
    for _rid, fid, atoms in fam_atoms:
        if fid in seen:
            continue
        seen.add(fid)
        atom_families.update(atoms)
    return res, atom_families


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="bo.gold_mods.scan")
    ap.add_argument("--workers", type=int, default=14)
    ap.add_argument("--limit", type=int)
    ap.add_argument("--out", default=str(tmp_dir() / "scan.jsonl"))
    a = ap.parse_args(argv)
    res, _atoms = scan(a.workers, a.limit)
    with open(a.out, "w", encoding="utf-8") as f:
        for r in res:
            f.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")
    n_pairs = sum(len(r["pairs"]) for r in res)
    print(f"[{now_iso()}] scan: {len(res)} repos, {n_pairs} pares -> {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
