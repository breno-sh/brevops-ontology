"""terraform fmt e validate offline, num sandbox sem credenciais (decisão D1 do Breno, 02/11).

env -i com PATH mínimo, HOME temporário em $BO_TMP, sem ~/.aws, ~/.config/gcloud, ~/.azure, ~/.oci e sem
variável de credencial; provider só do mirror local (binário assinado, conferido pelo lock dos SCHEMA-*).
Nada de plan, apply ou refresh: só fmt, init -backend=false e validate.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from . import PROVIDER_SCHEMA_DIR, data_root, tmp_root

MIRROR = "downloads/terraform-registry/plugin-cache"
CRED_PREFIXES = ("AWS_", "GOOGLE_", "ARM_", "OCI_", "TF_VAR_", "AZURE_", "CLOUDSDK_")


def terraform_bin() -> str:
    p = shutil.which("terraform")
    if not p:
        raise RuntimeError("terraform não está no PATH (pino em universe/pins.json)")
    return p


def sandbox_env(work: Path, provider_source: str | None = None, mirror: Path | None = None) -> dict:
    home = work / "home"
    home.mkdir(parents=True, exist_ok=True)
    rc = home / ".terraformrc"
    if provider_source:
        rc.write_text(
            "provider_installation {\n  filesystem_mirror {\n"
            f'    path    = "{mirror or (data_root() / MIRROR)}"\n    include = ["{provider_source}"]\n  }}\n'
            '  direct {\n    exclude = ["registry.terraform.io/*/*"]\n  }\n}\n', encoding="utf-8")
    else:
        rc.write_text("", encoding="utf-8")
    env = {"PATH": "/usr/bin:/bin", "HOME": str(home), "TMPDIR": str(work), "TF_IN_AUTOMATION": "1",
           "TF_INPUT": "0", "CHECKPOINT_DISABLE": "1", "TF_CLI_CONFIG_FILE": str(rc)}
    assert not any(k.startswith(CRED_PREFIXES) for k in env)
    return env


def fmt_text(text: str) -> str:
    work = tmp_root() / "fmt"
    work.mkdir(parents=True, exist_ok=True)
    r = subprocess.run([terraform_bin(), "fmt", "-no-color", "-"], input=text, capture_output=True, text=True,
                       env=sandbox_env(work), timeout=300)
    if r.returncode != 0:
        raise RuntimeError("terraform fmt reprovou: " + r.stderr[-1500:])
    return r.stdout


SOURCES = {"aws": "registry.terraform.io/hashicorp/aws", "google": "registry.terraform.io/hashicorp/google",
           "azurerm": "registry.terraform.io/hashicorp/azurerm", "oci": "registry.terraform.io/oracle/oci"}


def validate(provider: str, main_tf: Path) -> dict:
    """init -backend=false com o lock do SCHEMA-* e validate -json; devolve o JSON do validate."""
    work = tmp_root() / f"validate_{provider}"
    if work.exists():
        shutil.rmtree(work)
    root = work / "root"
    root.mkdir(parents=True)
    shutil.copyfile(main_tf, root / "main.tf")
    lock = data_root() / PROVIDER_SCHEMA_DIR[provider] / "plugin_cache" / "terraform.lock.hcl"
    shutil.copyfile(lock, root / ".terraform.lock.hcl")
    own = data_root() / PROVIDER_SCHEMA_DIR[provider] / "plugin_cache"
    mirror = own if (own / "registry.terraform.io").is_dir() else None
    env = sandbox_env(work, SOURCES[provider], mirror)
    tf = terraform_bin()
    i = subprocess.run([tf, "init", "-backend=false", "-input=false", "-no-color", "-lockfile=readonly"],
                       cwd=root, env=env, capture_output=True, text=True, timeout=900)
    if i.returncode != 0:
        return {"valid": False, "init_failed": True, "diagnostics": [{"summary": "init", "detail": i.stderr[-1500:]}]}
    v = subprocess.run([tf, "validate", "-json", "-no-color"], cwd=root, env=env, capture_output=True, text=True,
                       timeout=900)
    try:
        return json.loads(v.stdout)
    except json.JSONDecodeError:
        return {"valid": False, "diagnostics": [{"summary": "saída não JSON", "detail": v.stderr[-1500:]}]}
