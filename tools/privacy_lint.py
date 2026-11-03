#!/usr/bin/env python3
"""Linter de privacidade (§8): reprova ids de conta/recurso, e-mails, dinheiro fora do
cost_estimate.json agregado e conteúdo Withheld (segredos, env, UserData, logs, conteúdo de
objeto ou mensagem; nem como hash).

  privacy_lint.py [--strict] CAMINHO ...   varre arquivos e diretórios (ausente = nada a varrer, com nota)
  privacy_lint.py --staged                 varre o que está no índice do git (hook de pre-commit)
  privacy_lint.py --selftest               IDs falsos plantados têm de reprovar; arquivo limpo tem de passar

--strict: binário também é varrido; arquivo grande, ilegível ou caminho ausente reprova.
Listas privadas fora do repositório: ~/.config/bo/gcp_projects.txt e ~/.config/bo/private_terms.txt
(ou BO_PRIVACY_PROJECTS / BO_PRIVACY_TERMS). O valor achado nunca é impresso inteiro.
"""
import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import argparse  # noqa: E402
import os  # noqa: E402
import subprocess  # noqa: E402

from bo.repo import core, fixtures, privacy  # noqa: E402

SELF_EXEMPT = ("tools/privacy_lint.py", "src/bo/repo/privacy.py")
UD = "user" + "_data"


def planted() -> dict[str, tuple[str, str]]:
    """Valores falsos montados em tempo de execução (o código-fonte não os contém literalmente)."""
    d12 = "".join(str(i % 10) for i in range(1, 13))
    guid = "-".join(["0b1f6d3e", "4a2c", "4e7b", "9c1d", "5f6a7b8c9d0e"])
    key = "AK" + "IA" + "Q" * 16
    return {
        "conta12.txt": ("doze_digitos", f"conta = {d12}\n"),
        "arn.json": ("arn", '{"role": "' + "ar" + "n:aws:iam::" + "x" * 3 + ':role/bo"}\n'),
        "ocid.txt": ("ocid", "compartment " + "oc" + "id1.compartment.oc1..aaaab\n"),
        "sub.txt": ("azure_subscription", "/subscriptions/" + guid + "/resourceGroups/rg\n"),
        "mail.txt": ("email", "contato: fulano" + "@" + "empresa.com.br\n"),
        "dinheiro.json": ("money", '{"custo": "US' + "$" + ' 12.50"}\n'),
        "reais.txt": ("money", "gasto de R" + "$ 1.234,00\n"),
        "chave.txt": ("secret_aws_key", "id " + key + "\n"),
        "pem.txt": ("secret_private_key", "-----BEGIN " + "PRIVATE KEY-----\nabc\n"),
        "senha.yaml": ("secret_assignment", 'password: "' + "s3nh4" + 'Forte9"\n'),
        "ud.json": ("withheld_content", '{"' + UD + '": "' + "IyEvYmluL3No" + '"}\n'),
        "udhash.json": ("withheld_hash", '{"' + UD + '_sha256": "' + "ab" * 32 + '"}\n'),
        "env.json": ("withheld_env", '{"Environ' + 'ment": {"Variables": {"K": "v"}}}\n'),
        "msg.json": ("withheld_hash", '{"message' + '_body_md5": "' + "cd" * 16 + '"}\n'),
        "proj.txt": ("projeto_gcp", "projeto meu-projeto-" + "secreto-42 em uso\n"),
        "empresa.txt": ("termo_privado", "cliente Firma" + "Secreta Ltda\n"),
        "dotenv.env": ("secret_env_line", "export API" + "_TOKEN=" + "z" * 20 + "\n"),
    }


def clean_text() -> str:
    h = "".join(str(i % 10) for i in range(1, 13)) + "abcdef" * 9  # dígitos dentro de um hash
    return (f"sha256 {h[:64]}\nquando 2026-11-02T21:16:16-03:00\ncontato teste@example.org\n"
            "script: echo \"$1\" e ${BO_DATA}\nnúmero 1234567890123 (13 dígitos)\n"
            'password: "REDACTED"\n{"' + UD + '": null}\n')


