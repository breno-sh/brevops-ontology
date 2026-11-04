"""Gera $BO_DATA/CORPUS-AZURE/.staging/{usage.jsonl, atom_totals.jsonl, type_totals.jsonl, build_report.json}.

  python -I -m bo.corpus_azure.build [--out DIR] [--sample-mod M]

A contagem é a biblioteca única dos CORPUS em bo/base (bo.corpus_oci.counting: AtomIndex, Tally, dumps), com o
provedor azurerm como argumento; aqui ficam só a leitura das entradas, o relatório e o resumo. Lê o
resources.parquet (azurerm), o symbolic_config.jsonl só nos intervalos de bytes dos repositórios com azurerm
(pelo symbolic_config.index.json do HCL) e o atoms.jsonl do SCHEMA-AZURE. Nada é executado. A troca da staging
para a pasta do módulo é do bo.corpus_azure.swap, dentro da trava.

--sample-mod M (teste de regeneração): só 1 em M repositórios (sha256 do repo_id), escrito em --out.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from collections import Counter
from pathlib import Path

from bo.corpus_oci import counting

from . import MODULE, PROVIDER

PARAMS = {"top_n": 25, "library": "bo.corpus_oci.counting"}


def bo_data() -> Path:
    return Path(os.environ.get("BO_DATA", "/Users/breno/doutorado/brevops-data"))


def inputs() -> dict:
    d = bo_data()
    return {"resources": d / "HCL" / "resources.parquet", "symbolic": d / "HCL" / "symbolic_config.jsonl",
            "index": d / "HCL" / "symbolic_config.index.json", "atoms": d / "SCHEMA-AZURE" / "atoms.jsonl"}


def now() -> str:
    os.environ["TZ"] = "America/Recife"
    time.tzset()
    s = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    return s[:-2] + ":" + s[-2:]


def sample_pick(repo_id: str, mod: int) -> bool:
    return int(hashlib.sha256(repo_id.encode()).hexdigest(), 16) % mod == 0


def read_resources(path: Path) -> list[dict]:
    import pyarrow.parquet as pq
    return pq.read_table(path, filters=[("provider", "==", PROVIDER)]).to_pylist()


def tally_corpus(sample_mod: int = 0) -> tuple[counting.Tally, dict]:
    """Tally do azurerm (ou da amostra) e contadores de leitura."""
    src = inputs()
    for k, p in src.items():
        if not p.is_file():
            raise FileNotFoundError(f"entrada ausente ({k}): {p}")
    atoms = counting.AtomIndex.load(str(src["atoms"]), PROVIDER)
    tally = counting.Tally(PROVIDER, atoms)
    repos = set()
    for row in read_resources(src["resources"]):
        if sample_mod and not sample_pick(row["repo_id"], sample_mod):
            continue
        if tally.add_resource(row):
            repos.add(row["repo_id"])
    idx = json.loads(src["index"].read_text(encoding="utf-8"))["repos"]
    read = Counter()
    with open(src["symbolic"], "rb") as f:
        for repo in sorted(repos):
            span = idx.get(repo)
            if span is None:
                read["repos_without_records"] += 1
                continue
            start, end, n = span
            f.seek(start)
            lines = f.read(end - start).splitlines()
            if len(lines) != n:
                raise ValueError(f"índice do HCL diverge do jsonl: {len(lines)} linhas, índice diz {n}")
            read["records_read"] += n
            for ln in lines:
                rec = json.loads(ln)
                if rec["repo_id"] != repo:
                    raise ValueError("faixa do índice com registro de outro repositório")
                tally.add_record(rec)
    read["repos"] = len(repos)
    return tally, dict(read)


def write_jsonl(path: Path, recs) -> None:
    tmp = path.with_suffix(path.suffix + ".part")
    with open(tmp, "w", encoding="utf-8") as f:
        for r in recs:
            f.write(counting.dumps(r) + "\n")
    tmp.replace(path)


def build(out: Path, sample_mod: int = 0) -> dict:
    t0 = time.time()
    tally, read = tally_corpus(sample_mod)
    usage = tally.usage_records()
    out.mkdir(parents=True, exist_ok=True)
    write_jsonl(out / "usage.jsonl", usage)
    if sample_mod:
        return {"repos": read["repos"], "rows": len(usage)}
    atom_tot = tally.atom_totals()
    type_tot = tally.type_totals()
    write_jsonl(out / "atom_totals.jsonl", atom_tot)
    write_jsonl(out / "type_totals.jsonl", type_tot)
    report = summarize(tally, read, usage, atom_tot, type_tot)
    report["elapsed_s"] = round(time.time() - t0, 1)
    report["generated_at"] = now()
    (out / "build_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
                                           encoding="utf-8")
    return report


def summarize(tally: counting.Tally, read: dict, usage: list, atom_tot: list, type_tot: list) -> dict:
    top = PARAMS["top_n"]
    st, res = tally.stats, tally.resources
    conf = [a for a in atom_tot if a["configurable"]]
    used = [a for a in atom_tot if a["n_set"]]
    settings = {c: sum(a["n_" + c] for a in atom_tot) for c in counting.CLASSES}
    total = sum(settings.values())
    conc, acc, marks = {}, 0, [0.5, 0.9]
    for i, v in enumerate(sorted((a["n_set"] for a in atom_tot), reverse=True), 1):
        acc += v
        while marks and total and acc >= marks[0] * total:
            conc[f"atoms_for_{int(marks.pop(0) * 100)}pct_settings"] = i
    out_types = sorted((t for t in type_tot if not t["in_schema"]), key=lambda t: (-t["n_resources"],
                                                                                    t["resource_type"]))
    managed = st["managed_records"]
    n_conf_used = sum(1 for a in conf if a["n_set"])
    return {
        "module": MODULE, "provider": PROVIDER, "params": dict(PARAMS),
        "corpus": {"n_repos": len({k[0] for k in res}), "n_families": len({v[0] for v in res.values()}),
                   "n_modules": len({(k[0], counting.module_key(k[1])) for k in res}),
                   "n_resources": st["managed_blocks"], "n_data_blocks_skipped": st["data_blocks"],
                   "n_repos_without_records": read.get("repos_without_records", 0)},
        "rows": {"usage_rows": len(usage), "atom_rows": sum(1 for u in usage if "atom_id" in u),
                 "type_rows": sum(1 for u in usage if "atom_id" not in u)},
        "records": {"records_read_in_ranges": read.get("records_read", 0),
                    "data_source_records": st["data_records"], "resource_records": managed,
                    "attributed_records": st["attributed_records"],
                    "attributed_share": round(st["attributed_records"] / managed, 6) if managed else None,
                    "term_class_records": {c: st[f"term_class:{c}"] for c in counting.CLASSES},
                    "unattributed_by_cause": {c: st[f"unattributed:{c}"] for c in counting.UNATTRIBUTED}},
        "atoms": {"n_atoms": len(atom_tot), "n_configurable": len(conf), "n_used": len(used),
                  "n_configurable_used": n_conf_used,
                  "configurable_used_share": round(n_conf_used / len(conf), 6) if conf else None,
                  "n_nonconfigurable_used": sum(1 for a in used if not a["configurable"]),
                  "n_used_in_10plus_repos": sum(1 for a in used if a["n_repos"] >= 10),
                  "n_used_in_2plus_families": sum(1 for a in used if a["n_families"] >= 2), **conc},
        "types": {"n_types_schema": len(tally.atoms.paths), "n_types_used": len(type_tot),
                  "n_types_used_in_schema": sum(1 for t in type_tot if t["in_schema"]),
                  "n_types_used_not_in_schema": len(out_types),
                  "resources_type_not_in_schema": sum(t["n_resources"] for t in out_types),
                  "top_types_not_in_schema": [{"resource_type": t["resource_type"], "n_resources": t["n_resources"],
                                               "n_repos": t["n_repos"]} for t in out_types[:top]]},
        "settings_by_class": {**settings, "total": total},
        "top_atoms_by_repos": [{"atom_id": a["atom_id"], "n_repos": a["n_repos"], "n_families": a["n_families"],
                                "n_modules": a["n_modules"], "n_set": a["n_set"]}
                               for a in sorted(used, key=lambda a: (-a["n_repos"], a["atom_id"]))[:top]],
        "unattributed_top": [
            {"cause": c, "resource_type": rt, "path": counting.safe_report_path(tally.atoms, p), "records": n}
            for (c, rt, p), n in sorted(tally.unattributed.items(), key=lambda kv: (-kv[1], kv[0]))[:top]],
        "rules": {
            "library": "bo.corpus_oci.counting (a mesma dos CORPUS em bo/base), provedor azurerm",
            "resource": "linha de resources.parquet do azurerm sem o segmento data. no endereço; "
                        "count/for_each contam uma vez",
            "module": "(repo_id, dirname(file)) com o caminho já simbolizado pelo HCL",
            "atom_resolution": "sem [n]; dynamic[\"b\"][n].content. -> b.; caminho exato ou maior prefixo que é "
                               "átomo de atributo (ex.: security_rule { access = ... } -> security_rule)",
            "explicit_null": "literal null resolve o átomo mas não o configura (Terraform: igual a omitir)",
            "class": "withheld se contém termo retido; literal se literal ou documento sem símbolo nem termo "
                     "embutido; senão symbolic; várias ocorrências: withheld > symbolic > literal",
            "type_row": "linha sem atom_id por (repo, tipo): n_resources = recursos do tipo; n_set = recursos "
                        "com >= 1 átomo configurado",
            "atom_row": "linha com atom_id só quando n_set > 0; n_resources = recursos do tipo no repositório",
        },
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="bo.corpus_azure.build")
    ap.add_argument("--sample-mod", type=int, default=0)
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)
    if a.sample_mod and not a.out:
        print("--sample-mod exige --out", file=sys.stderr)
        return 2
    out = Path(a.out) if a.out else bo_data() / MODULE / ".staging"
    print(f"[{now()}] {MODULE}: build em {out}", flush=True)
    r = build(out, a.sample_mod)
    if a.sample_mod:
        print(f"[{now()}] amostra: {r['repos']} repositórios, {r['rows']} linhas", flush=True)
        return 0
    print(f"[{now()}] {r['corpus']['n_repos']} repositórios, {r['corpus']['n_resources']} recursos, "
          f"{r['rows']['usage_rows']} linhas usage, {r['atoms']['n_used']} átomos usados, {r['elapsed_s']} s",
          flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
