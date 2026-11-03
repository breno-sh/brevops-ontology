"""Pin, caminhos e fontes do DOCS-GCP. Nada aqui baixa nem executa: só lê arquivos já conferidos."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from bo.schema import core as schema_core

MODULE = "DOCS-GCP"
PROVIDER = "google"
SOURCE_ADDR = "registry.terraform.io/hashicorp/google"
REPO = "hashicorp/terraform-provider-google"
REPO_URL = "https://github.com/hashicorp/terraform-provider-google"
DOCS_PREFIX = "website/docs"          # caminho das páginas no repositório oficial
LICENSE = "MPL-2.0 (repositório hashicorp/terraform-provider-google)"


def bo_repo() -> Path:
    return Path(os.environ.get("BO_REPO") or Path(__file__).resolve().parents[3])


def bo_data() -> Path:
    return Path(os.environ.get("BO_DATA") or "/Users/breno/doutorado/brevops-data")


def bo_tmp() -> Path:
    p = Path(os.environ.get("BO_TMP") or bo_data() / "tmp" / MODULE)
    p.mkdir(parents=True, exist_ok=True)
    return p


def pins_path() -> Path:
    return bo_repo() / "universe" / "pins.json"


def pin() -> dict:
    """A entrada do provider google no pins.json (C13)."""
    doc = json.loads(pins_path().read_text(encoding="utf-8"))
    for p in doc["providers"]:
        if p["provider"] == PROVIDER:
            return p
    raise SystemExit(f"pins.json sem o provider {PROVIDER}")


def version() -> str:
    return pin()["version"]


def tag() -> str:
    return "v" + version()


def prefetch_dir() -> Path:
    return bo_data() / "downloads" / "prefetch" / PROVIDER / version()


def download_dir() -> Path:
    return bo_data() / "downloads" / "docs-google"


def docs_root() -> Path:
    """Raiz das páginas copiadas: downloads/docs-google/website/docs (mesmo caminho do repositório)."""
    return download_dir() / DOCS_PREFIX


def out_dir() -> Path:
    return bo_data() / MODULE


def results_dir() -> Path:
    return bo_repo() / "results" / MODULE


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def prefetch_manifest() -> dict:
    return json.loads((prefetch_dir() / "MANIFEST.json").read_text(encoding="utf-8"))


def tag_commit() -> tuple[str, str]:
    """(sha do commit da tag, data da tag AAAA-MM-DD) como a pré-busca registrou; o fetch confere no GitHub."""
    d = prefetch_manifest()["sources"]["docs"]
    if d["tag"] != tag():
        raise SystemExit(f"pré-busca na tag {d['tag']}, pin pede {tag()}")
    return d["commit"], d["commit_date"][:10]


def schema_path() -> Path:
    return prefetch_dir() / "providers-schema.json"


def load_types() -> dict[str, schema_core.TypeSchema]:
    """Tipos de recurso do schema fixado, com o sha256 conferido contra o pins.json (schema_sha256)."""
    sp = schema_path()
    got = sha256_file(sp)
    want = pin()["schema_sha256"]
    if got != want:
        raise SystemExit(f"schema {sp}: sha256 {got[:12]}… diverge do pins.json {want[:12]}…")
    doc = schema_core.load(sp)
    ps = schema_core.providers(doc)[PROVIDER]
    return {ts.resource_type: ts for ts in schema_core.iter_types(ps, PROVIDER, version())}
