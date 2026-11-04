"""terraform validate OFFLINE do HCL renderizado (google fixado), num sandbox sem credenciais (decisão D1).

  python -I -m bo.harness.google.tf_validate DIR [DIR ...]

Cada DIR é uma saída do bo.harness.google.render (versions.tf + um .tf por plano RENDERED). Sandbox: env -i (PATH
mínimo com o terraform fixado), HOME, TF_DATA_DIR e TMPDIR dentro de $BO_TMP, nenhuma variável AWS_/GOOGLE_/
ARM_/AZURE_/OCI_/TF_VAR_/CLOUDSDK_. O provider vem só do cache assinado do SCHEMA-GCP
($BO_DATA/SCHEMA-GCP/plugin_cache, binário conferido contra SIGNED.sha256) por -plugin-dir, com o lock em modo
somente leitura e -backend=false. Nada de plan nem apply. Sai 0 só se todo DIR valida.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

from . import common as C

CRED_PREFIXES = ("AWS_", "GOOGLE_", "GCLOUD_", "CLOUDSDK_", "ARM_", "AZURE_", "OCI_", "TF_VAR_")


class SandboxError(RuntimeError):
    pass


def terraform_bin() -> str:
    tf = shutil.which("terraform")
    if not tf:
        raise SandboxError("terraform não está no PATH")
    out = subprocess.run([tf, "version", "-json"], capture_output=True, text=True, timeout=60,
                         env={"PATH": "/usr/bin:/bin", "HOME": "/nonexistent", "CHECKPOINT_DISABLE": "1"})
    v = json.loads(out.stdout)["terraform_version"]
    if v != C.pins()["terraform"]["version"]:
        raise SandboxError(f"terraform {v} != fixado {C.pins()['terraform']['version']}")
    return tf


def plugin_dir() -> tuple[Path, Path, str]:
    """(pasta para -plugin-dir, lock, sha256 do binário conferido)."""
    pc = C.data() / "SCHEMA-GCP" / "plugin_cache"
    sig = pc / "SIGNED.sha256"
    if not sig.exists():
        raise SandboxError("SCHEMA-GCP/plugin_cache sem SIGNED.sha256")
    for line in sig.read_text(encoding="utf-8").splitlines():
        h, rel = line.split(None, 1)
        if "terraform-provider-google" in rel:
            got = hashlib.sha256((pc / rel.strip()).read_bytes()).hexdigest()
            if got != h:
                raise SandboxError("sha256 do provider google não confere com SIGNED.sha256")
            return pc, pc / "terraform.lock.hcl", got
    raise SandboxError("SIGNED.sha256 sem o binário do provider google")


def sandbox_env(work: Path, tf: str) -> dict:
    home = work / "home"
    home.mkdir(parents=True, exist_ok=True)
    (home / ".terraformrc").write_text("disable_checkpoint = true\n", encoding="utf-8")
    sk = C.tmp() / "sk"            # caminho curto: o socket do plugin tem limite de 104 caracteres no macOS
    sk.mkdir(parents=True, exist_ok=True)
    env = {"PATH": f"{Path(tf).parent}:/usr/bin:/bin", "HOME": str(home), "TMPDIR": str(sk),
           "TF_IN_AUTOMATION": "1", "CHECKPOINT_DISABLE": "1", "TF_CLI_CONFIG_FILE": str(home / ".terraformrc"),
           "TF_DATA_DIR": str(work / ".tfdata")}
    if any(k.startswith(CRED_PREFIXES) for k in env):
        raise SandboxError("variável de credencial no sandbox")
    return env


def validate_dir(root: Path) -> dict:
    tf = terraform_bin()
    pdir, lock, sha = plugin_dir()
    work = C.tmp() / "tf_validate" / root.name
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    env = sandbox_env(work, tf)
    shutil.copyfile(lock, root / ".terraform.lock.hcl")
    try:
        init = subprocess.run([tf, "init", "-backend=false", "-input=false", "-lockfile=readonly",
                               f"-plugin-dir={pdir}", "-no-color"], cwd=root, env=env, capture_output=True,
                              text=True, timeout=600)
        if init.returncode != 0:
            return {"dir": root.name, "ok": False, "stage": "init", "detail": (init.stderr or init.stdout)[-800:]}
        val = subprocess.run([tf, "validate", "-json", "-no-color"], cwd=root, env=env, capture_output=True,
                             text=True, timeout=600)
    finally:
        (root / ".terraform.lock.hcl").unlink(missing_ok=True)
        shutil.rmtree(work / ".tfdata", ignore_errors=True)
    try:
        doc = json.loads(val.stdout)
    except json.JSONDecodeError:
        return {"dir": root.name, "ok": False, "stage": "validate", "detail": (val.stderr or val.stdout)[-800:]}
    diags = [{"severity": d.get("severity"), "summary": d.get("summary"), "detail": (d.get("detail") or "")[:300]}
             for d in doc.get("diagnostics", [])]
    return {"dir": root.name, "ok": bool(doc.get("valid")), "stage": "validate", "provider_sha256": sha,
            "error_count": doc.get("error_count"), "diagnostics": diags[:20]}


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        print("uso: python -I -m bo.harness.google.tf_validate DIR [DIR ...]", file=sys.stderr)
        return 2
    res = [validate_dir(Path(d).resolve()) for d in argv]
    for r in res:
        print(f"[{C.now()}] tf_validate {r['dir']}: {'válido' if r['ok'] else 'INVÁLIDO'} ({r['stage']})")
        for d in r.get("diagnostics", [])[:5]:
            print(f"  {d['severity']}: {d['summary']} {d['detail'][:150]}")
        if not r["ok"] and r.get("detail"):
            print("  " + r["detail"][-300:])
    return 0 if res and all(r["ok"] for r in res) else 1


if __name__ == "__main__":
    sys.exit(main())
