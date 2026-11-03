#!/usr/bin/env python3
"""Smoke offline dos gates: todo comando resolve antes de rodar (nada do gate é executado).

  gate_smoke.py ID          confere os gates do módulo ID (lidos do modulos.json)
  gate_smoke.py --selftest  gate com módulo bo.* inexistente reprova antes de rodar

Confere executável, 'python -I -m bo.*' importável, pacote de terceiro na versão do
requirements.lock, script e alvo de make existentes, variáveis definidas e ROBOT/Terraform
na versão fixada. Módulo inexistente reprova com mensagem clara (saída 2), sem travar.
"""
import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import os  # noqa: E402
import subprocess  # noqa: E402

from bo.repo import catalog, core, fixtures, smoke  # noqa: E402

ME = str(Path(__file__).resolve())


def run_smoke(mid: str, env=None, timeout: int = 120):
    return subprocess.run([sys.executable, "-I", ME, mid], capture_output=True, text=True, env=env, timeout=timeout)


def selftest() -> int:
    ck = fixtures.Checks("gate_smoke.py --selftest")
    mods = [
        fixtures.module("BOM", gates=["python -I -m bo.bom.run  # existe", "test -d $BO_DATA",
                                      "make -C $BO_REPO gate ID=BOM"]),
        fixtures.module("RUIM", gates=["python -I -m bo.nao_existe.run && touch $BO_DATA/MARCA"]),
        fixtures.module("SEMEXE", gates=["comando-que-nao-existe-xyz --versao"]),
        fixtures.module("ROBO", gates=["robot --version"]),
        fixtures.module("TF", gates=["terraform -chdir=$BO_TMP fmt -check"]),
        fixtures.module("VAR", gates=["python -I $BO_REPO/tools/$NAO_DEFINIDA.py"]),
        fixtures.module("BASHC", gates=["bash -lc 'python -I -m bo.nao_existe.run'"]),
    ]
    with fixtures.sandbox(mods) as root:
        repo, data = root / "repo", root / "data"
        fixtures.commit_files(repo, "[BOM] cria o pacote", {
            "src/bo/bom/__init__.py": "", "src/bo/bom/run.py": "print('roda')\n",
            "Makefile": "gate:\n\t@true\n", **{f"gates/{m['stable_id']}.sh": "#!/bin/sh\n" for m in mods}})
        for m in mods:
            os.chmod(repo / "gates" / f"{m['stable_id']}.sh", 0o755)
        fake = root / "bin"
        fake.mkdir()
        (fake / "robot").write_text("#!/bin/sh\necho 'ROBOT version 1.9.7'\n", encoding="utf-8")
        (fake / "terraform").write_text("#!/bin/sh\necho '{\"terraform_version\": \"1.15.8\"}'\n", encoding="utf-8")
        for f in fake.iterdir():
            os.chmod(f, 0o755)
        env = dict(os.environ, PATH=f"{fake}:{os.environ.get('PATH', '')}")

        r = run_smoke("BOM", env)
        ck.expect("gate com bo.* existente, builtin e make resolve", r.returncode == 0, r.stdout[-400:] + r.stderr[-300:])
        r = run_smoke("RUIM", env)
        ck.expect("gate com módulo bo.* inexistente reprova", r.returncode == 1 and "bo.nao_existe.run" in r.stdout,
                  r.stdout[-300:])
        ck.expect("o gate reprovado não foi executado (sem efeito colateral)", not (data / "MARCA").exists())
        ck.expect("a mensagem diz o que fazer", "não importável" in r.stdout)
        r = run_smoke("SEMEXE", env)
        ck.expect("executável inexistente reprova", r.returncode == 1 and "não está no PATH" in r.stdout)
        r = run_smoke("VAR", env)
        ck.expect("variável indefinida reprova", r.returncode == 1 and "variável indefinida" in r.stdout)
        r = run_smoke("BASHC", env)
        ck.expect("bash -lc '...' é conferido por dentro", r.returncode == 1 and "bo.nao_existe.run" in r.stdout)
        r = run_smoke("ROBO", env)
        ck.expect("ROBOT sem versão fixada reprova", r.returncode == 1 and "sem versão fixada" in r.stdout)
        (repo / "ontology" / "patterns").mkdir(parents=True)
        core.write_json(repo / "ontology" / "patterns" / "toolchain_pins.json", {"robot": {"version": "1.9.7"}})
        r = run_smoke("ROBO", env)
        ck.expect("ROBOT na versão fixada passa", r.returncode == 0, r.stdout[-300:])
        core.write_json(repo / "ontology" / "patterns" / "toolchain_pins.json", {"robot": {"version": "1.9.8"}})
        r = run_smoke("ROBO", env)
        ck.expect("ROBOT em versão diferente da fixada reprova", r.returncode == 1 and "versão fixada" in r.stdout)
        r = run_smoke("TF", env)
        ck.expect("Terraform sem pin reprova", r.returncode == 1)
        (repo / "universe").mkdir()
        core.write_json(repo / "universe" / "pins.json", {"terraform": "1.15.8"})
        r = run_smoke("TF", env)
        ck.expect("Terraform na versão fixada passa", r.returncode == 0, r.stdout[-300:])
        try:
            r = run_smoke("NAO-EXISTE", env, timeout=60)
            ck.expect("módulo inexistente reprova com saída 2 e mensagem clara",
                      r.returncode == 2 and "não existe" in r.stderr, r.stderr[-200:])
        except subprocess.TimeoutExpired:
            ck.expect("módulo inexistente não trava", False, "estourou 60 s")
        os.remove(repo / "gates" / "BOM.sh")
        r = run_smoke("BOM", env)
        ck.expect("gates/<ID>.sh ausente reprova", r.returncode == 1 and "gates/BOM.sh ausente" in r.stdout)
    return ck.report()


def main() -> int:
    args = sys.argv[1:]
    if "--selftest" in args:
        return selftest()
    if len(args) != 1 or args[0].startswith("-"):
        raise core.BoError("uso: gate_smoke.py ID | --selftest", code=2)
    mid = args[0]
    repo = core.bo_repo()
    cat = catalog.load(repo)
    cat.get(mid)  # módulo inexistente: BoError com código 2
    env = core.module_env(mid, repo)
    rep = smoke.Smoker(cat, repo, env).smoke_module(mid)
    core.emit(f"[{core.now()}] gate_smoke {mid}: {len(rep.items)} verificação(ões) (catálogo: {cat.source})")
    for it in rep.items:
        core.emit(it.line())
    bad = sum(not i.ok for i in rep.items)
    core.emit("RESULTADO: " + ("OK" if not bad else f"REPROVADO ({bad} não resolve(m))"))
    return 0 if not bad else 1


if __name__ == "__main__":
    core.run_main(main)
