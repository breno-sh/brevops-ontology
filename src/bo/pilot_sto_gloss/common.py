"""Caminhos, hora (America/Recife), leitura e a definição da fatia sto do PILOT-STO-GLOSS."""

from __future__ import annotations

import datetime as _dt
import json
import os
from pathlib import Path
from zoneinfo import ZoneInfo

MODULE = "PILOT-STO-GLOSS"
TZ = ZoneInfo("America/Recife")
MODEL_ID = "claude-opus-5-5"

# Fatia sto (§3b do plano): contêiner de objetos e as facetas de versionamento, ciclo de vida, criptografia e
# acesso público (conta, contêiner, política e ACL). Cada tipo Terraform entra com o motivo; o que ficou de fora
# está em EXCLUDED, também com o motivo. A lista é a embalagem Terraform da fatia, não uma decisão de grão.
SLICE: dict[str, dict[str, str]] = {
    "aws": {
        "aws_s3_bucket": "contêiner (com blocos embutidos legados das facetas)",
        "aws_s3_bucket_versioning": "versionamento como recurso separado",
        "aws_s3_bucket_lifecycle_configuration": "ciclo de vida como recurso separado",
        "aws_s3_bucket_server_side_encryption_configuration": "criptografia como recurso separado",
        "aws_s3_bucket_public_access_block": "acesso público, nível do contêiner",
        "aws_s3_account_public_access_block": "acesso público, nível da conta",
        "aws_s3_bucket_acl": "acesso público por ACL",
        "aws_s3_bucket_policy": "acesso público por política",
        "aws_s3_bucket_ownership_controls": "decide se a ACL tem efeito (acesso público efetivo)",
    },
    "google": {
        "google_storage_bucket": "contêiner (facetas embutidas em blocos e atributos)",
        "google_storage_bucket_acl": "acesso público por ACL",
        "google_storage_bucket_access_control": "acesso público por entrada de ACL",
        "google_storage_bucket_iam_policy": "acesso público por política",
        "google_storage_bucket_iam_binding": "acesso público por política (vínculo por papel)",
        "google_storage_bucket_iam_member": "acesso público por política (membro)",
    },
    "azurerm": {
        "azurerm_storage_account": "conta de armazenamento (dona de versionamento, criptografia e acesso aninhado)",
        "azurerm_storage_container": "contêiner de blobs",
        "azurerm_storage_management_policy": "ciclo de vida da conta",
        "azurerm_storage_account_customer_managed_key": "criptografia com chave do cliente",
        "azurerm_storage_encryption_scope": "criptografia por escopo",
    },
    "oci": {
        "oci_objectstorage_bucket": "contêiner (versionamento, acesso público e chave embutidos)",
        "oci_objectstorage_object_lifecycle_policy": "ciclo de vida como recurso separado",
        "oci_objectstorage_namespace_metadata": "padrões do namespace (nível acima do contêiner)",
    },
}

EXCLUDED: dict[str, str] = {
    "aws_s3_object": "objeto: conteúdo é Withheld",
    "aws_s3_bucket_object": "objeto: conteúdo é Withheld",
    "aws_s3_object_copy": "objeto: conteúdo é Withheld",
    "google_storage_bucket_object": "objeto: conteúdo é Withheld",
    "azurerm_storage_blob": "objeto: conteúdo é Withheld",
    "oci_objectstorage_object": "objeto: conteúdo é Withheld",
    "aws_s3_bucket_replication_configuration": "replicação: fora das quatro facetas",
    "oci_objectstorage_replication_policy": "replicação: fora das quatro facetas",
    "azurerm_storage_object_replication": "replicação: fora das quatro facetas",
    "azurerm_storage_account_network_rules": "acesso de rede, não acesso público ao conteúdo",
    "oci_objectstorage_private_endpoint": "acesso de rede, não acesso público ao conteúdo",
    "oci_objectstorage_preauthrequest": "delegação temporária de acesso, não configuração do contêiner",
    "azurerm_storage_container_immutability_policy": "retenção imutável: fora das quatro facetas",
    "aws_s3_bucket_object_lock_configuration": "retenção imutável: fora das quatro facetas",
}


def repo() -> Path:
    env = os.environ.get("BO_REPO")
    return Path(env) if env else Path(__file__).resolve().parents[3]


def data_root() -> Path:
    return Path(os.environ.get("BO_DATA", "/Users/breno/doutorado/brevops-data"))


def data_dir() -> Path:
    return data_root() / MODULE


def results_dir() -> Path:
    return repo() / "results" / MODULE


def now() -> str:
    return _dt.datetime.now(TZ).replace(microsecond=0).isoformat()


def slice_types() -> dict[str, str]:
    """tipo Terraform -> provedor."""
    return {t: p for p, ts in SLICE.items() for t in ts}


def load_jsonl(path) -> list[dict]:
    out = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def iter_jsonl(path):
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                yield json.loads(line)


def dump_json(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=1, sort_keys=True) + "\n"


def atom_type(atom_id: str) -> str:
    return atom_id.split(":", 2)[1]


def slice_roles(path=None) -> dict[str, dict]:
    """atom_id -> registro C04 dos átomos da fatia (ROLES)."""
    st = slice_types()
    p = Path(path) if path else data_root() / "ROLES" / "roles.jsonl"
    return {r["atom_id"]: r for r in iter_jsonl(p) if atom_type(r["atom_id"]) in st}


def slice_evidence(path=None) -> list[dict]:
    """registros C25 (SERVICE-EVIDENCE) dos tipos da fatia."""
    st = slice_types()
    p = Path(path) if path else data_root() / "SERVICE-EVIDENCE" / "service_evidence.jsonl"
    return [r for r in iter_jsonl(p) if r.get("terraform_resource_type") in st]
