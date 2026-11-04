"""Caminhos e leitura das entradas do HIST-AWS. Nenhuma versão é digitada aqui: a lista sai de
universe/history_versions.json (PINS, C13 3.1.0) e o pin de universe/pins.json."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path

MODULE = "HIST-AWS"
PROVIDER = "aws"
ADDRESS = "registry.terraform.io/hashicorp/aws"
SOURCE = "hashicorp/aws"
NAME = "aws"
#: impressão digital da chave primária de assinatura da HashiCorp (âncora de confiança: a chave pública em si
#: vem do registro, que é dado baixado e por isso não basta sozinha)
HASHICORP_FPR = "C874011F0AB405110D02105534365D9472D7468F"
PLATFORM = "darwin_arm64"
REGISTRY = "https://registry.terraform.io"
RELEASES = "https://releases.hashicorp.com"


def bo_repo() -> Path:
    return Path(os.environ.get("BO_REPO") or Path(__file__).resolve().parents[3])


def bo_data() -> Path:
    return Path(os.environ.get("BO_DATA", "/Users/breno/doutorado/brevops-data"))


def bo_tmp() -> Path:
    return Path(os.environ.get("BO_TMP") or bo_data() / "tmp" / MODULE)


def out_dir() -> Path:
    """$BO_DATA/HIST-AWS: átomos por versão, schemas extraídos, versions.json, relatório e manifesto."""
    return bo_data() / MODULE


def schema_root() -> Path:
    """Schemas extraídos: texto do fornecedor (descrições com exemplos de ARN, de conta e de user_data), ou seja,
    dado não confiável derivado do download; fica na pasta de downloads do módulo, como o downloads/tfschema/ da
    SCHEMALIB, e não em $BO_DATA/HIST-AWS. O MANIFEST.sha256 do módulo lista cada arquivo pelo caminho portátil."""
    return bo_data() / "downloads" / "hist-aws" / "tfschema"


def schema_dir(version: str, root: Path | None = None) -> Path:
    """Saída do bo.schema.extract para uma versão (schema.json.gz, schema.json.sha256, receipt.json, SOURCE.txt,
    trust.json)."""
    return (root or schema_root()) / f"{NAME}-{version}"


def atoms_path(version: str) -> Path:
    return out_dir() / f"atoms_{version}.jsonl.gz"


def download_dir(version: str) -> Path:
    """Download não confiável (metadado do registro, SHA256SUMS, assinatura e, transitoriamente, o zip)."""
    return bo_data() / "downloads" / "hist-aws" / version


def prefetch_dir(version: str) -> Path:
    return bo_data() / "downloads" / "prefetch" / PROVIDER / version


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


def history_path() -> Path:
    return bo_repo() / "universe" / "history_versions.json"


def pins_path() -> Path:
    return bo_repo() / "universe" / "pins.json"


@dataclass(frozen=True)
class Listed:
    version: str
    released_at: str
    published_at: str
    reasons: tuple
    protocols: tuple
    darwin_arm64: bool


@dataclass(frozen=True)
class History:
    pin: str
    pin_schema_sha256: str | None
    versions: tuple            # Listed, na ordem do versions_doc
    versions_doc: dict
    left_truncation: dict


def read_history(path: Path | None = None) -> History:
    """A entrada aws do history_versions.json, com a seleção casada ao versions_doc (C13-HIST-SEL)."""
    doc = json.loads(Path(path or history_path()).read_text(encoding="utf-8"))
    hits = [p for p in doc.get("providers", []) if p.get("provider") == PROVIDER]
    if len(hits) != 1:
        raise SystemExit(f"{MODULE}: history_versions.json com {len(hits)} entradas para {PROVIDER}")
    e = hits[0]
    if e["source"] != ADDRESS:
        raise SystemExit(f"{MODULE}: history_versions fixa {e['source']}, esperado {ADDRESS}")
    vd = e["versions_doc"]["versions"]
    sel = {s["version"]: s for s in e["selection"]}
    if [v["version"] for v in vd] != [s["version"] for s in e["selection"]]:
        raise SystemExit(f"{MODULE}: selection e versions_doc divergem (C13-HIST-SEL)")
    out = []
    for v in vd:
        s = sel[v["version"]]
        if s["released_at"] != v["released_at"]:
            raise SystemExit(f"{MODULE}: released_at de {v['version']} diverge entre selection e versions_doc")
        out.append(Listed(v["version"], v["released_at"], s["published_at"], tuple(s["reasons"]),
                          tuple(s["protocols"]), bool(s["darwin_arm64"])))
    pin_sha = next((v.get("schema_sha256") for v in vd if v["version"] == e["pin"]), None)
    return History(e["pin"], pin_sha, tuple(out), e["versions_doc"], e["left_truncation"])


@dataclass(frozen=True)
class Pins:
    terraform_version: str
    terraform_sha256: str
    version: str
    shasums_sha256: str
    schema_sha256: str


def read_pins(path: Path | None = None) -> Pins:
    doc = json.loads(Path(path or pins_path()).read_text(encoding="utf-8"))
    hits = [x for x in doc.get("providers", []) if x.get("provider") == PROVIDER]
    if len(hits) != 1:
        raise SystemExit(f"{MODULE}: pins.json com {len(hits)} entradas para {PROVIDER}")
    e = hits[0]
    return Pins(doc["terraform"]["version"], doc["terraform"]["sha256"], e["version"], e["shasums_sha256"],
                e["schema_sha256"])


def semver_key(v: str) -> tuple:
    core = v.split("-", 1)[0].split("+", 1)[0]
    return tuple(int(x) for x in core.split("."))
