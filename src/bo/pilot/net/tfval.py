"""terraform validate OFFLINE no provider fixado, num sandbox sem credenciais (decisão D1 do Breno).

Sandbox: env -i (só PATH mínimo com o terraform fixado), HOME e TF_DATA_DIR temporários em $BO_TMP, nenhuma
variável AWS_/GOOGLE_/ARM_/AZURE_/OCI_/TF_VAR_, nenhum ~/.aws, ~/.config/gcloud, ~/.azure, ~/.oci. O provider vem
só do cache local do SCHEMA-<provedor> (plugin_cache: lock com h1/zh e binário assinado conferido pelo sha256 do
provider.json ou do SIGNED.sha256), por -plugin-dir; -backend=false; lock em modo somente leitura. Nada de plan ou
apply. Terraform na versão de universe/pins.json.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

SCHEMA_DIR = {"aws": "SCHEMA-AWS", "google": "SCHEMA-GCP", "azurerm": "SCHEMA-AZURE", "oci": "SCHEMA-OCI"}
SOURCE = {"aws": "hashicorp/aws", "google": "hashicorp/google", "azurerm": "hashicorp/azurerm", "oci": "oracle/oci"}
CRED_PREFIXES = ("AWS_", "GOOGLE_", "ARM_", "AZURE_", "OCI_", "TF_VAR_", "CLOUDSDK_")


class SandboxError(RuntimeError):
    pass


def data_root(base: Path | None = None) -> Path:
    return Path(base or os.environ.get("BO_DATA", "/Users/breno/doutorado/brevops-data"))


def pins(repo: Path) -> dict:
    return json.loads((repo / "universe" / "pins.json").read_text(encoding="utf-8"))


def terraform_bin(repo: Path) -> str:
    tf = shutil.which("terraform")
    if not tf:
        raise SandboxError("terraform não está no PATH")
    out = subprocess.run([tf, "version", "-json"], capture_output=True, text=True, timeout=60,
                         env={"PATH": "/usr/bin:/bin", "HOME": "/nonexistent", "CHECKPOINT_DISABLE": "1"})
    v = json.loads(out.stdout)["terraform_version"]
    want = pins(repo)["terraform"]["version"]
    if v != want:
        raise SandboxError(f"terraform {v} != fixado {want}")
    return tf


def plugin_dir(provider: str, base: Path) -> tuple[Path, Path, dict]:
    """(pasta para -plugin-dir, lock, prova do pino). Confere o sha256 do binário antes de usar."""
    pc = base / SCHEMA_DIR[provider] / "plugin_cache"
    lock = pc / "terraform.lock.hcl"
    if (pc / "provider.json").exists():
        pin = json.loads((pc / "provider.json").read_text(encoding="utf-8"))
        b = Path(pin["binary"]["path"].replace("$BO_DATA", str(base)))
        got = hashlib.sha256(b.read_bytes()).hexdigest()
        if got != pin["binary"]["sha256"]:
            raise SandboxError(f"{provider}: sha256 do binário {got[:12]} != pino {pin['binary']['sha256'][:12]}")
        mirror = base / "downloads" / "terraform-registry" / "plugin-cache"
        proof = {"binary_sha256": got, "version": pin["version"], "pin_file": f"$BO_DATA/{SCHEMA_DIR[provider]}/plugin_cache/provider.json"}
        return mirror, lock, proof
    sig = pc / "SIGNED.sha256"
    if not sig.exists():
        raise SandboxError(f"{provider}: plugin_cache sem provider.json nem SIGNED.sha256")
    for line in sig.read_text(encoding="utf-8").splitlines():
        h, rel = line.split(None, 1)
        if "terraform-provider-" in rel:
            got = hashlib.sha256((pc / rel.strip()).read_bytes()).hexdigest()
            if got != h:
                raise SandboxError(f"{provider}: sha256 do binário não confere com SIGNED.sha256")
            proof = {"binary_sha256": got, "version": rel.split("/")[3],
                     "pin_file": f"$BO_DATA/{SCHEMA_DIR[provider]}/plugin_cache/SIGNED.sha256"}
            return pc, lock, proof
    raise SandboxError(f"{provider}: SIGNED.sha256 sem binário")


def sandbox_env(work: Path, tf: str) -> dict:
    home = work / "home"
    home.mkdir(parents=True, exist_ok=True)
    (home / ".terraformrc").write_text("disable_checkpoint = true\n", encoding="utf-8")
    # TMPDIR curto: o socket unix do plugin estoura o limite de 104 caracteres do macOS com caminho longo
    sk = Path(os.environ.get("BO_TMP", str(work))) / "sk" / str(os.getpid())
    sk.mkdir(parents=True, exist_ok=True)
    env = {"PATH": f"{Path(tf).parent}:/usr/bin:/bin", "HOME": str(home), "TMPDIR": str(sk),
           "TF_IN_AUTOMATION": "1", "CHECKPOINT_DISABLE": "1", "TF_CLI_CONFIG_FILE": str(home / ".terraformrc"),
           "TF_DATA_DIR": str(work / ".tfdata")}
    for k in env:
        if k.startswith(CRED_PREFIXES):
            raise SandboxError(f"variável de credencial no sandbox: {k}")
    for d in (".aws", ".config/gcloud", ".azure", ".oci"):
        if (home / d).exists():
            raise SandboxError(f"{d} no HOME do sandbox")
    return env


def validate_dir(root: Path, provider: str, repo: Path, base: Path, work: Path) -> dict:
    tf = terraform_bin(repo)
    pdir, lock, proof = plugin_dir(provider, base)
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    env = sandbox_env(work, tf)
    shutil.copyfile(lock, root / ".terraform.lock.hcl")
    init = subprocess.run([tf, "init", "-backend=false", "-input=false", "-lockfile=readonly",
                           f"-plugin-dir={pdir}", "-no-color"], cwd=root, env=env, capture_output=True, text=True,
                          timeout=600)
    if init.returncode != 0:
        return {"ok": False, "stage": "init", "detail": (init.stderr or init.stdout)[-800:], "proof": proof}
    val = subprocess.run([tf, "validate", "-json", "-no-color"], cwd=root, env=env, capture_output=True, text=True,
                         timeout=600)
    try:
        doc = json.loads(val.stdout)
    except json.JSONDecodeError:
        return {"ok": False, "stage": "validate", "detail": (val.stderr or val.stdout)[-800:], "proof": proof}
    diags = [{"severity": d.get("severity"), "summary": d.get("summary"), "detail": (d.get("detail") or "")[:300],
              "file": (d.get("range") or {}).get("filename")} for d in doc.get("diagnostics", [])]
    return {"ok": bool(doc.get("valid")), "stage": "validate", "error_count": doc.get("error_count"),
            "warning_count": doc.get("warning_count"), "diagnostics": diags[:50], "proof": proof}
