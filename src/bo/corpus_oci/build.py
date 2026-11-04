"""Gera o uso por átomo do oci a partir das saídas do HCL e do SCHEMA-OCI.

  python -I -m bo.corpus_oci.build [--out DIR] [--provider oci]

Escreve em DIR (padrão $BO_DATA/CORPUS-OCI/.staging; nunca direto na pasta publicada — a troca é do
bo.corpus_oci.swap, dentro da trava):
  usage.jsonl        C06 usage, um registro por (repo, tipo) e por (repo, tipo, átomo configurado)
  atom_totals.jsonl  por átomo do schema: repositórios, famílias, módulos e recursos que o configuram
  type_totals.jsonl  por tipo presente no corpus (inclusive fora do schema)
  build_report.json  entradas (sha256), contagens de conferência e causas do que não vira átomo
Tudo determinístico (JSON canônico, ordem fixa): duas execuções dão os mesmos bytes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

from . import counting

PROVIDER = "oci"
MODULE = "CORPUS-OCI"


def bo_data() -> Path:
    return Path(os.environ.get("BO_DATA", "/Users/breno/doutorado/brevops-data"))


def inputs(provider: str = PROVIDER) -> dict:
    d = bo_data()
    return {
        "resources": d / "HCL" / "resources.parquet",
        "symbolic_config": d / "HCL" / "symbolic_config.jsonl",
        "symbolic_index": d / "HCL" / "symbolic_config.index.json",
        "atoms": d / f"SCHEMA-{provider.upper()}" / "atoms.jsonl",
    }


def portable(p: Path) -> str:
    s = str(p)
    for var in ("BO_DATA", "BO_REPO"):
        v = os.environ.get(var) or (str(bo_data()) if var == "BO_DATA" else "")
        if v and s.startswith(v.rstrip("/") + "/"):
            return f"${var}" + s[len(v.rstrip("/")):]
    return s


def sha256_file(p: Path, bufsize: int = 1 << 24) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        while True:
            b = f.read(bufsize)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def read_resources(path: Path, provider: str) -> list[dict]:
    import pyarrow.parquet as pq

    t = pq.read_table(path, filters=[("provider", "==", provider)])
    return t.to_pylist()


def run(provider: str, out: Path) -> dict:
    src = inputs(provider)
    for k, p in src.items():
        if not p.is_file():
            raise FileNotFoundError(f"entrada ausente ({k}): {portable(p)}")
    atoms = counting.AtomIndex.load(str(src["atoms"]), provider)
    tally = counting.Tally(provider, atoms)

    rows = read_resources(src["resources"], provider)
    repos = set()
    for row in rows:
        tally.add_resource(row)
        repos.add(row["repo_id"])

    idx = json.loads(src["symbolic_index"].read_text(encoding="utf-8"))["repos"]
    repos_without_records = 0
    with open(src["symbolic_config"], "rb") as f:
        for repo in sorted(repos):
            span = idx.get(repo)
            if span is None:
                repos_without_records += 1
                continue
            start, end, n = span
            f.seek(start)
            lines = f.read(end - start).splitlines()
            if len(lines) != n:
                raise ValueError(f"índice do HCL diverge do jsonl: {len(lines)} linhas, índice diz {n}")
            for ln in lines:
                rec = json.loads(ln)
                if rec["repo_id"] != repo:
                    raise ValueError("faixa do índice com registro de outro repositório")
                tally.add_record(rec)

    usage = tally.usage_records()
    atom_tot = tally.atom_totals()
    type_tot = tally.type_totals()

    out.mkdir(parents=True, exist_ok=True)
    _write_jsonl(out / "usage.jsonl", usage)
    _write_jsonl(out / "atom_totals.jsonl", atom_tot)
    _write_jsonl(out / "type_totals.jsonl", type_tot)

    st = tally.stats
    managed_keys = tally.resources
    report = {
        "module": MODULE,
        "provider": provider,
        "inputs": [{"name": k, "path": portable(p), "sha256": sha256_file(p)} for k, p in sorted(src.items())],
        "definitions": {
            "resource": "linha de resources.parquet do provedor sem o segmento data. no endereço",
            "module": "(repo_id, dirname(file)) com o caminho já simbolizado pelo HCL",
            "atom_resolution": "sem [n]; dynamic[\"b\"][n].content. -> b.; caminho exato ou maior prefixo "
                               "que é átomo de atributo",
            "explicit_null": "literal null resolve o átomo mas não o configura (Terraform: igual a omitir)",
            "class": "regra comum dos 4 CORPUS (coordenador, 2026-11-04): withheld se contém termo retido; "
                     "symbolic se depende de variável, recurso, data source, local, saída de módulo, count/each, "
                     "workspace ou função avaliada no plano; senão literal, inclusive cadeia simbolizada só por "
                     "privacidade; várias ocorrências: withheld > symbolic > literal",
            "type_record": "registro sem atom_id por (repo, tipo): n_set = recursos com >= 1 átomo",
        },
        "counts": {
            "repos": len(repos),
            "repos_with_managed": len({k[0] for k in managed_keys}),
            "families_with_managed": len({v[0] for v in managed_keys.values()}),
            "modules_with_managed": len({(k[0], counting.module_key(k[1])) for k in managed_keys}),
            "repos_without_records": repos_without_records,
            "managed_blocks": st["managed_blocks"],
            "managed_attrs_declared": tally.n_attrs_declared,
            "managed_records": st["managed_records"],
            "attributed_records": st["attributed_records"],
            "data_blocks": st["data_blocks"],
            "data_attrs_declared": st["data_attrs_declared"],
            "data_records": st["data_records"],
            "resources_with_atom": sum(1 for k in managed_keys if tally.set_atoms.get(k)),
            "resource_atom_pairs": sum(len(v) for v in tally.set_atoms.values()),
            "types_in_corpus": len(type_tot),
            "types_in_corpus_not_in_schema": sum(1 for t in type_tot if not t["in_schema"]),
            "schema_types": len(atoms.paths),
            "schema_atoms": atoms.n_atoms,
            "atoms_configured": sum(1 for a in atom_tot if a["n_set"]),
            "atoms_configured_in_2plus_families": sum(1 for a in atom_tot if a["n_families"] >= 2),
            "usage_records": len(usage),
            "usage_records_with_atom": sum(1 for u in usage if "atom_id" in u),
        },
        "term_class_records": {c: st[f"term_class:{c}"] for c in counting.CLASSES},
        "unattributed_records": {c: st[f"unattributed:{c}"] for c in counting.UNATTRIBUTED},
        "unattributed_top": [
            {"cause": c, "resource_type": rt, "path": counting.safe_report_path(atoms, p), "records": n}
            for (c, rt, p), n in sorted(tally.unattributed.items(), key=lambda kv: (-kv[1], kv[0]))[:60]
        ],
    }
    (out / "build_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1, sort_keys=True)
                                           + "\n", encoding="utf-8")
    return report


def _write_jsonl(path: Path, recs: list[dict]) -> None:
    tmp = path.with_suffix(path.suffix + ".part")
    with open(tmp, "w", encoding="utf-8") as f:
        for r in recs:
            f.write(counting.dumps(r) + "\n")
    tmp.replace(path)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="bo.corpus_oci.build")
    ap.add_argument("--provider", default=PROVIDER)
    ap.add_argument("--out", default=None, help="padrão: $BO_DATA/CORPUS-OCI/.staging")
    a = ap.parse_args(argv)
    out = Path(a.out) if a.out else bo_data() / MODULE / ".staging"
    rep = run(a.provider, out)
    c = rep["counts"]
    print(f"{MODULE}: {c['repos_with_managed']} repositórios, {c['families_with_managed']} famílias, "
          f"{c['modules_with_managed']} módulos, {c['managed_blocks']} recursos; "
          f"{c['atoms_configured']}/{c['schema_atoms']} átomos configurados; "
          f"{c['usage_records']} registros usage -> {portable(out)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
