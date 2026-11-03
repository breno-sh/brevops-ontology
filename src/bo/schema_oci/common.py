"""Caminhos e leitura do PINS para o SCHEMA-OCI. Nenhuma versão é digitada aqui: ela sai de universe/pins.json."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path

MODULE = "SCHEMA-OCI"
PROVIDER = "oci"
ADDRESS = "registry.terraform.io/oracle/oci"
NAMESPACE, NAME = "oracle", "oci"
#: impressão digital da chave primária com que a Oracle assina o SHA256SUMS do terraform-provider-oci.
#: É a âncora de confiança: a chave pública em si vem do registro (dado baixado), e só vale se a assinatura
#: conferir com ESTA chave primária (a pré-busca de 02/11 registrou a mesma no gpg-verify-status.txt).
ORACLE_FPR = "7F1079B5E6547DBFCCEFB9A41533A49284137CEB"
#: único prefixo aceito para baixar o zip (o download_url do registro é dado não confiável)
RELEASE_PREFIX = "https://github.com/oracle/terraform-provider-oci/releases/download/"


def bo_repo() -> Path:
    return Path(os.environ.get("BO_REPO") or Path(__file__).resolve().parents[3])


def bo_data() -> Path:
    return Path(os.environ.get("BO_DATA", "/Users/breno/doutorado/brevops-data"))


def bo_tmp() -> Path:
    return Path(os.environ.get("BO_TMP") or bo_data() / "tmp" / MODULE)


def out_dir() -> Path:
    return bo_data() / MODULE


def plugin_cache_dir() -> Path:
    """Saída plugin_cache/ do módulo: lock, configuração de instalação offline e o pino do binário."""
    return out_dir() / "plugin_cache"


def shared_cache() -> Path:
    """Cache de plugin onde o binário assinado mora (download: $BO_DATA/downloads/<fonte>/, padrão da bo.schema)."""
    from bo.schema import extract
    return extract.default_cache()


def zip_dir(version: str) -> Path:
    """Pasta própria do zip baixado do release (dado não confiável, com SOURCE.txt)."""
    return bo_data() / "downloads" / f"terraform-provider-{NAME}-{version}"


def prefetch_dir(version: str) -> Path:
    return bo_data() / "downloads" / "prefetch" / PROVIDER / version


def tfschema_dir(version: str) -> Path:
    from bo.schema import extract
    return extract.default_out(PROVIDER, version)


def portable(p: Path | str) -> str:
    s = str(p)
    for var, root in (("$BO_DATA", bo_data()), ("$BO_REPO", bo_repo())):
        r = str(root)
        if s == r or s.startswith(r + "/"):
            return var + s[len(r):]
    return s


def unportable(s: str) -> Path:
    for var, root in (("$BO_DATA", bo_data()), ("$BO_REPO", bo_repo())):
        if s == var or s.startswith(var + "/"):
            return Path(str(root) + s[len(var):])
    return Path(s)


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


@dataclass(frozen=True)
class Pin:
    provider: str
    source: str            # registry.terraform.io/oracle/oci
    version: str
    shasums_sha256: str
    schema_sha256: str
    terraform_version: str
    terraform_sha256: str


def read_pin(pins: Path | None = None) -> Pin:
    p = pins or bo_repo() / "universe" / "pins.json"
    doc = json.loads(Path(p).read_text(encoding="utf-8"))
    hits = [x for x in doc.get("providers", []) if x.get("provider") == PROVIDER]
    if len(hits) != 1:
        raise SystemExit(f"{MODULE}: pins.json com {len(hits)} entradas para {PROVIDER}")
    e = hits[0]
    if e["source"] != ADDRESS:
        raise SystemExit(f"{MODULE}: pins.json fixa {e['source']}, esperado {ADDRESS}")
    return Pin(PROVIDER, e["source"], e["version"], e["shasums_sha256"], e["schema_sha256"],
               doc["terraform"]["version"], doc["terraform"]["sha256"])
