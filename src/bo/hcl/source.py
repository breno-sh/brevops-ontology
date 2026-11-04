"""Leitura do TerraDS sem extrair nada em disco: tar externo em fluxo, tar interno em memória, sqlite imutável."""

from __future__ import annotations

import io
import posixpath
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


def repo_files(tid: str, data: bytes, stats=None) -> tuple[list, int]:
    """Arquivos .tf/.tf.json do repositório: [(caminho relativo, bytes)] ordenado; e o nº de outros arquivos.

    Link simbólico .tf (comum: network.tf -> ../../shared/network.tf) é lido como o Terraform leria: com o
    conteúdo do alvo, no caminho do link, se o alvo é arquivo do mesmo repositório (cadeia de até 8 links).
    Link para fora do repositório ou para alvo ausente não é lido e é contado (symlink_unresolved)."""
    out, other = [], 0
    pre = tid + "/"
    regular, links = {}, {}
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as inner:
        for im in inner:
            rel = im.name[len(pre):] if im.name.startswith(pre) else im.name
            if im.isfile():
                if rel.endswith(TF_SUFFIXES):
                    regular[rel] = inner.extractfile(im).read()
                else:
                    other += 1
            elif im.issym() and rel.endswith(TF_SUFFIXES):
                links[rel] = im.linkname
    for rel, target in links.items():
        cur, tgt, ok = rel, target, False
        for _ in range(8):
            if tgt.startswith("/"):
                break
            p = posixpath.normpath(posixpath.join(posixpath.dirname(cur), tgt))
            if p.startswith("..") or p == ".":
                break
            if p in regular:
                regular_target = regular[p]
                ok = True
                break
            if p in links:
                cur, tgt = p, links[p]
                continue
            break
        if ok:
            out.append((rel, regular_target))
            if stats is not None:
                stats["symlink_resolved"] += 1
        elif stats is not None:
            stats["symlink_unresolved"] += 1
    out.extend(regular.items())
    out.sort(key=lambda x: x[0])
    return out, other


def sqlite_conn() -> sqlite3.Connection:
    """Somente leitura e imutável: não cria -wal/-shm nem toca no arquivo."""
    return sqlite3.connect(f"file:{SQLITE}?mode=ro&immutable=1", uri=True)
