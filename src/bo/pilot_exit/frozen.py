"""Código congelado do E2E: de onde vem, que sha tem e a cópia em $BO_TMP que o avaliador executa.

Regra V1 do VALIDATOR_BRIEF: o sha do código avaliado tem de ser o sha registrado pelo produtor. Aqui:
  (a) o commit de entrega é o último commit '[<E2E>] ...' alcançável de bo/base;
  (b) o código do E2E (src/bo/pilot/<fatia>/ e src/bo/pilot_<fatia>_e2e/) em bo/base é idêntico ao do commit de
      entrega (ninguém mexeu depois);
  (c) se o E2E registrou hashes do próprio código (MANIFEST.sha256 ou summary.json), eles batem com a cópia.
Diferente em qualquer um: o avaliador para e relata; não avalia código diferente do congelado.
"""
from __future__ import annotations

import io
import re
import subprocess
import tarfile
from pathlib import Path

from . import common as C


class FrozenError(RuntimeError):
    pass


def git(root: Path, *args, binary: bool = False):
    r = subprocess.run(["git", "-C", str(root), *args], capture_output=True)
    if r.returncode != 0:
        raise FrozenError(f"git {' '.join(args[:3])}: {r.stderr.decode(errors='replace')[-200:]}")
    return r.stdout if binary else r.stdout.decode()


def delivery_commits(root: Path, mid: str, base: str = "bo/base") -> list[dict]:
    out = git(root, "log", "--format=%H%x09%cI%x09%s", base)
    tag = f"[{mid}]"
    rows = []
    for line in out.splitlines():
        h, at, subj = line.split("\t", 2)
        if subj.startswith(tag):
            rows.append({"commit": h, "at": at, "subject": subj})
    return rows


def tree_files(root: Path, commit: str, paths: list[str]) -> dict[str, str]:
    """{caminho: sha256 do conteúdo} dos arquivos sob 'paths' no commit (sem __pycache__)."""
    data = git(root, "archive", "--format=tar", commit, "--", *paths, binary=True) if _exists(root, commit, paths) else b""
    files = {}
    if data:
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:") as tf:
            for m in tf.getmembers():
                if m.isfile() and "__pycache__" not in m.name and not m.name.endswith(".pyc"):
                    files[m.name] = C.sha_bytes(tf.extractfile(m).read())
    return files


def _exists(root: Path, commit: str, paths: list[str]) -> bool:
    out = git(root, "ls-tree", "--name-only", commit, "--", *[p.rstrip("/") for p in paths])
    return bool(out.strip())


def digest(files: dict[str, str]) -> str:
    return C.sha_bytes("".join(f"{h}  {p}\n" for p, h in sorted(files.items())).encode())


def recorded_hashes(root: Path, mid: str, code_paths: list[str]) -> dict:
    """Hashes que o próprio E2E registrou do seu código: linhas do MANIFEST.sha256 sob os caminhos de código e
    parâmetros do summary.json cujo nome fala de sha de código."""
    res = root / "results" / mid
    files = {}
    mf = res / "MANIFEST.sha256"
    if mf.is_file():
        for line in mf.read_text(encoding="utf-8").splitlines():
            m = re.match(r"^([0-9a-f]{64})\s+\*?(.+)$", line.strip())
            if not m:
                continue
            p = m.group(2).replace("$BO_REPO/", "")
            if any(p.startswith(cp) for cp in code_paths):
                files[p] = m.group(1)
    params = {}
    s = C.read_json(res / "summary.json") or {}
    for k, v in ((s.get("agent_provenance") or {}).get("params") or {}).items():
        if re.search(r"code", k, re.I) and re.search(r"sha|digest|hash", k, re.I):
            params[k] = v
    return {"manifest_files": files, "params": params}


def identify(slice_: str, root: Path | None = None, base: str = "bo/base") -> dict:
    root = root or C.repo()
    s = C.SLICES[slice_]
    mid = s["e2e"]
    commits = delivery_commits(root, mid, base)
    if not commits:
        raise FrozenError(f"{mid} ainda não está em {base} (nenhum commit [{mid}])")
    last = commits[0]
    head = git(root, "rev-parse", base).strip()
    at_delivery = tree_files(root, last["commit"], s["code"])
    at_head = tree_files(root, head, s["code"])
    if not at_delivery:
        raise FrozenError(f"{mid}: o commit de entrega não tem código em {s['code']}")
    problems = []
    if at_delivery != at_head:
        changed = sorted(set(at_delivery.items()) ^ set(at_head.items()))
        problems.append(f"código do {mid} mudou depois da entrega ({len(changed)} diferença(s))")
    rec = recorded_hashes(root, mid, s["code"])
    for p, h in sorted(rec["manifest_files"].items()):
        if at_head.get(p) != h:
            problems.append(f"MANIFEST do {mid} registra {p} com outro sha")
    code_sha = digest(at_head)
    for k, v in rec["params"].items():
        if isinstance(v, str) and re.fullmatch(r"[0-9a-f]{64}", v) and v not in (code_sha, digest(at_delivery)):
            problems.append(f"summary.json do {mid}: {k} ≠ sha do código congelado")
    return {"slice": slice_, "module": mid, "base_head": head, "delivery_commit": last["commit"],
            "delivery_at": last["at"], "n_delivery_commits": len(commits), "files": len(at_head),
            "code_sha256": code_sha, "recorded": {"manifest_files": len(rec["manifest_files"]),
                                                   "params": sorted(rec["params"])},
            "match": not problems, "problems": problems}


def export(root: Path, commit: str, dest: Path) -> Path:
    """Cópia inteira da árvore do commit (código, pilot/, contracts/, ...) em dest; sem .git."""
    if dest.exists():
        import shutil
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    data = git(root, "archive", "--format=tar", commit, binary=True)
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:") as tf:
        tf.extractall(dest, filter="data")
    return dest
