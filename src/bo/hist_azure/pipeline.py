"""HIST-AZURE de ponta a ponta, versão a versão da lista histórica do PINS.

  python -I -m bo.hist_azure.pipeline [--only V ...] [--force]

Para cada versão de universe/history_versions.json (azurerm), na ordem do PINS:
  1. cadeia de confiança (bo.hist_azure.signed): metadado do registro com URLs oficiais, SHA256SUMS assinado
     pela chave primária da HashiCorp (GPG), zip da plataforma == SHA256SUMS, zip desempacotado no cache de
     plugin do módulo com h1 conferido; lock = h1 + zh de todas as plataformas;
  2. bo.schema.extract com esse lock (init -lockfile=readonly; schema sem rede IP; env -i, HOME temporário,
     sandbox-exec sem ~/.aws, ~/.config/gcloud, ~/.azure, ~/.oci); sha256 do binário carregado == membro do
     zip assinado; para o pin, sha256 da saída == schema_sha256 que o PINS registrou;
  3. átomos e tipos pela bo.schema.build + write_only (bo.hist_azure.atoms), validados (C01, C02), em gzip;
  4. apaga o binário desempacotado, o zip e a pasta de trabalho do terraform; ficam o schema, os hashes,
     o SHA256SUMS e a assinatura;
  5. registra a versão em extract_report.json (EXTRACTED, ou NOT_EXTRACTED com o motivo).
No fim: versions.json (C13, com schema_sha256 de toda versão extraída) e MANIFEST.sha256 (C17).
Retomável: versão já EXTRACTED com saídas que conferem é pulada (salvo --force).
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
import traceback
from pathlib import Path

from bo.schema import extract, lockfile

from . import atoms, common, signed

REPORT_SCHEMA = "bo.hist_azure.extract_report/1"


def terraform() -> tuple[Path, dict]:
    tf = Path(shutil.which("terraform") or "")
    if not tf.name:
        raise SystemExit("pipeline: terraform não está no PATH")
    tf = tf.resolve()
    r = subprocess.run([str(tf), "version", "-json"], env={"PATH": "/usr/bin:/bin", "HOME": str(common.bo_tmp()),
                       "CHECKPOINT_DISABLE": "1"}, capture_output=True, check=True)
    return tf, json.loads(r.stdout)


def load_report() -> dict:
    p = common.report_path()
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return {}


def record_ok(rec: dict | None) -> bool:
    """A versão já extraída ainda confere (schema, átomos e tipos com os sha256 registrados)?"""
    if not rec or rec.get("status") != "EXTRACTED":
        return False
    v = rec["version"]
    sd = common.schema_dir(v)
    try:
        return (common.gz_sha256(sd / "schema.json.gz") == rec["schema"]["sha256"]
                and common.sha256_file(common.atoms_path(v)) == rec["atoms"]["gz_sha256"]
                and common.sha256_file(common.types_path(v)) == rec["types"]["gz_sha256"])
    except (OSError, KeyError):
        return False


def cleanup(version: str, zip_path: Path | None) -> dict:
    """Apaga o binário do provider (cache), o zip e a pasta de trabalho do terraform da versão."""
    removed = []
    un = common.unpacked_dir(version)
    if un.exists():
        shutil.rmtree(un)
        removed.append(common.portable(un))
    for d in (un.parent, un.parent.parent):          # .../<v>/ e o nível do provider, se vazios
        try:
            d.rmdir()
        except OSError:
            pass
    if zip_path and zip_path.exists():
        zip_path.unlink()
        removed.append(common.portable(zip_path))
    work = common.bo_tmp() / "extract" / f"{common.PROVIDER}-{version}"
    if work.exists():
        shutil.rmtree(work)
        removed.append(common.portable(work))
    left = leftover_binaries()
    return {"removidos": removed, "binarios_restantes": left}


def leftover_binaries() -> list[str]:
    """Binários de provider ou zips que sobraram nas pastas do módulo (tem de ser vazio)."""
    out = []
    for root in (common.dl_root(), common.bo_tmp()):
        if not root.exists():
            continue
        for p in root.rglob("*"):
            if p.is_file() and (p.name.startswith("terraform-provider-") and not p.name.endswith(("_SHA256SUMS",
                                ".sig")) or p.suffix in (".zip", ".part")):
                out.append(common.portable(p))
    return sorted(out)


def write_source(version: str, platform: str, tf_version: str) -> None:
    d = common.dl_dir(version)
    (d / "SOURCE.txt").write_text(
        f"Fonte: {common.release_base(version)}/ e {common.registry_download_url(version, platform)}\n"
        f"Baixado/conferido pelo {common.MODULE} (decisão D1, autorizada pelo Breno em 02/11/2026).\n"
        "Metadado do registro lido como JSON; SHA256SUMS conferido por GPG (VALIDSIG, chave primária da "
        "HashiCorp);\nzip da plataforma conferido pelo SHA256SUMS, desempacotado no cache de plugin do módulo "
        f"e executado só pelo terraform {tf_version}\nem sandbox sem credenciais (env -i, HOME temporário, "
        "sandbox-exec, schema sem rede IP), para 'providers schema -json'.\nO zip e o binário foram apagados "
        "depois da extração; ficam aqui só o metadado, o SHA256SUMS, a assinatura\ne schema/ (a saída do "
        "terraform, byte a byte, em gzip determinístico, com sha256 e recibo).\n"
        "Dado não confiável: lido como JSON, nunca executado.\n", encoding="utf-8")


def process(item: common.Listed, platform: str, tf_version: str) -> dict:
    """Uma versão. Devolve o registro EXTRACTED; exceção sobe para o chamador virar NOT_EXTRACTED."""
    from bo.repo.core import now
    v = item.version
    started, t0 = now(), time.monotonic()
    work = common.bo_tmp() / "pipeline" / v
    work.mkdir(parents=True, exist_ok=True)
    common.dl_dir(v).mkdir(parents=True, exist_ok=True)
    zip_path = None
    try:
        ch = signed.chain(v, platform, work)
        lp = ch.pop("_locked")
        zip_path = ch["zip"].pop("_path")
        lock = work / "terraform.lock.hcl"
        lock.write_text(lockfile.render([lp]), encoding="utf-8")

        sd = common.schema_dir(v)
        receipt = extract.extract(common.SOURCE, lock, out=sd, cache=common.plugin_cache(), version=v)
        raw_sha = (sd / "schema.json.sha256").read_text(encoding="utf-8").split()[0]
        gz = sd / "schema.json.gz"
        if common.gz_sha256(gz) != raw_sha:
            raise RuntimeError("schema.json.gz não descomprime no sha256 de schema.json.sha256")
        if item.schema_sha256 and raw_sha != item.schema_sha256:
            raise RuntimeError(f"schema extraído {raw_sha} != schema_sha256 do PINS {item.schema_sha256}")
        if receipt["lock"]["hashes"] != list(lp.hashes):
            raise RuntimeError("o recibo do extract não usou o lock da versão")
        binfile = receipt["provider_binary"]["file"]
        member = ch["unpacked"]["files"].get(binfile, {})
        if receipt["provider_binary"]["sha256"] != member.get("sha256"):
            raise RuntimeError("binário carregado pelo terraform != membro do zip assinado")
        if receipt["terraform"]["version"] != tf_version:
            raise RuntimeError(f"extract rodou terraform {receipt['terraform']['version']} != {tf_version}")
        # o recibo do extract aponta o lock na pasta temporária, que é apagada: o lock (só hashes) fica
        # ao lado do schema e o recibo passa a apontar para ele
        shutil.copyfile(lock, sd / "terraform.lock.hcl")
        receipt["lock"]["path"] = common.portable(sd / "terraform.lock.hcl")
        (sd / "receipt.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=1) + "\n",
                                         encoding="utf-8")

        br = atoms.make(gz, v, work / "build", common.atoms_path(v), common.types_path(v))
    finally:
        cl = cleanup(v, zip_path)
    if cl["binarios_restantes"]:
        raise RuntimeError(f"sobrou binário depois da limpeza: {cl['binarios_restantes'][:3]}")
    write_source(v, platform, tf_version)
    shutil.rmtree(work, ignore_errors=True)
    return {
        "version": v, "released_at": item.released_at, "published_at": item.published_at,
        "reasons": list(item.reasons), "status": "EXTRACTED", "reason": None,
        "chain": ch,
        "provider_binary": {"file": binfile, "sha256": member["sha256"], "bytes": member["bytes"],
                            "os_arch": receipt["provider_binary"]["os_arch"], "apagado": True},
        "schema": {"path": common.portable(gz), "sha256": raw_sha, "gz_sha256": common.sha256_file(gz),
                   "bytes": receipt["schema_json"]["bytes"], "format_version": receipt["schema_json"]["format_version"],
                   "resource_types": receipt["schema_json"]["resource_types"],
                   "data_sources": receipt["schema_json"]["data_sources"],
                   "receipt": common.portable(sd / "receipt.json"),
                   "igual_ao_pins": (raw_sha == item.schema_sha256) if item.schema_sha256 else None},
        "terraform": receipt["terraform"]["version"],
        "sandbox": receipt["sandbox"]["network"],
        "atoms": {"path": common.portable(common.atoms_path(v)), "count": br["atoms"],
                  "gz_sha256": br["atoms_gz_sha256"], "jsonl_sha256": br["atoms_jsonl_sha256"],
                  "write_only": br["write_only"], "flags": br["flags"]},
        "types": {"path": common.portable(common.types_path(v)), "count": br["types"],
                  "gz_sha256": br["types_gz_sha256"], "jsonl_sha256": br["types_jsonl_sha256"]},
        "provider_schema_canonical_sha256": br["schema_sha256"],
        "validated": br.get("validated", []),
        "limpeza": cl,
        "started_at": started, "finished_at": now(), "seconds": round(time.monotonic() - t0, 1),
    }


def versions_doc(hist: common.History, recs: dict) -> dict:
    from bo.repo.core import now
    vs = []
    for it in hist.listed:
        e = {"version": it.version, "released_at": it.released_at}
        r = recs.get(it.version)
        if r and r["status"] == "EXTRACTED":
            e["schema_sha256"] = r["schema"]["sha256"]
        vs.append(e)
    return {"schema": "bo.versions/1", "contract": "C13", "contract_version": hist.contract_version,
            "module": common.MODULE, "generated_at": now(), "provider": common.PROVIDER, "versions": vs}


MANIFEST_OWN = ("versions.json", "extract_report.json")


def manifest_lines(hist: common.History, recs: dict) -> list[str]:
    """Saídas do módulo (relativas) + o que elas citam em $BO_DATA/downloads (portável). Sem logs voláteis."""
    out = common.out_dir()
    lines = [f"{common.sha256_file(out / rel)}  {rel}" for rel in MANIFEST_OWN]
    for it in hist.listed:
        r = recs.get(it.version)
        if not r or r["status"] != "EXTRACTED":
            continue
        v = it.version
        for p in (common.atoms_path(v), common.types_path(v)):
            lines.append(f"{common.sha256_file(p)}  {p.name}")
        d, sd = common.dl_dir(v), common.schema_dir(v)
        for p in (d / f"registry-download-{common.PLATFORM}.json", d / common.sums_name(v),
                  d / (common.sums_name(v) + ".sig"), sd / "schema.json.gz", sd / "schema.json.sha256",
                  sd / "receipt.json", sd / "terraform.lock.hcl"):
            lines.append(f"{common.sha256_file(p)}  {common.portable(p)}")
    return lines


def write_outputs(hist: common.History, recs: dict, platform: str, tf_version: str, started: str) -> dict:
    from bo.repo.core import now
    order = [it.version for it in hist.listed]
    ext = [v for v in order if recs.get(v, {}).get("status") == "EXTRACTED"]
    rep = {
        "schema": REPORT_SCHEMA, "module": common.MODULE, "provider": common.PROVIDER, "source": common.ADDRESS,
        "platform": platform, "terraform": tf_version,
        "history": {"path": common.portable(hist.path), "sha256": hist.sha256, "pin": hist.pin,
                    "contract_version": hist.contract_version, "listed": len(order),
                    "left_truncation": hist.left_truncation, "cutoff": hist.cutoff},
        "started_at": started, "finished_at": now(),
        "totals": {"listed": len(order), "extracted": len(ext),
                   "not_extracted": len(order) - len(ext),
                   "atoms": {v: recs[v]["atoms"]["count"] for v in ext},
                   "types": {v: recs[v]["types"]["count"] for v in ext}},
        "versions": [recs.get(v) or {"version": v, "status": "NOT_EXTRACTED", "reason": "não processada"}
                     for v in order],
    }
    common.write_json(common.report_path(), rep)
    common.write_json(common.versions_path(), versions_doc(hist, recs))
    mf = common.out_dir() / "MANIFEST.sha256"
    mf.write_text("\n".join(manifest_lines(hist, recs)) + "\n", encoding="utf-8")
    return rep


def run(only: list[str] | None = None, force: bool = False) -> dict:
    from bo.repo.core import now
    started = now()
    hist = common.read_history()
    tf, tv = terraform()
    tf_version = common.terraform_pin()
    if tv["terraform_version"] != tf_version:
        raise SystemExit(f"pipeline: terraform {tv['terraform_version']} != pins.json {tf_version}")
    platform = tv["platform"]
    if platform != common.PLATFORM:
        raise SystemExit(f"pipeline: plataforma {platform} != {common.PLATFORM}")
    common.out_dir().mkdir(parents=True, exist_ok=True)
    common.plugin_cache().mkdir(parents=True, exist_ok=True)
    prev = {r["version"]: r for r in load_report().get("versions", []) if r and r.get("version")}
    recs = dict(prev)
    for it in hist.listed:
        v = it.version
        if only and v not in only:
            continue
        if not force and record_ok(prev.get(v)):
            print(f"[{now()}] {v}: já extraída e conferida, pulada", flush=True)
            continue
        if not it.darwin_arm64:
            recs[v] = {"version": v, "released_at": it.released_at, "published_at": it.published_at,
                       "reasons": list(it.reasons), "status": "NOT_EXTRACTED",
                       "reason": f"o PINS registra que {v} não tem pacote {common.PLATFORM}"}
            continue
        print(f"[{now()}] {v}: extraindo", flush=True)
        try:
            recs[v] = process(it, platform, tf_version)
            r = recs[v]
            print(f"[{now()}] {v}: {r['types']['count']} tipos, {r['atoms']['count']} átomos, "
                  f"schema {r['schema']['sha256'][:12]}, {r['seconds']} s", flush=True)
        except Exception as e:      # o motivo fica registrado; a versão não some
            recs[v] = {"version": v, "released_at": it.released_at, "published_at": it.published_at,
                       "reasons": list(it.reasons), "status": "NOT_EXTRACTED",
                       "reason": f"{type(e).__name__}: {str(e)[:600]}",
                       "trace_tail": traceback.format_exc().splitlines()[-3:],
                       "at": now()}
            print(f"[{now()}] {v}: NÃO extraída: {recs[v]['reason']}", flush=True)
        write_outputs(hist, recs, platform, tf_version, started)
    return write_outputs(hist, recs, platform, tf_version, started)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="bo.hist_azure.pipeline", description=__doc__.split("\n")[0])
    ap.add_argument("--only", nargs="*", help="só estas versões (as outras ficam como estão no relatório)")
    ap.add_argument("--force", action="store_true", help="refaz mesmo as já extraídas")
    a = ap.parse_args(argv)
    r = run(a.only, a.force)
    t = r["totals"]
    print(json.dumps({"listed": t["listed"], "extracted": t["extracted"], "not_extracted": t["not_extracted"]},
                     ensure_ascii=False))
    return 0 if t["extracted"] + t["not_extracted"] == t["listed"] else 1


if __name__ == "__main__":
    sys.exit(main())
