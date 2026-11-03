"""Leitura do TerraDS sem extrair nada em disco: tar externo em fluxo, tar interno em memória, sqlite imutável."""

from __future__ import annotations

import io
import sqlite3
import tarfile

from .common import SQLITE, TAR

TF_SUFFIXES = (".tf", ".tf.json")


def iter_repos(tar_path=TAR, limit: int | None = None, only: set | None = None):
    """(terrads_id, bytes do tar.gz interno), na ordem do arquivo."""
    n = 0
    with tarfile.open(tar_path, "r:gz") as outer:
        for m in outer:
            if not m.isfile() or not m.name.endswith(".tar.gz"):
                continue
            tid = m.name[:-7].split("/")[-1]
            if only is not None and tid not in only:
                continue
            yield tid, outer.extractfile(m).read()
            n += 1
            if limit is not None and n >= limit:
                return


def repo_files(tid: str, data: bytes) -> tuple[list, int]:
    """Arquivos .tf/.tf.json do repositório: [(caminho relativo, bytes)] ordenado; e o nº de outros arquivos."""
    out, other = [], 0
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as inner:
        for im in inner:
            if not im.isfile():
                continue
            name = im.name
            pre = tid + "/"
            rel = name[len(pre):] if name.startswith(pre) else name
            if rel.endswith(TF_SUFFIXES):
                out.append((rel, inner.extractfile(im).read()))
            else:
                other += 1
    out.sort(key=lambda x: x[0])
    return out, other


def sqlite_conn() -> sqlite3.Connection:
    """Somente leitura e imutável: não cria -wal/-shm nem toca no arquivo."""
    return sqlite3.connect(f"file:{SQLITE}?mode=ro&immutable=1", uri=True)
