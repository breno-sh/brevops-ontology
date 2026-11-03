"""Crosscheck do oci na versão fixada (bo.schema.crosscheck, sem afrouxar) + classificação do que sobra.

  python -I -m bo.schema_oci.crossdiff [--out-dir DIR]

1. Roda a comparação da biblioteca (bo.schema.crosscheck: read_types, documented, compare) sobre o
   types.jsonl do módulo e o índice do Registry da MESMA versão; o veredito dela é gravado como está.
2. Classifica cada tipo sem página e cada página sem tipo lendo o título ('# ...') da página no
   website/docs/ da tag da versão (pré-busca; dado não confiável, só lido como texto). A classificação é
   desta análise, NÃO muda o veredito do gate, e cada linha traz a prova (título lido, onde está o nome).

Classes (ordem de teste):
  pagina_com_slug_divergente   a página sem tipo tem título que nomeia um tipo do schema sem página
                               (o slug da página difere do nome do tipo que ela documenta)
  pagina_de_data_source_em_r   página em resources cujo título é '# Data Source: ...'
  pagina_de_tipo_ausente       o título nomeia um oci_* que não é tipo de recurso deste schema
  pagina_sem_titulo            página sem título '# ...' legível
  tipo_sem_documentacao        tipo do schema sem página e sem página de título igual

Saída: <out-dir>/crosscheck_oci-<versão>.json (relatório da biblioteca) e
       <out-dir>/crosscheck_classificacao.json (esta classificação). Sai 0 se gravou; o gate é o
       'python -I -m bo.schema.crosscheck --provider oci', não este comando.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from bo.schema import crosscheck as cc

from . import common

TITLE = re.compile(r"^#\s+(Data Source:\s*)?(oci_[a-z0-9_]+)\s*$", re.M)
ANY_TITLE = re.compile(r"^#\s+\S", re.M)


def page_title(path: Path) -> dict:
    """{'existe', 'data_source', 'nomeia'} do título '# ...' da página (só texto; nada é executado)."""
    if not path.is_file():
        return {"existe": False, "data_source": False, "nomeia": None, "tem_titulo": False}
    text = path.read_text(encoding="utf-8", errors="replace")
    m = TITLE.search(text)
    return {"existe": True, "data_source": bool(m and m.group(1)), "nomeia": m.group(2) if m else None,
            "tem_titulo": bool(ANY_TITLE.search(text))}


def resource_pages(index: dict) -> dict[str, dict]:
    """{nome normalizado da página (oci_<slug>): entrada do índice} das páginas resources/hcl."""
    out = {}
    for d in index.get("docs") or []:
        if d.get("category") == "resources" and d.get("language") == "hcl":
            s = d["slug"]
            out[s if s.startswith("oci_") else "oci_" + s] = d
    return out


def classify(rep: dict, pages: dict[str, dict], docs_root: Path, schema_types: set[str],
             data_sources: set[str]) -> dict:
    no_doc = set(rep["tipos_sem_pagina"])
    rows_p, rows_t, paired = [], [], set()
    for p in sorted(rep["paginas_sem_tipo"]):
        e = pages[p]
        rel = e["path"][len("website/docs/"):] if e["path"].startswith("website/docs/") else e["path"]
        t = page_title(docs_root / rel)
        row = {"pagina": p, "arquivo": e["path"], "titulo_nomeia": t["nomeia"], "titulo_data_source": t["data_source"]}
        if t["nomeia"] and not t["data_source"] and t["nomeia"] in no_doc:
            row["classe"] = "pagina_com_slug_divergente"
            row["documenta_o_tipo"] = t["nomeia"]
            paired.add(t["nomeia"])
        elif t["data_source"]:
            row["classe"] = "pagina_de_data_source_em_r"
            row["data_source_no_schema"] = t["nomeia"] in data_sources
        elif t["nomeia"] and t["nomeia"] not in schema_types:
            row["classe"] = "pagina_de_tipo_ausente"
        elif not t["tem_titulo"] or not t["existe"]:
            row["classe"] = "pagina_sem_titulo"
            row["arquivo_existe"] = t["existe"]
        else:
            row["classe"] = "nao_classificada"
        rows_p.append(row)
    for tname in sorted(no_doc):
        if tname in paired:
            doc = next(r["pagina"] for r in rows_p if r.get("documenta_o_tipo") == tname)
            rows_t.append({"tipo": tname, "classe": "pagina_com_slug_divergente", "pagina": doc})
        else:
            rows_t.append({"tipo": tname, "classe": "tipo_sem_documentacao"})
    count: dict[str, int] = {}
    for r in rows_p + rows_t:
        k = ("pagina:" if "pagina" in r and "tipo" not in r else "tipo:") + r["classe"]
        count[k] = count.get(k, 0) + 1
    return {"paginas_sem_tipo": rows_p, "tipos_sem_pagina": rows_t, "contagem": dict(sorted(count.items()))}


def run(out_dir: Path | None = None) -> dict:
    from bo.repo.core import now
    out_dir = out_dir or common.out_dir()
    tpath = out_dir / "types.jsonl"            # o types.jsonl ao lado do relatório (publicado ou de uma regeneração)
    version, types = cc.read_types(tpath)
    ipath = cc.index_path(common.PROVIDER, version)
    index = json.loads(ipath.read_text(encoding="utf-8"))
    rep = cc.compare(types, cc.documented(index, common.PROVIDER, version))
    lib = {"generated_at": now(), "provider": common.PROVIDER, "provider_version": version,
           "types": tpath.name, "types_sha256": common.sha256_file(tpath), "index": common.portable(ipath),
           "index_sha256": common.sha256_file(ipath), **rep}
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"crosscheck_oci-{version}.json").write_text(json.dumps(lib, ensure_ascii=False, indent=1) + "\n",
                                                            encoding="utf-8")
    from bo.schema import core
    gz = common.tfschema_dir(version) / "schema.json.gz"
    ps = core.providers(core.load(gz))[common.PROVIDER]
    docs_root = common.prefetch_dir(version) / "docs"
    cls = classify(rep, resource_pages(index), docs_root, set(ps.get("resource_schemas") or {}),
                   set(ps.get("data_source_schemas") or {}))
    doc = {
        "schema": "bo.schema_oci.crosscheck_classificacao/1", "module": common.MODULE,
        "provider": common.PROVIDER, "provider_version": version,
        "veredito_da_biblioteca": rep["veredito"],
        "nota": ("classificação desta análise sobre o que a bo.schema.crosscheck deixou sem causa; não muda o "
                 "veredito do gate (o comando da biblioteca não foi afrouxado)"),
        "fontes": {"index": common.portable(ipath), "index_sha256": common.sha256_file(ipath),
                   "docs": common.portable(docs_root), "schema": common.portable(gz)},
        "resumo": {"tipos_schema": rep["tipos_schema"], "paginas_indice": rep["paginas_indice"],
                   "iguais": rep["iguais"], "explicadas_pela_biblioteca": len(rep["explicadas"]),
                   "tipos_sem_pagina": len(rep["tipos_sem_pagina"]), "paginas_sem_tipo": len(rep["paginas_sem_tipo"])},
        **cls,
    }
    (out_dir / "crosscheck_classificacao.json").write_text(
        json.dumps(doc, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return doc


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="bo.schema_oci.crossdiff", description=__doc__.split("\n")[0])
    ap.add_argument("--out-dir", type=Path)
    a = ap.parse_args(argv)
    d = run(a.out_dir)
    r = d["resumo"]
    print(f"crosscheck oci {d['provider_version']}: {r['tipos_schema']} tipos, {r['paginas_indice']} páginas, "
          f"{r['iguais']} iguais, {r['explicadas_pela_biblioteca']} explicadas pela biblioteca, "
          f"{r['tipos_sem_pagina']} tipos sem página, {r['paginas_sem_tipo']} páginas sem tipo "
          f"-> {d['veredito_da_biblioteca']}")
    for k, v in d["contagem"].items():
        print(f"  {k}: {v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
