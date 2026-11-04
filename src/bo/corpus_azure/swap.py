"""Troca a staging pela pasta do módulo e publica resumo e manifesto (só dentro da trava merge-base).

  tools/lock.sh with merge-base --owner CORPUS-AZURE --wait 600 -- python -I -m bo.corpus_azure.swap

1. confere que a trava merge-base é do CORPUS-AZURE;
2. valida a staging (usage C06 no validador oficial) antes de trocar, salvo --skip-validate (validação já feita
   e registrada em .staging/contract_report.json com o sha do arquivo);
3. os.replace de cada arquivo da staging para $BO_DATA/CORPUS-AZURE/ e remove a staging;
4. grava o bloco "counts" do results/CORPUS-AZURE/summary.json (preserva a proveniência) e o
   results/CORPUS-AZURE/MANIFEST.sha256 com caminhos portáteis.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

from . import MODULE
from .build import bo_data, now

FILES = ("usage.jsonl", "atom_totals.jsonl", "type_totals.jsonl", "build_report.json")


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 22), b""):
            h.update(b)
    return h.hexdigest()


def bo_repo() -> Path:
    return Path(os.environ.get("BO_REPO", "/Users/breno/doutorado/brevops-ontology"))


def holds_lock() -> bool:
    o = bo_data() / "locks" / "merge-base" / "owner"
    try:
        txt = o.read_text(encoding="utf-8")
    except OSError:
        return False
    return any(ln.startswith("owner=") and ln[6:].split("@", 1)[0] == MODULE for ln in txt.splitlines())


def publish(repo: Path, data: Path) -> None:
    rep = json.loads((data / "build_report.json").read_text(encoding="utf-8"))
    sp = repo / "results" / MODULE / "summary.json"
    sp.parent.mkdir(parents=True, exist_ok=True)
    summ = json.loads(sp.read_text(encoding="utf-8")) if sp.exists() else {}
    summ.setdefault("schema", "bo.summary/1")
    summ.setdefault("contract", "C17")
    summ.setdefault("contract_version", "3.0.0")
    summ["module"] = MODULE
    summ["generated_at"] = now()
    summ.setdefault("sources", [])
    summ["counts"] = {k: v for k, v in rep.items() if k not in ("elapsed_s", "generated_at")}
    summ["counts"]["outputs_sha256"] = {f: sha256_file(data / f) for f in FILES}
    summ["notes"] = notes(rep)
    sp.write_text(json.dumps(summ, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    lines = [f"{sha256_file(data / f)}  $BO_DATA/{MODULE}/{f}" for f in FILES]
    (repo / "results" / MODULE / "MANIFEST.sha256").write_text("\n".join(lines) + "\n", encoding="utf-8")


def notes(r: dict) -> str:
    c, a, rec, t = r["corpus"], r["atoms"], r["records"], r["types"]
    s, u = r["settings_by_class"], rec["unattributed_by_cause"]
    return (f"azurerm no TerraDS: {c['n_repos']} repositórios, {c['n_families']} famílias, {c['n_modules']} módulos, "
            f"{c['n_resources']} recursos ({c['n_data_blocks_skipped']} blocos data fora). "
            f"{r['rows']['usage_rows']} linhas usage ({r['rows']['type_rows']} por tipo, {r['rows']['atom_rows']} por "
            f"átomo), contadas pela biblioteca única bo.corpus_oci.counting. Átomos configuráveis usados: "
            f"{a['n_configurable_used']}/{a['n_configurable']} ({a['configurable_used_share']:.1%}); "
            f"{a['atoms_for_90pct_settings']} átomos cobrem 90% das configurações. Registros de recurso atribuídos a "
            f"átomo do schema 5.12.0: {rec['attributed_records']}/{rec['resource_records']} "
            f"({rec['attributed_share']:.1%}); fora: {u['attr_not_in_schema']} atributo fora do schema, "
            f"{u['type_not_in_schema']} de {t['n_types_used_not_in_schema']} tipos ausentes do schema 5.12.0, "
            f"{u['meta_argument']} meta-argumento, {u['dynamic_meta']} meta de dynamic, {u['explicit_null']} null "
            f"explícito. Classe por recurso x átomo: literal {s['literal']}, simbólico {s['symbolic']}, retido "
            f"{s['withheld']}. Sem split (é do SPLIT).")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="bo.corpus_azure.swap")
    ap.add_argument("--skip-validate", action="store_true")
    ap.add_argument("--publish-only", action="store_true", help="só refaz summary counts e manifesto")
    a = ap.parse_args(argv)
    data = bo_data() / MODULE
    stg = data / ".staging"
    repo = bo_repo()
    if a.publish_only:
        publish(repo, data)
        print(f"[{now()}] {MODULE}: summary e manifesto refeitos")
        return 0
    if not holds_lock():
        print(f"{MODULE}: a trava merge-base não é minha; rode via tools/lock.sh with merge-base", file=sys.stderr)
        return 2
    miss = [f for f in FILES if not (stg / f).is_file()]
    if miss:
        print(f"{MODULE}: staging incompleta: {miss}", file=sys.stderr)
        return 1
    if a.skip_validate:
        cr = stg / "contract_report.json"
        ok = cr.is_file() and json.loads(cr.read_text())["sha256"] == sha256_file(stg / "usage.jsonl")
        if not ok:
            print(f"{MODULE}: --skip-validate sem contract_report.json do mesmo arquivo", file=sys.stderr)
            return 1
    else:
        r = subprocess.run([sys.executable, "-I", "-m", "bo.contracts.validate", "usage", str(stg / "usage.jsonl")])
        if r.returncode != 0:
            print(f"{MODULE}: staging reprovada no C06; nada trocado", file=sys.stderr)
            return 1
    for f in FILES + ("contract_report.json",):
        if (stg / f).is_file():
            os.replace(stg / f, data / f)
    for p in stg.iterdir():
        p.unlink()
    stg.rmdir()
    publish(repo, data)
    print(f"[{now()}] {MODULE}: staging trocada; summary e manifesto publicados")
    return 0


if __name__ == "__main__":
    sys.exit(main())
