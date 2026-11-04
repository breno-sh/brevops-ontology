"""Caminhos e leitura das entradas do HIST-OCI. Nenhuma versão é digitada aqui: a lista sai de
universe/history_versions.json (PINS, C13 3.1.0) e o pin, de universe/pins.json."""

from __future__ import annotations

import gzip
import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path

MODULE = "HIST-OCI"
PROVIDER = "oci"
ADDRESS = "registry.terraform.io/oracle/oci"
NAMESPACE, NAME = "oracle", "oci"
PLATFORM = "darwin_arm64"
#: impressão digital da chave primária com que a Oracle assina o SHA256SUMS do terraform-provider-oci.
#: Âncora de confiança: a chave pública vem do registro (dado baixado) e só vale se a assinatura conferir com
#: ESTA chave primária. É a mesma âncora do SCHEMA-OCI (pré-busca de 02/11, gpg-verify-status.txt).
ORACLE_FPR = "7F1079B5E6547DBFCCEFB9A41533A49284137CEB"
#: únicos prefixos aceitos para baixar (as URLs do registro são dado não confiável)
REGISTRY_PREFIX = f"https://registry.terraform.io/v1/providers/{NAMESPACE}/{NAME}/"
RELEASE_PREFIX = "https://github.com/oracle/terraform-provider-oci/releases/download/"


def bo_repo() -> Path:
    return Path(os.environ.get("BO_REPO") or Path(__file__).resolve().parents[3])


def bo_data() -> Path:
    return Path(os.environ.get("BO_DATA", "/Users/breno/doutorado/brevops-data"))


def bo_tmp() -> Path:
    return Path(os.environ.get("BO_TMP") or bo_data() / "tmp" / MODULE)


def out_dir() -> Path:
    return bo_data() / MODULE


def downloads() -> Path:
    """Pasta própria dos downloads do módulo (dado não confiável, com SOURCE.txt)."""
    return bo_data() / "downloads" / "hist-oci"


def version_dl(version: str) -> Path:
    """Metadado do registro, SHA256SUMS e assinatura de uma versão (pequenos; ficam)."""
    return downloads() / "release" / version


def zip_dir(version: str) -> Path:
    """Zip do binário assinado de uma versão (apagado depois de extrair)."""
    return downloads() / "zip" / version


def plugin_cache() -> Path:
    """Cache de plugin próprio (o binário desempacotado mora aqui só durante a extração)."""
    return downloads() / "plugin-cache"


def unpacked_dir(version: str) -> Path:
    return plugin_cache() / "registry.terraform.io" / NAMESPACE / NAME / version / PLATFORM


def tfschema_dir(version: str) -> Path:
    """Saída da bo.schema.extract para uma versão (schema.json.gz, sha256, recibo). Pasta própria, para não
    regravar o recibo que o SCHEMA-OCI lista no manifesto dele."""
    return downloads() / "tfschema" / f"{NAME}-{version}"


def atoms_path(version: str) -> Path:
    return out_dir() / f"atoms_{version}.jsonl.gz"


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


def gz_sha256(p: Path) -> str:
    """sha256 do conteúdo descomprimido."""
    h = hashlib.sha256()
    with gzip.open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def write_gz(src: Path, dest: Path, inner_name: str) -> None:
    """gzip determinístico (mtime 0, nome interno fixo, nível 9): mesma entrada, mesmos bytes."""
    tmp = dest.with_name(dest.name + ".part")
    with open(src, "rb") as fi, open(tmp, "wb") as fo:
        with gzip.GzipFile(filename=inner_name, mode="wb", fileobj=fo, mtime=0, compresslevel=9) as g:
            for chunk in iter(lambda: fi.read(1 << 20), b""):
                g.write(chunk)
    os.replace(tmp, dest)


def semver_key(v: str) -> tuple:
    core = v.split("-", 1)[0].split("+", 1)[0]
    return tuple(int(x) for x in core.split("."))


@dataclass(frozen=True)
class Listed:
    """Uma versão da lista histórica do PINS (versions_doc + selection)."""
    version: str
    released_at: str
    published_at: str
    reasons: tuple
    index_sha256: str
    protocols: tuple
    darwin_arm64: bool
    schema_sha256: str | None


@dataclass(frozen=True)
class History:
    source: str
    pin: str
    versions: tuple            # de Listed, na ordem do versions_doc
    left_truncation: dict
    window: dict
    cutoff: dict
    doc_sha256: str
    doc_path: str


def history_path() -> Path:
    return bo_repo() / "universe" / "history_versions.json"


def read_history(path: Path | None = None) -> History:
    p = path or history_path()
    doc = json.loads(Path(p).read_text(encoding="utf-8"))
    hits = [x for x in doc.get("providers", []) if x.get("provider") == PROVIDER]
    if len(hits) != 1:
        raise SystemExit(f"{MODULE}: history_versions.json com {len(hits)} entradas para {PROVIDER}")
    e = hits[0]
    if e["source"] != ADDRESS:
        raise SystemExit(f"{MODULE}: history_versions.json fixa {e['source']}, esperado {ADDRESS}")
    vd = e["versions_doc"]["versions"]
    sel = e["selection"]
    if [(v["version"], v["released_at"]) for v in vd] != [(s["version"], s["released_at"]) for s in sel]:
        raise SystemExit(f"{MODULE}: C13-HIST-SEL violada na entrada (versions_doc != selection)")
    out = []
    for v, s in zip(vd, sel):
        out.append(Listed(v["version"], v["released_at"], s["published_at"], tuple(s["reasons"]),
                          s["index_sha256"], tuple(s["protocols"]), bool(s["darwin_arm64"]),
                          v.get("schema_sha256")))
    return History(e["source"], e["pin"], tuple(out), dict(e["left_truncation"]), dict(doc["window"]),
                   dict(doc["cutoff"]), sha256_file(Path(p)), portable(p))


def read_pin(path: Path | None = None) -> dict:
    """Entrada do oci no pins.json (versão e schema_sha256 do pin) e a versão do terraform."""
    p = path or bo_repo() / "universe" / "pins.json"
    doc = json.loads(Path(p).read_text(encoding="utf-8"))
    hits = [x for x in doc.get("providers", []) if x.get("provider") == PROVIDER]
    if len(hits) != 1:
        raise SystemExit(f"{MODULE}: pins.json com {len(hits)} entradas para {PROVIDER}")
    return {**hits[0], "terraform_version": doc["terraform"]["version"]}
