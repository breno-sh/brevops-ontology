"""Fonte fixada do Apache Libcloud: download como dado não confiável, conferência de hash e extração segura.

O pacote nunca é importado nem executado: o tar.gz é baixado para $BO_DATA/downloads/libcloud/, conferido
contra o sha256 publicado pelo PyPI, e extraído com tarfile filter='data' (sem links para fora, sem
permissões especiais). Daí em diante só o ast lê os .py.
"""

from __future__ import annotations

import hashlib
import os
import tarfile
import urllib.request
from pathlib import Path

VERSION = "3.9.1"
SDIST = f"apache_libcloud-{VERSION}.tar.gz"
URL = f"https://files.pythonhosted.org/packages/source/a/apache_libcloud/{SDIST}"
PYPI_JSON = "https://pypi.org/pypi/apache-libcloud/json"
SHA256 = "b65eaa5ac32b28a0f9555e6a223dba39e73b99b682cd849624587ce7bc251661"
SIZE = 2582796
UPLOADED = "2026-04-21T07:09:45Z"   # upload_time do sdist no PyPI
LICENSE = "Apache-2.0"
LICENSE_URI = "https://www.apache.org/licenses/LICENSE-2.0"
TREE = f"apache_libcloud-{VERSION}"


def bo_data() -> Path:
    return Path(os.environ.get("BO_DATA", "/Users/breno/doutorado/brevops-data"))


def download_dir() -> Path:
    return bo_data() / "downloads" / "libcloud"


def sdist_path() -> Path:
    return download_dir() / SDIST


def tree_root() -> Path:
    return download_dir() / "extracted" / TREE


def pkg_root() -> Path:
    return tree_root() / "libcloud"


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def tree_digest(root: Path) -> str:
    """sha256 do conjunto (caminho relativo, sha256) de todos os .py da árvore extraída."""
    h = hashlib.sha256()
    for p in sorted(root.rglob("*.py")):
        h.update(f"{p.relative_to(root).as_posix()}\0{sha256_file(p)}\n".encode())
    return h.hexdigest()


class SourceError(Exception):
    pass


def verify() -> dict:
    """Confere o tar.gz contra o pin e a árvore extraída contra o tar.gz (mesmo conteúdo .py)."""
    sd = sdist_path()
    if not sd.is_file():
        raise SourceError(f"{sd} ausente: rode python -I -m bo.gold_libcloud.build --fetch")
    got = sha256_file(sd)
    if got != SHA256:
        raise SourceError(f"sha256 do {SDIST} = {got[:16]}..., pin = {SHA256[:16]}...")
    root = tree_root()
    if not root.is_dir():
        raise SourceError(f"{root} ausente: rode python -I -m bo.gold_libcloud.build --fetch")
    with tarfile.open(sd) as t:
        members = {m.name: m for m in t.getmembers() if m.isfile() and m.name.endswith(".py")}
        for name, m in members.items():
            p = root.parent / name
            if not p.is_file():
                raise SourceError(f"extração incompleta: falta {name}")
            f = t.extractfile(m)
            if hashlib.sha256(f.read()).hexdigest() != sha256_file(p):
                raise SourceError(f"extração diverge do tar.gz em {name}")
    return {"sdist": str(sd), "sha256": got, "py_files": len(members), "tree_digest": tree_digest(root)}


def fetch() -> dict:
    d = download_dir()
    d.mkdir(parents=True, exist_ok=True)
    sd = sdist_path()
    if not sd.is_file() or sha256_file(sd) != SHA256:
        tmp = sd.with_suffix(".part")
        with urllib.request.urlopen(URL, timeout=120) as r, open(tmp, "wb") as f:
            f.write(r.read())
        if sha256_file(tmp) != SHA256:
            tmp.unlink()
            raise SourceError("download não confere com o sha256 fixado")
        tmp.replace(sd)
    root = tree_root()
    if not root.is_dir():
        with tarfile.open(sd) as t:
            t.extractall(d / "extracted", filter="data")
    write_source_txt()
    return verify()


def write_source_txt() -> Path:
    p = download_dir() / "SOURCE.txt"
    p.write_text(
        "Fonte: Apache Libcloud (dado não confiável; nunca importado nem executado)\n"
        f"Versão: {VERSION}\n"
        f"URL: {URL}\n"
        f"Índice: {PYPI_JSON} (sha256 e tamanho publicados pelo PyPI)\n"
        f"Arquivo: {SDIST}\n"
        f"sha256: {SHA256}\n"
        f"Tamanho: {SIZE} bytes\n"
        f"Publicado no PyPI: {UPLOADED}\n"
        f"Licença: {LICENSE} ({LICENSE_URI}); NOTICE e LICENSE dentro de extracted/{TREE}/\n"
        f"Extraído em: extracted/{TREE}/ com tarfile filter='data'\n"
        "Uso: leitura com ast pelo bo.gold_libcloud (módulo GOLD-LIBCLOUD)\n",
        encoding="utf-8")
    return p