def selftest() -> int:
    ck = fixtures.Checks("privacy_lint.py --selftest")
    root = Path(fixtures.scratch_root()) / f"privacy-selftest-{os.getpid()}"
    saved = {k: os.environ.get(k) for k in ("BO_PRIVACY_PROJECTS", "BO_PRIVACY_TERMS")}
    try:
        root.mkdir(parents=True, exist_ok=True)
        (root / "lists").mkdir(exist_ok=True)
        (root / "lists" / "proj.txt").write_text("meu-projeto-" + "secreto-42\n", encoding="utf-8")
        (root / "lists" / "terms.txt").write_text("Firma" + "Secreta\n", encoding="utf-8")
        os.environ["BO_PRIVACY_PROJECTS"] = str(root / "lists" / "proj.txt")
        os.environ["BO_PRIVACY_TERMS"] = str(root / "lists" / "terms.txt")
        lists, _ = privacy.load_lists()
        bad = root / "bad"
        bad.mkdir(exist_ok=True)
        for name, (rule, txt) in planted().items():
            (bad / name).write_text(txt, encoding="utf-8")
            f = privacy.scan_text(txt, name, lists)
            ck.expect(f"plantado {name} reprova pela regra {rule}", any(x.rule == rule for x in f),
                      "regras achadas: " + ",".join(sorted({x.rule for x in f})))
            ck.expect(f"mensagem de {name} não expõe o valor", all(len(x.hint) < 40 for x in f))
        good = root / "good"
        good.mkdir(exist_ok=True)
        (good / "limpo.txt").write_text(clean_text(), encoding="utf-8")
        (good / "cost_estimate.json").write_text('{"total": "US' + "$" + ' 25.00"}\n', encoding="utf-8")
        f = privacy.scan_text(clean_text(), "limpo.txt", lists)
        ck.expect("arquivo limpo (hash com dígitos, data, example.org, $1, null) passa", not f,
                  ",".join(x.rule for x in f))
        f, n, _ = privacy.scan_paths([good], strict=True, lists=lists)
        ck.expect("dinheiro só dentro de cost_estimate.json é aceito", not f, ",".join(x.rule for x in f))
        (bad / "blob.bin").write_bytes(b"\x00\x01" + ("AK" + "IA" + "Z" * 16).encode() + b"\x00")
        f, n, _ = privacy.scan_paths([bad / "blob.bin"], strict=True, lists=lists)
        ck.expect("--strict varre binário", any(x.rule == "secret_aws_key" for x in f))
        f, n, _ = privacy.scan_paths([bad / "blob.bin"], strict=False, lists=lists)
        ck.expect("sem --strict, binário é ignorado", not f)
        # CLI de ponta a ponta: diretório sujo reprova, limpo passa, ausente passa com nota
        me = str(Path(__file__).resolve())
        r_bad = subprocess.run([sys.executable, "-I", me, "--strict", str(bad)], capture_output=True, text=True)
        r_good = subprocess.run([sys.executable, "-I", me, "--strict", str(good)], capture_output=True, text=True)
        r_abs_strict = subprocess.run([sys.executable, "-I", me, "--strict", str(good), str(root / "nao-existe")],
                                      capture_output=True, text=True)
        r_abs = subprocess.run([sys.executable, "-I", me, str(good), str(root / "nao-existe")],
                               capture_output=True, text=True)
        ck.expect("CLI reprova diretório com plantados", r_bad.returncode == 1)
        ck.expect("CLI aceita diretório limpo", r_good.returncode == 0, r_good.stdout[-300:])
        ck.expect("--strict reprova caminho ausente (sem passe por vacuidade)", r_abs_strict.returncode == 1)
        ck.expect("sem --strict, caminho ausente vira nota", r_abs.returncode == 0 and "nota" in r_abs.stdout)
        ck.expect("saída da CLI não contém nenhum valor plantado",
                  not any(t.strip().split()[-1] in r_bad.stdout for _, t in planted().values() if len(t) > 8))
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        import shutil
        shutil.rmtree(root, ignore_errors=True)
    return ck.report()


def staged() -> int:
    top = Path(core.git(Path.cwd(), "rev-parse", "--show-toplevel").strip())
    names = core.git(top, "diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z").split("\0")
    lists, notes = privacy.load_lists()
    findings = []
    for n in filter(None, names):
        if n in SELF_EXEMPT:
            continue
        b = subprocess.run(["git", "-C", str(top), "show", f":{n}"], capture_output=True).stdout
        findings.extend(privacy.scan_bytes(b, n, lists, strict=False))
    for f in findings:
        print(f"  {f}")
    if findings:
        core.fail(f"privacy_lint (pre-commit): {len(findings)} achado(s) no índice; commit bloqueado")
        return 1
    return 0


def main() -> int:
    if "--selftest" in sys.argv[1:]:
        return selftest()
    ap = argparse.ArgumentParser(prog="privacy_lint.py")
    ap.add_argument("--strict", action="store_true")
    ap.add_argument("--staged", action="store_true")
    ap.add_argument("paths", nargs="*")
    a = ap.parse_args()
    if a.staged:
        return staged()
    if not a.paths:
        raise core.BoError("passe pelo menos um caminho (ou --staged / --selftest)", code=2)
    lists, notes = privacy.load_lists()
    findings, n, notes2 = privacy.scan_paths([Path(p) for p in a.paths], strict=a.strict, lists=lists)
    core.emit(f"[{core.now()}] privacy_lint{' --strict' if a.strict else ''}: {n} arquivo(s) varrido(s)")
    for x in notes + notes2:
        core.emit(f"  nota: {x}")
    for f in findings:
        core.emit(f"  ACHADO {f}")
    core.emit("RESULTADO: " + ("OK" if not findings else f"REPROVADO ({len(findings)} achado(s))"))
    return 1 if findings else 0


if __name__ == "__main__":
    core.run_main(main)
