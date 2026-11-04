"""Schema do google-beta da MESMA versão do pin, evidência da causa so_beta do bo.schema.crosscheck (SCHEMALIB).

  python -I -m bo.schema_gcp.beta_schema [--extract]

A doc do google e do google-beta é uma só e o índice do Registry do hashicorp/google lista páginas beta; o
crosscheck da biblioteca só aceita a causa so_beta com o schema do google-beta extraído de binário assinado e
conferido, que ele lê em $BO_DATA/downloads/tfschema/google-beta-<versão>/. Este comando o produz:
  1. lock com zh: do SHA256SUMS do release ($BO_DATA/downloads/google-beta-<versão>/, conferido contra o shasum do
     registro); terraform init -lockfile=readonly baixa o pacote assinado para o cache de plugin compartilhado;
  2. h1 da pasta desempacotada entra no lock; bo.schema.extract (mesmo sandbox sem credenciais) grava o schema.
Só o nome dos tipos é usado; nada do google-beta vira átomo.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from bo.schema import lockfile
from bo.schema import extract as X

from . import common as C

BETA_ADDRESS = "registry.terraform.io/hashicorp/google-beta"


def beta_dir(version: str) -> Path:
    return C.bo_data() / "downloads" / f"google-beta-{version}"


def beta_lock(version: str, cache: Path | None = None) -> Path:
    """Lock do google-beta: zh: do SHA256SUMS baixado (o init confere a assinatura do release) e, se o pacote já
    estiver desempacotado no cache (depois de um init que o conferiu contra os zh:), o h1 da pasta dele."""
    d = beta_dir(version)
    sums = d / f"terraform-provider-google-beta_{version}_SHA256SUMS"
    pref = f"terraform-provider-google-beta_{version}_"
    zh = []
    for line in sums.read_text(encoding="utf-8").splitlines():
        sha, fname = line.split("  ")
        if not fname.startswith(pref):
            raise C.PinError(f"SHA256SUMS do google-beta com arquivo de outro release: {fname}")
        if fname.endswith(".zip"):
            zh.append(f"zh:{sha}")
    reg = json.loads((d / "registry-download-darwin_arm64.json").read_text(encoding="utf-8"))
    if f"zh:{reg['shasum']}" not in zh:
        raise C.PinError("shasum do registro do google-beta fora do SHA256SUMS")
    hashes = list(zh)
    pdir = (cache or X.default_cache()) / BETA_ADDRESS / version / C.OS_ARCH
    if pdir.is_dir():
        hashes.append(C.dirhash_h1(pdir))
    lp = lockfile.LockedProvider(BETA_ADDRESS, version, version, tuple(sorted(hashes)))
    return C.write_lock(lp, C.bo_tmp() / "beta" / "terraform.lock.hcl")


def prime_cache(version: str) -> None:
    """terraform init (rede só para o registro) com o lock só de zh:: baixa, confere e desempacota no cache."""
    lp = lockfile.find(lockfile.read(beta_lock(version)), "hashicorp/google-beta")
    tf = Path(X.shutil.which("terraform") or "").resolve()
    work = C.bo_tmp() / "beta" / "prime"
    if work.exists():
        X.shutil.rmtree(work)
    cache = X.default_cache()
    for d in (work / "home", work / "tmp", cache):
        d.mkdir(parents=True, exist_ok=True)
    (work / "home" / "terraformrc").write_text("", encoding="utf-8")
    (work / "versions.tf").write_text(X.versions_tf(lp), encoding="utf-8")
    (work / ".terraform.lock.hcl").write_text(lockfile.render([lp]), encoding="utf-8")
    r = X.run_sandboxed([str(tf), "init", "-backend=false", "-input=false", "-lockfile=readonly", "-no-color"],
                        work, cache, tf, network=True, capture=True)
    if r.returncode:
        raise SystemExit(f"beta_schema: init do google-beta falhou: {(r.stderr or b'').decode()[-800:]}")


def beta_schema_path(version: str) -> Path:
    return C.bo_data() / "downloads" / "tfschema" / f"google-beta-{version}" / "schema.json.gz"


def ensure(version: str, force: bool = False) -> Path:
    """Extrai o schema do google-beta se faltar (ou com force); devolve o schema.json.gz."""
    p = beta_schema_path(version)
    if force or not p.exists():
        prime_cache(version)
        X.extract("hashicorp/google-beta", beta_lock(version), out=p.parent, version=version)
    return p


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="bo.schema_gcp.beta_schema", description=__doc__.split("\n")[0])
    ap.add_argument("--extract", action="store_true", help="refaz a extração (rede só no init)")
    a = ap.parse_args(argv)
    p = ensure(C.read_pin()["version"], a.extract)
    print(f"beta_schema: {C.portable(p)} sha256 {C.read_sha_file(p.parent / 'schema.json.sha256')[:12]}…")
    return 0


if __name__ == "__main__":
    sys.exit(main())
