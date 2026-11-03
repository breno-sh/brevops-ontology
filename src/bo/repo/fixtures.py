"""Ambiente descartável para os --selftest: repositório git, BO_DATA e modulos.json sintéticos.

Fica em $BO_TMP (ou $BO_DATA/tmp/REPO), nunca em /tmp, e é apagado no fim.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from contextlib import contextmanager
from pathlib import Path

from . import core

ENV_KEYS = ("BO_REPO", "BO_DATA", "BO_MODULES", "BO_LANES", "BO_BASE", "BO_TMP", "BO_ID", "BO_PRIVACY_PROJECTS")


def scratch_root() -> Path:
    t = os.environ.get("BO_TMP")
    p = Path(t) if t else core.bo_data() / "tmp" / "REPO"
    p.mkdir(parents=True, exist_ok=True)
    return p


def module(mid, deps=(), inputs=(), outputs=(), gates=(), owns=None):
    pkg = mid.lower().replace("-", "_")
    return {
        "id": mid, "stable_id": mid, "wave": 0, "deps": list(deps), "inputs": list(inputs),
        "outputs": list(outputs), "gates": list(gates), "contracts": [], "needs_cloud": False, "lock": None,
        "branch": "bo/" + mid.lower(), "worktree": "$LANES/bo-" + mid.lower(),
        "owns": owns if owns is not None else [f"$BO_REPO/src/bo/{pkg}/", f"$BO_REPO/tests/{pkg}/",
                                                f"$BO_REPO/gates/{mid}.sh", f"$BO_REPO/results/{mid}/",
                                                f"$BO_DATA/{mid}/"],
    }


def git(repo: Path, *args: str) -> str:
    env = dict(os.environ, GIT_AUTHOR_NAME="Teste", GIT_AUTHOR_EMAIL="teste@example.org",
               GIT_COMMITTER_NAME="Teste", GIT_COMMITTER_EMAIL="teste@example.org")
    r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, env=env)
    if r.returncode != 0:
        raise RuntimeError(f"git {args}: {r.stderr}")
    return r.stdout


def commit_files(repo: Path, msg: str, files: dict[str, str]) -> str:
    for rel, content in files.items():
        p = repo / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "--allow-empty", "-m", msg)
    return git(repo, "rev-parse", "HEAD").strip()


@contextmanager
def sandbox(modules: list[dict], index_sets: dict | None = None, artifacts: list[dict] | None = None):
    root = Path(tempfile.mkdtemp(prefix="selftest-", dir=scratch_root()))
    saved = {k: os.environ.get(k) for k in ENV_KEYS}
    try:
        repo, data, lanes = root / "repo", root / "data", root / "lanes"
        for d in (repo, data, lanes):
            d.mkdir()
        for m in modules:
            m["worktree"] = m["worktree"].replace("$LANES", str(lanes))
        if artifacts is None:
            artifacts = [{"path": o, "producer": m["stable_id"], "kind": "data", "contract": None,
                          "consumers": []} for m in modules for o in m["outputs"]]
        mj = root / "modulos.json"
        mj.write_text(json.dumps({"index_sets": index_sets or {}, "modules": modules,
                                  "artifact_catalog": {"artifacts": artifacts, "external_inputs": []}},
                                 ensure_ascii=False, indent=1), encoding="utf-8")
        git(repo, "init", "-q", "-b", "bo/base")
        commit_files(repo, "[REPO] inicia o repositório de teste", {})
        os.environ.update({"BO_REPO": str(repo), "BO_DATA": str(data), "BO_MODULES": str(mj),
                           "BO_LANES": str(lanes), "BO_BASE": "bo/base"})
        os.environ.pop("BO_TMP", None)
        os.environ.pop("BO_ID", None)
        yield root
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(root, ignore_errors=True)


class Checks:
    """Coleção de expectativas do selftest: imprime só o nome da verificação, nunca o valor plantado."""

    def __init__(self, title: str):
        self.title, self.items = title, []

    def expect(self, name: str, ok: bool, detail: str = "") -> None:
        self.items.append((name, bool(ok), detail))

    def report(self) -> int:
        bad = [i for i in self.items if not i[1]]
        for name, ok, detail in self.items:
            print(f"  [{'ok' if ok else 'FALHOU'}] {name}" + (f" — {detail}" if detail and not ok else ""))
        print(f"{self.title}: {len(self.items) - len(bad)}/{len(self.items)} expectativas "
              f"{'cumpridas' if not bad else 'cumpridas; SELFTEST REPROVADO'}")
        return 0 if not bad and self.items else 1
