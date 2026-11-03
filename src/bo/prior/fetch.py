"""Baixa (como dado, nunca executado) os artefatos fixados por commit em sources.MODELS.

  python -I -m bo.prior.fetch [MODEL ...]      baixa para $BO_DATA/downloads/prior-<model>/ e grava SOURCE.txt +
                                               fetch_manifest.json (sha256 de cada arquivo, URL, commit, hora)
  python -I -m bo.prior.fetch --check          confere offline os sha256 do fetch_manifest.json de cada modelo

Rede só aqui. Tarball é extraído só nos membros que casam com o padrão, com tarfile filter='data' (sem links,
sem caminho absoluto, sem '..'). A listagem de árvore usa a API do GitHub pelo `gh` já autenticado na máquina
(nenhum token é lido ou gravado por este código).
"""

from __future__ import annotations

import concurrent.futures as cf
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import tarfile
import time
import urllib.request
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from . import sources as S

TZ = ZoneInfo("America/Recife")
UA = "brevops-prior-fetch/1 (dados de pesquisa; leitura)"


def now() -> str:
    return datetime.now(TZ).replace(microsecond=0).isoformat()


def bo_data() -> Path:
    return Path(os.environ.get("BO_DATA") or "/Users/breno/doutorado/brevops-data")


def dl_root(model: str) -> Path:
    return bo_data() / "downloads" / f"prior-{model}"


def sha256(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def git_blob(b: bytes) -> str:
    return hashlib.sha1(b"blob %d\0" % len(b) + b).hexdigest()


def http_get(url: str, tries: int = 4) -> bytes:
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=120) as r:
                return r.read()
        except Exception as e:  # noqa: BLE001 - nova tentativa com espera
            last = e
            time.sleep(2 * (i + 1))
    raise RuntimeError(f"falhou {url}: {last}")


def gh_tree(repo: str, commit: str) -> list[dict]:
    out = subprocess.run(["gh", "api", f"repos/{repo}/git/trees/{commit}?recursive=1"], check=True,
                         capture_output=True, text=True).stdout
    d = json.loads(out)
    if d.get("truncated"):
        raise RuntimeError(f"árvore truncada em {repo}@{commit}")
    return [t for t in d["tree"] if t["type"] == "blob"]


def _raw(repo: str, commit: str, path: str) -> str:
    return f"https://raw.githubusercontent.com/{repo}/{commit}/{path}"


def _save(root: Path, rel: str, data: bytes) -> dict:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)
    return {"path": rel, "sha256": sha256(data), "git_blob": git_blob(data), "bytes": len(data)}


def fetch_spec(spec: dict, root: Path) -> list[dict]:
    repo, commit = spec["repo"], spec["commit"]
    base = repo.replace("/", "__")
    files = []
    if spec["kind"] in ("raw", "tree"):
        if spec["kind"] == "raw":
            paths = list(spec["paths"])
        else:
            tree = gh_tree(repo, commit)
            if "regex" in spec:
                rx = re.compile(spec["regex"])
                paths = [t["path"] for t in tree if rx.match(t["path"])]
            else:
                paths = [t["path"] for t in tree
                         if t["path"].startswith(spec["prefix"]) and t["path"].endswith(spec["suffix"])]
                paths += spec.get("extra", [])
        with cf.ThreadPoolExecutor(12) as ex:
            got = dict(zip(paths, ex.map(lambda p: http_get(_raw(repo, commit, p)), paths)))
        for p in sorted(got):
            rec = _save(root, f"{base}/{p}", got[p])
            rec.update({"url": _raw(repo, commit, p), "repo": repo, "commit": commit})
            files.append(rec)
    elif spec["kind"] == "tar":
        url = f"https://codeload.github.com/{repo}/tar.gz/{commit}"
        blob = http_get(url)
        rx = re.compile(spec["include"])
        with tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz") as tf:
            for m in tf.getmembers():
                if not m.isfile() or not rx.match(m.name):
                    continue
                inner = m.name.split("/", 1)[1]
                f = tf.extractfile(m)
                data = f.read() if f else b""
                rec = _save(root, f"{base}/{inner}", data)
                rec.update({"url": f"{url} :: {inner}", "repo": repo, "commit": commit})
                files.append(rec)
        files.append({"path": f"{base}.tar.gz (não guardado)", "sha256": sha256(blob), "bytes": len(blob),
                      "url": url, "repo": repo, "commit": commit, "archive": True})
    else:
        raise ValueError(spec["kind"])
    return files


def fetch(model: str) -> dict:
    m = S.MODELS[model]
    root = dl_root(model)
    if root.exists() and any(root.iterdir()):
        raise SystemExit(f"{root} já existe e não está vazia: download é único (apague só se for refazer de propósito)")
    root.mkdir(parents=True, exist_ok=True)
    started = now()
    files = []
    for spec in m["fetch"]:
        files += fetch_spec(spec, root)
    man = {"schema": "bo.prior.fetch/1", "model": model, "retrieved_started": started, "retrieved_at": now(),
           "license": m["license"], "repo": m.get("repo"), "commit": m.get("commit"), "files": files}
    (root / "fetch_manifest.json").write_text(json.dumps(man, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
                                              encoding="utf-8")
    lines = [f"PRIOR / {m['title']} (dado não confiável: só lido, nunca executado, compilado ou importado)",
             f"repo: {m.get('repo')}  licença: {m['license']}",
             f"commit: {m.get('commit')} ({m.get('commit_date')})",
             f"baixado: {started} .. {man['retrieved_at']} (America/Recife) por python -I -m bo.prior.fetch {model}",
             "sha256 de cada arquivo:"]
    lines += [f"{f['sha256']}  {f['path']}" for f in files]
    (root / "SOURCE.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[{now()}] {model}: {len([f for f in files if not f.get('archive')])} arquivo(s) em {root}")
    return man


def check() -> int:
    bad = 0
    for model in S.ORDER:
        if not S.MODELS[model]["fetch"]:
            continue
        root = dl_root(model)
        mf = root / "fetch_manifest.json"
        if not mf.is_file():
            print(f"FAIL {model}: {mf} ausente")
            bad += 1
            continue
        man = json.loads(mf.read_text(encoding="utf-8"))
        n = 0
        for f in man["files"]:
            if f.get("archive"):
                continue
            p = root / f["path"]
            if not p.is_file() or sha256(p.read_bytes()) != f["sha256"]:
                print(f"FAIL {model}: {f['path']} ausente ou com sha256 diferente")
                bad += 1
            n += 1
        print(f"OK   {model}: {n} arquivo(s) conferem com fetch_manifest.json")
    return 1 if bad else 0


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv[:1] == ["--check"]:
        return check()
    todo = argv or [m for m in S.ORDER if S.MODELS[m]["fetch"]]
    for m in todo:
        fetch(m)
    return 0


if __name__ == "__main__":
    sys.exit(main())
