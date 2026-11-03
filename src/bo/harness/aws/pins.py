"""Versão fixada do provider aws e o schema do provider conferido por sha256 contra universe/pins.json (PINS).

O schema é a saída de 'terraform providers schema -json' do binário assinado (pré-busca em
$BO_DATA/downloads/prefetch/aws/<versão>/providers-schema.json, decisão D1). Sem o arquivo ou com sha diferente
do fixado, nada é renderizado: o renderizador não adivinha quais campos são obrigatórios.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path

from . import PROVIDER, PROVIDER_SOURCE


class PinError(RuntimeError):
    pass


def repo_root() -> Path:
    env = os.environ.get("BO_REPO")
    if env and (Path(env) / "universe").is_dir():
        return Path(env)
    return Path(__file__).resolve().parents[4]


def data_root() -> Path:
    return Path(os.environ.get("BO_DATA") or "/Users/breno/doutorado/brevops-data")


def tmp_root() -> Path:
    """$BO_TMP do módulo; nunca /tmp."""
    t = os.environ.get("BO_TMP")
    p = Path(t) if t else data_root() / "tmp" / "HARNESS-AWS"
    rp = str(p.resolve())
    if rp == "/tmp" or rp.startswith(("/tmp/", "/private/tmp/")):
        raise PinError(f"BO_TMP aponta para /tmp ({rp}); o harness só trabalha em $BO_DATA/tmp/<ID>")
    p.mkdir(parents=True, exist_ok=True)
    return p


@dataclass(frozen=True)
class Pin:
    terraform_version: str
    provider_version: str
    schema_sha256: str
    pins_path: Path


def load_pin(pins_path: Path | None = None) -> Pin:
    p = pins_path or repo_root() / "universe" / "pins.json"
    if not p.exists():
        raise PinError(f"pins.json ausente: {p}")
    d = json.loads(p.read_text(encoding="utf-8"))
    for e in d.get("providers", []):
        if e.get("provider") == PROVIDER and e.get("source") == PROVIDER_SOURCE:
            return Pin(d["terraform"]["version"], e["version"], e["schema_sha256"], p)
    raise PinError(f"pins.json sem o provider {PROVIDER} ({PROVIDER_SOURCE})")


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def schema_path(pin: Pin | None = None) -> Path:
    pin = pin or load_pin()
    env = os.environ.get("BO_AWS_SCHEMA")
    return Path(env) if env else data_root() / "downloads" / "prefetch" / PROVIDER / pin.provider_version / \
        "providers-schema.json"


def verified_schema_path(pin: Pin | None = None) -> tuple[Path, Pin]:
    pin = pin or load_pin()
    p = schema_path(pin)
    if not p.exists():
        raise PinError(f"schema do provider aws {pin.provider_version} ausente: {p}")
    got = sha256_file(p)
    if got != pin.schema_sha256:
        raise PinError(f"schema {p} tem sha256 {got[:12]}…, o fixado em pins.json é {pin.schema_sha256[:12]}…")
    return p, pin


def socket_dir() -> Path:
    """TMPDIR curto para o Terraform: o socket unix do plugin do provider estoura o limite de 104 caracteres
    do macOS quando o TMPDIR é um caminho longo ('Failed to load plugin schemas')."""
    p = tmp_root() / "sk" / str(os.getpid())
    p.mkdir(parents=True, exist_ok=True)
    return p


def mirror_dir(pin: Pin | None = None) -> Path:
    """Filesystem mirror empacotado com o zip assinado do provider (só para init/validate offline)."""
    pin = pin or load_pin()
    return data_root() / "downloads" / f"terraform-aws-{pin.provider_version}" / "mirror"
