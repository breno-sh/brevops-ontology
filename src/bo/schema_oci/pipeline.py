"""SCHEMA-OCI de ponta a ponta: pacote assinado conferido -> schema extraído em sandbox -> átomos e tipos.

  python -I -m bo.schema_oci.pipeline [--skip-extract] [--skip-offline] [--no-download]

  1. versão, sha256 do SHA256SUMS e do schema saem de universe/pins.json (nada digitado);
  2. cadeia de confiança (bo.schema_oci.signed): SHA256SUMS == pins, assinatura GPG da Oracle (chave primária
     âncora), zip da plataforma == SHA256SUMS == registro, zip desempacotado no cache de plugin com h1 == lock
     da pré-busca;
  3. lock do módulo (h1 + zh de todas as plataformas) em plugin_cache/terraform.lock.hcl;
  4. bo.schema.extract com esse lock (init -lockfile=readonly, schema sem rede, env -i, sandbox-exec);
     confere sha256 da saída == pins.json == pré-busca e sha256 do binário carregado == membro do zip assinado;
  5. átomos e tipos pela bo.schema.build + campo write_only do C01 2.1.0 (bo.schema_oci.atoms), validados;
  6. plugin_cache/: lock, configuração de instalação offline (filesystem_mirror), pino do binário, README;
     prova de terraform validate offline (bo.schema_oci.offline);
  7. crosscheck da biblioteca + classificação (bo.schema_oci.crossdiff);
  8. build_report.json e MANIFEST.sha256 em $BO_DATA/SCHEMA-OCI.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

from bo.schema import extract, lockfile

from . import atoms, common, crossdiff, manifest, offline, signed

README = """\
plugin_cache/ do SCHEMA-OCI: terraform validate offline no provider fixado ({address} {version}, {os_arch}).

O binário assinado NÃO é copiado para cá: é dado baixado e mora em $BO_DATA/downloads/<fonte>/ (regra dos
downloads; é o cache de plugin padrão da bo.schema.extract), no layout desempacotado do terraform:
  {binary_dir}
(o zip conferido fica em {zip_path}). Este diretório guarda o que o fixa e o que o usa:
  terraform.lock.hcl  lock do provider: h1 da pasta desempacotada + zh de todos os zips do SHA256SUMS assinado
  terraformrc         provider_installation com filesystem_mirror só para {address}; instalação direta desligada
  provider.json       pino: sha256 e tamanho de cada arquivo do pacote, h1, zip, SHA256SUMS, assinatura, schema
Uso (sandbox sem credenciais, sem rede):
  cp terraform.lock.hcl <pasta>/.terraform.lock.hcl
  TF_CLI_CONFIG_FILE=<este dir>/terraformrc terraform init -backend=false -lockfile=readonly
  terraform validate -json
