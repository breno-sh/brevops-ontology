#!/usr/bin/env python3
"""Linter de commit (C00): assunto '[ID] texto' em português simples, sem 'Co-Authored-By',
sem menção a Claude/IA/modelo, sem assinatura de ferramenta, sem merge na branch do módulo.

  commit_lint.py BRANCH                 confere os commits do módulo (base..BRANCH e os '[ID] ...')
  commit_lint.py --message-file ARQ     hook commit-msg
  commit_lint.py --message "TEXTO"
  commit_lint.py --selftest             'Co-Authored-By' e 'Claude' têm de reprovar

A proveniência do agente não vai no commit: vai no summary.json (C17), via tools/provenance.py.
"""
import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import argparse  # noqa: E402
import subprocess  # noqa: E402

from bo.repo import catalog, commits, core, fixtures  # noqa: E402


def selftest() -> int:
    ck = fixtures.Checks("commit_lint.py --selftest")
    good = ["[REPO] cria o linter de commit e os testes",
            "[REPO] corrige a trava de merge\n\nA trava agora guarda o dono e a hora.",
            "[COORD] congela os contratos do FREEZE0"]
    for m in good:
        p = commits.lint_message(m, known_ids={"REPO"})
        ck.expect(f"aceita: {m.splitlines()[0]}", not p, "; ".join(map(str, p)))
    co = "Co-Authored-By: " + "Cla" + "ude Opus <noreply@" + "anthropic.com>"
    bad = {
        "trailer Co-Authored-By": "[REPO] cria a trava\n\n" + co,
        "Co-Authored-By sem nome de IA": "[REPO] cria a trava\n\nCo-authored-by: Fulano <f@example.org>",
        "menção a Claude no assunto": "[REPO] ajusta o gate pedido pelo " + "Cla" + "ude",
        "menção a Claude no corpo": "[REPO] ajusta o gate\n\nfeito com o " + "Cla" + "ude Code",
        "assinatura gerado com": "[REPO] ajusta o gate\n\n\U0001F916 Generated with ferramenta",
        "menção a IA": "[REPO] ajusta o gate sugerido pela IA",
        "inglês": "[REPO] add the commit linter for this repo",
        "sem prefixo [ID]": "cria o linter de commit",
        "assunto longo": "[REPO] " + "cria " * 20,
        "ID desconhecido": "[XYZ] cria o linter",
    }
    for label, m in bad.items():
        p = commits.lint_message(m, known_ids={"REPO"})
        ck.expect(f"reprova: {label}", bool(p))
    ck.expect("ID de outro módulo na branch reprova",
              bool(commits.lint_message("[CONTRACTS] cria o validador", expected_id="REPO")))
    # modo branch, de ponta a ponta, num repositório descartável
    with fixtures.sandbox([fixtures.module("REPO")]) as root:
        repo = root / "repo"
        fixtures.git(repo, "checkout", "-q", "-b", "bo/repo")
        fixtures.commit_files(repo, "[REPO] cria a ferramenta de teste", {"tools/x.py": "X = 1\n"})
        me = str(Path(__file__).resolve())
        r = subprocess.run([sys.executable, "-I", me, "bo/repo"], capture_output=True, text=True)
        ck.expect("branch só com commits bons passa", r.returncode == 0, r.stdout[-300:] + r.stderr[-300:])
        fixtures.commit_files(repo, "[REPO] ajusta a ferramenta\n\n" + co, {"tools/x.py": "X = 2\n"})
        r = subprocess.run([sys.executable, "-I", me, "bo/repo"], capture_output=True, text=True)
        ck.expect("branch com Co-Authored-By reprova", r.returncode != 0)
        r = subprocess.run([sys.executable, "-I", me, "bo/nao-existe"], capture_output=True, text=True)
        ck.expect("branch inexistente reprova com mensagem clara", r.returncode == 2 and "não existe" in r.stderr)
    return ck.report()


def main() -> int:
    if "--selftest" in sys.argv[1:]:
        return selftest()
    ap = argparse.ArgumentParser(prog="commit_lint.py")
    ap.add_argument("branch", nargs="?")
    ap.add_argument("--message-file")
    ap.add_argument("--message")
    a = ap.parse_args()
    repo = core.bo_repo()
    try:
        cat = catalog.load(repo)
        known = set(cat.modules)
    except core.BoError:
        cat, known = None, None
    if a.message_file or a.message is not None:
        msg = Path(a.message_file).read_text(encoding="utf-8") if a.message_file else a.message
        expected = None
        try:
            cur = core.git(Path.cwd(), "rev-parse", "--abbrev-ref", "HEAD").strip()
            m = cat.by_branch(cur) if cat else None
            expected = m.id if m else None
        except core.BoError:
            pass
        probs = commits.lint_message(msg, expected_id=expected, known_ids=known)
        for p in probs:
            print(f"  {p}")
        if probs:
            core.fail("commit_lint: mensagem recusada (português, '[ID] ', sem atribuição nem menção a IA)")
            return 1
        return 0
    if not a.branch:
        raise core.BoError("passe a branch (ex.: bo/repo), --message-file ou --selftest", code=2)
    mid, shas = commits.module_commits(repo, cat, a.branch)
    if not shas:
        raise core.BoError(f"nenhum commit do módulo {mid} em {a.branch}")
    probs = []
    for sha in shas:
        if commits.is_merge(repo, sha):
            probs.append(commits.Problem(sha[:10], "commit de merge na branch do módulo (use rebase)"))
            continue
        probs.extend(commits.lint_message(commits.commit_message(repo, sha), expected_id=mid,
                                          known_ids=known, ref=sha[:10]))
    core.emit(f"[{core.now()}] commit_lint {a.branch} (módulo {mid}): {len(shas)} commit(s)")
    for p in probs:
        core.emit(f"  {p}")
    core.emit("RESULTADO: " + ("OK" if not probs else f"REPROVADO ({len(probs)} problema(s))"))
    return 1 if probs else 0


if __name__ == "__main__":
    core.run_main(main)
