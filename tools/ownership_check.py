#!/usr/bin/env python3
"""Checador de posse (§7.2): o diff do módulo só toca o que está em owns.

  ownership_check.py ID [--branch B]     commits do módulo (base..branch e '[ID] ...') + worktree suja
  ownership_check.py --all               prova que as posses do catálogo são disjuntas (sem sobreposição)
  ownership_check.py --selftest

Diretório em owns (termina em /) cobre a subárvore; arquivo cobre só ele. Posses em $BO_DATA
não passam pelo git e não entram aqui (são conferidas pelo privacy_lint e pelos gates do módulo).
"""
import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import argparse  # noqa: E402
import subprocess  # noqa: E402

from bo.repo import catalog, commits, core, fixtures  # noqa: E402
from bo.repo.catalog import matches, overlaps  # noqa: E402


def repo_owns(cat, mod) -> list[str]:
    out = []
    marker = "\0REPO\0"
    for o in mod.owns:
        if not o.startswith("$BO_REPO/"):
            continue
        for x in cat.expand(o, mod.id, repo=Path(marker)):
            out.append(x.replace(marker + "/", "", 1))
    return out


def changed_files(repo: Path, sha: str) -> list[str]:
    out = core.git(repo, "diff-tree", "--no-commit-id", "-r", "--name-only", "--root", "-m", sha)
    return sorted(set(filter(None, out.splitlines())))


def check(cat, mid: str, repo: Path, branch: str | None) -> tuple[list[str], int, int]:
    mod = cat.get(mid, allow_synthetic=True)
    owns = repo_owns(cat, mod)
    branch = branch or mod.branch
    _, shas = commits.module_commits(repo, cat, branch, mid)
    probs, nfiles = [], 0
    for sha in shas:
        for f in changed_files(repo, sha):
            nfiles += 1
            if not any(matches(f, o) for o in owns):
                probs.append(f"{sha[:10]}: {f} fora de owns de {mid}")
    wt = Path(mod.worktree)
    if wt.is_dir() and (wt / ".git").exists():
        for line in core.git(wt, "status", "--porcelain").splitlines():
            f = line[3:].split(" -> ")[-1].strip('"')
            if not any(matches(f, o) for o in owns):
                probs.append(f"worktree {wt}: {f} modificado fora de owns")
    return probs, len(shas), nfiles


def all_disjoint(cat) -> list[str]:
    owns = [(m.id, p) for m in cat.modules.values() for o in m.owns for p in cat.expand(o, m.id)]
    probs = []
    for i in range(len(owns)):
        for j in range(i + 1, len(owns)):
            (a, p), (b, q) = owns[i], owns[j]
            if a != b and overlaps(p, q):
                probs.append(f"{a}:{p} sobrepõe {b}:{q}")
    return probs


def selftest() -> int:
    ck = fixtures.Checks("ownership_check.py --selftest")
    mods = [fixtures.module("ALFA"), fixtures.module("BETA")]
    with fixtures.sandbox(mods) as root:
        repo = root / "repo"
        me = str(Path(__file__).resolve())
        fixtures.git(repo, "checkout", "-q", "-b", "bo/alfa")
        fixtures.commit_files(repo, "[ALFA] cria o pacote", {"src/bo/alfa/x.py": "X = 1\n",
                                                             "results/ALFA/summary.json": "{}\n"})
        run = lambda *a: subprocess.run([sys.executable, "-I", me, *a], capture_output=True, text=True)  # noqa: E731
        r = run("ALFA")
        ck.expect("diff dentro de owns passa", r.returncode == 0, r.stdout[-300:] + r.stderr[-200:])
        fixtures.commit_files(repo, "[ALFA] mexe no pacote do vizinho", {"src/bo/beta/y.py": "Y = 1\n"})
        r = run("ALFA")
        ck.expect("diff no pacote de outro módulo reprova", r.returncode == 1 and "src/bo/beta/y.py" in r.stdout)
        fixtures.git(repo, "reset", "-q", "--hard", "HEAD~1")
        fixtures.commit_files(repo, "[ALFA] mexe na raiz", {"Makefile": "x:\n"})
        r = run("ALFA")
        ck.expect("arquivo da raiz fora de owns reprova", r.returncode == 1)
        fixtures.git(repo, "reset", "-q", "--hard", "HEAD~1")
        fixtures.git(repo, "checkout", "-q", "bo/base")
        fixtures.git(repo, "merge", "-q", "--ff-only", "bo/alfa")
        r = run("ALFA")
        ck.expect("depois do merge ff, os commits '[ALFA]' continuam conferidos", r.returncode == 0 and
                  "2 arquivo" in r.stdout, r.stdout[-200:])
        r = run("--all")
        ck.expect("posses sintéticas disjuntas passam no --all", r.returncode == 0, r.stdout[-200:])
    return ck.report()


def main() -> int:
    if "--selftest" in sys.argv[1:]:
        return selftest()
    ap = argparse.ArgumentParser(prog="ownership_check.py")
    ap.add_argument("module", nargs="?")
    ap.add_argument("--branch")
    ap.add_argument("--all", action="store_true")
    a = ap.parse_args()
    repo = core.bo_repo()
    cat = catalog.load(repo)
    if a.all:
        probs = all_disjoint(cat)
        core.emit(f"[{core.now()}] ownership_check --all: {len(cat.modules)} módulos")
        for p in probs[:200]:
            core.emit(f"  {p}")
        core.emit("RESULTADO: " + ("OK (posses disjuntas)" if not probs else f"REPROVADO ({len(probs)})"))
        return 1 if probs else 0
    if not a.module:
        raise core.BoError("passe o ID do módulo (ou --all / --selftest)", code=2)
    probs, n, nf = check(cat, a.module, repo, a.branch)
    if n == 0:
        raise core.BoError(f"nenhum commit do módulo {a.module} encontrado")
    core.emit(f"[{core.now()}] ownership_check {a.module}: {n} commit(s), {nf} arquivo(s) tocados")
    for p in probs:
        core.emit(f"  {p}")
    core.emit("RESULTADO: " + ("OK" if not probs else f"REPROVADO ({len(probs)} fora de owns)"))
    return 1 if probs else 0


if __name__ == "__main__":
    core.run_main(main)
