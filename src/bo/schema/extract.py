"""Extração de 'terraform providers schema -json' num sandbox sem credenciais (decisão D1).

  python -I -m bo.schema.extract --source hashicorp/aws --lock ARQ.terraform.lock.hcl [--out DIR]

O que roda, e como:
  1. pasta de trabalho em $BO_TMP/extract/<nome>-<versão>/ com um versions.tf de um provider só, na versão
     exata do lock, e o recorte do lock com os hashes dele;
  2. 'terraform init -backend=false -input=false -lockfile=readonly': baixa o pacote ASSINADO do registro
     (o terraform confere a assinatura e reprova se o pacote não bater com um hash do lock);
  3. 'terraform providers schema -json' SEM rede: só o GetProviderSchema do plugin, sem configurar o provider.
Os dois passos rodam com env -i (só PATH, HOME temporário, cache de plugin e TMPDIR) e sob sandbox-exec, que
nega leitura de ~/.aws, ~/.config/gcloud, ~/.azure, ~/.oci, ~/.ssh, ~/brevops-keys, ~/.config/bo, ~/.terraform.d e
da partição selada, e nega escrita fora da pasta de trabalho e do cache de plugin.

Saída (dado derivado de download não confiável, fora do git): $BO_DATA/downloads/tfschema/<nome>-<versão>/
  schema.json.gz       a saída do terraform, byte a byte (gzip determinístico, mtime 0)
  schema.json.sha256   sha256 da saída crua ('<sha>  schema.json')
  receipt.json         versão do terraform, hashes do lock, sha256 do binário do provider, contagens, sandbox
  SOURCE.txt           de onde veio e como foi feito
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from . import lockfile

HOME = Path.home()
DENY_READ = [HOME / ".aws", HOME / ".config" / "gcloud", HOME / ".azure", HOME / ".oci", HOME / ".ssh",
             HOME / "brevops-keys", HOME / ".config" / "bo", HOME / ".terraform.d", HOME / ".terraformrc"]


def bo_data() -> Path:
    return Path(os.environ.get("BO_DATA", "/Users/breno/doutorado/brevops-data"))


def bo_tmp() -> Path:
    return Path(os.environ.get("BO_TMP") or bo_data() / "tmp" / "SCHEMALIB")


def default_out(name: str, version: str) -> Path:
    return bo_data() / "downloads" / "tfschema" / f"{name}-{version}"


def default_cache() -> Path:
    return bo_data() / "downloads" / "terraform-registry" / "plugin-cache"


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _sb_path(p: Path) -> str:
    return str(p.resolve()).replace('"', '\\"')


def sandbox_profile(writable: list[Path], network: bool) -> str:
    deny = list(DENY_READ) + [bo_data() / "SPLIT" / "sealed"]
    lines = ["(version 1)", "(allow default)"]
    if not network:
        # sem rede IP; o soquete unix local do go-plugin (handshake terraform <-> provider) continua permitido
        lines += ["(deny network-outbound (remote ip))", "(deny network-bind (local ip))"]
    lines.append("(deny file-read* " + " ".join(f'(subpath "{_sb_path(p)}")' for p in deny) + ")")
    lines.append("(deny file-write*)")
    allow = writable + [Path("/dev"), Path("/private/var/folders")]
    lines.append("(allow file-write* " + " ".join(f'(subpath "{_sb_path(p)}")' for p in allow) + ")")
    return "\n".join(lines) + "\n"


def sandbox_env(work: Path, cache: Path, terraform: Path) -> dict:
    return {
        "PATH": f"{terraform.parent}:/usr/bin:/bin",
        "HOME": str(work / "home"),
        "TMPDIR": str(work / "tmp"),
        "TF_PLUGIN_CACHE_DIR": str(cache),
        "TF_CLI_CONFIG_FILE": str(work / "home" / "terraformrc"),
        "TF_IN_AUTOMATION": "1",
        "CHECKPOINT_DISABLE": "1",
        "LANG": "C",
    }


def run_sandboxed(cmd: list[str], work: Path, cache: Path, terraform: Path, network: bool,
                  capture: bool = False) -> subprocess.CompletedProcess:
    prof = work / ("net.sb" if network else "offline.sb")
    prof.write_text(sandbox_profile([work, cache], network), encoding="utf-8")
    full = ["/usr/bin/sandbox-exec", "-f", str(prof), "/usr/bin/env", "-i",
            *[f"{k}={v}" for k, v in sandbox_env(work, cache, terraform).items()], *cmd]
    return subprocess.run(full, cwd=work, stdout=subprocess.PIPE if capture else None,
                          stderr=subprocess.PIPE, check=False)


def versions_tf(lp: lockfile.LockedProvider) -> str:
    return ("terraform {\n  required_providers {\n"
            f'    {lp.name} = {{ source = "{lp.source}", version = "= {lp.version}" }}\n'
            "  }\n}\n")


def extract(source: str, lock: Path, out: Path | None = None, cache: Path | None = None,
            terraform: str | None = None, version: str | None = None) -> dict:
    from bo.repo.core import now
    lp = lockfile.find(lockfile.read(lock), source)
    if version and version != lp.version:
        raise SystemExit(f"extract: --version {version} != versão do lock {lp.version}")
    tf = Path(shutil.which(terraform or "terraform") or "")
    if not tf.name:
        raise SystemExit("extract: terraform não está no PATH")
    tf = tf.resolve()
    out = out or default_out(lp.name, lp.version)
    cache = cache or default_cache()
    work = bo_tmp() / "extract" / f"{lp.name}-{lp.version}"
    if work.exists():
        shutil.rmtree(work)
    for d in (work / "home", work / "tmp", cache):
        d.mkdir(parents=True, exist_ok=True)
    (work / "home" / "terraformrc").write_text("", encoding="utf-8")
    (work / "versions.tf").write_text(versions_tf(lp), encoding="utf-8")
    (work / ".terraform.lock.hcl").write_text(lockfile.render([lp]), encoding="utf-8")
    started = now()

    tv = run_sandboxed([str(tf), "version", "-json"], work, cache, tf, network=False, capture=True)
    if tv.returncode:
        raise SystemExit(f"extract: terraform version falhou: {tv.stderr.decode()[-500:]}")
    tf_version = json.loads(tv.stdout)["terraform_version"]

    init = run_sandboxed([str(tf), "init", "-backend=false", "-input=false", "-lockfile=readonly", "-no-color"],
                         work, cache, tf, network=True, capture=True)
    if init.returncode:
        raise SystemExit(f"extract: terraform init falhou (rc {init.returncode}): "
                         f"{(init.stderr or b'').decode()[-1500:]}")
    res = run_sandboxed([str(tf), "providers", "schema", "-json"], work, cache, tf, network=False, capture=True)
    if res.returncode:
        raise SystemExit(f"extract: providers schema falhou (rc {res.returncode}): {res.stderr.decode()[-1500:]}")
    raw = res.stdout
    doc = json.loads(raw)
    ps = (doc.get("provider_schemas") or {}).get(lp.address)
    if ps is None:
        raise SystemExit(f"extract: saída sem provider_schemas[{lp.address}]")

    bins = sorted((work / ".terraform" / "providers" / lp.address / lp.version).glob("*/terraform-provider-*"))
    if len(bins) != 1:
        raise SystemExit(f"extract: esperava 1 binário do provider, achei {len(bins)}")
    binary = bins[0].resolve()

    out.mkdir(parents=True, exist_ok=True)
    sha = hashlib.sha256(raw).hexdigest()
    with open(out / "schema.json.gz", "wb") as f:
        with gzip.GzipFile(filename="schema.json", mode="wb", fileobj=f, mtime=0, compresslevel=9) as g:
            g.write(raw)
    (out / "schema.json.sha256").write_text(f"{sha}  schema.json\n", encoding="utf-8")
    receipt = {
        "schema": "bo.schema_extract/1",
        "provider": {"address": lp.address, "source": lp.source, "name": lp.name, "version": lp.version},
        "lock": {"path": str(lock), "sha256": sha256_file(lock), "hashes": list(lp.hashes),
                 "mode": "-lockfile=readonly (o init reprova pacote fora destes hashes)"},
        "terraform": {"version": tf_version, "path": str(tf), "sha256": sha256_file(tf)},
        "provider_binary": {"file": binary.name, "os_arch": bins[0].parent.name, "sha256": sha256_file(binary),
                            "bytes": binary.stat().st_size},
        "schema_json": {"sha256": sha, "bytes": len(raw), "format_version": doc.get("format_version"),
                        "resource_types": len(ps.get("resource_schemas") or {}),
                        "data_sources": len(ps.get("data_source_schemas") or {})},
        "sandbox": {"env": sorted(sandbox_env(work, cache, tf)), "deny_read": [str(p) for p in DENY_READ]
                    + ["$BO_DATA/SPLIT/sealed"], "network": {"init": "permitida (registro)", "schema": "IP negado (só soquete unix local do plugin)"},
                    "write": ["pasta de trabalho em $BO_TMP", "cache de plugin em $BO_DATA/downloads"]},
        "started_at": started,
        "finished_at": now(),
    }
    (out / "receipt.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    (out / "SOURCE.txt").write_text(
        f"Saída de 'terraform providers schema -json' para {lp.source} {lp.version}.\n"
        f"Pacote assinado baixado de https://{lp.address.split('/')[0]} por terraform {tf_version} "
        "(init -lockfile=readonly), binário executado só para o schema, sem rede e sem credenciais "
        "(env -i, HOME temporário, sandbox-exec).\n"
        f"Lock de origem: {lock}\nGerado por: python -I -m bo.schema.extract (módulo SCHEMALIB).\n"
        "Dado não confiável: lido como JSON, nunca executado.\n", encoding="utf-8")
    return receipt


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="bo.schema.extract", description=__doc__.split("\n")[0])
    ap.add_argument("--source", required=True, help="hashicorp/aws, oracle/oci, ...")
    ap.add_argument("--lock", required=True, type=Path, help=".terraform.lock.hcl que fixa a versão e os hashes")
    ap.add_argument("--version", help="confere que o lock fixa esta versão")
    ap.add_argument("--out", type=Path)
    ap.add_argument("--plugin-cache", type=Path)
    ap.add_argument("--terraform")
    a = ap.parse_args(argv)
    r = extract(a.source, a.lock, a.out, a.plugin_cache, a.terraform, a.version)
    print(json.dumps({"provider": r["provider"], "schema_json": r["schema_json"],
                      "terraform": r["terraform"]["version"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
