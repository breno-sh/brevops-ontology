"""Conferências do uso publicado (ou de uma pasta de staging) contra as entradas, sem recontar pelo mesmo código.

  python -I -m bo.corpus_oci.check [--dir DIR] [--provider oci]

Recalcula do resources.parquet, por conta própria, o denominador de cada (repo, família, tipo) e confere:
  - C06-USAGE em todo registro (soma das classes = n_set <= n_resources) e campos do contrato;
  - um registro de tipo por (repo, tipo) e o conjunto deles igual ao do parquet (mesmos recursos);
  - registro de átomo: atom_id existe no atoms.jsonl, prefixo provider:tipo, n_resources do tipo,
    n_set <= n_set do tipo, n_withheld <= n_withheld do tipo, sem repetição;
  - repositório → família 1:1;
  - build_report: registros lidos = n_attrs declarados no parquet (gerenciados e data), atribuídos +
    não atribuídos = lidos, sha256 das entradas iguais aos arquivos de agora;
  - atom_totals e type_totals batem com o usage (somas, repositórios por átomo, famílias <= repositórios,
    módulos >= repositórios).
Sai 0 se tudo confere; 1 com a lista do que não confere.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

from . import build, counting

FIELDS = {"repo_id", "family_id", "provider", "resource_type", "n_resources", "n_set", "n_literal",
          "n_symbolic", "n_withheld"}


def _jsonl(p: Path):
    with open(p, encoding="utf-8") as f:
        for ln in f:
            if ln.strip():
                yield json.loads(ln)


def check(d: Path, provider: str, verify_input_sha: bool = True) -> list[str]:
    errs: list[str] = []
    src = build.inputs(provider)

    def err(msg):
        if len(errs) < 200:
            errs.append(msg)

    atom_ids = {}
    for a in _jsonl(src["atoms"]):
        atom_ids[a["atom_id"]] = a["resource_type"]

    # denominador independente: parquet do provedor, sem data source
    import pyarrow.parquet as pq

    t = pq.read_table(src["resources"], columns=["repo_id", "family_id", "resource_address", "resource_type",
                                                 "provider", "n_attrs"],
                      filters=[("provider", "==", provider)]).to_pydict()
    den = Counter()
    attrs_managed = attrs_data = 0
    repo_fam = {}
    for repo, fam, addr, rt, na in zip(t["repo_id"], t["family_id"], t["resource_address"], t["resource_type"],
                                       t["n_attrs"]):
        if repo_fam.setdefault(repo, fam) != fam:
            err(f"repositório com duas famílias no parquet: {repo}")
        if counting.is_data_address(addr):
            attrs_data += na
            continue
        den[(repo, fam, rt)] += 1
        attrs_managed += na

    type_rec = {}
    atom_rec = {}
    atom_sum = Counter()
    atom_repos = defaultdict(int)
    n = 0
    for u in _jsonl(d / "usage.jsonl"):
        n += 1
        keys = set(u)
        if not FIELDS <= keys or keys - FIELDS - {"atom_id"}:
            err(f"registro {n}: campos {sorted(keys)}")
            continue
        if u["provider"] != provider:
            err(f"registro {n}: provedor {u['provider']}")
        cls = u["n_literal"] + u["n_symbolic"] + u["n_withheld"]
        if cls != u["n_set"] or u["n_set"] > u["n_resources"] or min(u[k] for k in FIELDS if k.startswith("n_")) < 0:
            err(f"registro {n}: C06-USAGE ({cls} / {u['n_set']} / {u['n_resources']})")
        k = (u["repo_id"], u["family_id"], u["resource_type"])
        if "atom_id" not in u:
            if k in type_rec:
                err(f"registro {n}: registro de tipo repetido")
            type_rec[k] = u
            continue
        a = u["atom_id"]
        if atom_ids.get(a) != u["resource_type"] or not a.startswith(f"{provider}:{u['resource_type']}:"):
            err(f"registro {n}: atom_id fora do schema ou de outro tipo: {a}")
        if (k, a) in atom_rec:
            err(f"registro {n}: átomo repetido no mesmo (repo, tipo)")
        atom_rec[(k, a)] = u
        atom_sum[a] += u["n_set"]
        atom_repos[a] += 1

    if set(type_rec) != set(den):
        err(f"(repo, família, tipo) do usage != parquet: {len(set(type_rec) - set(den))} a mais, "
            f"{len(set(den) - set(type_rec))} a menos")
    for k, u in type_rec.items():
        if den.get(k) != u["n_resources"]:
            err(f"n_resources do tipo diverge do parquet em {k[2]}: {u['n_resources']} != {den.get(k)}")
    for (k, a), u in atom_rec.items():
        tr = type_rec.get(k)
        if tr is None:
            err(f"átomo sem registro de tipo: {a}")
            continue
        if u["n_resources"] != tr["n_resources"] or u["n_set"] > tr["n_set"] or u["n_withheld"] > tr["n_withheld"]:
            err(f"átomo incoerente com o tipo: {a}")

    rep = json.loads((d / "build_report.json").read_text(encoding="utf-8"))
    c = rep["counts"]
    if c["managed_attrs_declared"] != attrs_managed or c["managed_records"] != attrs_managed:
        err(f"registros gerenciados lidos {c['managed_records']} != n_attrs do parquet {attrs_managed}")
    if c["data_records"] != attrs_data:
        err(f"registros de data source lidos {c['data_records']} != n_attrs do parquet {attrs_data}")
    if c["attributed_records"] + sum(rep["unattributed_records"].values()) != c["managed_records"]:
        err("atribuídos + não atribuídos != registros gerenciados lidos")
    if sum(rep["term_class_records"].values()) != c["managed_records"]:
        err("classes de termo != registros gerenciados lidos")
    if c["managed_blocks"] != sum(den.values()) or c["usage_records"] != n:
        err("contagens do build_report divergem do parquet ou do usage")
    if c["resource_atom_pairs"] != sum(atom_sum.values()):
        err("pares (recurso, átomo) do build_report != soma de n_set dos átomos")
    if verify_input_sha:
        for i in rep["inputs"]:
            p = src[i["name"]]
            if build.sha256_file(p) != i["sha256"]:
                err(f"entrada mudou desde a geração: {i['path']}")

    seen = set()
    for a in _jsonl(d / "atom_totals.jsonl"):
        seen.add(a["atom_id"])
        if a["n_set"] != atom_sum.get(a["atom_id"], 0) or a["n_repos"] != atom_repos.get(a["atom_id"], 0):
            err(f"atom_totals diverge do usage: {a['atom_id']}")
        if a["n_families"] > a["n_repos"] or a["n_modules"] < a["n_repos"] or a["n_set"] < a["n_modules"]:
            err(f"atom_totals incoerente (famílias/repos/módulos/recursos): {a['atom_id']}")
        if a["n_literal"] + a["n_symbolic"] + a["n_withheld"] != a["n_set"] or a["n_set"] > a["type_n_resources"]:
            err(f"atom_totals fora do C06-USAGE: {a['atom_id']}")
    if seen != set(atom_ids):
        err(f"atom_totals não cobre o schema: {len(set(atom_ids) - seen)} átomos faltando")
    tt = list(_jsonl(d / "type_totals.jsonl"))
    by_type = Counter()
    for (repo, fam, rt), v in den.items():
        by_type[rt] += v
    if {x["resource_type"]: x["n_resources"] for x in tt} != dict(by_type):
        err("type_totals diverge do parquet")
    return errs


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="bo.corpus_oci.check")
    ap.add_argument("--provider", default=build.PROVIDER)
    ap.add_argument("--dir", default=None, help="padrão: $BO_DATA/CORPUS-OCI")
    ap.add_argument("--skip-input-sha", action="store_true", help="não recalcula o sha256 das entradas")
    a = ap.parse_args(argv)
    d = Path(a.dir) if a.dir else build.bo_data() / build.MODULE
    errs = check(d, a.provider, verify_input_sha=not a.skip_input_sha)
    for e in errs:
        print("NÃO CONFERE:", e)
    print(f"bo.corpus_oci.check {build.portable(d)}: {'OK' if not errs else f'{len(errs)} problema(s)'}")
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
