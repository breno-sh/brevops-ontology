"""Extração de uma versão histórica do google pelo binário ASSINADO, num sandbox sem credenciais (decisão D1).

Usa a biblioteca (bo.schema.extract.extract, SCHEMALIB): pasta de trabalho em $BO_TMP, env -i com HOME temporário,
sandbox-exec que nega ~/.aws, ~/.config/gcloud, ~/.azure, ~/.oci, ~/.ssh, ~/brevops-keys e a partição selada;
'terraform init -lockfile=readonly' baixa o pacote e reprova se o zip não bater com um zh: do lock (que vem do
SHA256SUMS assinado); 'terraform providers schema -json' roda com IP negado.

Depois da extração: h1 da pasta desempacotada, sha256 de cada arquivo do provider e do binário (conferido com o
receipt da biblioteca) vão para o receipt do HIST-GCP; o binário e a pasta de trabalho são APAGADOS.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from . import common as C


def plugin_cache() -> Path:
    return C.bo_tmp() / "plugin-cache"


def provider_dir(version: str) -> Path:
    return plugin_cache() / C.ADDRESS / version / C.OS_ARCH


def work_dir(version: str) -> Path:
    # a mesma pasta que bo.schema.extract monta: $BO_TMP/extract/<nome>-<versão>
    return C.bo_tmp() / "extract" / f"{C.PROVIDER}-{version}"


def cleanup(version: str) -> dict:
    """Apaga binário (plugin cache da versão) e pasta de trabalho; devolve o que foi apagado."""
    gone = {}
    for name, p in (("plugin_cache", provider_dir(version).parent), ("work", work_dir(version))):
        if p.exists():
            size = sum(f.stat().st_size for f in p.rglob("*") if f.is_file() and not f.is_symlink())
            shutil.rmtree(p)
            gone[name] = size
    return gone


def disk_free_gib(p: Path) -> float:
    return shutil.disk_usage(p).free / 2**30


def run(version: str, chain: dict, tf: dict) -> dict:
    """Extrai a versão (chain = signed.verify_local/fetch_and_verify disponível). Devolve o bloco do receipt."""
    from bo.schema import extract as X
    from . import signed
    h1_zip = signed.fetch_zip_h1(version, chain)
    lp = signed.locked_provider(version, chain["zips"], h1_zip)
    lock = signed.write_lock(lp, C.lock_path(version))
    out = C.raw_schema_dir(version)
    cleanup(version)
    try:
        rec = X.extract(C.SOURCE, lock, out=out, cache=plugin_cache(), terraform=str(tf["path"]), version=version)
        if rec["terraform"]["version"] != tf["version"] or rec["terraform"]["sha256"] != tf["binary_sha256"]:
            raise C.HistError(f"{version}: extração com outro terraform ({rec['terraform']['version']})")
        pdir = provider_dir(version)
        files = sorted(p for p in pdir.rglob("*") if p.is_file())
        bins = [p for p in files if p.name.startswith("terraform-provider-")]
        if len(bins) != 1:
            raise C.HistError(f"{version}: esperava 1 binário no plugin cache, achei {len(bins)}")
        bsha = C.sha256_file(bins[0])
        if bsha != rec["provider_binary"]["sha256"]:
            raise C.HistError(f"{version}: binário do plugin cache não é o que a biblioteca executou")
        h1 = C.dirhash_h1(pdir)
        if h1 != h1_zip:
            raise C.HistError(f"{version}: h1 da pasta desempacotada ({h1}) != h1 do zip assinado ({h1_zip})")
        unpacked = [{"path": p.relative_to(pdir).as_posix(), "sha256": C.sha256_file(p), "bytes": p.stat().st_size}
                    for p in files]
        raw_sha = C.read_sha_file(out / "schema.json.sha256")
        if raw_sha != rec["schema_json"]["sha256"]:
            raise C.HistError(f"{version}: schema.json.sha256 != receipt da biblioteca")
        if C.sha256_bytes(C.gunzip_bytes(out / "schema.json.gz")) != raw_sha:
            raise C.HistError(f"{version}: schema.json.gz não descomprime no sha gravado")
        return {
            "lock": {"path": C.portable(lock), "sha256": C.sha256_file(lock), "hashes": len(lp.hashes),
                     "h1_from_signed_zip": h1_zip,
                     "mode": "-lockfile=readonly (o init reprova zip fora dos zh: do SHA256SUMS assinado)"},
            "provider_binary": {"file": bins[0].name, "os_arch": C.OS_ARCH, "sha256": bsha,
                                "bytes": rec["provider_binary"]["bytes"], "h1": h1, "unpacked": unpacked,
                                "deleted_after_extract": True},
            "schema_json": {"path": C.portable(out / "schema.json.gz"), "sha256": raw_sha,
                            "gz_sha256": C.sha256_file(out / "schema.json.gz"),
                            "bytes": rec["schema_json"]["bytes"], "format_version": rec["schema_json"]["format_version"],
                            "resource_types": rec["schema_json"]["resource_types"],
                            "data_sources": rec["schema_json"]["data_sources"]},
            "terraform": {"version": tf["version"], "binary_sha256": tf["binary_sha256"],
                          "zip_sha256": tf["zip_sha256"]},
            "sandbox": {"library": "bo.schema.extract (SCHEMALIB)", "env": rec["sandbox"]["env"],
                        "deny_read": [C.portable(p) for p in rec["sandbox"]["deny_read"]],
                        "network": rec["sandbox"]["network"]},
            "extracted_at": {"started": rec["started_at"], "finished": rec["finished_at"]},
        }
    finally:
        cleanup(version)
        if provider_dir(version).exists() or work_dir(version).exists():
            raise C.HistError(f"{version}: binário ou pasta de trabalho não foram apagados")
