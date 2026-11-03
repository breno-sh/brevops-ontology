"""Regeneração determinística dos arquivos do REPO (make owners / make manifest).

  owners    modules/owners.json = retrato do modulos.json (mesma entrada -> mesmo arquivo)
  state     modules/state.json inicial (só se não existir: é estado vivo, nunca sobrescrito)
  manifest  results/REPO/MANIFEST.sha256 dos arquivos versionados do REPO (caminhos relativos à raiz)
  check     confere que owners.json e MANIFEST regenerados saem idênticos aos versionados
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from . import catalog, core, state

MANIFEST_REL = "results/REPO/MANIFEST.sha256"


def owners_text(cat) -> str:
    return json.dumps(catalog.snapshot(cat), ensure_ascii=False, indent=1) + "\n"


def repo_files(repo: Path) -> list[str]:
    """Arquivos versionados que o REPO possui (exceto o próprio manifesto)."""
    cat = catalog.load(repo)
    mod = cat.get("REPO")
    owns = []
    for o in mod.owns:
        if o.startswith("$BO_REPO/"):
            owns.append(o[len("$BO_REPO/"):])
    tracked = core.git(repo, "ls-files").splitlines()
    out = [f for f in tracked if any(catalog.matches(f, o) for o in owns) and f != MANIFEST_REL]
    return sorted(out)


def manifest_text(repo: Path) -> str:
    lines = [f"{core.sha256_file(Path(repo) / f)}  {f}" for f in repo_files(repo)]
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    what = argv[0] if argv else "check"
    repo = core.bo_repo()
    if what == "owners":
        cat = catalog.load(repo)
        p = repo / catalog.OWNERS_REL
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(owners_text(cat), encoding="utf-8")
        core.emit(f"owners: {p} ({len(cat.modules)} módulos; fonte sha256 {core.sha256_file(cat.source)[:12]}…)")
        return 0
    if what == "state":
        p = state.path(repo)
        if p.exists():
            core.emit(f"state: {p} já existe (estado vivo; não sobrescrevo)")
            return 0
        state.save(state.initial(catalog.load(repo)), repo)
        core.emit(f"state: {p} criado")
        return 0
    if what == "manifest":
        p = repo / MANIFEST_REL
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(manifest_text(repo), encoding="utf-8")
        core.emit(f"manifest: {p} ({len(repo_files(repo))} arquivos)")
        return 0
    if what == "check":
        probs = []
        cat = catalog.load(repo)
        cur = (repo / catalog.OWNERS_REL).read_text(encoding="utf-8") if (repo / catalog.OWNERS_REL).exists() else ""
        if cat.source.name == "owners.json":
            core.emit("  nota: modulos.json do plano ausente; retrato conferido só contra si mesmo")
        elif owners_text(cat) != cur:
            probs.append("modules/owners.json difere do regenerado a partir do modulos.json (rode make owners)")
        mp = repo / MANIFEST_REL
        if not mp.exists() or mp.read_text(encoding="utf-8") != manifest_text(repo):
            probs.append("results/REPO/MANIFEST.sha256 difere do regenerado (rode make manifest)")
        for p in probs:
            core.emit(f"  FAIL {p}")
        core.emit("regeneração idêntica: " + ("OK" if not probs else "REPROVADO"))
        return 1 if probs else 0
    raise core.BoError(f"alvo desconhecido: {what}", code=2)
