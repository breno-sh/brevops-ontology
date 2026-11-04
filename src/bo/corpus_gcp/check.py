"""Conferência do uso gravado em $BO_DATA/CORPUS-GCP (gate do módulo).

  python -I -m bo.corpus_gcp.check [--data DIR] [--sample-mod M]

1. entradas: o sha256 de cada entrada no build_report.json é o do arquivo atual; manifesto da pasta confere;
2. invariantes do usage.jsonl contra o resources.parquet e o schema: uma linha de tipo por (repo, tipo) com
   n_resources = blocos gerenciados do google no parquet; todo atom_id é átomo do SCHEMA-GCP e do tipo da linha;
   n_resources da linha de átomo = o da linha do tipo; n_set do átomo <= n_set do tipo; C06-USAGE;
3. atom_totals.jsonl e type_totals.jsonl = soma do usage.jsonl (n_repos, n_families, n_resources, classes);
4. RECONTAGEM INDEPENDENTE numa amostra determinística de repositórios (sha256(repo_id) % M == 0): outro código,
   sem bo.corpus_gcp.paths/count (normalização por expressão regular, leitura linha a linha), compara as linhas
   do usage.jsonl desses repositórios uma a uma.
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import re
import sys
from pathlib import Path

from . import common as C

META_TOP = ("count", "for_each", "provider", "depends_on", "lifecycle", "provisioner", "connection")
# classe pelo JSON serializado do termo (aspas estruturais não aparecem escapadas dentro de valores)
_WH = '"kind":"withheld"'
_SYMB = re.compile(r'"kind":"reference"|"name_class":"(variable|local|module_output|data_source|resource_attribute|'
                   r'count_index|each_key|workspace|path)"|"op":"(hcl_provider_function|file|filebase64|filebase64sha256|filebase64sha512|'
                   r'filemd5|filesha1|filesha256|filesha512|fileexists|fileset|templatefile|abspath|pathexpand|'
                   r'timestamp|plantimestamp|uuid|bcrypt)"')


def _cls(term: dict) -> str:
    s = json.dumps(term, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    if _WH in s:
        return "withheld"
    return "symbolic" if _SYMB.search(s) else "literal"


def _fail(msgs: list, m: str) -> None:
    if len(msgs) < 50:
        msgs.append(m)
    else:
        msgs[-1] = "... (mais falhas)"


def check_inputs(d: Path, errs: list) -> None:
    rep = json.load(open(d / "build_report.json", encoding="utf-8"))
    cur = C.inputs()
    for e in rep["inputs"]:
        p = cur.get(e["path"])
        if p is None or C.sha256_file(p) != e["sha256"]:
            _fail(errs, f"entrada mudou desde o build: {e['path']}")
    for ln in open(d / "MANIFEST.sha256", encoding="utf-8"):
        if not ln.strip():
            continue
        sha, name = ln.rstrip("\n").split("  ", 1)
        if C.sha256_file(d / name) != sha:
            _fail(errs, f"manifesto diverge: {name}")
    for name, sha in rep["outputs"].items():
        if C.sha256_file(d / name) != sha:
            _fail(errs, f"saída diverge do build_report: {name}")


def parquet_google_managed() -> dict[tuple[str, str], int]:
    import pyarrow.compute as pc
    import pyarrow.parquet as pq
    t = pq.read_table(C.hcl_dir() / "resources.parquet", columns=["repo_id", "resource_address", "resource_type",
                                                                  "provider"])
    t = t.filter(pc.equal(t["provider"], "google"))
    data = re.compile(r"^(module\.SYM-[0-9a-f]+\.)*data\.")
    n: collections.Counter = collections.Counter()
    for rid, addr, rt in zip(t["repo_id"].to_pylist(), t["resource_address"].to_pylist(),
                             t["resource_type"].to_pylist()):
        if not data.match(addr):
            n[(rid, rt)] += 1
    return n


def schema_atoms() -> dict[str, str]:
    out = {}
    for ln in open(C.atoms_path(), encoding="utf-8"):
        if ln.strip():
            a = json.loads(ln)
            if a.get("provider") == "google":
                out[a["atom_id"]] = a["resource_type"]
    return out


def check_invariants(d: Path, errs: list) -> dict:
    pq_n = parquet_google_managed()
    atoms = schema_atoms()
    type_rows: dict[tuple[str, str], dict] = {}
    atom_rows = []
    fam_of: dict[str, str] = {}
    for i, ln in enumerate(open(d / "usage.jsonl", encoding="utf-8"), 1):
        u = json.loads(ln)
        if u["provider"] != "google":
            _fail(errs, f"linha {i}: provider {u['provider']}")
        if fam_of.setdefault(u["repo_id"], u["family_id"]) != u["family_id"]:
            _fail(errs, f"linha {i}: repositório com duas famílias")
        if u["n_literal"] + u["n_symbolic"] + u["n_withheld"] != u["n_set"] or u["n_set"] > u["n_resources"]:
            _fail(errs, f"linha {i}: C06-USAGE")
        k = (u["repo_id"], u["resource_type"])
        if "atom_id" not in u:
            if k in type_rows:
                _fail(errs, f"linha {i}: segunda linha de tipo para o mesmo (repo, tipo)")
            type_rows[k] = u
        else:
            if atoms.get(u["atom_id"]) != u["resource_type"]:
                _fail(errs, f"linha {i}: atom_id fora do schema ou de outro tipo")
            if u["n_set"] < 1:
                _fail(errs, f"linha {i}: linha de átomo com n_set 0")
            atom_rows.append(u)
    if set(type_rows) != set(pq_n):
        _fail(errs, f"(repo, tipo) do usage != parquet: {len(set(type_rows) ^ set(pq_n))} diferença(s)")
    for k, u in type_rows.items():
        if pq_n.get(k) != u["n_resources"]:
            _fail(errs, "n_resources da linha de tipo != blocos gerenciados no parquet")
    tot_atoms: dict[str, list] = {}
    for u in atom_rows:
        t = type_rows.get((u["repo_id"], u["resource_type"]))
        if t is None:
            _fail(errs, "linha de átomo sem linha de tipo")
            continue
        if u["n_resources"] != t["n_resources"] or u["n_set"] > t["n_set"]:
            _fail(errs, "linha de átomo incoerente com a linha do tipo")
        a = tot_atoms.setdefault(u["atom_id"], [0, set(), 0, 0, 0, 0])
        a[0] += 1
        a[1].add(u["family_id"])
        a[2] += u["n_set"]
        a[3] += u["n_literal"]
        a[4] += u["n_symbolic"]
        a[5] += u["n_withheld"]
    n_at = 0
    for ln in open(d / "atom_totals.jsonl", encoding="utf-8"):
        x = json.loads(ln)
        n_at += 1
        a = tot_atoms.get(x["atom_id"], [0, set(), 0, 0, 0, 0])
        got = [x["n_repos"], x["n_families"], x["n_resources"], x["n_literal"], x["n_symbolic"], x["n_withheld"]]
        if got != [a[0], len(a[1]), a[2], a[3], a[4], a[5]]:
            _fail(errs, f"atom_totals diverge do usage: {x['atom_id']}")
        if x["n_modules"] > x["n_resources"] or (x["n_resources"] > 0) != (x["n_modules"] > 0):
            _fail(errs, f"atom_totals com n_modules incoerente: {x['atom_id']}")
    if n_at != len(atoms):
        _fail(errs, f"atom_totals tem {n_at} átomos, o schema {len(atoms)}")
    tt: dict[str, list] = {}
    for (rid, rt), u in type_rows.items():
        t = tt.setdefault(rt, [0, 0, 0])
        t[0] += 1
        t[1] += u["n_resources"]
        t[2] += u["n_set"]
    n_tt = 0
    for ln in open(d / "type_totals.jsonl", encoding="utf-8"):
        x = json.loads(ln)
        n_tt += 1
        if [x["n_repos"], x["n_resources"], x["n_resources_with_atom"]] != tt.get(x["resource_type"]):
            _fail(errs, f"type_totals diverge do usage: {x['resource_type']}")
    if n_tt != len(tt):
        _fail(errs, "type_totals com número de tipos diferente do usage")
    return {"rows": len(type_rows) + len(atom_rows), "type_rows": len(type_rows), "atom_rows": len(atom_rows),
            "repos": len(fam_of), "resources": sum(pq_n.values())}


# ------------------------------------------------------------------------------- recontagem independente
_IDX = re.compile(r"\[[0-9]+\]")
_DYN = re.compile(r'dynamic\["([^"]+)"\]')


def _norm(p: str):
    """Mesma regra, outro código: tira índices, troca dynamic["x"] por x, tira o .content do dynamic."""
    if p.split(".")[0].split("[")[0] in META_TOP:
        return None, False
    q = _DYN.sub(lambda m: "\x00" + m.group(1), p)
    q = _IDX.sub("", q)
    parts = q.split(".")
    out, prev_dyn = [], False
    for s in parts:
        if prev_dyn and s == "content":
            prev_dyn = False
            continue
        if prev_dyn and s in ("for_each", "iterator", "labels"):
            return None, False
        prev_dyn = s.startswith("\x00")
        out.append(s.lstrip("\x00"))
    whole_block = bool(re.search(r'(\]|dynamic\["[^"]+"\]\[[0-9]+\]\.content)$', p))
    return ".".join(out), whole_block


def recount(sample_mod: int) -> dict[str, list[dict]]:
    import pyarrow.parquet as pq
    atoms: dict[str, set] = collections.defaultdict(set)
    for aid, rt in schema_atoms().items():
        atoms[rt].add(aid.split(":", 2)[2])
    t = pq.read_table(C.hcl_dir() / "resources.parquet")
    data = re.compile(r"^(module\.SYM-[0-9a-f]+\.)*data\.")
    res: dict[str, dict] = collections.defaultdict(dict)
    fam = {}
    for r in t.to_pylist():
        if r["provider"] != "google":
            continue
        if int(hashlib.sha256(r["repo_id"].encode()).hexdigest(), 16) % sample_mod:
            continue
        fam[r["repo_id"]] = r["family_id"]
        if not data.match(r["resource_address"]):
            res[r["repo_id"]][(r["file"], r["resource_address"])] = r["resource_type"]
    idx = json.load(open(C.hcl_dir() / "symbolic_config.index.json", encoding="utf-8"))["repos"]
    rank = {"literal": 0, "symbolic": 1, "withheld": 2}
    out = {}
    with open(C.hcl_dir() / "symbolic_config.jsonl", "rb") as f:
        for rid in sorted(fam):
            setv: dict[tuple, str] = {}
            if rid in idx:
                s, e, _ = idx[rid]
                f.seek(s)
                for ln in f.read(e - s).decode("utf-8").splitlines():
                    r = json.loads(ln)
                    key = (r["file"], r["resource_address"])
                    rt = res[rid].get(key)
                    if r["provider"] != "google" or rt is None or rt not in atoms:
                        continue
                    p, whole = _norm(r["attr_path"])
                    if p is None:
                        continue
                    segs = p.split(".")
                    hit = None
                    if not whole and p in atoms[rt]:
                        hit = p
                    else:
                        for k in range(len(segs) if whole else len(segs) - 1, 0, -1):
                            if ".".join(segs[:k]) in atoms[rt]:
                                hit = ".".join(segs[:k])
                                break
                    if hit is None:
                        continue
                    if r["term"] == {"kind": "literal", "datatype": "null", "value": None}:
                        continue
                    c = _cls(r["term"])
                    old = setv.get((key, hit))
                    if old is None or rank[c] > rank[old]:
                        setv[(key, hit)] = c
            rows = []
            by_t: dict[str, list] = collections.defaultdict(list)
            for key, rt in res[rid].items():
                by_t[rt].append(key)
            for rt in sorted(by_t):
                keys = set(by_t[rt])
                per_res: dict = collections.defaultdict(dict)
                for (key, a), c in setv.items():
                    if key in keys:
                        per_res[key][a] = c
                worst = collections.Counter()
                for key, m in per_res.items():
                    worst[max(m.values(), key=rank.get)] += 1
                rows.append({"repo_id": rid, "family_id": fam[rid], "provider": "google", "resource_type": rt,
                             "n_resources": len(keys), "n_set": sum(worst.values()), "n_literal": worst["literal"],
                             "n_symbolic": worst["symbolic"], "n_withheld": worst["withheld"]})
                per_atom: dict = collections.defaultdict(collections.Counter)
                for key, m in per_res.items():
                    for a, c in m.items():
                        per_atom[a][c] += 1
                for a in sorted(per_atom):
                    k = per_atom[a]
                    rows.append({"repo_id": rid, "family_id": fam[rid], "provider": "google", "resource_type": rt,
                                 "atom_id": f"google:{rt}:{a}", "n_resources": len(keys), "n_set": sum(k.values()),
                                 "n_literal": k["literal"], "n_symbolic": k["symbolic"], "n_withheld": k["withheld"]})
            if rows:
                out[rid] = rows
    return out


def check_recount(d: Path, sample_mod: int, errs: list) -> dict:
    ref = recount(sample_mod)
    got: dict[str, list] = collections.defaultdict(list)
    for ln in open(d / "usage.jsonl", encoding="utf-8"):
        u = json.loads(ln)
        if u["repo_id"] in ref:
            got[u["repo_id"]].append(u)
    n_rows = bad = 0
    for rid, rows in ref.items():
        n_rows += len(rows)
        a = sorted(C.dumps(x) for x in rows)
        b = sorted(C.dumps(x) for x in got.get(rid, []))
        if a != b:
            bad += 1
            _fail(errs, f"recontagem independente diverge em {rid}: {len(set(a) ^ set(b))} linha(s)")
    return {"sample_mod": sample_mod, "repos": len(ref), "rows": n_rows, "repos_diverging": bad}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="bo.corpus_gcp.check")
    ap.add_argument("--data", default=None, help="pasta (padrão $BO_DATA/CORPUS-GCP)")
    ap.add_argument("--sample-mod", type=int, default=20)
    a = ap.parse_args(argv)
    d = Path(a.data) if a.data else C.out_dir()
    errs: list = []
    check_inputs(d, errs)
    inv = check_invariants(d, errs)
    rc = check_recount(d, a.sample_mod, errs)
    for e in errs:
        print("  FAIL", e)
    print(f"[{C.now()}] corpus_gcp.check: {inv['rows']} linhas ({inv['type_rows']} de tipo, {inv['atom_rows']} de "
          f"átomo), {inv['repos']} repositórios, {inv['resources']} blocos; recontagem independente em "
          f"{rc['repos']} repositórios ({rc['rows']} linhas, 1 em {rc['sample_mod']}), {rc['repos_diverging']} "
          f"divergente(s) -> {'OK' if not errs else 'REPROVADO'}")
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
