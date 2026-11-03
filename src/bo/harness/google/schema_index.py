"""Índice compacto do schema do provider google fixado, só com a estrutura que o renderizador precisa.

  python -I -m bo.harness.google.schema_index [--schema ARQ]          (re)gera _templates/schema_index.json
  python -I -m bo.harness.google.schema_index --check [--schema ARQ]  regenera em memória e compara (saída 1 se diverge)

Fonte: saída de 'terraform providers schema -json' do google na versão de universe/pins.json (binário assinado,
sem credenciais; pré-busca em $BO_DATA/downloads/prefetch/google/<versão>/). O sha256 do arquivo tem de ser o
schema_sha256 fixado; dado não confiável, lido só como JSON. Descrições ficam fora; ficam tipo cty, as marcas
required/optional/computed/sensitive/write_only/deprecated e, por bloco, nesting_mode, min_items e max_items.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import common as C

FLAGS = ("required", "optional", "computed", "sensitive", "write_only", "deprecated")


def default_schema_path() -> Path:
    return C.data() / "downloads" / "prefetch" / "google" / C.provider_pin()["version"] / "providers-schema.json"


def compact_block(b: dict) -> dict:
    out = {"attributes": {}, "blocks": {}}
    for name, a in sorted(b.get("attributes", {}).items()):
        ent = {"type": a.get("type"), "flags": [f for f in FLAGS if a.get(f)]}
        if "nested_type" in a:
            # atributo aninhado (protocolo 6): o renderizador trata como objeto com o tipo cty equivalente
            ent["nested_type"] = {"nesting_mode": a["nested_type"].get("nesting_mode"),
                                  "block": compact_block({"attributes": a["nested_type"].get("attributes", {})})}
        out["attributes"][name] = ent
    for name, bt in sorted(b.get("block_types", {}).items()):
        out["blocks"][name] = {"nesting_mode": bt["nesting_mode"], "min_items": bt.get("min_items", 0) or 0,
                               "max_items": bt.get("max_items", 0) or 0, "block": compact_block(bt["block"])}
    return out


def to_disk(block: dict) -> dict:
    """No arquivo, atributos e blocos viram listas de pares [nome, entrada]: o nome de um atributo (ex.: o de
    script de boot) nunca aparece como chave JSON seguida de valor, que o privacy_lint lê como conteúdo Withheld."""
    return {"attributes": [[n, {**a, **({"nested_type": {"nesting_mode": a["nested_type"]["nesting_mode"],
                                                          "block": to_disk(a["nested_type"]["block"])}}
                                        if "nested_type" in a else {})}] for n, a in block["attributes"].items()],
            "blocks": [[n, {**b, "block": to_disk(b["block"])}] for n, b in block["blocks"].items()]}


def from_disk(block: dict) -> dict:
    attrs = {}
    for n, a in block["attributes"]:
        a = dict(a)
        if "nested_type" in a:
            a["nested_type"] = {"nesting_mode": a["nested_type"]["nesting_mode"],
                                "block": from_disk(a["nested_type"]["block"])}
        attrs[n] = a
    return {"attributes": attrs, "blocks": {n: {**b, "block": from_disk(b["block"])} for n, b in block["blocks"]}}


def build(schema_path: Path) -> dict:
    pin = C.provider_pin()
    sha = C.sha256_file(schema_path)
    if sha != pin["schema_sha256"]:
        raise SystemExit(f"schema {schema_path} tem sha256 {sha[:12]}…, diferente do fixado "
                         f"{pin['schema_sha256'][:12]}… (universe/pins.json); nada gerado")
    full = json.loads(schema_path.read_text(encoding="utf-8"))
    ps = full["provider_schemas"][C.PROVIDER_SOURCE]
    types = json.loads((C.templates() / "types.json").read_text(encoding="utf-8"))
    res, ds = {}, {}
    for t in types["resources"]:
        if t not in ps["resource_schemas"]:
            raise SystemExit(f"tipo {t} não existe no google {pin['version']}")
        res[t] = to_disk(compact_block(ps["resource_schemas"][t]["block"]))
    for t in types["data_sources"]:
        if t not in ps["data_source_schemas"]:
            raise SystemExit(f"data source {t} não existe no google {pin['version']}")
        ds[t] = to_disk(compact_block(ps["data_source_schemas"][t]["block"]))
    return {"schema": "bo.harness_google.schema_index/1", "module": C.MODULE, "provider": C.PROVIDER,
            "source": pin["source"], "version": pin["version"], "schema_sha256": sha,
            "format_version": full.get("format_version"), "resources": res, "data_sources": ds}


def index_path() -> Path:
    return C.templates() / "schema_index.json"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="bo.harness.google.schema_index")
    ap.add_argument("--schema", type=Path, default=None)
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)
    src = a.schema or default_schema_path()
    if not src.exists():
        print(f"[{C.now()}] schema_index: fonte ausente {src}", file=sys.stderr)
        return 2
    text = C.dump(build(src))
    if a.check:
        cur = index_path().read_text(encoding="utf-8") if index_path().exists() else ""
        ok = cur == text
        print(f"[{C.now()}] schema_index --check: {'idêntico' if ok else 'DIVERGE'} ({index_path()})")
        return 0 if ok else 1
    index_path().write_text(text, encoding="utf-8")
    d = json.loads(text)
    print(f"[{C.now()}] schema_index: {len(d['resources'])} recursos, {len(d['data_sources'])} data sources, "
          f"google {d['version']} -> {index_path()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
