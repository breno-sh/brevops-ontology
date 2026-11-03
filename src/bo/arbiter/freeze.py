"""Congelamento do árbitro: arbiter/ARBITER.sha256 lista o sha256 de tudo de que o veredito depende.

Entram: o pacote bo.arbiter inteiro; todo módulo bo.* que ele importa (fecho calculado, não digitado à mão:
a implementação de referência do SEMANTICS, o registro fechado do TRANSFORMS, a E/S e o validador do C09/C21);
os dados que esses módulos leem (tabela formal de composição, registro de transformações, esquemas C00, C09, C10,
C20 e C21); e arbiter/RULES.html. Caminhos relativos à raiz do repositório (shasum -a 256 -c rodado de $BO_REPO).
arbiter_sha256 do C21 = sha256 do próprio ARBITER.sha256: muda se QUALQUER arquivo congelado mudar.
"""

from __future__ import annotations

import json
import os
import pkgutil
import subprocess
import sys
from pathlib import Path

from .common import repo, sha256_bytes, sha256_file

DATA_FILES = (
    "semantics/composition_table.json",
    "transforms/transforms.yaml",
    "contracts/C00_conventions.schema.json",
    "contracts/C09_correspondences.schema.json",
    "contracts/C10_transforms.schema.json",
    "contracts/C20_glossary.schema.json",
    "contracts/C21_verdicts.schema.json",
)
RULES_HTML = "arbiter/RULES.html"
MANIFEST = "arbiter/ARBITER.sha256"


def arbiter_modules() -> list[str]:
    import bo.arbiter as pkg
    return sorted(f"bo.arbiter.{m.name}" for m in pkgutil.iter_modules(pkg.__path__))


_PROBE = r"""
import importlib, json, pkgutil, sys
import bo.arbiter as pkg
for m in sorted(pkgutil.iter_modules(pkg.__path__), key=lambda m: m.name):
    importlib.import_module("bo.arbiter." + m.name)
print(json.dumps(sorted(getattr(mod, "__file__", None) or "" for n, mod in list(sys.modules.items())
                        if n == "bo" or n.startswith("bo."))))
"""


def code_files() -> list[str]:
    """Fecho de importação: bo.* carregados por um interpretador LIMPO (python -I) que importa todo módulo do
    bo.arbiter; só o que está sob $BO_REPO/src. Subprocesso para o resultado não depender do que o chamador já
    importou."""
    root = (repo() / "src").resolve()
    env = dict(os.environ, BO_REPO=str(repo()))
    out = subprocess.run([sys.executable, "-I", "-B", "-c", _PROBE], capture_output=True, text=True, env=env,
                         check=False)
    if out.returncode != 0:
        raise RuntimeError(f"sonda de importação falhou: {out.stderr.strip()[-400:]}")
    files = set()
    for f in json.loads(out.stdout.strip().splitlines()[-1]):
        if not f:
            continue
        try:
            files.add(str(Path("src") / Path(f).resolve().relative_to(root)))
        except ValueError:
            continue
    pkg_dir = Path("src/bo/arbiter")
    for p in sorted((repo() / pkg_dir).glob("*.py")):
        files.add(str(pkg_dir / p.name))
    return sorted(files)


def frozen_files() -> list[str]:
    return sorted(set(code_files()) | set(DATA_FILES) | {RULES_HTML})


def manifest_text(files: list[str] | None = None) -> str:
    r = repo()
    lines = []
    for rel in files or frozen_files():
        lines.append(f"{sha256_file(r / rel)}  {rel}\n")
    return "".join(lines)


def manifest_path() -> Path:
    return repo() / MANIFEST


def verify() -> list[str]:
    """Linhas do ARBITER.sha256 que não conferem (vazio = congelado e íntegro)."""
    p = manifest_path()
    if not p.exists():
        return [f"{MANIFEST} ausente"]
    bad = []
    r = repo()
    for line in p.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        h, rel = line.split("  ", 1)
        f = r / rel
        if not f.exists():
            bad.append(f"{rel}: ausente")
        elif sha256_file(f) != h:
            bad.append(f"{rel}: sha256 diferente do congelado")
    listed = {line.split("  ", 1)[1] for line in p.read_text(encoding="utf-8").splitlines() if line.strip()}
    for rel in sorted(set(code_files()) - listed):
        bad.append(f"{rel}: código importado pelo árbitro fora do congelamento")
    return bad


def arbiter_sha() -> str:
    p = manifest_path()
    if p.exists():
        return sha256_file(p)
    return sha256_bytes(manifest_text().encode("utf-8"))


if __name__ == "__main__":
    bad = verify()
    for b in bad:
        print(f"  FALHA {b}")
    print("árbitro congelado e íntegro" if not bad else f"{len(bad)} divergência(s)")
    sys.exit(1 if bad else 0)
