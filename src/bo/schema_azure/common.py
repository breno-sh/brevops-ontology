"""Caminhos e leitura do PINS para o SCHEMA-AZURE. A versão nunca é digitada: sai de universe/pins.json."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path

MODULE = "SCHEMA-AZURE"
PROVIDER = "azurerm"
SOURCE = "hashicorp/azurerm"
ADDRESS = "registry.terraform.io/hashicorp/azurerm"
#: impressão digital da chave primária de assinatura da HashiCorp. É a âncora de confiança: a chave pública
#: vem do registro (dado baixado) e por isso não basta sozinha; a assinatura tem de ser desta chave primária.
HASHICORP_FPR = "C874011F0AB405110D02105534365D9472D7468F"
#: host oficial dos pacotes da HashiCorp (o registro aponta para ele; a URL é montada aqui, não lida do download)
RELEASES = "https://releases.hashicorp.com"


def bo_repo() -> Path:
    return Path(os.environ.get("BO_REPO") or Path(__file__).resolve().parents[3])


def bo_data() -> Path:
    return Path(os.environ.get("BO_DATA", "/Users/breno/doutorado/brevops-data"))


def bo_tmp() -> Path:
    return Path(os.environ.get("BO_TMP") or bo_data() / "tmp" / MODULE)


def out_dir() -> Path:
    return bo_data() / MODULE


def plugin_cache_dir() -> Path:
    """Saída plugin_cache/: lock, configuração de instalação offline, pino do binário e README."""
    return out_dir() / "plugin_cache"


def shared_cache() -> Path:
    """Cache de plugin (layout desempacotado do terraform) onde o binário assinado mora: é download, então
    fica em $BO_DATA/downloads/, no padrão da bo.schema.extract."""
    from bo.schema import extract
    return extract.default_cache()


def prefetch_dir(version: str) -> Path:
    return bo_data() / "downloads" / "prefetch" / PROVIDER / version


def tfschema_dir(version: str) -> Path:
    from bo.schema import extract
    return extract.default_out(PROVIDER, version)


def zip_name(version: str, platform: str) -> str:
    return f"terraform-provider-{PROVIDER}_{version}_{platform}.zip"


def zip_dir(version: str) -> Path:
    """Espelho empacotado (filesystem_mirror) do zip assinado, no mesmo layout do HARNESS-AWS."""
    return bo_data() / "downloads" / f"terraform-{PROVIDER}-{version}" / "mirror" / "registry.terraform.io" / \
        "hashicorp" / PROVIDER


def zip_url(version: str, platform: str) -> str:
    return f"{RELEASES}/terraform-provider-{PROVIDER}/{version}/{zip_name(version, platform)}"


def portable(p: Path | str) -> str:
    s = str(p)
    for var, root in (("$BO_DATA", bo_data()), ("$BO_REPO", bo_repo())):
        r = str(root)
        if s == r or s.startswith(r + "/"):
            return var + s[len(r):]
    return s


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


@dataclass(frozen=True)
class Pin:
    provider: str
    source: str            # registry.terraform.io/hashicorp/azurerm
    version: str
    shasums_sha256: str
    schema_sha256: str
    terraform_version: str


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
               doc["terraform"]["version"])
