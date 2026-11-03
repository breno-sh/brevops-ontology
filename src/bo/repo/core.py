"""Ambiente (C00), tempo, hashes, git e JSON: o mínimo que todas as ferramentas usam."""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

TZ = ZoneInfo("America/Recife")

DEFAULT_BO_REPO = "/Users/breno/doutorado/brevops-ontology"
DEFAULT_BO_DATA = "/Users/breno/doutorado/brevops-data"
DEFAULT_LANES = "/Users/breno/doutorado/pesquisa-lanes"
DEFAULT_PLAN_DIR = "/Users/breno/doutorado/pesquisa/superficie/reports/brevops_ontology"
DEFAULT_MODULES_JSON = DEFAULT_PLAN_DIR + "/modulos.json"
BASE_BRANCH_DEFAULT = "bo/base"

# Raiz deste checkout (worktree ou repositório principal): src/bo/repo/core.py -> raiz
CHECKOUT_ROOT = Path(__file__).resolve().parents[3]

SKIP_NAMES = {"__pycache__", ".DS_Store", ".pytest_cache"}


class BoError(Exception):
    """Erro esperado, com mensagem clara para o usuário (sai com código != 0)."""

    def __init__(self, msg: str, code: int = 1):
        super().__init__(msg)
        self.code = code


# ---------------------------------------------------------------- ambiente

def bo_repo() -> Path:
    v = os.environ.get("BO_REPO")
    return Path(v) if v else CHECKOUT_ROOT


def bo_data() -> Path:
    return Path(os.environ.get("BO_DATA") or DEFAULT_BO_DATA)


def lanes_dir() -> Path:
    return Path(os.environ.get("BO_LANES") or DEFAULT_LANES)


def base_branch() -> str:
    return os.environ.get("BO_BASE") or BASE_BRANCH_DEFAULT


def modules_json() -> Path:
    return Path(os.environ.get("BO_MODULES") or DEFAULT_MODULES_JSON)


def bo_tmp(module_id: str) -> Path:
    return bo_data() / "tmp" / module_id


def module_env(module_id: str, repo: Path | None = None) -> dict:
    """Ambiente padrão (C00) para rodar comandos de um módulo."""
    env = dict(os.environ)
    env["BO_REPO"] = str(repo or bo_repo())
    env["BO_DATA"] = str(bo_data())
    env["BO_ID"] = module_id
    tmp = bo_tmp(module_id)
    tmp.mkdir(parents=True, exist_ok=True)
    env["BO_TMP"] = str(tmp)
    env["TMPDIR"] = str(tmp)  # nunca /tmp compartilhado
    if "BO_MODULES" not in env:
        env["BO_MODULES"] = str(modules_json())
    return env


# ---------------------------------------------------------------- tempo

def now() -> str:
    """ISO-8601 com fuso America/Recife (C00)."""
    return _dt.datetime.now(TZ).isoformat(timespec="seconds")


def stamp() -> str:
    """Carimbo compacto para nomes de arquivo."""
    return _dt.datetime.now(TZ).strftime("%Y%m%dT%H%M%S")


# ---------------------------------------------------------------- hashes

def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def iter_tree(root: Path):
    """Arquivos de uma árvore em ordem determinística (pula caches)."""
    out = []
    for dp, dns, fns in os.walk(root, followlinks=False):
        links = [d for d in dns if (Path(dp) / d).is_symlink()]
        dns[:] = sorted(d for d in dns if d not in SKIP_NAMES and d not in links)
        for fn in sorted(fns + links):
            if fn in SKIP_NAMES or fn.endswith(".pyc"):
                continue
            out.append(Path(dp) / fn)
    return sorted(out)


def hash_path(p: Path) -> dict:
    """Hash de arquivo ou diretório. Diretório: sha256 das linhas 'relpath\\tsha'."""
    p = Path(p)
    if p.is_symlink():
        return {"kind": "symlink", "sha256": sha256_bytes(os.readlink(p).encode())}
    if p.is_file():
        return {"kind": "file", "sha256": sha256_file(p), "bytes": p.stat().st_size}
    if p.is_dir():
        files = {}
        for f in iter_tree(p):
            rel = f.relative_to(p).as_posix()
            if f.is_symlink():
                files[rel] = sha256_bytes(("symlink:" + os.readlink(f)).encode())
            else:
                files[rel] = sha256_file(f)
        lines = "".join(f"{k}\t{v}\n" for k, v in sorted(files.items()))
        return {"kind": "dir", "sha256": sha256_bytes(lines.encode()), "files": files}
    return {"kind": "missing", "sha256": None}


# ---------------------------------------------------------------- json

def read_json(p: Path, default=None):
    p = Path(p)
    if not p.exists():
        return default
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def canonical_json(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def write_json(p: Path, obj, sort_keys: bool = False) -> None:
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1, sort_keys=sort_keys)
        f.write("\n")
    os.replace(tmp, p)


# ---------------------------------------------------------------- git

def git(repo: Path, *args: str, check: bool = True) -> str:
    r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    if check and r.returncode != 0:
        raise BoError(f"git {' '.join(args)} falhou: {r.stderr.strip()}")
    return r.stdout


def git_ok(repo: Path, *args: str) -> bool:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True).returncode == 0


def ref_exists(repo: Path, ref: str) -> bool:
    return git_ok(repo, "rev-parse", "--verify", "--quiet", ref + "^{commit}")


def git_common_dir(repo: Path) -> Path:
    out = git(repo, "rev-parse", "--git-common-dir").strip()
    p = Path(out)
    return p if p.is_absolute() else (Path(repo) / p).resolve()


# ---------------------------------------------------------------- saída

def emit(msg: str) -> None:
    print(msg, flush=True)


def fail(msg: str) -> None:
    print(f"REPROVADO: {msg}", file=sys.stderr, flush=True)


def run_main(fn) -> None:
    """Executa um main() traduzindo BoError em mensagem clara e código de saída."""
    try:
        rc = fn()
    except BoError as e:
        fail(str(e))
        rc = e.code
    except KeyboardInterrupt:
        rc = 130
    sys.exit(rc or 0)
