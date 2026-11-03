"""Terraform só em fmt e validate, num sandbox sem credenciais (decisão D1).

env -i com HOME temporário em $BO_TMP, sem variável ARM_*/AZURE_*/AWS_*/GOOGLE_*, sem ~/.azure etc.
Qualquer outro subcomando é recusado aqui: o apply real mora no executor, atrás das travas de nuvem. O init só
existe dentro de validate_offline: -plugin-dir (cache local do provider assinado, sem registro), -backend=false
e lock fixado em modo somente leitura.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from ._common import HarnessError, tmp_dir

ALLOWED = {"fmt", "validate", "version"}
PLUGIN_DIR_REL = ("downloads", "terraform-registry", "plugin-cache")


def terraform_bin() -> str:
    tf = shutil.which("terraform")
    if not tf:
        raise HarnessError("terraform não está no PATH")
    return tf


def sandbox_env() -> dict:
    home = tmp_dir() / "tf-home"
    home.mkdir(parents=True, exist_ok=True)
    tmp = tmp_dir() / "tf-tmp"
    tmp.mkdir(parents=True, exist_ok=True)
    return {
        "HOME": str(home),
        "PATH": "/usr/bin:/bin:" + str(Path(terraform_bin()).parent),
        "TMPDIR": str(tmp),
        "LANG": "C.UTF-8",
        "CHECKPOINT_DISABLE": "1",
        "TF_IN_AUTOMATION": "1",
        "TF_CLI_CONFIG_FILE": os.devnull,
    }


def run(subcmd: str, args: list[str], chdir: Path, timeout: int = 300) -> subprocess.CompletedProcess:
    if subcmd not in ALLOWED:
        raise HarnessError(f"terraform {subcmd} recusado: offline só fmt/validate")
    cmd = [terraform_bin(), f"-chdir={chdir}", subcmd, *args]
    return subprocess.run(cmd, env=sandbox_env(), capture_output=True, text=True, timeout=timeout)


def fmt_check(chdir: Path) -> tuple[bool, str]:
    p = run("fmt", ["-check", "-diff", "-recursive"], chdir)
    return p.returncode == 0, (p.stdout + p.stderr)


def fmt_text(text: str, work: Path) -> str:
    """Formata `text` com o terraform fmt e devolve o resultado (para comparar com o escritor)."""
    work.mkdir(parents=True, exist_ok=True)
    f = work / "probe.tf"
    f.write_text(text, encoding="utf-8")
    p = run("fmt", ["-list=false", "-write=true", "probe.tf"], work)
    if p.returncode != 0:
        raise HarnessError("terraform fmt reprovou o texto: " + (p.stderr or p.stdout)[-400:])
    return f.read_text(encoding="utf-8")


def plugin_dir() -> Path:
    from ._common import data_root
    return data_root().joinpath(*PLUGIN_DIR_REL)


def validate_offline(module_dir: Path, lock: Path) -> tuple[bool, str]:
    """Copia o módulo para $BO_TMP, init sem rede (-plugin-dir) e terraform validate. Devolve (ok, saída)."""
    work = tmp_dir() / "validate" / module_dir.name
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    for f in module_dir.glob("*.tf"):
        shutil.copy2(f, work / f.name)
    shutil.copy2(lock, work / ".terraform.lock.hcl")
    cmd = [terraform_bin(), f"-chdir={work}", "init", "-input=false", "-backend=false", "-lockfile=readonly",
           f"-plugin-dir={plugin_dir()}"]
    p = subprocess.run(cmd, env=sandbox_env(), capture_output=True, text=True, timeout=600)
    if p.returncode != 0:
        return False, "init: " + (p.stderr or p.stdout)[-800:]
    p = run("validate", ["-no-color"], work)
    return p.returncode == 0, (p.stdout + p.stderr)[-800:]
