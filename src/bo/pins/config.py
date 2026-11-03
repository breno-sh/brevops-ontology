"""Parâmetros fixos do PINS: providers, data de corte, janela histórica, pin do Terraform e caminhos."""

from __future__ import annotations

import datetime as _dt
import os
from pathlib import Path
from zoneinfo import ZoneInfo

TZ = ZoneInfo("America/Recife")
UTC = _dt.timezone.utc

MODULE = "PINS"

# provider -> (namespace, tipo) no Terraform Registry
PROVIDERS: dict[str, tuple[str, str]] = {
    "aws": ("hashicorp", "aws"),
    "google": ("hashicorp", "google"),
    "azurerm": ("hashicorp", "azurerm"),
    "oci": ("oracle", "oci"),
}

# Data de corte única (America/Recife, inclusiva): a versão estável de cada provider é a maior versão semver
# sem sufixo de pré-lançamento publicada até 23:59:59 deste dia. É o dia das decisões D1/D6 e da pré-busca.
CUTOFF_DATE = _dt.date(2026, 11, 2)

# Janela histórica: truncamento à esquerda declarado em 01/01/2021 (início do 1º trimestre amostrado).
HISTORY_START = _dt.date(2021, 1, 1)

# Terraform CLI: ferramenta de extração, fixada no que o ambiente já usa (mise global) e que gerou os schemas da
# pré-busca. Não é "a estável no corte" — essa é registrada à parte em selection.json, com o motivo.
TERRAFORM_VERSION = "1.15.8"
TERRAFORM_PLATFORM = ("darwin", "arm64")

REGISTRY = "https://registry.terraform.io"
RELEASES_API = "https://api.releases.hashicorp.com/v1/releases"
RELEASES = "https://releases.hashicorp.com"


def cutoff_end() -> _dt.datetime:
    """Primeiro instante depois da data de corte (exclusivo), em America/Recife."""
    d = CUTOFF_DATE + _dt.timedelta(days=1)
    return _dt.datetime(d.year, d.month, d.day, tzinfo=TZ)


def day_start(d: _dt.date) -> _dt.datetime:
    return _dt.datetime(d.year, d.month, d.day, tzinfo=TZ)


def bo_repo() -> Path:
    v = os.environ.get("BO_REPO")
    return Path(v) if v else Path(__file__).resolve().parents[3]


def bo_data() -> Path:
    return Path(os.environ.get("BO_DATA") or "/Users/breno/doutorado/brevops-data")


def bo_tmp() -> Path:
    p = Path(os.environ.get("BO_TMP") or (bo_data() / "tmp" / MODULE))
    p.mkdir(parents=True, exist_ok=True)
    return p


def index_dir() -> Path:
    return bo_data() / MODULE / "registry_index"


def prefetch_dir() -> Path:
    return bo_data() / "downloads" / "prefetch"


def pins_path() -> Path:
    return bo_repo() / "universe" / "pins.json"


def history_path() -> Path:
    return bo_repo() / "universe" / "history_versions.json"


def results_dir() -> Path:
    return bo_repo() / "results" / MODULE


def legacy_versions_tf() -> Path:
    return Path("/Users/breno/doutorado/pesquisa-lanes/c1-37-icsa/superficie/data/tfschema4/versions.tf")


def now_iso() -> str:
    return _dt.datetime.now(TZ).replace(microsecond=0).isoformat()
