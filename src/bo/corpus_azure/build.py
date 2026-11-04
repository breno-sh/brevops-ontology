"""Gera $BO_DATA/CORPUS-AZURE/.staging/{usage.jsonl, atom_totals.jsonl, type_totals.jsonl, build_report.json}.

  python -I -m bo.corpus_azure.build [--workers N] [--sample-mod M]

Lê o resources.parquet (recursos do azurerm), o symbolic_config.jsonl só nos intervalos de bytes dos repositórios
com azurerm (pelo symbolic_config.index.json do HCL) e o atoms.jsonl do SCHEMA-AZURE. Nada é executado; nenhum
nome em claro é lido além dos ids sintéticos do HCL. A troca da staging para a pasta do módulo é do
bo.corpus_azure.swap, dentro da trava.

--sample-mod M (só para o teste de regeneração): processa 1 em M repositórios (sha256 do repo_id) e escreve em
--out, sem totais globais.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from collections import Counter, defaultdict
from multiprocessing import get_context
from pathlib import Path

from . import MODULE, PROVIDER
from .count import CLASSES, UNMATCHED, AtomIndex, is_data_address, repo_usage

PARAMS = {"min_repos_unmatched_report": 5, "top_n": 25, "chunk_repos": 64}


def env_path(name: str, default: str) -> Path:
    return Path(os.environ.get(name, default))


def bo_data() -> Path:
    return env_path("BO_DATA", "/Users/breno/doutorado/brevops-data")


def inputs() -> dict:
    d = bo_data()
    return {"resources": d / "HCL" / "resources.parquet", "symbolic": d / "HCL" / "symbolic_config.jsonl",
            "index": d / "HCL" / "symbolic_config.index.json", "atoms": d / "SCHEMA-AZURE" / "atoms.jsonl"}


def now() -> str:
    os.environ.setdefault("TZ", "America/Recife")
    time.tzset()
    s = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    return s[:-2] + ":" + s[-2:]


def dumps(o) -> str:
    return json.dumps(o, sort_keys=True, ensure_ascii=False)


def sample_pick(repo_id: str, mod: int) -> bool:
    return int(hashlib.sha256(repo_id.encode()).hexdigest(), 16) % mod == 0


def load_atoms(path: Path) -> list:
    out = []
    with open(path, encoding="utf-8") as f:
        for ln in f:
            a = json.loads(ln)
            if a["provider"] == PROVIDER:
                out.append(a)
    return out


def load_resources(path: Path) -> tuple[dict, int]:
    import pyarrow.compute as pc
    import pyarrow.parquet as pq
    t = pq.read_table(path, columns=["repo_id", "family_id", "file", "resource_address", "resource_type",
                                     "provider"])
    t = t.filter(pc.equal(t["provider"], PROVIDER))
    by_repo: dict[str, list] = defaultdict(list)
    n_data = 0
    for rid, fam, f, a, rt in zip(*(t[c].to_pylist() for c in
                                    ("repo_id", "family_id", "file", "resource_address", "resource_type"))):
        if is_data_address(a):
            n_data += 1
            continue
        by_repo[rid].append((f, a, rt, fam))
    return dict(by_repo), n_data


_W: dict = {}


def _init(atoms_path: str, sym_path: str):
    _W["index"] = AtomIndex(load_atoms(Path(atoms_path)))
    _W["f"] = open(sym_path, "rb")


def _records(span):
    if span is None:
        return
    f = _W["f"]
    s, e = span[0], span[1]
    f.seek(s)
    buf = f.read(e - s)
    needle = f'"{PROVIDER}"'.encode()  # pré-filtro barato; o filtro exato por provider é do repo_usage
    for ln in buf.split(b"\n"):
        if ln and needle in ln:
            yield json.loads(ln)


def _work(chunk):
    out = []
    for rid, span, resources in chunk:
        u = repo_usage(PROVIDER, rid, resources, _records(span), _W["index"])
        if span is not None:
            u["audit"]["records_total_repo"] = span[2]
        out.append((rid, u))
    return out


def run_repos(tasks: list, workers: int):
    paths = inputs()
    step = PARAMS["chunk_repos"]
    chunks = [tasks[i:i + step] for i in range(0, len(tasks), step)]
    if workers <= 1:
        _init(str(paths["atoms"]), str(paths["symbolic"]))
        for c in chunks:
            yield from _work(c)
        return
    ctx = get_context("spawn")
    with ctx.Pool(workers, initializer=_init, initargs=(str(paths["atoms"]), str(paths["symbolic"]))) as pool:
        for res in pool.imap(_work, chunks):
            yield from res


def build(out: Path, workers: int, sample_mod: int = 0) -> dict:
    t0 = time.time()
    paths = inputs()
    atoms = load_atoms(paths["atoms"])
    by_repo, n_data = load_resources(paths["resources"])
    idx = json.load(open(paths["index"], encoding="utf-8"))["repos"]
    rids = sorted(by_repo)
    if sample_mod:
        rids = [r for r in rids if sample_pick(r, sample_mod)]
    tasks = [(r, idx.get(r), by_repo[r]) for r in rids]
    out.mkdir(parents=True, exist_ok=True)
    atom_meta = {a["atom_id"]: a for a in atoms}
    types_in_schema = {a["resource_type"] for a in atoms}
    tot = {a: {"n_repos": 0, "n_families": set(), "n_modules": 0, "n_resources": 0, "n_literal": 0,
               "n_symbolic": 0, "n_withheld": 0} for a in atom_meta}
    ttot: dict[str, dict] = defaultdict(lambda: {"n_repos": 0, "n_families": set(), "n_modules": 0,
                                                 "n_resources": 0, "n_set": 0})
    audit: Counter = Counter()
    unmatched_repos: Counter = Counter()
    fams, n_modules, n_rows, n_atom_rows = set(), 0, 0, 0
    with open(out / "usage.jsonl", "w", encoding="utf-8") as fu:
        for rid, u in run_repos(tasks, workers):
            audit.update(u["audit"])
            unmatched_repos.update(tuple(x) for x in u["unmatched_paths"])
            n_modules += u["n_modules"]
            for row in u["rows"]:
                fu.write(dumps(row) + "\n")
                n_rows += 1
                fams.add(row["family_id"])
                aid = row.get("atom_id")
                if aid is None:
                    tt = ttot[row["resource_type"]]
                    tt["n_repos"] += 1
                    tt["n_families"].add(row["family_id"])
                    tt["n_modules"] += u["type_modules"][row["resource_type"]]
                    tt["n_resources"] += row["n_resources"]
                    tt["n_set"] += row["n_set"]
                    continue
                n_atom_rows += 1
                t = tot[aid]
                t["n_repos"] += 1
                t["n_families"].add(row["family_id"])
                t["n_modules"] += u["atom_modules"][aid]
                for k in ("n_literal", "n_symbolic", "n_withheld"):
                    t[k] += row[k]
                t["n_resources"] += row["n_set"]
    if sample_mod:
        return {"repos": len(rids), "rows": n_rows}
    # totais por átomo (todos os átomos do schema, inclusive os nunca usados) e por tipo
    with open(out / "atom_totals.jsonl", "w", encoding="utf-8") as fa:
        for aid in sorted(tot):
            t, m = tot[aid], atom_meta[aid]
            rt = m["resource_type"]
            fa.write(dumps({"atom_id": aid, "resource_type": rt, "path": m["path"],
                            "configurable": m["configurable"], "required": m["required"],
                            "n_repos": t["n_repos"], "n_families": len(t["n_families"]),
                            "n_modules": t["n_modules"], "n_resources_set": t["n_resources"],
                            "n_resources_of_type": ttot[rt]["n_resources"] if rt in ttot else 0,
                            "n_literal": t["n_literal"], "n_symbolic": t["n_symbolic"],
                            "n_withheld": t["n_withheld"]}) + "\n")
    with open(out / "type_totals.jsonl", "w", encoding="utf-8") as ft:
        for rt in sorted(set(ttot) | types_in_schema):
            tt = ttot.get(rt, {"n_repos": 0, "n_families": set(), "n_modules": 0, "n_resources": 0, "n_set": 0})
            ft.write(dumps({"resource_type": rt, "in_schema": rt in types_in_schema, "n_repos": tt["n_repos"],
                            "n_families": len(tt["n_families"]), "n_modules": tt["n_modules"],
                            "n_resources": tt["n_resources"], "n_resources_with_atom": tt["n_set"]}) + "\n")
    report = summarize(tot, ttot, atom_meta, types_in_schema, audit, unmatched_repos, len(rids), len(fams),
                       n_modules, n_rows, n_atom_rows, n_data, idx, by_repo)
    report["elapsed_s"] = round(time.time() - t0, 1)
    report["generated_at"] = now()
    (out / "build_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
                                           encoding="utf-8")
    return report


def summarize(tot, ttot, atom_meta, types_in_schema, audit, unmatched_repos, n_repos, n_fams, n_modules, n_rows,
              n_atom_rows, n_data, idx, by_repo) -> dict:
    top = PARAMS["top_n"]
    used = [a for a, t in tot.items() if t["n_repos"] > 0]
    conf = [a for a, m in atom_meta.items() if m["configurable"]]
    used_conf = [a for a in conf if tot[a]["n_repos"] > 0]
    used_nonconf = [a for a in used if not atom_meta[a]["configurable"]]
    n_res = sum(len(v) for v in by_repo.values())
    n_res_in_schema = sum(t["n_resources"] for rt, t in ttot.items() if rt in types_in_schema)
    cls_tot = {c: sum(t["n_" + c] for t in tot.values()) for c in CLASSES}
    settings = sum(cls_tot.values())
    # concentração: quantos átomos cobrem 50% e 90% das configurações (recurso x átomo)
    vols = sorted((t["n_resources"] for t in tot.values()), reverse=True)
    conc, acc, marks = {}, 0, [0.5, 0.9]
    for i, v in enumerate(vols, 1):
        acc += v
        while marks and settings and acc >= marks[0] * settings:
            conc[f"atoms_for_{int(marks.pop(0) * 100)}pct_settings"] = i
    by_repos = sorted(used, key=lambda a: (-tot[a]["n_repos"], a))[:top]
    unm = {c: audit.get("unmatched:" + c, 0) for c in UNMATCHED}
    rec_res = audit.get("records_provider", 0) - audit.get("records_data_source", 0)
    frequent_unmatched = [{"resource_type": rt, "path": p, "n_repos": n} for (rt, p), n in
                          sorted(unmatched_repos.items(), key=lambda x: (-x[1], x[0]))
                          if n >= PARAMS["min_repos_unmatched_report"]][:top]
    types_used = [rt for rt, t in ttot.items() if t["n_resources"] > 0]
    out_types = sorted((rt for rt in types_used if rt not in types_in_schema),
                       key=lambda rt: (-ttot[rt]["n_resources"], rt))
    return {
        "module": MODULE, "provider": PROVIDER, "params": dict(PARAMS),
        "corpus": {"n_repos": n_repos, "n_families": n_fams, "n_modules": n_modules, "n_resources": n_res,
                   "n_resources_type_in_schema": n_res_in_schema, "n_data_blocks_skipped": n_data,
                   "n_repos_without_records": sum(1 for r in by_repo if r not in idx)},
        "rows": {"usage_rows": n_rows, "atom_rows": n_atom_rows, "type_rows": n_rows - n_atom_rows},
        "records": {"provider_records": audit.get("records_provider", 0),
                    "data_source_records": audit.get("records_data_source", 0),
                    "resource_records": rec_res, "matched_records": audit.get("records_matched", 0),
                    "matched_object_attr_records": audit.get("records_matched_object_attr", 0),
                    "matched_share": round(audit.get("records_matched", 0) / rec_res, 6) if rec_res else None,
                    "orphan_records": audit.get("records_orphan", 0),
                    "type_mismatch_records": audit.get("records_type_mismatch", 0),
                    "unmatched_by_category": unm},
        "atoms": {"n_atoms": len(atom_meta), "n_configurable": len(conf), "n_used": len(used),
                  "n_configurable_used": len(used_conf),
                  "configurable_used_share": round(len(used_conf) / len(conf), 6) if conf else None,
                  "n_nonconfigurable_used": len(used_nonconf),
                  "n_used_in_10plus_repos": sum(1 for a in used if tot[a]["n_repos"] >= 10),
                  **conc},
        "types": {"n_types_schema": len(types_in_schema), "n_types_used": len(types_used),
                  "n_types_used_in_schema": sum(1 for rt in types_used if rt in types_in_schema),
                  "n_types_used_not_in_schema": len(out_types),
                  "resources_type_not_in_schema": sum(ttot[rt]["n_resources"] for rt in out_types),
                  "top_types_not_in_schema": [{"resource_type": rt, "n_resources": ttot[rt]["n_resources"],
                                               "n_repos": ttot[rt]["n_repos"]} for rt in out_types[:top]]},
        "settings_by_class": {**cls_tot, "total": settings},
        "top_atoms_by_repos": [{"atom_id": a, "n_repos": tot[a]["n_repos"], "n_modules": tot[a]["n_modules"],
                                "n_resources_set": tot[a]["n_resources"]} for a in by_repos],
        "frequent_unmatched_paths": frequent_unmatched,
        "rules": {
            "resource": "bloco resource (não data) do azurerm; count/for_each contam uma vez",
            "module": "diretório do arquivo .tf no repositório",
            "type_row": "linha sem atom_id por (repo, tipo): n_resources = blocos do tipo; n_set = blocos com "
                        ">= 1 átomo configurado; classe do bloco = a mais fraca entre os seus átomos",
            "atom_row": "linha com atom_id só quando n_set > 0; n_resources = blocos do tipo no repositório",
            "class": "withheld > symbolic > literal por recurso; literal = valor sai só do texto do atributo",
            "object_attr": "campo de atributo de tipo objeto escrito como bloco (security_rule { ... }) configura "
                           "o átomo do atributo, se o campo existe no tf_type",
            "unmatched": "caminho que não é path de átomo do tipo no atoms.jsonl não vira átomo (contado aqui)",
        },
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="bo.corpus_azure.build")
    ap.add_argument("--workers", type=int, default=max(1, min(12, (os.cpu_count() or 2) - 2)))
    ap.add_argument("--sample-mod", type=int, default=0)
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)
    out = Path(a.out) if a.out else bo_data() / MODULE / ".staging"
    if a.sample_mod and not a.out:
        print("--sample-mod exige --out", file=sys.stderr)
        return 2
    print(f"[{now()}] {MODULE}: build em {out} ({a.workers} processos)", flush=True)
    r = build(out, a.workers, a.sample_mod)
    if a.sample_mod:
        print(f"[{now()}] amostra: {r['repos']} repositórios, {r['rows']} linhas", flush=True)
        return 0
    print(f"[{now()}] {r['corpus']['n_repos']} repositórios, {r['corpus']['n_resources']} recursos, "
          f"{r['rows']['usage_rows']} linhas usage, {r['atoms']['n_used']} átomos usados, {r['elapsed_s']} s",
          flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