O init reprova se o pacote não bater com o h1 do lock. Antes de confiar no binário, confira o sha256 de
provider.json (python -I -m bo.schema_oci.manifest confere o MANIFEST.sha256 inteiro, binário incluído).
Prova: python -I -m bo.schema_oci.offline (uma configuração válida passa, uma com argumento inexistente reprova).
"""


def terraform() -> tuple[Path, dict]:
    tf = Path(shutil.which("terraform") or "")
    if not tf.name:
        raise SystemExit("pipeline: terraform não está no PATH")
    tf = tf.resolve()
    r = subprocess.run([str(tf), "version", "-json"], env={"PATH": "/usr/bin:/bin", "HOME": str(common.bo_tmp()),
                       "CHECKPOINT_DISABLE": "1"}, capture_output=True, check=True)
    return tf, json.loads(r.stdout)


def gz_sha256(p: Path) -> str:
    h = hashlib.sha256()
    with gzip.open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def terraformrc(cache: Path) -> str:
    return ("# Instalação offline do provider fixado (SCHEMA-OCI). Uso: TF_CLI_CONFIG_FILE=<este arquivo>.\n"
            "provider_installation {\n  filesystem_mirror {\n"
            f'    path    = "{cache}"\n'
            f'    include = ["{common.ADDRESS}"]\n'
            "  }\n  direct {\n    exclude = [\"registry.terraform.io/*/*\"]\n  }\n}\n")


def run(skip_extract: bool = False, skip_offline: bool = False, download: bool = True) -> dict:
    from bo.contracts import validate as V
    from bo.repo.core import now
    started = now()
    pin = common.read_pin()
    tf, tv = terraform()
    if tv["terraform_version"] != pin.terraform_version:
        raise SystemExit(f"pipeline: terraform {tv['terraform_version']} != pins.json {pin.terraform_version}")
    platform = tv["platform"]
    work = common.bo_tmp() / "pipeline"
    work.mkdir(parents=True, exist_ok=True)
    out, pc, cache = common.out_dir(), common.plugin_cache_dir(), common.shared_cache()
    pc.mkdir(parents=True, exist_ok=True)

    # 2-3. cadeia de confiança e lock
    chain = signed.chain(pin, platform, work, download=download)
    lp = chain.pop("_locked")
    lock = pc / "terraform.lock.hcl"
    lock.write_text(lockfile.render([lp]), encoding="utf-8")

    # 4. extração em sandbox (bo.schema.extract)
    sdir = common.tfschema_dir(pin.version)
    if skip_extract:
        receipt = json.loads((sdir / "receipt.json").read_text(encoding="utf-8"))
    else:
        receipt = extract.extract(f"{common.NAMESPACE}/{common.NAME}", lock, cache=cache, version=pin.version)
    raw_sha = (sdir / "schema.json.sha256").read_text(encoding="utf-8").split()[0]
    gz = sdir / "schema.json.gz"
    if gz_sha256(gz) != raw_sha:
        raise SystemExit("pipeline: schema.json.gz não descomprime no sha256 de schema.json.sha256")
    if raw_sha != pin.schema_sha256:
        raise SystemExit(f"pipeline: schema extraído {raw_sha} != pins.json {pin.schema_sha256}")
    pre_schema = common.prefetch_dir(pin.version) / "providers-schema.json"
    pre_sha = common.sha256_file(pre_schema)
    if pre_sha != raw_sha:
        raise SystemExit(f"pipeline: schema extraído {raw_sha} != pré-busca {pre_sha}")
    if receipt["lock"]["hashes"] != list(lp.hashes):
        raise SystemExit("pipeline: o recibo do extract não usou o lock do módulo")
    binfile = receipt["provider_binary"]["file"]
    zip_member = chain["unpacked"]["files"].get(binfile, {})
    if receipt["provider_binary"]["sha256"] != zip_member.get("sha256"):
        raise SystemExit("pipeline: binário carregado pelo terraform != membro do zip assinado")
    shutil.copyfile(sdir / "schema.json.sha256", out / "schema.json.sha256")

    # 5. átomos e tipos
    br = atoms.make(gz, pin.version, out / "atoms.jsonl", out / "types.jsonl")
    if br["types"] != receipt["schema_json"]["resource_types"]:
        raise SystemExit(f"pipeline: {br['types']} tipos != {receipt['schema_json']['resource_types']} do recibo")
    val = {}
    for alias, p in (("C01_atoms", out / "atoms.jsonl"), ("C02_types", out / "types.jsonl")):
        res = V.validate(alias, p)
        val[alias] = {"ok": res.ok, "errors": res.errors[:10]}
        if not res.ok:
            raise SystemExit(f"pipeline: {alias} não confere: {res.errors[:5]}")

    # 6. plugin_cache/
    bdir = cache / "registry.terraform.io" / common.NAMESPACE / common.NAME / pin.version / platform
    (pc / "terraformrc").write_text(terraformrc(cache), encoding="utf-8")
    pin_doc = {
        "schema": "bo.schema_oci.provider_pin/1",
        "address": common.ADDRESS, "version": pin.version, "os_arch": platform,
        "binary": {"path": common.portable(bdir / binfile), **chain["unpacked"]["files"][binfile]},
        "package_files": {k: {"path": common.portable(bdir / k), **v} for k, v in chain["unpacked"]["files"].items()},
        "h1": chain["unpacked"]["h1"],
        "zip": chain["zip"], "shasums": chain["shasums"], "gpg": chain["gpg"],
        "lock_sha256": common.sha256_file(lock),
        "schema_json_sha256": raw_sha,
        "terraform_version": tv["terraform_version"],
    }
    (pc / "provider.json").write_text(json.dumps(pin_doc, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
                                      encoding="utf-8")
    (pc / "README.txt").write_text(README.format(address=common.ADDRESS, version=pin.version, os_arch=platform,
                                                 binary_dir=common.portable(bdir),
                                                 zip_path=chain["zip"]["path"]), encoding="utf-8")
    off = None if skip_offline else offline.run()
    if off and off["veredito"] != "PASS":
        raise SystemExit(f"pipeline: validate offline reprovou: {off['cases']}")

    # 7. crosscheck (biblioteca, sem afrouxar) + classificação
    cx = crossdiff.run(out)

    # 8. relatório e manifesto
    report = {
        "schema": "bo.schema_oci.build_report/1", "module": common.MODULE,
        "started_at": started, "finished_at": now(),
        "pin": {"source": pin.source, "version": pin.version, "shasums_sha256": pin.shasums_sha256,
                "schema_sha256": pin.schema_sha256, "terraform": pin.terraform_version},
        "chain": chain,
        "extract": {"reexecutado": not skip_extract, "receipt": common.portable(sdir / "receipt.json"),
                    "schema_json_sha256": raw_sha, "igual_ao_pins": True, "igual_a_pre_busca": True,
                    "terraform": receipt["terraform"]["version"],
                    "terraform_binary_sha256": receipt["terraform"]["sha256"],
                    "provider_binary_sha256": receipt["provider_binary"]["sha256"],
                    "binario_igual_ao_zip_assinado": True,
                    "sandbox": receipt["sandbox"]["network"],
                    "data_sources": receipt["schema_json"]["data_sources"]},
        "build": {**br, "flags": atoms.flag_totals(out / "atoms.jsonl"),
                  "atoms_sha256": common.sha256_file(out / "atoms.jsonl"),
                  "types_sha256": common.sha256_file(out / "types.jsonl")},
        "validation": val,
        "offline_validate": off,
        "crosscheck": {"veredito_da_biblioteca": cx["veredito_da_biblioteca"], **cx["resumo"],
                       "contagem": cx["contagem"]},
    }
    (out / "build_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
                                           encoding="utf-8")
    pkg = [bdir / k for k in sorted(chain["unpacked"]["files"])]
    manifest.write(out, [gz, sdir / "schema.json.sha256", sdir / "receipt.json",
                         common.unportable(chain["zip"]["path"]), *pkg])
    return report


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="bo.schema_oci.pipeline", description=__doc__.split("\n")[0])
    ap.add_argument("--skip-extract", action="store_true", help="reusa o schema já extraído (confere sha256)")
    ap.add_argument("--skip-offline", action="store_true")
    ap.add_argument("--no-download", action="store_true", help="reprova se o zip não estiver baixado")
    a = ap.parse_args(argv)
    r = run(a.skip_extract, a.skip_offline, not a.no_download)
    b = r["build"]
    print(json.dumps({"version": r["pin"]["version"], "types": b["types"], "atoms": b["atoms"],
                      "data_sources": b["data_sources"], "write_only": b["write_only"],
                      "schema_sha256": r["extract"]["schema_json_sha256"],
                      "offline": (r["offline_validate"] or {}).get("veredito"),
                      "crosscheck": r["crosscheck"]["veredito_da_biblioteca"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
