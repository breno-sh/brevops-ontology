"""Blocos de construção dos JSON Schema do CONTRACTS (draft 2020-12) e caminhos/hora do pacote.

Os contratos são escritos em Python (src/bo/contracts/spec_*.py) e gravados por bo.contracts.build em
$BO_REPO/contracts/Cnn_<nome>.schema.json. Cada schema traz um bloco x-bo-contract com os arquivos que o
contrato cobre (tipo de arquivo, padrão de nome, formato, definição do registro) e as regras que o JSON
Schema não exprime; essas regras rodam em bo.contracts.rules, chamadas pelo validador único.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
from pathlib import Path
from zoneinfo import ZoneInfo

DRAFT = "https://json-schema.org/draft/2020-12/schema"
BASE_URI = "https://w3id.org/brevops/contracts/"
TZ = ZoneInfo("America/Recife")
PKG = Path(__file__).resolve().parent


def repo() -> Path:
    r = os.environ.get("BO_REPO")
    if r:
        return Path(r)
    return PKG.parents[2]


def data_root() -> Path:
    return Path(os.environ.get("BO_DATA") or "/Users/breno/doutorado/brevops-data")


def data_dir() -> Path:
    return data_root() / "CONTRACTS"


def tmp_dir() -> Path:
    p = Path(os.environ.get("BO_TMP") or (data_root() / "tmp" / "CONTRACTS"))
    p.mkdir(parents=True, exist_ok=True)
    return p


def contracts_dir() -> Path:
    return repo() / "contracts"


def stubs_dir() -> Path:
    return contracts_dir() / "stubs"


def results_dir() -> Path:
    return repo() / "results" / "CONTRACTS"


def now() -> str:
    return _dt.datetime.now(TZ).replace(microsecond=0).isoformat()


def dumps(obj) -> str:
    """JSON canônico dos arquivos gravados (ordem de chaves estável, UTF-8, indentação 1)."""
    return json.dumps(obj, ensure_ascii=False, indent=1, sort_keys=False) + "\n"


def jsonl(recs: list) -> str:
    return "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in recs)


def schema_uri(cid: str, name: str) -> str:
    return f"{BASE_URI}{cid}/{name}.schema.json"


# ------------------------------------------------------------------------------- construtores de schema
def obj(props: dict, required=(), *, extra=False, **kw) -> dict:
    """Objeto fechado por padrão (additionalProperties: false)."""
    o = {"type": "object", "properties": props}
    if required:
        o["required"] = list(required)
    if extra is False:
        o["additionalProperties"] = False
    elif extra is not True:
        o["additionalProperties"] = extra
    o.update(kw)
    return o


def arr(items, min_items: int | None = None, *, unique=False, **kw) -> dict:
    a = {"type": "array", "items": items}
    if min_items is not None:
        a["minItems"] = min_items
    if unique:
        a["uniqueItems"] = True
    a.update(kw)
    return a


def enum(*vals, **kw) -> dict:
    return {"enum": list(vals), **kw}


def const(v, **kw) -> dict:
    return {"const": v, **kw}


def string(pattern: str | None = None, min_len: int | None = 1, **kw) -> dict:
    s = {"type": "string"}
    if min_len is not None:
        s["minLength"] = min_len
    if pattern:
        s["pattern"] = pattern
    s.update(kw)
    return s


def text(min_len: int = 3, **kw) -> dict:
    return {"type": "string", "minLength": min_len, **kw}


def integer(minimum: int | None = 0, **kw) -> dict:
    i = {"type": "integer"}
    if minimum is not None:
        i["minimum"] = minimum
    i.update(kw)
    return i


def number(**kw) -> dict:
    return {"type": "number", **kw}


def boolean(**kw) -> dict:
    return {"type": "boolean", **kw}


def nullable(s: dict) -> dict:
    return {"anyOf": [{"type": "null"}, s]}


C00 = "C00/conventions.schema.json"


def c00(name: str) -> dict:
    """Referência a uma definição comum do C00 (convenções)."""
    return {"$ref": f"{BASE_URI}{C00}#/$defs/{name}"}


def local(name: str) -> dict:
    return {"$ref": f"#/$defs/{name}"}


def header(schema_id: str, cid: str, version: str, *, module=False, generated=True) -> tuple[dict, list]:
    """Cabeçalho de documento (JSON/YAML de topo): schema, contract, contract_version [, module, generated_at]."""
    props = {"schema": const(schema_id), "contract": const(cid), "contract_version": const(version)}
    req = ["schema", "contract", "contract_version"]
    if module:
        props["module"] = c00("stable_id")
        req.append("module")
    if generated:
        props["generated_at"] = c00("datetime")
        req.append("generated_at")
    return props, req


def contract_schema(cid: str, name: str, version: str, title: str, *, status: str, files: list, defs: dict,
                    rules: list, description: str, producers=(), consumers=(), adopted=()) -> dict:
    """Documento de schema de um contrato. files: [{kind, file, format, record, unit, note?}]."""
    return {
        "$schema": DRAFT,
        "$id": schema_uri(cid, name),
        "title": f"{cid} {name} {version}: {title}",
        "description": description,
        "x-bo-contract": {
            "id": cid, "name": name, "version": version, "status": status, "owner": "CONTRACTS",
            "files": files, "semantic_rules": rules, "producers": sorted(producers), "consumers": sorted(consumers),
            "adopted_from": list(adopted),
        },
        "$defs": defs,
    }


def file_kind(kind: str, file: str, fmt: str, record: str | None, unit: str, note: str = "") -> dict:
    d = {"kind": kind, "file": file, "format": fmt, "record": record, "unit": unit}
    if note:
        d["note"] = note
    return d
