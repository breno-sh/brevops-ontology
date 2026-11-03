"""Tipos de recurso de um schema extraído x índice de documentação do Terraform Registry da mesma versão.

  python -I -m bo.schema.crosscheck --provider aws [--types ARQ] [--index ARQ] [--fetch] [--out ARQ]

--types   types.jsonl (C02) do produtor; padrão $BO_DATA/<SCHEMA-X>/types.jsonl (SCHEMA-AWS, -AZURE, -GCP, -OCI).
          A versão é a dos registros (todos iguais), nunca digitada.
--index   resposta de GET https://registry.terraform.io/v1/providers/<ns>/<nome>/<versão> (campo 'docs');
          padrão $BO_DATA/downloads/registry-docs/<provedor>-<versão>/index.json. --fetch baixa se faltar
          (dado não confiável: só lido como JSON, com SOURCE.txt ao lado).

Índice = páginas category 'resources', language 'hcl'; o slug vira <provedor>_<slug>. Diferenças com causa
mecânica (não reprovam):
  alias_bloco_identico  tipo sem página cujo block_sha256 é o de um tipo documentado (ex.: aws_alb = aws_lb)
  familia_iam           tipo <x>_iam_binding/_member/_policy/_audit_config coberto pela página <x>_iam
Reprova (sai 1) se sobrar tipo sem página ou página sem tipo. Sai 0 só com nº de tipos = índice, a menos das
causas acima, todas listadas no relatório.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

REGISTRY = {"aws": "hashicorp/aws", "google": "hashicorp/google", "azurerm": "hashicorp/azurerm", "oci": "oracle/oci"}
PRODUCER = {"aws": "SCHEMA-AWS", "azurerm": "SCHEMA-AZURE", "google": "SCHEMA-GCP", "oci": "SCHEMA-OCI"}
IAM_SUFFIXES = ("_iam_binding", "_iam_member", "_iam_policy", "_iam_audit_config")


def bo_data() -> Path:
    return Path(os.environ.get("BO_DATA", "/Users/breno/doutorado/brevops-data"))


def read_types(path: Path) -> tuple[str, dict[str, str]]:
    types, versions = {}, set()
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                t = json.loads(line)
                types[t["resource_type"]] = t["block_sha256"]
                versions.add(t["provider_version"])
    if len(versions) != 1:
        raise SystemExit(f"crosscheck: {path} com {len(versions)} versões ({sorted(versions)})")
    return versions.pop(), types


def index_path(provider: str, version: str) -> Path:
    return bo_data() / "downloads" / "registry-docs" / f"{provider}-{version}" / "index.json"


def fetch(provider: str, version: str, dest: Path) -> None:
    url = f"https://registry.terraform.io/v1/providers/{REGISTRY[provider]}/{version}"
    import time
    for attempt in range(4):
        try:
            with urllib.request.urlopen(url, timeout=120) as r:      # noqa: S310 (URL fixa do registro)
                data = r.read()
            break
        except urllib.error.HTTPError as e:
            if e.code < 500 or attempt == 3:
                raise
            time.sleep(5 * (attempt + 1))
    json.loads(data)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    (dest.parent / "SOURCE.txt").write_text(
        f"GET {url}\nÍndice de documentação do Terraform Registry (campo 'docs').\n"
        "Baixado por python -I -m bo.schema.crosscheck --fetch. Dado não confiável: só lido como JSON.\n",
        encoding="utf-8")


def documented(index: dict, provider: str, version: str) -> set[str]:
    if index.get("version") not in (None, version):
        raise SystemExit(f"crosscheck: índice da versão {index.get('version')}, tipos da {version}")
    pref = provider + "_"
    out = set()
    for d in index.get("docs") or []:
        if d.get("category") == "resources" and d.get("language") == "hcl":
            s = d["slug"]
            out.add(s if s.startswith(pref) else pref + s)
    return out


def compare(types: dict[str, str], docs: set[str]) -> dict:
    tset = set(types)
    no_doc, no_type = sorted(tset - docs), sorted(docs - tset)
    doc_sha = {types[t]: t for t in sorted(tset & docs)}
    explained, rest = [], []
    for t in no_doc:
        if types[t] in doc_sha:
            explained.append({"tipo": t, "causa": "alias_bloco_identico", "documentado_como": doc_sha[types[t]]})
            continue
        fam = next((t[: -len(s)] + "_iam" for s in IAM_SUFFIXES if t.endswith(s)), None)
        if fam and fam in docs:
            explained.append({"tipo": t, "causa": "familia_iam", "documentado_como": fam})
            continue
        rest.append(t)
    covered_pages = {e["documentado_como"] for e in explained if e["causa"] == "familia_iam"}
    pages_left = [p for p in no_type if p not in covered_pages]
    return {"tipos_schema": len(tset), "paginas_indice": len(docs), "iguais": len(tset & docs),
            "explicadas": explained, "tipos_sem_pagina": rest, "paginas_sem_tipo": pages_left,
            "veredito": "PASS" if not rest and not pages_left else "FAIL"}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="bo.schema.crosscheck", description=__doc__.split("\n")[0])
    ap.add_argument("--provider", required=True, choices=sorted(REGISTRY))
    ap.add_argument("--types", type=Path)
    ap.add_argument("--index", type=Path)
    ap.add_argument("--fetch", action="store_true")
    ap.add_argument("--out", type=Path)
    a = ap.parse_args(argv)
    tpath = a.types or bo_data() / PRODUCER[a.provider] / "types.jsonl"
    if not tpath.exists():
        print(f"crosscheck: {tpath} não existe (o {PRODUCER[a.provider]} grava o types.jsonl)", file=sys.stderr)
        return 2
    version, types = read_types(tpath)
    ipath = a.index or index_path(a.provider, version)
    if not ipath.exists():
        if not a.fetch:
            print(f"crosscheck: índice {ipath} ausente (use --fetch)", file=sys.stderr)
            return 2
        fetch(a.provider, version, ipath)
    rep = compare(types, documented(json.loads(ipath.read_text(encoding="utf-8")), a.provider, version))
    from bo.repo.core import now
    rep = {"generated_at": now(), "provider": a.provider, "provider_version": version, "types": str(tpath),
           "index": str(ipath), **rep}
    if a.out:
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(json.dumps(rep, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    causes = {}
    for e in rep["explicadas"]:
        causes[e["causa"]] = causes.get(e["causa"], 0) + 1
    print(f"crosscheck {a.provider} {version}: {rep['tipos_schema']} tipos, {rep['paginas_indice']} páginas, "
          f"{rep['iguais']} iguais, explicadas {causes or '{}'}, sem página {len(rep['tipos_sem_pagina'])}, "
          f"página sem tipo {len(rep['paginas_sem_tipo'])} -> {rep['veredito']}")
    for t in rep["tipos_sem_pagina"][:20]:
        print(f"  tipo sem página: {t}")
    for p in rep["paginas_sem_tipo"][:20]:
        print(f"  página sem tipo: {p}")
    return 0 if rep["veredito"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
