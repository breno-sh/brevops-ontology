"""Terraform offline num sandbox sem credenciais: só `fmt` e `init -backend=false` + `validate` (decisão D1).

O ambiente é montado do zero (env -i): HOME temporário dentro de $BO_TMP, PATH mínimo com o terraform fixado,
CHECKPOINT_DISABLE, nenhuma variável OCI_*, TF_VAR_*, AWS_*, GOOGLE_*, ARM_*; nenhum ~/.oci é alcançável porque o
HOME é outro. O init usa -plugin-dir com o binário assinado já baixado (sem rede). apply, plan, import e destroy
não existem aqui.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from . import TERRAFORM_VERSION, plugin_cache, tmp_root

ALLOWED = ("fmt", "init", "validate", "version")


class SandboxError(RuntimeError):
    pass


def terraform_bin() -> Path:
    p = shutil.which("terraform")
    if not p:
        raise SandboxError("terraform não está no PATH")
    return Path(p).resolve()


@dataclass
class Run:
    args: list
    rc: int
    out: str
    err: str


def env(home: Path) -> dict:
    tf = terraform_bin()
    return {
        "HOME": str(home), "PATH": f"{tf.parent}:/usr/bin:/bin", "TMPDIR": str(home),
        "CHECKPOINT_DISABLE": "1", "TF_IN_AUTOMATION": "1", "TF_INPUT": "0", "LANG": "C.UTF-8",
    }


def run(args: list[str], cwd: Path, timeout: int = 600) -> Run:
    if not args or args[0] not in ALLOWED:
        raise SandboxError(f"subcomando proibido no sandbox: {args[:1]}")
    if args[0] == "init" and "-backend=false" not in args:
        raise SandboxError("init só com -backend=false")
    home = tmp_root() / "tf_sandbox_home"
    home.mkdir(parents=True, exist_ok=True)
    p = subprocess.run([str(terraform_bin()), *args], cwd=str(cwd), env=env(home), capture_output=True, text=True,
                       timeout=timeout)
    return Run(args, p.returncode, p.stdout, p.stderr)


def version_ok() -> bool:
    r = run(["version"], tmp_root())
    return f"Terraform v{TERRAFORM_VERSION}" in r.out


def fmt_check(d: Path) -> Run:
    return run(["fmt", "-check", "-recursive", "-diff"], d)


def init_validate(d: Path) -> tuple[Run, Run | None]:
    cache = plugin_cache()
    if not cache.exists():
        raise SandboxError(f"binário do provider ausente em {cache} (refaça o download do D1)")
    i = run(["init", "-backend=false", "-input=false", "-no-color", f"-plugin-dir={cache}"], d)
    if i.rc != 0:
        return i, None
    v = run(["validate", "-no-color", "-json"], d)
    return i, v


def provider_env_clean() -> list[str]:
    """Nomes de variáveis do ambiente ATUAL que dariam credencial a um provider (relatório; o sandbox não as passa)."""
    pref = ("OCI_", "TF_VAR_", "AWS_", "GOOGLE_", "ARM_", "AZURE_")
    return sorted(k for k in os.environ if k.startswith(pref))
