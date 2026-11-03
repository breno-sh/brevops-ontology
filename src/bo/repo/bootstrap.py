"""make bootstrap: deixa o ambiente pronto para os gates (idempotente).

1. .pth no site-packages do interpretador: 'python -I -m bo.*' passa a achar $BO_REPO/src
   (lido de BO_REPO no ambiente; sem ele, o repositório principal). -I ignora PYTHONPATH,
   então este é o único jeito de o pacote resolver sob -I sem instalar nada.
2. .git/info/exclude (vale para todas as worktrees): caches e arquivos locais da lane.
3. hooks pre-commit (privacy_lint --staged) e commit-msg (commit_lint) no diretório comum do git.
4. árvore $BO_DATA (tmp/, locks/) e $BO_DATA/tmp/REPO.
"""

from __future__ import annotations

import os
import site
import sys
from pathlib import Path

from . import core

PTH_NAME = "brevops_ontology.pth"
PTH_LINE = ("import os, sys; _r = os.environ.get('BO_REPO') or {default!r}; _p = os.path.join(_r, 'src'); "
            "(os.path.isdir(_p) and _p not in sys.path) and sys.path.append(_p)\n")
EXCLUDE = ["__pycache__/", "*.pyc", ".pytest_cache/", ".claude/", ".bo/", ".DS_Store", ".venv/"]
HOOK_HEADER = "#!/bin/sh\n# instalado por make bootstrap (BrevOps); usa as ferramentas da worktree corrente\n"
HOOKS = {
    "pre-commit": HOOK_HEADER + 'top=$(git rev-parse --show-toplevel)\n'
                  'exec python -I "$top/tools/privacy_lint.py" --staged\n',
    "commit-msg": HOOK_HEADER + 'top=$(git rev-parse --show-toplevel)\n'
                  'exec python -I "$top/tools/commit_lint.py" --message-file "$1"\n',
}


def site_dir() -> Path:
    for d in site.getsitepackages():
        if d.endswith("site-packages") and Path(d).is_dir():
            return Path(d)
    raise core.BoError("site-packages do interpretador não encontrado")


def install_pth() -> tuple[Path, bool]:
    p = site_dir() / PTH_NAME
    want = PTH_LINE.format(default=core.DEFAULT_BO_REPO)
    if p.exists() and p.read_text(encoding="utf-8") == want:
        return p, False
    p.write_text(want, encoding="utf-8")
    return p, True


def install_exclude(repo: Path) -> tuple[Path, int]:
    p = core.git_common_dir(repo) / "info" / "exclude"
    p.parent.mkdir(parents=True, exist_ok=True)
    cur = p.read_text(encoding="utf-8").splitlines() if p.exists() else []
    add = [x for x in EXCLUDE if x not in cur]
    if add:
        with open(p, "a", encoding="utf-8") as f:
            f.write("\n# BrevOps (make bootstrap)\n" + "\n".join(add) + "\n")
    return p, len(add)


def install_hooks(repo: Path) -> list[str]:
    d = core.git_common_dir(repo) / "hooks"
    d.mkdir(parents=True, exist_ok=True)
    done = []
    for name, body in HOOKS.items():
        p = d / name
        if p.exists() and p.read_text(encoding="utf-8") != body and HOOK_HEADER not in p.read_text(encoding="utf-8"):
            raise core.BoError(f"hook {p} já existe e não é do BrevOps; não sobrescrevo")
        p.write_text(body, encoding="utf-8")
        os.chmod(p, 0o755)
        done.append(str(p))
    return done


def data_tree() -> list[str]:
    out = []
    for d in (core.bo_data() / "tmp", core.bo_data() / "locks", core.bo_data() / "tmp" / "REPO",
              core.bo_data() / "REPO", core.bo_data() / "downloads"):
        d.mkdir(parents=True, exist_ok=True)
        out.append(str(d))
    return out


def main(argv=None) -> int:
    repo = core.bo_repo()
    p, changed = install_pth()
    core.emit(f"[{core.now()}] bootstrap ({sys.executable})")
    core.emit(f"  .pth {'gravado' if changed else 'já estava'}: {p}")
    ex, n = install_exclude(repo)
    core.emit(f"  exclude: {ex} (+{n} padrão(ões))")
    for h in install_hooks(repo):
        core.emit(f"  hook: {h}")
    for d in data_tree():
        core.emit(f"  dir: {d}")
    return 0


def check() -> list[str]:
    """Problemas de ambiente (vazio = pronto)."""
    probs = []
    try:
        p = site_dir() / PTH_NAME
        if not p.exists():
            probs.append(f"{p} ausente: rode make -C $BO_REPO bootstrap")
    except core.BoError as e:
        probs.append(str(e))
    return probs
