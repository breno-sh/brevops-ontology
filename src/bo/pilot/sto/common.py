"""Caminhos, hora (America/Recife), leitura/escrita canônica e a definição da fatia sto do PILOT-STO-E2E.

Semente das bibliotecas de escala: nada aqui conhece o oráculo; o oráculo só é carregado por bo.pilot.sto.oracle_io,
e só na avaliação. Todo dado gerado vai para $BO_DATA/PILOT-STO-E2E/ (staging dentro dele, trocado sob trava) ou
para $BO_TMP; resultados públicos para $BO_REPO/results/PILOT-STO-E2E/.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
from pathlib import Path
from zoneinfo import ZoneInfo

MODULE = "PILOT-STO-E2E"
SLICE_ID = "sto"
TZ = ZoneInfo("America/Recife")
MODEL_ID = "claude-opus-5-5"
PROVIDERS = ("aws", "google", "azurerm", "oci")
PAIR_CODE = {"aws": "AWS", "google": "GCP", "azurerm": "AZ", "oci": "OCI"}
SCHEMA_DIR = {"aws": "SCHEMA-AWS", "google": "SCHEMA-GCP", "azurerm": "SCHEMA-AZURE", "oci": "SCHEMA-OCI"}
CONTROLS = ("c1_table", "c2_taxonomy", "c3_full")
CONTROL_CODE = {"c1_table": "c1", "c2_taxonomy": "c2", "c3_full": "c3"}
DIRECTIONS = tuple(f"{a}->{b}" for a in PROVIDERS for b in PROVIDERS if a != b)

# Tipos Terraform da fatia (mesma embalagem do PILOT-STO-GLOSS; é a lista de tipos, não decisão de grão).
SLICE_TYPES = {
    "aws": ("aws_s3_bucket", "aws_s3_bucket_versioning", "aws_s3_bucket_lifecycle_configuration",
            "aws_s3_bucket_server_side_encryption_configuration", "aws_s3_bucket_public_access_block",
            "aws_s3_account_public_access_block", "aws_s3_bucket_acl", "aws_s3_bucket_policy",
            "aws_s3_bucket_ownership_controls"),
    "google": ("google_storage_bucket", "google_storage_bucket_acl", "google_storage_bucket_access_control",
               "google_storage_bucket_iam_policy", "google_storage_bucket_iam_binding", "google_storage_bucket_iam_member"),
    "azurerm": ("azurerm_storage_account", "azurerm_storage_container", "azurerm_storage_management_policy",
                "azurerm_storage_account_customer_managed_key", "azurerm_storage_encryption_scope"),
    "oci": ("oci_objectstorage_bucket", "oci_objectstorage_object_lifecycle_policy", "oci_objectstorage_namespace_metadata"),
}
META_ARGS = ("depends_on", "count", "for_each", "lifecycle", "provider", "provisioner", "connection")


def repo() -> Path:
    env = os.environ.get("BO_REPO")
    if env:
        return Path(env)
    return Path(__file__).resolve().parents[4]


def data_root() -> Path:
    return Path(os.environ.get("BO_DATA", "/Users/breno/doutorado/brevops-data"))


def data_dir() -> Path:
    return data_root() / MODULE


def tmp_dir() -> Path:
    p = Path(os.environ.get("BO_TMP") or (data_root() / "tmp" / MODULE))
    p.mkdir(parents=True, exist_ok=True)
    return p


def results_dir() -> Path:
    return repo() / "results" / MODULE


def map_dir() -> Path:
    """Saídas do PILOT-STO-MAP. BO_STO_MAP_DIR só existe para desenvolver contra o staging antes do merge."""
    return Path(os.environ.get("BO_STO_MAP_DIR") or (data_root() / "PILOT-STO-MAP"))


def oracle_dir() -> Path:
    return repo() / "pilot" / "sto" / "oracle"


def fixtures_calib_dir() -> Path:
    return repo() / "pilot" / "sto" / "fixtures_calib"


def portable(p: Path | str) -> str:
    s = str(p)
    for var, root in (("$BO_REPO", str(repo())), ("$BO_DATA", str(data_root()))):
        if s == root or s.startswith(root + "/"):
            return var + s[len(root):]
    return s


def now() -> str:
    return _dt.datetime.now(TZ).isoformat(timespec="seconds")


def canon(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def sha256_text(s: str) -> str:
    return sha256_bytes(s.encode("utf-8"))


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_obj(obj) -> str:
    return sha256_text(canon(obj))


def iter_jsonl(p: Path):
    with open(p, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                yield json.loads(line)


def read_json(p: Path):
    with open(p, encoding="utf-8") as fh:
        return json.load(fh)


def write_json(p: Path, obj) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")


def write_result(p: Path, obj) -> bool:
    """Grava um resultado só se o conteúdo (sem generated_at) mudou: rodar o gate de novo não suja a worktree."""
    if p.exists():
        try:
            old = read_json(p)
        except ValueError:
            old = None
        if isinstance(old, dict) and {k: v for k, v in old.items() if k != "generated_at"} == \
                {k: v for k, v in obj.items() if k != "generated_at"}:
            return False
    write_json(p, obj)
    return True


def write_jsonl(p: Path, rows) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(canon(r) + "\n")


def short_id(*parts) -> str:
    """Id curto e estável (hex) para símbolos e nomes derivados; nunca a partir de dado real."""
    return sha256_text("|".join(str(p) for p in parts))[:16]


def provider_of_atom(atom_id: str) -> str:
    return atom_id.split(":", 1)[0]


def type_of_atom(atom_id: str) -> str:
    return atom_id.split(":", 2)[1]


def path_of_atom(atom_id: str) -> str:
    return atom_id.split(":", 2)[2]


def pair_key(a: str, b: str) -> str:
    return PAIR_CODE[a] + PAIR_CODE[b]
