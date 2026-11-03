"""Reprodução do catalogo4v2.jsonl pela biblioteca bo.schema (gate do SCHEMALIB).

  python -I -m bo.schema.repro --catalog ARQ.jsonl [--schemas-dir DIR] [--out ARQ] [--check]

Para cada provedor do catálogo, abre o schema extraído na MESMA versão que a linha do catálogo declara
($BO_DATA/downloads/tfschema/<provedor>-<versão>/schema.json.gz, conferido pelo schema.json.sha256),
gera os átomos (C01) e os tipos (C02) com bo.schema.core, recalcula as contagens do catálogo com a régua
do C1 (bo.schema.ruler) e compara tipo a tipo as seis contagens (COUNT_FIELDS) e a árvore.

Toda diferença recebe uma causa mecânica (CAUSES); 'nao_explicada' reprova. Os átomos e tipos completos
são gravados em $BO_TMP/repro/ e validados por bo.contracts.validate (C01, C02).

Sai 0 só se: taxa de tipos com as seis contagens iguais >= 99,5%, nenhuma diferença sem causa, C01 e C02
conferem, e os sha256 dos schemas batem. Relatório: $BO_DATA/SCHEMALIB/repro_catalogo4v2.json.
--check: recalcula e exige igualdade com o relatório gravado (menos generated_at), sem regravar.
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import os
import sys
from pathlib import Path

from . import core, ruler

THRESHOLD = 0.995
REPORT_SCHEMA = "bo.schemalib.repro/1"

#: causas mecânicas de diferença, na ordem em que são testadas
CAUSES = {
    "schema_ausente": "não há schema extraído para (provedor, versão) da linha do catálogo",
    "ausente_no_schema": "o tipo está no catálogo e não no schema da mesma versão",
    "extra_no_schema": "o tipo está no schema e não no catálogo",
    "regua_reclassificada": "mesmos atributos e blocos; só a partição cfg/provider_populated/computed_only difere",
    "nao_explicada": "contagem de atributos ou de blocos difere sem causa mecânica",
}


def bo_data() -> Path:
    return Path(os.environ.get("BO_DATA", "/Users/breno/doutorado/brevops-data"))


def bo_tmp() -> Path:
    return Path(os.environ.get("BO_TMP") or bo_data() / "tmp" / "SCHEMALIB")


def default_schemas_dir() -> Path:
    return bo_data() / "downloads" / "tfschema"


def default_out() -> Path:
    return bo_data() / "SCHEMALIB" / "repro_catalogo4v2.json"


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def portable(p: Path) -> str:
    s = str(p)
    for var in ("BO_DATA", "BO_REPO"):
        root = os.environ.get(var) or (str(bo_data()) if var == "BO_DATA" else "")
        if root and s.startswith(root.rstrip("/") + "/"):
            return f"${var}/" + s[len(root.rstrip("/")) + 1:]
    return s


def read_catalog(path: Path) -> list[dict]:
    rows = []
    with open(path, encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            if line.strip():
                r = json.loads(line)
                if r.get("kind", "resource") != "resource":
                    raise SystemExit(f"{path}:{i}: kind {r.get('kind')!r} (o catalogo4v2 só tem resource)")
                rows.append(r)
    return rows


def open_schema(sdir: Path, provider: str, version: str) -> tuple[dict | None, dict]:
    """(provider_schema ou None, descrição da fonte). Confere o sha256 da saída crua do terraform."""
    d = sdir / f"{provider}-{version}"
    info = {"provider": provider, "version": version, "path": portable(d / "schema.json.gz")}
    gz, shaf = d / "schema.json.gz", d / "schema.json.sha256"
    if not gz.exists() or not shaf.exists():
        info["erro"] = "ausente"
        return None, info
    import gzip
    raw = gzip.open(gz, "rb").read()
    want = shaf.read_text(encoding="utf-8").split()[0]
    got = hashlib.sha256(raw).hexdigest()
    info["sha256"] = got
    if got != want:
        info["erro"] = f"sha256 {got[:12]}… != schema.json.sha256 {want[:12]}…"
        return None, info
    rc = d / "receipt.json"
    if rc.exists():
        r = json.loads(rc.read_text(encoding="utf-8"))
        info["receipt_sha256"] = sha256_file(rc)
        info["terraform"] = r.get("terraform", {}).get("version")
        info["provider_binary_sha256"] = r.get("provider_binary", {}).get("sha256")
        info["lock_hashes"] = r.get("lock", {}).get("hashes")
        if r.get("schema_json", {}).get("sha256") != got:
            info["erro"] = "receipt.json não descreve este schema"
            return None, info
    doc = json.loads(raw)
    ps = core.providers(doc)
    if provider not in ps:
        info["erro"] = f"schema sem o provedor {provider}"
        return None, info
    info["format_version"] = doc.get("format_version")
    return ps[provider], info


def explain(cat_row: dict | None, got: dict | None, schema_version: str | None) -> str:
    if cat_row is None:
        return "extra_no_schema"
    if schema_version is None:
        return "schema_ausente"
    if got is None:
        return "ausente_no_schema"
    if (got["n_atributos_total"] == cat_row["n_atributos_total"]
            and got["n_blocos_total"] == cat_row["n_blocos_total"]):
        return "regua_reclassificada"
    return "nao_explicada"


def validate_contracts(atoms_files: list[Path], types_files: list[Path]) -> dict:
    try:
        from bo.contracts import validate as V
    except ImportError as e:      # o CONTRACTS é dep mergeada; sem ele o gate reprova
        return {"ok": False, "erro": f"bo.contracts.validate não importa: {e}"}
    out = {"ok": True, "arquivos": []}
    for alias, files in (("C01_atoms", atoms_files), ("C02_types", types_files)):
        for p in files:
            r = V.validate(alias, p)
            out["arquivos"].append({"contrato": alias, "arquivo": portable(p), "registros": r.n, "ok": r.ok,
                                    "erros": r.errors[:10], "n_erros": len(r.errors)})
            out["ok"] &= r.ok
    return out


def run(catalog: Path, sdir: Path, work: Path) -> dict:
    rows = read_catalog(catalog)
    by_prov = collections.defaultdict(dict)
    versions = collections.defaultdict(set)
    for r in rows:
        by_prov[r["provedor"]][r["tipo"]] = r
        versions[r["provedor"]].add(r["provider_version"])
    sources, per, diffs = [], {}, []
    atoms_files, types_files = [], []
    total = {"tipos_catalogo": len(rows), "iguais": 0, "arvore_igual": 0, "comparados": 0}
    errors = []
    work.mkdir(parents=True, exist_ok=True)
    for prov in sorted(by_prov):
        cat = by_prov[prov]
        if len(versions[prov]) != 1:
            errors.append(f"{prov}: catálogo com {len(versions[prov])} versões ({sorted(versions[prov])})")
        ver = sorted(versions[prov])[0]
        ps, info = open_schema(sdir, prov, ver)
        sources.append(info)
        p = {"versao": ver, "tipos_catalogo": len(cat), "tipos_schema": 0, "iguais": 0, "arvore_igual": 0,
             "diferentes": 0, "totais_catalogo": {k: 0 for k in ruler.COUNT_FIELDS},
             "totais_biblioteca": {k: 0 for k in ruler.COUNT_FIELDS}, "atomos": 0,
             "atomos_por_flag": {k: 0 for k in (*core.FLAGS, "configurable")},
             "atributos_nested_type": 0, "atributos_write_only": 0}
        for r in cat.values():
            for k in ruler.COUNT_FIELDS:
                p["totais_catalogo"][k] += r[k]
        if ps is None:
            errors.append(f"{prov} {ver}: schema {info.get('erro')}")
            for t in sorted(cat):
                diffs.append({"type_id": f"{prov}:{t}", "causa": explain(cat[t], None, None)})
            p["diferentes"] = len(cat)
            per[prov] = p
            continue
        seen = set()
        af, tf = work / f"atoms_{prov}-{ver}.jsonl", work / f"types_{prov}-{ver}.jsonl"
        with open(af, "w", encoding="utf-8") as fa, open(tf, "w", encoding="utf-8") as ft:
            for ts in core.iter_types(ps, prov, ver):
                p["tipos_schema"] += 1
                for a in ts.atoms:
                    fa.write(json.dumps(a, ensure_ascii=False, sort_keys=True) + "\n")
                    for k in p["atomos_por_flag"]:
                        p["atomos_por_flag"][k] += a[k]
                ft.write(json.dumps(core.type_record(ts), ensure_ascii=False, sort_keys=True) + "\n")
                p["atomos"] += len(ts.atoms)
                p["atributos_nested_type"] += _count_attr_key(ts.block, "nested_type")
                p["atributos_write_only"] += _count_attr_key(ts.block, "write_only")
                got = ruler.counts(ts)
                for k in ruler.COUNT_FIELDS:
                    p["totais_biblioteca"][k] += got[k]
                r = cat.get(ts.resource_type)
                seen.add(ts.resource_type)
                if r is None:
                    diffs.append({"type_id": ts.type_id, "causa": explain(None, got, ver)})
                    p["diferentes"] += 1
                    continue
                total["comparados"] += 1
                if all(r[k] == got[k] for k in ruler.COUNT_FIELDS):
                    p["iguais"] += 1
                else:
                    p["diferentes"] += 1
                    diffs.append({"type_id": ts.type_id, "causa": explain(r, got, ver),
                                  "campos": {k: [r[k], got[k]] for k in ruler.COUNT_FIELDS if r[k] != got[k]}})
                if r.get("arvore") == ruler.tree(ts):
                    p["arvore_igual"] += 1
        for t in sorted(set(cat) - seen):
            diffs.append({"type_id": f"{prov}:{t}", "causa": explain(cat[t], None, ver)})
            p["diferentes"] += 1
        atoms_files.append(af)
        types_files.append(tf)
        total["iguais"] += p["iguais"]
        total["arvore_igual"] += p["arvore_igual"]
        per[prov] = p
    rate = total["iguais"] / total["tipos_catalogo"] if total["tipos_catalogo"] else 0.0
    total["taxa_iguais"] = round(rate, 6)
    total["taxa_arvore_igual"] = round(total["arvore_igual"] / total["tipos_catalogo"], 6) if rows else 0.0
    contracts = validate_contracts(atoms_files, types_files)
    causes = collections.Counter(d["causa"] for d in diffs)
    reasons = list(errors)
    if rate < THRESHOLD:
        reasons.append(f"taxa {rate:.4%} < {THRESHOLD:.1%}")
    if causes.get("nao_explicada"):
        reasons.append(f"{causes['nao_explicada']} diferença(s) sem causa mecânica")
    if not contracts.get("ok"):
        reasons.append("C01/C02 não conferem")
    return {
        "schema": REPORT_SCHEMA,
        "module": "SCHEMALIB",
        "generated_at": None,
        "criterio": {
            "limiar_taxa_iguais": THRESHOLD,
            "igualdade": "as seis contagens do catalogo4v2 por tipo: " + ", ".join(ruler.COUNT_FIELDS),
            "regua": "bo.schema.ruler (provider_populated = computed, não required, nome em "
                     + "/".join(sorted(ruler.PROVIDER_POPULATED_NAMES)) + ")",
            "secundario": "árvore por bloco (req/opt/cfg/provider_populated/computed_only) idêntica à 'arvore'",
            "causas": CAUSES,
        },
        "entradas": {"catalogo": {"path": str(catalog), "sha256": sha256_file(catalog), "linhas": len(rows)},
                     "schemas": sources},
        "por_provedor": per,
        "total": total,
        "diferencas_por_causa": dict(sorted(causes.items())),
        "diferencas": diffs,
        "contratos": contracts,
        "veredito": "PASS" if not reasons else "FAIL",
        "motivos": reasons,
    }


def _count_attr_key(block: dict, key: str) -> int:
    n = sum(1 for a in (block.get("attributes") or {}).values() if a.get(key))
    for bt in (block.get("block_types") or {}).values():
        n += _count_attr_key(bt.get("block") or {}, key)
    return n


def comparable(rep: dict) -> dict:
    r = dict(rep)
    r.pop("generated_at", None)
    return r


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="bo.schema.repro", description=__doc__.split("\n")[0])
    ap.add_argument("--catalog", required=True, type=Path)
    ap.add_argument("--schemas-dir", type=Path, default=None)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--check", action="store_true", help="recalcula e compara com o relatório gravado")
    a = ap.parse_args(argv)
    from bo.repo.core import now
    out = a.out or default_out()
    rep = run(a.catalog, a.schemas_dir or default_schemas_dir(), bo_tmp() / "repro")
    t = rep["total"]
    print(f"[{now()}] bo.schema.repro: {t['iguais']}/{t['tipos_catalogo']} tipos com as 6 contagens iguais "
          f"({t['taxa_iguais']:.4%}); árvore igual em {t['arvore_igual']}; "
          f"diferenças por causa {rep['diferencas_por_causa'] or '{}'}; "
          f"C01/C02 {'conferem' if rep['contratos'].get('ok') else 'NÃO conferem'}")
    for prov, p in rep["por_provedor"].items():
        print(f"  {prov:8s} {p['versao']:8s} catálogo {p['tipos_catalogo']:5d} schema {p['tipos_schema']:5d} "
              f"iguais {p['iguais']:5d} átomos {p['atomos']:6d}")
    for m in rep["motivos"]:
        print(f"  FAIL {m}")
    if a.check:
        if not out.exists():
            print(f"  FAIL --check: {out} não existe")
            return 1
        old = json.loads(out.read_text(encoding="utf-8"))
        if comparable(old) != comparable(rep):
            print(f"  FAIL --check: o relatório gravado difere do recalculado ({portable(out)})")
            return 1
        print(f"  regeneração idêntica: {portable(out)}")
    else:
        rep["generated_at"] = now()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(rep, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"  relatório: {portable(out)}")
    print(f"RESULTADO: {rep['veredito']}")
    return 0 if rep["veredito"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
