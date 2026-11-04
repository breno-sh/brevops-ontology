"""SCHEMA-GCP de ponta a ponta: pin -> lock assinado -> extração em sandbox -> átomos/tipos -> cruzamento -> manifesto.

  python -I -m bo.schema_gcp.pipeline [--extract] [--no-crosscheck-fetch]

1. versão, sha do SHA256SUMS e sha do schema saem do universe/pins.json (PINS); a pré-busca é conferida contra eles;
2. lock em $BO_DATA/SCHEMA-GCP/plugin_cache/terraform.lock.hcl: h1 da pré-busca + zh: do SHA256SUMS assinado;
3. bo.schema.extract (biblioteca): terraform init -lockfile=readonly baixa o pacote ASSINADO para o plugin_cache e
   'providers schema -json' roda sem rede e sem credenciais. Só com --extract ou se o schema ainda não existe;
4. sha256 da saída crua == schema_sha256 do pin; h1 da pasta do provider no plugin_cache == h1 do lock;
5. o plugin_cache sozinho, offline (bo.schema_gcp.offline), refaz o schema com o mesmo sha e passa no validate;
6. átomos e tipos pela biblioteca (bo.schema_gcp.atoms), validados no validador único (C01, C02);
7. bo.schema.crosscheck --provider google (índice do Registry da versão); o veredito é registrado, não ajustado;
   bo.schema_gcp.beta_check mede a causa das páginas sem tipo (google-beta da mesma versão), sem mudar o veredito;
8. plugin_cache/SIGNED.sha256 (sha256 dos arquivos do provider, depois do h1 conferido), build_report.json e
   MANIFEST.sha256 da pasta do módulo.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

from . import atoms as A
from . import common as C
from . import offline

MANIFEST_SKIP = {"MANIFEST.sha256", "consume_ledger.json", "gate_report.json"}
#: logs voláteis que as ferramentas do REPO gravam na pasta do módulo (make integration): não são saídas
MANIFEST_SKIP_DIRS = {"integration"}


def manifest_files(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*")
                  if p.is_file() and p.name not in MANIFEST_SKIP and not p.name.startswith("MANIFEST.sha256")
                  and "__pycache__" not in p.parts
                  and p.relative_to(root).parts[0] not in MANIFEST_SKIP_DIRS
                  and p.name != ".DS_Store")


def write_manifest(root: Path) -> int:
    files = manifest_files(root)
    lines = [f"{C.sha256_file(p)}  {p.relative_to(root).as_posix()}\n" for p in files]
    (root / "MANIFEST.sha256").write_text("".join(lines), encoding="utf-8")
    return len(lines)


def crosscheck(out: Path, fetch: bool) -> dict:
    from bo.schema import crosscheck as XC
    args = ["--provider", C.PROVIDER, "--out", str(out)]
    if fetch:
        args.append("--fetch")
    rc = XC.main(args)
    rep = json.loads(out.read_text(encoding="utf-8")) if out.exists() else {}
    causes: dict = {}
    for e in rep.get("explicadas", []):
        causes[e["causa"]] = causes.get(e["causa"], 0) + 1
    return {"rc": rc, "veredito": rep.get("veredito"), "tipos_schema": rep.get("tipos_schema"),
            "paginas_indice": rep.get("paginas_indice"), "iguais": rep.get("iguais"), "explicadas": causes,
            "tipos_sem_pagina": len(rep.get("tipos_sem_pagina", [])),
            "paginas_sem_tipo": len(rep.get("paginas_sem_tipo", [])), "relatorio": C.portable(out)}


def run(do_extract: bool, fetch_index: bool) -> dict:
    from bo.repo.core import now
    from bo.schema import extract as X
    started = now()
    pin = C.read_pin()
    v = pin["version"]
    sig = C.signed_inputs(pin)
    out, cache = C.out_dir(), C.plugin_cache()
    out.mkdir(parents=True, exist_ok=True)
    lp = C.locked_provider(pin, sig)
    lock = C.write_lock(lp, C.lock_path())

    sdir = C.tfschema_dir(v)
    schema_gz = sdir / "schema.json.gz"
    if do_extract or not (schema_gz.exists() and (sdir / "receipt.json").exists()):
        X.extract(C.SOURCE, lock, out=sdir, cache=cache, version=v)
    receipt = json.loads((sdir / "receipt.json").read_text(encoding="utf-8"))
    if receipt["lock"]["sha256"] != C.sha256_file(lock):
        raise C.PinError("receipt.json do extract foi feito com outro lock (rode com --extract)")
    raw_sha = C.read_sha_file(sdir / "schema.json.sha256")
    if raw_sha != pin["schema_sha256"]:
        raise C.PinError(f"schema extraído ({raw_sha[:12]}…) != schema_sha256 do pin ({pin['schema_sha256'][:12]}…)")
    if receipt["terraform"]["version"] != pin["terraform"]["version"]:
        raise C.PinError(f"terraform {receipt['terraform']['version']} != pin {pin['terraform']['version']}")

    pdir = C.provider_dir(cache, v)
    h1 = C.dirhash_h1(pdir)
    if h1 != sig["h1"]:
        raise C.PinError(f"h1 da pasta do provider ({h1}) != h1 do lock ({sig['h1']})")
    binary = sorted(pdir.glob("terraform-provider-*"))
    if len(binary) != 1 or C.sha256_file(binary[0]) != receipt["provider_binary"]["sha256"]:
        raise C.PinError("binário do plugin_cache não é o do receipt do extract")
    C.signed_path().write_text(C.signed_lines(cache, v, sig["h1"]), encoding="utf-8")

    off = offline.run(C.bo_tmp() / "offline-pipeline")
    if off["sha256"] != raw_sha:
        raise C.PinError(f"schema offline pelo plugin_cache ({off['sha256'][:12]}…) != extraído ({raw_sha[:12]}…)")

    shutil.copyfile(sdir / "schema.json.sha256", out / "schema.json.sha256")
    b = A.build(schema_gz, v, out / "atoms.jsonl", out / "types.jsonl")

    from bo.contracts import validate as V
    val = {}
    for alias, p in (("C01_atoms", out / "atoms.jsonl"), ("C02_types", out / "types.jsonl")):
        res = V.validate(alias, p)
        val[alias] = {"ok": res.ok, "records": res.n, "errors": res.errors[:10]}
        if not res.ok:
            raise SystemExit(f"pipeline: {alias} reprovou: {res.errors[:5]}")

    xc = crosscheck(out / f"crosscheck_{C.PROVIDER}-{v}.json", fetch_index)
    from . import beta_check
    if beta_check.main([]) != 0:
        raise SystemExit("pipeline: beta_check falhou")
    bc = json.loads((out / f"crosscheck_beta_{C.PROVIDER}-{v}.json").read_text(encoding="utf-8"))
    xc["causa_paginas_sem_tipo"] = {"relatorio": C.portable(out / f"crosscheck_beta_{C.PROVIDER}-{v}.json"),
                                    "conclusao": bc["conclusao"], **{k: (len(x) if isinstance(x, list) else x)
                                                                    for k, x in bc["contagens"].items()}}

    report = {
        "schema": "bo.schema_gcp.build_report/1", "module": C.ID, "started_at": started, "finished_at": now(),
        "provider": {"address": C.ADDRESS, "version": v, "os_arch": C.OS_ARCH},
        "pin": {"file": C.portable(pin["pins_path"]), "sha256": pin["pins_sha256"],
                "shasums_sha256": pin["shasums_sha256"], "schema_sha256": pin["schema_sha256"],
                "terraform": pin["terraform"]["version"]},
        "signed": {"sha256sums": C.portable(sig["sha256sums"]), "sha256sums_sha256": sig["sha256sums_sha256"],
                   "gpg_fingerprint": sig["gpg_fingerprint"], "zip_sha256_os_arch": sig["zips"][C.OS_ARCH],
                   "platforms": len(sig["zips"]), "lock": C.portable(lock), "lock_sha256": C.sha256_file(lock),
                   "lock_hashes": len(lp.hashes)},
        "extract": {"dir": C.portable(sdir), "schema_json_gz_sha256": C.sha256_file(schema_gz),
                    "schema_json_sha256": raw_sha, "schema_json_bytes": receipt["schema_json"]["bytes"],
                    "format_version": receipt["schema_json"]["format_version"],
                    "terraform": receipt["terraform"]["version"], "started_at": receipt["started_at"],
                    "network": receipt["sandbox"]["network"]},
        "plugin_cache": {"dir": C.portable(pdir), "h1": h1, "h1_matches_lock": True,
                         "binary": binary[0].name, "binary_sha256": receipt["provider_binary"]["sha256"],
                         "binary_bytes": receipt["provider_binary"]["bytes"]},
        "offline": {"schema_sha256": off["sha256"], "matches": True, "terraform": off["terraform_version"],
                    "validate": off["validate"], "network": "IP negado (sandbox-exec)"},
        "build": b, "validate": val, "crosscheck": xc,
    }
    (out / "build_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    report["manifest_files"] = write_manifest(out)
    return report


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="bo.schema_gcp.pipeline", description=__doc__.split("\n")[0])
    ap.add_argument("--extract", action="store_true", help="refaz a extração (rede só no init, para o registro)")
    ap.add_argument("--no-crosscheck-fetch", action="store_true", help="não baixa o índice do Registry se faltar")
    a = ap.parse_args(argv)
    r = run(a.extract, not a.no_crosscheck_fetch)
    print(json.dumps({"build": r["build"], "crosscheck": r["crosscheck"], "h1": r["plugin_cache"]["h1"],
                      "offline": r["offline"]["matches"], "manifest_files": r["manifest_files"]},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
