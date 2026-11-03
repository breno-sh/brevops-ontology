"""Prova de que o plugin_cache/ serve o 'terraform validate' offline dos pilotos.

  python -I -m bo.schema_aws.offline [--keep]

Monta duas configurações em $BO_TMP/offline_validate/ (uma válida, uma com argumento inexistente) e roda
'terraform init -lockfile=readonly' e 'terraform validate -json' com a configuração de instalação do
plugin_cache/ (filesystem_mirror só com o provider fixado, instalação direta desligada), dentro do mesmo
sandbox da bo.schema.extract: env -i, HOME temporário, sem credenciais, rede IP negada nos dois passos,
escrita só na pasta de trabalho. Passa se a válida sai valid=true, a inválida sai valid=false com o erro
de argumento, e o binário que o terraform carregou é o do pino (sha256 de provider.json).
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

from bo.schema import extract

from . import common

OK_TF = """\
resource "aws_s3_bucket" "exemplo" {
  bucket = "bo-exemplo-offline"
}

resource "aws_security_group" "exemplo" {
  name = "bo-exemplo"
  ingress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["10.0.0.0/8"]
  }
}
"""

BAD_TF = """\
resource "aws_s3_bucket" "exemplo" {
  bucket               = "bo-exemplo-offline"
  atributo_inexistente = 1
}
"""


def versions_tf(version: str) -> str:
    return ("terraform {\n  required_providers {\n"
            f'    aws = {{ source = "hashicorp/aws", version = "= {version}" }}\n  }}\n}}\n')


def _run(cmd: list[str], work: Path, tf: Path) -> subprocess.CompletedProcess:
    prof = work / "offline.sb"
    prof.write_text(extract.sandbox_profile([work], network=False), encoding="utf-8")
    env = extract.sandbox_env(work, work / "unused-cache", tf)
    env.pop("TF_PLUGIN_CACHE_DIR")           # instala só do filesystem_mirror do plugin_cache/
    full = ["/usr/bin/sandbox-exec", "-f", str(prof), "/usr/bin/env", "-i",
            *[f"{k}={v}" for k, v in env.items()], *cmd]
    return subprocess.run(full, cwd=work, capture_output=True, check=False)


def case(name: str, body: str, pin: dict, pc: Path, tf: Path, root: Path) -> dict:
    work = root / name
    if work.exists():
        shutil.rmtree(work)
    (work / "home").mkdir(parents=True)
    (work / "tmp").mkdir()
    shutil.copyfile(pc / "terraformrc", work / "home" / "terraformrc")
    shutil.copyfile(pc / "terraform.lock.hcl", work / ".terraform.lock.hcl")
    (work / "versions.tf").write_text(versions_tf(pin["version"]), encoding="utf-8")
    (work / "main.tf").write_text(body, encoding="utf-8")
    init = _run([str(tf), "init", "-backend=false", "-input=false", "-lockfile=readonly", "-no-color"], work, tf)
    rep = {"case": name, "init_rc": init.returncode}
    if init.returncode:
        rep["init_err"] = init.stderr.decode(errors="replace")[-800:]
        return rep
    pdir = work / ".terraform" / "providers" / common.ADDRESS / pin["version"] / pin["os_arch"]
    bins = sorted(pdir.resolve().glob("terraform-provider-*"))
    rep["provider_dir_symlink"] = pdir.is_symlink()
    rep["binary_sha256_ok"] = len(bins) == 1 and common.sha256_file(bins[0]) == pin["binary"]["sha256"]
    v = _run([str(tf), "validate", "-json", "-no-color"], work, tf)
    rep["validate_rc"] = v.returncode
    try:
        doc = json.loads(v.stdout)
    except json.JSONDecodeError:
        rep["validate_err"] = (v.stderr or v.stdout).decode(errors="replace")[-800:]
        return rep
    rep["valid"] = doc.get("valid")
    rep["error_count"] = doc.get("error_count")
    rep["summaries"] = sorted({d.get("summary", "") for d in doc.get("diagnostics") or []})
    return rep


def run(keep: bool = False) -> dict:
    pc = common.plugin_cache_dir()
    pin = json.loads((pc / "provider.json").read_text(encoding="utf-8"))
    tf = Path(shutil.which("terraform") or "")
    if not tf.name:
        raise SystemExit("offline: terraform não está no PATH")
    tf = tf.resolve()
    root = common.bo_tmp() / "offline_validate"
    ok = case("valida", OK_TF, pin, pc, tf, root)
    bad = case("invalida", BAD_TF, pin, pc, tf, root)
    passed = (ok.get("init_rc") == 0 and ok.get("valid") is True and ok.get("error_count") == 0
              and ok.get("binary_sha256_ok") is True
              and bad.get("init_rc") == 0 and bad.get("valid") is False
              and "Unsupported argument" in bad.get("summaries", [])
              and bad.get("binary_sha256_ok") is True)
    if not keep:
        shutil.rmtree(root, ignore_errors=True)
    return {"provider": pin["address"], "version": pin["version"], "network": "IP negado (init e validate)",
            "cases": [ok, bad], "veredito": "PASS" if passed else "FAIL"}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="bo.schema_aws.offline", description=__doc__.split("\n")[0])
    ap.add_argument("--keep", action="store_true", help="não apaga a pasta de trabalho")
    ap.add_argument("--out", type=Path)
    a = ap.parse_args(argv)
    rep = run(a.keep)
    if a.out:
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(json.dumps(rep, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    for c in rep["cases"]:
        print(f"  {c['case']}: init rc {c.get('init_rc')}, valid {c.get('valid')}, erros {c.get('error_count')}, "
              f"binário do pino {c.get('binary_sha256_ok')}, {c.get('summaries', c.get('init_err', ''))}")
    print(f"offline validate {rep['provider']} {rep['version']}: {rep['veredito']}")
    return 0 if rep["veredito"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
