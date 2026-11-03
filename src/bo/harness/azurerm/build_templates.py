"""Gera deploy/fixtures/azurerm/_templates/ a partir do schema fixado do provider (dado, nunca executado).

  python -I -m bo.harness.azurerm.build_templates [--schema ARQ] [--pins ARQ] [--check]

Saídas (regeneração idêntica conferida por --check):
  schema_index.jsonl   1ª linha = cabeçalho (provider, versão, sha256 do schema de origem); depois uma linha por
                       tipo de recurso e de data source, com a árvore de blocos e as marcas de cada atributo
                       (atributos e blocos como listas [nome, ...], sem nome de atributo como chave JSON):
                       r=required o=optional c=computed s=sensitive w=write_only (só o que o renderizador e o
                       redator usam; descrições ficam de fora)
  versions.tf          bloco terraform{} e provider{} fixados: a ÚNICA forma que o harness acrescenta ao HCL
  terraform.lock.hcl   lock do provider fixado (cópia do prefetch conferido por GPG); usado só pelo validate
  TEMPLATES.json       versões, origens, sha256 dos arquivos e a lista declarada do que versions.tf põe no HCL

O schema de origem tem de bater com o schema_sha256 do azurerm em universe/pins.json (PINS).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import hclwrite as H
from ._common import HarnessError, data_root, dumps, portable, repo, sha256_bytes, sha256_file, templates_dir

INDEX_SCHEMA = "bo.harness_azurerm.schema_index/1"
SOURCE_KEY = "registry.terraform.io/hashicorp/azurerm"
FLAGS = (("r", "required"), ("o", "optional"), ("c", "computed"), ("s", "sensitive"), ("w", "write_only"))


def default_schema(version: str) -> Path:
    return data_root() / "downloads" / "prefetch" / "azurerm" / version / "providers-schema.json"


def load_pins(path: Path) -> dict:
    pins = json.loads(path.read_text(encoding="utf-8"))
    az = [p for p in pins.get("providers", []) if p.get("provider") == "azurerm"]
    if len(az) != 1:
        raise HarnessError(f"{path}: precisa de exatamente 1 provider azurerm (achei {len(az)})")
    return {"terraform": pins["terraform"]["version"], "provider": az[0]}


def enc_type(t):
    """Tipo cty com objetos como lista de pares [nome, tipo] (ordem por nome), para o índice não ter chave JSON
    com nome de atributo (o privacy_lint é lexical e confundiria nome de atributo sensível seguido de tipo com segredo)."""
    if isinstance(t, list) and t and t[0] == "object":
        out = ["object", [[k, enc_type(v)] for k, v in sorted(t[1].items())]]
        if len(t) > 2:
            out.append(sorted(t[2]))
        return out
    if isinstance(t, list):
        return [enc_type(x) for x in t]
    return t


def compact(block: dict) -> dict:
    """Nó: {"a": [[atributo, marcas, tipo], ...], "b": [[bloco, nesting_mode, min, max, nó], ...]}, por nome."""
    out = {}
    attrs = []
    for name, a in sorted(block.get("attributes", {}).items()):
        if "nested_type" in a:
            raise HarnessError(f"atributo {name} com nested_type: o índice não cobre (não há nenhum no 5.12.0)")
        attrs.append([name, "".join(f for f, k in FLAGS if a.get(k)), enc_type(a["type"])])
    blocks = []
    for name, b in sorted(block.get("block_types", {}).items()):
        blocks.append([name, b["nesting_mode"], b.get("min_items", 0), b.get("max_items", 0), compact(b["block"])])
    if attrs:
        out["a"] = attrs
    if blocks:
        out["b"] = blocks
    return out


def versions_blocks(tf_version: str, prov: dict) -> list:
    source = prov["source"].replace("registry.terraform.io/", "")
    tf = H.Block("terraform", (), [
        H.Attr("required_version", H.Lit(f"= {tf_version}")),
        H.Block("required_providers", (), [
            H.Attr("azurerm", H.ObjE((("source", H.Lit(source)), ("version", H.Lit(f"= {prov['version']}"))))),
        ]),
    ])
    pv = H.Block("provider", ("azurerm",), [H.Block("features")])
    return [tf, pv]


# o que versions.tf acrescenta ao HCL, declarado (conferido pelo no_silent_insert)
def declared_boilerplate(tf_version: str, prov: dict) -> list[dict]:
    source = prov["source"].replace("registry.terraform.io/", "")
    return [
        {"path": "terraform.required_version", "value": f"= {tf_version}", "why": "Terraform fixado (PINS)"},
        {"path": "terraform.required_providers.azurerm.source", "value": source, "why": "origem do provider"},
        {"path": "terraform.required_providers.azurerm.version", "value": f"= {prov['version']}",
         "why": "provider fixado (PINS)"},
        {"path": "provider.azurerm.features", "value": {}, "why": "bloco features{} obrigatório no azurerm"},
    ]


def build(schema_path: Path, pins_path: Path) -> dict[str, bytes]:
    pins = load_pins(pins_path)
    prov = pins["provider"]
    sha = sha256_file(schema_path)
    if sha != prov["schema_sha256"]:
        raise HarnessError(f"schema {schema_path} tem sha256 {sha[:12]}…, mas o PINS fixa {prov['schema_sha256'][:12]}…")
    doc = json.loads(schema_path.read_text(encoding="utf-8"))
    ps = doc["provider_schemas"][SOURCE_KEY]
    header = {
        "schema": INDEX_SCHEMA, "provider": "azurerm", "source": prov["source"], "version": prov["version"],
        "source_schema_sha256": sha, "format_version": doc.get("format_version"),
        "resource_types": len(ps["resource_schemas"]), "data_sources": len(ps.get("data_source_schemas", {})),
        "flags": {f: k for f, k in FLAGS},
    }
    lines = [json.dumps(header, sort_keys=True, separators=(",", ":"))]
    for kind, key in (("resource", "resource_schemas"), ("data", "data_source_schemas")):
        for t in sorted(ps.get(key, {})):
            rec = {"kind": kind, "type": t, "block": compact(ps[key][t]["block"])}
            lines.append(json.dumps(rec, sort_keys=True, separators=(",", ":")))
    index = ("\n".join(lines) + "\n").encode()
    versions = H.file_text(versions_blocks(pins["terraform"], prov)).encode()
    lock_src = schema_path.parent / "terraform.lock.hcl"
    lock = lock_src.read_bytes()
    if f'version     = "{prov["version"]}"'.encode() not in lock:
        raise HarnessError(f"{lock_src} não fixa o azurerm {prov['version']}")
    manifest = {
        "schema": "bo.harness_azurerm.templates/1", "module": "HARNESS-AZURE", "provider": "azurerm",
        "terraform_version": pins["terraform"], "provider_version": prov["version"], "provider_source": prov["source"],
        "sources": [
            {"path": portable(schema_path), "sha256": sha, "what": "terraform providers schema -json (azurerm fixado)"},
            {"path": portable(pins_path), "sha256": sha256_file(pins_path), "what": "versões fixadas (PINS)"},
            {"path": portable(lock_src), "sha256": sha256_bytes(lock), "what": "lock do provider (prefetch, GPG ok)"},
        ],
        "declared_boilerplate": declared_boilerplate(pins["terraform"], prov),
        "files": {"schema_index.jsonl": sha256_bytes(index), "versions.tf": sha256_bytes(versions),
                  "terraform.lock.hcl": sha256_bytes(lock)},
    }
    return {"schema_index.jsonl": index, "versions.tf": versions, "terraform.lock.hcl": lock,
            "TEMPLATES.json": dumps(manifest).encode()}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="bo.harness.azurerm.build_templates")
    ap.add_argument("--pins", default=str(repo() / "universe" / "pins.json"))
    ap.add_argument("--schema", default=None)
    ap.add_argument("--out", default=str(templates_dir()))
    ap.add_argument("--check", action="store_true", help="só confere que os arquivos gravados são idênticos")
    a = ap.parse_args(argv)
    try:
        pins_path = Path(a.pins)
        schema = Path(a.schema) if a.schema else default_schema(load_pins(pins_path)["provider"]["version"])
        files = build(schema, pins_path)
    except (HarnessError, OSError, KeyError) as e:
        print(f"build_templates: {e}", file=sys.stderr)
        return 2
    out = Path(a.out)
    if a.check:
        bad = [n for n, b in files.items() if not (out / n).is_file() or (out / n).read_bytes() != b]
        if bad:
            print("build_templates --check: diferente do gerado: " + ", ".join(bad), file=sys.stderr)
            return 1
        print(f"build_templates --check: {len(files)} arquivo(s) idênticos ao gerado")
        return 0
    out.mkdir(parents=True, exist_ok=True)
    for n, b in files.items():
        (out / n).write_bytes(b)
    print(f"build_templates: {len(files)} arquivo(s) em {portable(out)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
