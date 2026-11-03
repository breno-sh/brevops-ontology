"""Harness OCI (HARNESS-OCI): renderizador de HCL a partir de um plano de lowering (C26) e executor
apply -> espera -> leitura -> destroy, com o redator antes de qualquer gravação.

Regras que o pacote inteiro segue:
  - o renderizador NÃO insere nada: cada atributo do HCL vem de um valor do plano (carried, synthesized ou
    default_declared, os dois últimos marcados) ou de um binding de contexto declarado; o resto do HCL é
    encanamento fixo do molde (terraform, provider, variable, module), conferido pelo no_silent_insert;
  - campo obrigatório do schema do provider fixado que o plano não traz faz o caso falhar como UNKNOWN_INPUT
    (nenhum default inventado);
  - diretório de trabalho só dentro de $BO_TMP, exclusivo por execução; nunca /tmp;
  - nesta fase só há execução offline com respostas gravadas (sintéticas); o executor ao vivo recusa rodar sem o
    kit de segurança (SAFETY) e sem GO.
"""

from __future__ import annotations

import os
from pathlib import Path

MODULE_ID = "HARNESS-OCI"
PROVIDER = "oci"
PROVIDER_SOURCE = "oracle/oci"
PROVIDER_REGISTRY_SOURCE = "registry.terraform.io/oracle/oci"
PROVIDER_VERSION = "9.11.0"
TERRAFORM_VERSION = "1.15.8"
# sha256 dos bytes de `terraform providers schema -json` do oci 9.11.0 (igual ao schema_sha256 de universe/pins.json)
SCHEMA_SHA256 = "ae0101e5473f7adfd65993dfc335c99285df2bc88ed97fe74c712fb704f55237"

PKG_DIR = Path(__file__).resolve().parent
DATA_DIR = PKG_DIR / "data"
SCHEMA_TABLE = DATA_DIR / f"oci-{PROVIDER_VERSION}.schema_table.jsonl"


def repo_root() -> Path:
    """Raiz do repositório: $BO_REPO se definido, senão a que contém este pacote."""
    env = os.environ.get("BO_REPO")
    if env:
        return Path(env)
    return PKG_DIR.parents[3]


def data_root() -> Path:
    return Path(os.environ.get("BO_DATA") or "/Users/breno/doutorado/brevops-data")


def tmp_root() -> Path:
    """$BO_TMP do módulo (exclusivo). Sem a variável, o padrão do C00: $BO_DATA/tmp/HARNESS-OCI."""
    env = os.environ.get("BO_TMP")
    return Path(env) if env else data_root() / "tmp" / MODULE_ID


def module_data() -> Path:
    return data_root() / MODULE_ID


def templates_dir() -> Path:
    return repo_root() / "deploy" / "fixtures" / "oci" / "_templates"


def raw_schema_path() -> Path:
    return data_root() / "downloads" / f"registry-oci-{PROVIDER_VERSION}" / "schema.json.gz"


def plugin_cache() -> Path:
    return data_root() / "downloads" / f"registry-oci-{PROVIDER_VERSION}" / "plugin-cache"
