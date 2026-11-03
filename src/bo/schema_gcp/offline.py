"""Uso OFFLINE do plugin_cache guardado: o mesmo caminho que o 'terraform validate' dos pilotos vai seguir.

Monta uma pasta em $BO_TMP com versions.tf (google na versão do pin) e o lock do plugin_cache, aponta o
terraform para o plugin_cache como filesystem_mirror (layout desempacotado) e roda, sob o sandbox da biblioteca
(bo.schema.extract.run_sandboxed: env -i, HOME temporário, sandbox-exec sem credenciais) e SEM rede IP:
  terraform init -backend=false -input=false -lockfile=readonly   (confere o h1 do lock na pasta do provider)
  terraform validate -json                                        (o provider carrega e responde o schema)
  terraform providers schema -json                                (a saída crua, comparada ao sha do pin)
Nada é baixado; se o plugin_cache não bastar, o init reprova.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

from bo.schema import extract as X
from bo.schema import lockfile

from . import common as C


def terraformrc(mirror: Path) -> str:
    m = str(mirror.resolve()).replace('"', '\\"')
    return ("provider_installation {\n"
            f'  filesystem_mirror {{\n    path    = "{m}"\n    include = ["{C.ADDRESS}"]\n  }}\n'
            f'  direct {{\n    exclude = ["{C.ADDRESS}"]\n  }}\n'
            "}\n")


def run(work: Path, mirror: Path | None = None, terraform: str | None = None) -> dict:
    """Extração offline; devolve {'raw': bytes, 'sha256', 'terraform_version', 'validate'}."""
    mirror = mirror or C.plugin_cache()
    lp = lockfile.find(lockfile.read(mirror / "terraform.lock.hcl"), C.SOURCE)
    tf = Path(shutil.which(terraform or "terraform") or "")
    if not tf.name:
        raise SystemExit("offline: terraform não está no PATH")
    tf = tf.resolve()
    if work.exists():
        shutil.rmtree(work)
    cache = work / "cache"
    for d in (work / "home", work / "tmp", cache):
        d.mkdir(parents=True)
    (work / "home" / "terraformrc").write_text(terraformrc(mirror), encoding="utf-8")
    (work / "versions.tf").write_text(X.versions_tf(lp), encoding="utf-8")
    (work / ".terraform.lock.hcl").write_text(lockfile.render([lp]), encoding="utf-8")

    def step(args: list[str], what: str):
        r = X.run_sandboxed([str(tf), *args], work, cache, tf, network=False, capture=True)
        if r.returncode:
            raise SystemExit(f"offline: {what} falhou (rc {r.returncode}): {(r.stderr or b'').decode()[-1500:]}")
        return r

    tv = json.loads(step(["version", "-json"], "terraform version").stdout)["terraform_version"]
    step(["init", "-backend=false", "-input=false", "-lockfile=readonly", "-no-color"], "terraform init offline")
    val = json.loads(step(["validate", "-json", "-no-color"], "terraform validate").stdout)
    if not val.get("valid"):
        raise SystemExit(f"offline: terraform validate não válido: {val.get('diagnostics')}")
    raw = step(["providers", "schema", "-json"], "providers schema").stdout
    return {"raw": raw, "sha256": hashlib.sha256(raw).hexdigest(), "terraform_version": tv,
            "validate": {"valid": val["valid"], "error_count": val.get("error_count", 0),
                         "warning_count": val.get("warning_count", 0)}}
