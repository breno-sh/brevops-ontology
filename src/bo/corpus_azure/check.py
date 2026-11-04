"""Conferência das saídas do CORPUS-AZURE além do contrato (chamada pelo gates/CORPUS-AZURE.sh).

  python -I -m bo.corpus_azure.check [--sample-mod 50]

1. cada (repo, tipo) tem exatamente uma linha de tipo (sem atom_id); toda linha de átomo tem a de tipo, o mesmo
   n_resources e n_set <= n_set do tipo; atom_id existe no atoms.jsonl e é do resource_type da linha;
2. as linhas de tipo somam os recursos do azurerm (sem data) do resources.parquet, por repositório e por tipo,
   e a família de cada repositório é a do parquet;
3. atom_totals.jsonl e type_totals.jsonl batem com a soma do usage.jsonl;
4. build_report.json, summary.json (bloco counts) e MANIFEST.sha256 batem com os arquivos;
5. regeneração: 1 em M repositórios (sha256 do repo_id) refeitos do zero saem com as mesmas linhas, byte a byte;
6. nenhum campo de partição (split) em linha alguma.
Grava $BO_DATA/CORPUS-AZURE/check_report.json.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections import Counter, defaultdict

from bo.corpus_oci import counting

from . import MODULE, PROVIDER
from .build import bo_data, inputs, now, read_resources, sample_pick
from .swap import FILES, bo_repo, sha256_file

SPLIT_KEYS = ("split", "partition", "fold", "calib", "eval", "holdout", "test")


def main(argv=None) -> int:  # noqa: C901
    ap = argparse.ArgumentParser(prog="bo.corpus_azure.check")
    ap.add_argument("--sample-mod", type=int, default=50)
    a = ap.parse_args(argv)
    data = bo_data() / MODULE
    errs: list[str] = []
    info: dict = {}

    atoms = {}
    with open(inputs()["atoms"], encoding="utf-8") as f:
        for ln in f:
            x = json.loads(ln)
            atoms[x["atom_id"]] = x
    by_repo = defaultdict(list)
    for row in read_resources(inputs()["resources"]):
        if not counting.is_data_address(row["resource_address"]):
            by_repo[row["repo_id"]].append(row)
    want_type = Counter()
    want_fam = {}
    for rid, rs in by_repo.items():
        for row in rs:
            want_type[(rid, row["resource_type"])] += 1
            if want_fam.setdefault(rid, row["family_id"]) != row["family_id"]:
                errs.append(f"repositório {rid} com mais de uma família no parquet")

    type_rows: dict[tuple, dict] = {}
    atom_rows: list[dict] = []
    lines_by_repo: dict[str, list] = defaultdict(list)
    tot = defaultdict(lambda: [0, 0])  # atom -> [n_repos, n_set]
    ttot = defaultdict(lambda: [0, 0])  # tipo -> [n_repos, n_resources]
    prev = None
    with open(data / "usage.jsonl", encoding="utf-8") as f:
        for ln in f:
            u = json.loads(ln)
            rid = u["repo_id"]
            if prev is not None and rid < prev:
                errs.append("usage.jsonl fora de ordem por repo_id")
            prev = rid
            if sample_pick(rid, a.sample_mod):
                lines_by_repo[rid].append(ln)
            bad = [k for k in u if any(s in k.lower() for s in SPLIT_KEYS)]
            if bad:
                errs.append(f"campo de partição {bad} em {rid}")
            if u["provider"] != PROVIDER:
                errs.append(f"provider {u['provider']} em {rid}")
            key = (rid, u["resource_type"])
            if "atom_id" not in u:
                if key in type_rows:
                    errs.append(f"linha de tipo repetida {key}")
                type_rows[key] = u
                ttot[u["resource_type"]][0] += 1
                ttot[u["resource_type"]][1] += u["n_resources"]
            else:
                atom_rows.append(u)
                tot[u["atom_id"]][0] += 1
                tot[u["atom_id"]][1] += u["n_set"]
            if want_fam.get(rid) != u["family_id"]:
                errs.append(f"família de {rid} diverge do parquet")
    for u in atom_rows:
        key = (u["repo_id"], u["resource_type"])
        t = type_rows.get(key)
        m = atoms.get(u["atom_id"])
        if t is None:
            errs.append(f"linha de átomo sem linha de tipo {key}")
        elif t["n_resources"] != u["n_resources"] or u["n_set"] > t["n_set"]:
            errs.append(f"linha de átomo incoerente com a de tipo {key} {u['atom_id']}")
        if m is None or m["resource_type"] != u["resource_type"]:
            errs.append(f"atom_id fora do atoms.jsonl ou de outro tipo: {u['atom_id']}")
        if u["n_set"] == 0:
            errs.append(f"linha de átomo com n_set 0: {u['atom_id']}")
    got_type = Counter({k: v["n_resources"] for k, v in type_rows.items()})
    if got_type != want_type:
        diff = (set(got_type.items()) ^ set(want_type.items()))
        errs.append(f"linhas de tipo não batem com o parquet ({len(diff)} diferença(s))")
    info["usage"] = {"type_rows": len(type_rows), "atom_rows": len(atom_rows),
                     "resources": sum(got_type.values()), "resources_parquet": sum(want_type.values()),
                     "repos": len({k[0] for k in type_rows}), "repos_parquet": len(by_repo)}

    # 3. totais
    n_tot = 0
    with open(data / "atom_totals.jsonl", encoding="utf-8") as f:
        for ln in f:
            t = json.loads(ln)
            n_tot += 1
            exp = tot.get(t["atom_id"], [0, 0])
            if [t["n_repos"], t["n_set"]] != exp:
                errs.append(f"atom_totals diverge do usage: {t['atom_id']}")
            if t["n_literal"] + t["n_symbolic"] + t["n_withheld"] != t["n_set"]:
                errs.append(f"atom_totals: classes não somam n_set em {t['atom_id']}")
            if t["n_set"] > t["type_n_resources"] or t["n_modules"] < (1 if t["n_repos"] else 0) \
                    or t["n_modules"] > t["n_set"] or t["n_families"] > t["n_repos"] \
                    or t["type_n_resources"] != ttot.get(t["resource_type"], [0, 0])[1]:
                errs.append(f"atom_totals: módulos ou recursos fora dos limites em {t['atom_id']}")
    if n_tot != len(atoms):
        errs.append(f"atom_totals tem {n_tot} átomos, atoms.jsonl {len(atoms)}")
    n_tt = 0
    schema_types = {a["resource_type"] for a in atoms.values()}
    with open(data / "type_totals.jsonl", encoding="utf-8") as f:
        for ln in f:
            t = json.loads(ln)
            n_tt += 1
            if [t["n_repos"], t["n_resources"]] != ttot.get(t["resource_type"], [0, 0]):
                errs.append(f"type_totals diverge do usage: {t['resource_type']}")
            if t["in_schema"] != (t["resource_type"] in schema_types):
                errs.append(f"type_totals.in_schema errado: {t['resource_type']}")
    if n_tt != len(ttot):
        errs.append(f"type_totals tem {n_tt} tipos, usage {len(ttot)}")

    # 4. relatório, resumo e manifesto
    rep = json.loads((data / "build_report.json").read_text(encoding="utf-8"))
    if rep["rows"]["usage_rows"] != len(type_rows) + len(atom_rows) or rep["rows"]["type_rows"] != len(type_rows):
        errs.append("build_report.rows não bate com o usage.jsonl")
    if rep["corpus"]["n_resources"] != sum(want_type.values()) or rep["corpus"]["n_repos"] != len(by_repo):
        errs.append("build_report.corpus não bate com o parquet")
    if rep["atoms"]["n_used"] != sum(1 for v in tot.values() if v[0] > 0):
        errs.append("build_report.atoms.n_used não bate com o usage.jsonl")
    s = rep["settings_by_class"]
    if s["literal"] + s["symbolic"] + s["withheld"] != s["total"] or s["total"] != sum(v[1] for v in tot.values()):
        errs.append("settings_by_class não soma o n_set das linhas de átomo")
    repo = bo_repo()
    summ = json.loads((repo / "results" / MODULE / "summary.json").read_text(encoding="utf-8"))
    sha = {f: sha256_file(data / f) for f in FILES}
    if summ.get("counts", {}).get("outputs_sha256") != sha:
        errs.append("summary.json counts.outputs_sha256 não bate com os arquivos")
    if summ.get("counts", {}).get("corpus") != rep["corpus"]:
        errs.append("summary.json counts.corpus não bate com o build_report")
    man = {}
    for ln in (repo / "results" / MODULE / "MANIFEST.sha256").read_text(encoding="utf-8").splitlines():
        h, p = ln.split("  ", 1)
        man[p] = h
    if man != {f"$BO_DATA/{MODULE}/{f}": h for f, h in sha.items()}:
        errs.append("MANIFEST.sha256 não bate com os arquivos")

    # 5. regeneração da amostra
    tmp = os.environ.get("BO_TMP", str(bo_data() / "tmp" / MODULE))
    out = os.path.join(tmp, f"regen_sample{a.sample_mod}")
    r = subprocess.run([sys.executable, "-I", "-m", "bo.corpus_azure.build", "--sample-mod", str(a.sample_mod),
                        "--out", out], capture_output=True, text=True)
    if r.returncode != 0:
        errs.append("regeneração da amostra falhou: " + r.stderr[-300:])
    else:
        with open(os.path.join(out, "usage.jsonl"), encoding="utf-8") as f:
            regen = f.readlines()
        orig = [ln for rid in sorted(lines_by_repo) for ln in lines_by_repo[rid]]
        n_sample_repos = sum(1 for rid in by_repo if sample_pick(rid, a.sample_mod))
        if regen != orig:
            errs.append(f"regeneração da amostra diverge ({len(regen)} x {len(orig)} linhas)")
        info["regen"] = {"sample_mod": a.sample_mod, "repos": n_sample_repos, "lines": len(regen),
                         "identical": regen == orig}

    report = {"module": MODULE, "checked_at": now(), "result": "PASS" if not errs else "FAIL",
              "errors": errs[:50], "n_errors": len(errs), "info": info}
    (data / "check_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n",
                                            encoding="utf-8")
    print(json.dumps(info, ensure_ascii=False))
    for e in errs[:20]:
        print("FAIL", e)
    print(f"[{now()}] {MODULE} check: " + ("OK" if not errs else f"REPROVADO ({len(errs)})"))
    return 0 if not errs else 1


if __name__ == "__main__":
    sys.exit(main())
