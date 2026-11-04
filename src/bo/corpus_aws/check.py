"""Invariantes das saídas do CORPUS-AWS contra as entradas.

  python -I -m bo.corpus_aws.check [DIR] [--validator] [--sample-mod M]

DIR: pasta com usage.jsonl, atom_totals.jsonl, build_report.json e counts.json (padrão $BO_DATA/CORPUS-AWS).
Confere, sem reutilizar o código de contagem:
  1. forma: chaves do C06 usage e nada mais (nenhum campo de partição), provedor, ordem canônica, unicidade,
     C06-USAGE, linha de tipo única por (repo, tipo) e linhas de átomo com o mesmo n_resources;
  2. recontagem pelo parquet (pyarrow, agrupado): recursos gerenciados por (repo, família, tipo) == linhas de tipo;
  3. átomos: atom_id do tipo da linha e presente no schema; atom_totals cobre o schema inteiro e é a soma do usage;
  4. segunda implementação, numa amostra determinística de repositórios (sha256(repo) % M == 0): as regras U1-U9
     reescritas de forma independente dão as mesmas linhas;
  5. build_report: sha256 das entradas == arquivos atuais e das saídas == arquivos da pasta; consistência zero.
--deps confere o sha256 de cada entrada consumida com o MANIFEST.sha256 publicado pela dep (HCL, SCHEMA-AWS).
--validator também roda o validador oficial (python -I -m bo.contracts.validate usage). Grava check_report.json
na pasta (carimbo com o sha256 de cada arquivo; o promote exige o carimbo com o validador).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

from . import common as K

USAGE_KEYS = {"repo_id", "family_id", "provider", "resource_type", "n_resources", "n_set", "n_literal",
              "n_symbolic", "n_withheld"}
FILES = ("usage.jsonl", "atom_totals.jsonl", "build_report.json", "counts.json")
DEFAULT_SAMPLE_MOD = 61


# ------------------------------------------------------------------------------------------------ 2ª implementação
_IDX = re.compile(r"\[\d+\]")
_DYN = re.compile(r'dynamic\["([^"]*)"\](?:\[\d+\])*\.')
_META = {"count", "for_each", "provider", "depends_on", "lifecycle", "provisioner", "connection"}
_SYMB = {"variable", "local", "module_output", "data_source", "resource_attribute", "count_index", "each_key",
         "workspace"}
_IMPURE = {"file", "fileexists", "fileset", "filebase64", "filebase64sha256", "filebase64sha512", "filemd5",
           "filesha1", "filesha256", "filesha512", "templatefile", "abspath", "pathexpand", "timestamp",
           "plantimestamp", "uuid", "bcrypt"}


def naive_path(p: str):
    """None para meta; senão a lista de segmentos (dynamic["b"][i].content. -> b.)."""
    s = p
    while True:
        m = _DYN.search(s)
        if not m:
            break
        rest = s[m.end():]
        if not rest.startswith("content.") and rest != "content":
            return None  # for_each / iterator / labels do dynamic
        s = s[:m.start()] + m.group(1) + ("." + rest[len("content."):] if rest.startswith("content.") else "")
    s = _IDX.sub("", s)
    segs = s.split(".")
    if segs[0] in _META:
        return None
    return segs


def naive_class(t, found=None) -> set:
    """Conjunto de marcas do termo: 'w' retido, 's' simbólico (termo e árvore de documento em funções separadas)."""
    found = set() if found is None else found
    k = t["kind"]
    if k == "withheld":
        found.add("w")
    elif k == "reference":
        found.add("s")
    elif k == "symbol":
        if t["name_class"] in _SYMB:
            found.add("s")
    elif k == "expression":
        if t["op"] in _IMPURE:
            found.add("s")
        for a in t["args"]:
            naive_class(a, found)
    elif k == "document":
        _naive_tree(t["tree"], found)
    elif k != "literal":
        raise ValueError(f"termo desconhecido {k!r}")
    return found


def _naive_tree(x, found) -> None:
    # árvore JSON de documento: só os valores de "$term" e "$key" são termos; o resto é dado comum
    if isinstance(x, list):
        for v in x:
            _naive_tree(v, found)
    elif isinstance(x, dict):
        for kk, v in x.items():
            if kk in ("$term", "$key") and isinstance(v, dict) and "kind" in v:
                naive_class(v, found)
            else:
                _naive_tree(v, found)


def naive_repo(lines, managed: dict, atoms: dict, configurable_under: dict):
    """(tipo, átomo) -> [n_set, lit, sym, wh] por regras reescritas."""
    cell = {}
    for r in lines:
        key = (r["file"], r["resource_address"])
        if key not in managed:
            continue
        t = managed[key]
        segs = naive_path(r["attr_path"])
        if segs is None or t not in atoms or r["term"] == {"kind": "literal", "datatype": "null", "value": None}:
            continue
        marks = naive_class(r["term"])
        cls = 2 if "w" in marks else (1 if "s" in marks else 0)
        hit = None
        for k in range(len(segs), 0, -1):
            if ".".join(segs[:k]) in atoms[t]:
                hit = ".".join(segs[:k])
                break
        if hit is None and r["term"].get("kind") == "withheld":
            u = configurable_under.get((t, ".".join(segs)), ())
            if len(u) == 1:
                hit = next(iter(u))
        if hit is None:
            continue
        ck = (key, hit)
        cell[ck] = max(cell.get(ck, -1), cls)
    out = defaultdict(lambda: [0, 0, 0, 0])
    for ((f, a), p), c in cell.items():
        row = out[(managed[(f, a)], p)]
        row[0] += 1
        row[1 + c] += 1
    return out


# ------------------------------------------------------------------------------------------------ conferência
DEPS = ("HCL", "SCHEMA-AWS")


def deps_manifest_entries() -> tuple[dict, list[str]]:
    """Caminho real -> sha256 nos MANIFEST.sha256 das deps (results/<D>/ e $BO_DATA/<D>/)."""
    entries, seen = {}, []
    for dep in DEPS:
        for mf in (K.bo_repo() / "results" / dep / "MANIFEST.sha256", K.bo_data() / dep / "MANIFEST.sha256"):
            if not mf.is_file():
                continue
            seen.append(K.portable(mf))
            for ln in mf.read_text(encoding="utf-8").splitlines():
                if not ln.strip():
                    continue
                sha, p = ln.split("  ", 1)
                for var, root in (("$BO_DATA", str(K.bo_data())), ("$BO_REPO", str(K.bo_repo()))):
                    if p.startswith(var):
                        p = root + p[len(var):]
                path = Path(p) if p.startswith("/") else (mf.parent / p)
                entries[str(path.resolve())] = sha
    return entries, seen


def consumed_vs_deps(d: Path) -> list[str]:
    """O sha256 de cada entrada consumida (build_report) é o que o manifesto da dep publicou."""
    report = json.loads((Path(d) / "build_report.json").read_text(encoding="utf-8"))
    entries, seen = deps_manifest_entries()
    errs = []
    if not seen:
        return ["nenhum MANIFEST.sha256 das deps (HCL, SCHEMA-AWS) encontrado"]
    for e in report["inputs"]:
        p = e["path"]
        for var, root in (("$BO_DATA", str(K.bo_data())), ("$BO_REPO", str(K.bo_repo()))):
            if p.startswith(var):
                p = root + p[len(var):]
        want = entries.get(str(Path(p).resolve()))
        if want is None:
            errs.append(f"entrada {e['name']} ({e['path']}) fora dos manifestos das deps")
        elif want != e["sha256"]:
            errs.append(f"entrada {e['name']}: consumida com sha {e['sha256'][:12]}…, manifesto da dep {want[:12]}…")
    return errs


def stamp_matches(d: Path, need_validator: bool = True) -> bool:
    p = Path(d) / "check_report.json"
    try:
        rep = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    if rep.get("result") != "PASS" or (need_validator and not rep.get("validator")):
        return False
    return all((Path(d) / n).is_file() and rep.get("files", {}).get(n) == K.sha256_file(Path(d) / n)
               for n in FILES)


def run(d: Path, validator: bool, sample_mod: int) -> tuple[list[str], dict]:
    errs: list[str] = []
    info: dict = {}
    inp = K.inputs()
    for n in FILES:
        if not (d / n).is_file():
            return [f"falta {n} em {d}"], info
    report = json.loads((d / "build_report.json").read_text(encoding="utf-8"))
    counts = json.loads((d / "counts.json").read_text(encoding="utf-8"))
    prov = report["provider"]

    # 5. build_report
    names = {"resources": inp["resources"], "symbolic_config": inp["symbolic_config"],
             "symbolic_index": inp["symbolic_index"], "atoms": inp["atoms"]}
    seen = {e["name"]: e for e in report["inputs"]}
    for k, p in names.items():
        e = seen.get(k)
        if e is None:
            errs.append(f"build_report sem a entrada {k}")
        elif e["sha256"] != K.sha256_file(p):
            errs.append(f"entrada {k} mudou desde a contagem ({K.portable(p)})")
    for n in ("usage.jsonl", "atom_totals.jsonl"):
        if report["outputs"].get(n) != K.sha256_file(d / n):
            errs.append(f"sha256 de {n} != build_report")
    for k, v in counts["consistency"].items():
        if v:
            errs.append(f"consistência {k} = {v}")
    info["inputs_sha256"] = {e["name"]: e["sha256"] for e in report["inputs"]}

    # schema
    atoms: dict[str, set] = defaultdict(set)
    configurable_under: dict = defaultdict(set)
    with open(inp["atoms"], encoding="utf-8") as f:
        for line in f:
            a = json.loads(line)
            atoms[a["resource_type"]].add(a["path"])
            if a.get("configurable"):
                segs = a["path"].split(".")
                for k in range(1, len(segs)):
                    configurable_under[(a["resource_type"], ".".join(segs[:k]))].add(a["path"])

    # 2. recontagem pelo parquet
    import pyarrow.compute as pc
    import pyarrow.parquet as pq
    t = pq.read_table(inp["resources"], columns=["repo_id", "family_id", "file", "resource_address",
                                                 "resource_type", "provider"])
    t = t.filter(pc.equal(t["provider"], prov))
    is_data = pc.match_substring_regex(t["resource_address"], r"^(module\.SYM-[0-9a-f]+\.)*data\.")
    tm = t.filter(pc.invert(is_data))
    g = tm.group_by(["repo_id", "family_id", "resource_type"]).aggregate([("file", "count")])
    want_type = {(r, f, ty): n for r, f, ty, n in zip(g["repo_id"].to_pylist(), g["family_id"].to_pylist(),
                                                      g["resource_type"].to_pylist(), g["file_count"].to_pylist())}

    # amostra para a 2ª implementação
    def sampled(rid):
        return int(hashlib.sha256(rid.encode()).hexdigest(), 16) % sample_mod == 0
    sample_repos = sorted({r for (r, _f, _t) in want_type if sampled(r)})
    managed_by_repo: dict = defaultdict(dict)
    for r, fl, a, ty in zip(tm["repo_id"].to_pylist(), tm["file"].to_pylist(), tm["resource_address"].to_pylist(),
                            tm["resource_type"].to_pylist()):
        if sampled(r):
            managed_by_repo[r][(fl, a)] = ty

    # 1 e 3. forma, ordem, linhas de tipo e soma dos átomos
    got_type = {}
    sums = defaultdict(lambda: [0, 0, 0, 0, 0, set()])
    sample_rows = defaultdict(dict)
    prev = None
    cur_type = None
    n_rows = 0
    split_rx = re.compile(r"split|partition|calib|holdout|test_set", re.I)
    with open(d / "usage.jsonl", encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            u = json.loads(line)
            n_rows += 1
            ks = set(u)
            if ks - USAGE_KEYS - {"atom_id"} or USAGE_KEYS - ks:
                errs.append(f"usage[{i}]: chaves fora do C06 usage: {sorted(ks ^ (USAGE_KEYS | {'atom_id'}))}")
                break
            if any(split_rx.search(k) for k in ks):
                errs.append(f"usage[{i}]: campo de partição")
            if u["provider"] != prov:
                errs.append(f"usage[{i}]: provedor {u['provider']}")
            if u["n_literal"] + u["n_symbolic"] + u["n_withheld"] != u["n_set"] or u["n_set"] > u["n_resources"]:
                errs.append(f"usage[{i}]: C06-USAGE")
            aid = u.get("atom_id")
            key = (u["repo_id"], u["resource_type"], "" if aid is None else aid)
            if prev is not None and key <= prev:
                errs.append(f"usage[{i}]: fora da ordem canônica ou repetida")
            prev = key
            tk = (u["repo_id"], u["family_id"], u["resource_type"])
            if aid is None:
                if u["n_set"] != 0:
                    errs.append(f"usage[{i}]: linha de tipo com n_set != 0")
                got_type[tk] = u["n_resources"]
                cur_type = (tk, u["n_resources"])
                continue
            if cur_type is None or cur_type[0] != tk or cur_type[1] != u["n_resources"]:
                errs.append(f"usage[{i}]: linha de átomo sem a linha de tipo ou com outro n_resources")
            pre = f"{prov}:{u['resource_type']}:"
            if not aid.startswith(pre) or aid[len(pre):] not in atoms.get(u["resource_type"], ()):
                errs.append(f"usage[{i}]: atom_id fora do schema ou de outro tipo")
            if u["n_set"] < 1:
                errs.append(f"usage[{i}]: linha de átomo com n_set 0")
            s = sums[aid]
            s[0] += 1
            s[1] += u["n_set"]
            s[2] += u["n_literal"]
            s[3] += u["n_symbolic"]
            s[4] += u["n_withheld"]
            s[5].add(u["family_id"])
            if u["repo_id"] in managed_by_repo:
                sample_rows[u["repo_id"]][(u["resource_type"], aid[len(pre):])] = \
                    [u["n_set"], u["n_literal"], u["n_symbolic"], u["n_withheld"]]
            if len(errs) > 50:
                break
    if got_type != want_type:
        miss = len(set(want_type) - set(got_type))
        extra = len(set(got_type) - set(want_type))
        diff = sum(1 for k in set(want_type) & set(got_type) if want_type[k] != got_type[k])
        errs.append(f"linhas de tipo != recontagem do parquet: {miss} faltam, {extra} sobram, {diff} diferem")
    if counts["usage_rows"]["total"] != n_rows:
        errs.append("counts.usage_rows.total != linhas do usage.jsonl")
    info["usage_rows"] = n_rows
    info["type_rows_recounted"] = len(want_type)

    type_tot = Counter()
    for (_r, _f, ty), n in want_type.items():
        type_tot[ty] += n
    n_at = 0
    seen_atoms = set()
    with open(d / "atom_totals.jsonl", encoding="utf-8") as f:
        prev = None
        for i, line in enumerate(f, 1):
            a = json.loads(line)
            n_at += 1
            k = (a["resource_type"], a["path"])
            if prev is not None and k <= prev:
                errs.append(f"atom_totals[{i}]: fora de ordem")
            prev = k
            seen_atoms.add(a["atom_id"])
            s = sums.get(a["atom_id"], [0, 0, 0, 0, 0, set()])
            if [a["n_repos"], a["n_resources"], a["n_literal"], a["n_symbolic"], a["n_withheld"], a["n_families"]] \
                    != [s[0], s[1], s[2], s[3], s[4], len(s[5])]:
                errs.append(f"atom_totals[{i}]: não é a soma do usage")
            if a["type_n_resources"] != type_tot.get(a["resource_type"], 0):
                errs.append(f"atom_totals[{i}]: type_n_resources != recontagem do parquet")
            if a["n_modules"] < (1 if a["n_repos"] else 0) or a["n_modules"] > a["n_resources"] \
                    or a["n_modules"] < a["n_repos"]:
                errs.append(f"atom_totals[{i}]: n_modules fora de [n_repos, n_resources]")
            if len(errs) > 80:
                break
    schema_ids = {f"{prov}:{ty}:{p}" for ty, ps in atoms.items() for p in ps}
    if seen_atoms != schema_ids:
        errs.append(f"atom_totals não cobre o schema: {len(schema_ids - seen_atoms)} faltam, "
                    f"{len(seen_atoms - schema_ids)} sobram")
    if set(sums) - schema_ids:
        errs.append("usage com átomo fora do schema")
    info["atom_totals_rows"] = n_at

    # 4. segunda implementação na amostra
    idx = json.loads(inp["symbolic_index"].read_text(encoding="utf-8"))["repos"]
    diff_repos = 0
    n_cells = 0
    with open(inp["symbolic_config"], "rb") as fh:
        for rid in sample_repos:
            lines = []
            if rid in idx:
                s0, e0, _n = idx[rid]
                fh.seek(s0)
                for ln in fh.read(e0 - s0).split(b"\n"):
                    if ln:
                        r = json.loads(ln)
                        if r["provider"] == prov:
                            lines.append(r)
            nv = naive_repo(lines, managed_by_repo[rid], atoms, configurable_under)
            got = sample_rows.get(rid, {})
            want = {k: v for k, v in nv.items()}
            n_cells += sum(v[0] for v in want.values())
            if got != want:
                diff_repos += 1
                if diff_repos <= 5:
                    ks = sorted(set(got) ^ set(want)) or sorted(k for k in want if want[k] != got.get(k))
                    errs.append(f"2ª implementação diverge num repositório da amostra ({len(ks)} chave(s))")
    info["sample"] = {"mod": sample_mod, "repos": len(sample_repos), "cells": n_cells,
                      "repos_divergent": diff_repos}

    # validador oficial
    if validator and not errs:
        env = dict(os.environ)
        cp = subprocess.run([sys.executable, "-I", "-m", "bo.contracts.validate", "usage", str(d / "usage.jsonl")],
                            env=env, capture_output=True, text=True)
        tail = (cp.stdout + cp.stderr).strip().splitlines()[-1:] or [""]
        info["validator"] = tail[0][-200:]
        if cp.returncode != 0:
            errs.append("validador oficial reprovou o usage.jsonl")
    return errs, info


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="bo.corpus_aws.check")
    ap.add_argument("dir", nargs="?")
    ap.add_argument("--validator", action="store_true")
    ap.add_argument("--deps", action="store_true")
    ap.add_argument("--sample-mod", type=int, default=DEFAULT_SAMPLE_MOD)
    a = ap.parse_args(argv)
    validator = a.validator
    d = Path(a.dir) if a.dir else K.out_dir()
    errs, info = run(d, validator, a.sample_mod)
    if a.deps:
        de = consumed_vs_deps(d)
        info["deps_manifests"] = "OK" if not de else f"{len(de)} problema(s)"
        errs += de
    rep = {"module": K.MODULE, "checked_at": K.now(), "dir": K.portable(d), "result": "FAIL" if errs else "PASS",
           "validator": bool(validator and not errs), "errors": errs[:100], "info": info,
           "files": {n: K.sha256_file(d / n) for n in FILES if (d / n).is_file()}}
    K.write_json(d / "check_report.json", rep)
    for e in errs[:30]:
        print("  FALHA", e)
    s = info.get("sample", {})
    print(f"[{K.now()}] check {K.portable(d)}: {'PASS' if not errs else 'FAIL'}; {info.get('usage_rows')} linhas; "
          f"amostra {s.get('repos')} repositórios / {s.get('cells')} células, {s.get('repos_divergent')} divergentes"
          + (f"; validador: {info.get('validator')}" if validator else ""))
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
