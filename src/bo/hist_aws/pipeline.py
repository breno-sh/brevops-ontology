"""HIST-AWS de ponta a ponta: para cada versão listada pelo PINS, pacote assinado conferido -> schema extraído
em sandbox sem credenciais -> átomos C01 por versão. Binários apagados depois de cada versão.

  python -I -m bo.hist_aws.pipeline [--only V ...] [--keep-binaries] [--finalize-only]

Por versão (lista e datas de universe/history_versions.json; nada digitado):
  1. metadado do registro, SHA256SUMS e assinatura (bo.hist_aws.fetch; pré-busca para o pin);
  2. cadeia de confiança (bo.hist_aws.trust): GPG VALIDSIG da chave primária da HashiCorp, zip == SHA256SUMS ==
     shasum do registro, zip desempacotado num cache de plugin em $BO_TMP com h1 == membros do zip;
  3. lock h1 + zh de todas as plataformas; bo.schema.extract (SCHEMALIB): init -lockfile=readonly, schema sem
     rede IP, env -i, HOME temporário, sandbox-exec que nega ~/.aws, ~/.config/gcloud, ~/.azure, ~/.oci...;
  4. confere: binário carregado == membro do zip assinado; lock usado == lock do módulo; no pin, sha256 do
     schema == universe/pins.json;
  5. átomos (bo.hist_aws.atoms: bo.schema.build + write_only do C01 2.1.0), validados, em atoms_<v>.jsonl.gz;
  6. apaga zip baixado, pasta desempacotada e pasta de trabalho do terraform (fica só schema + hashes);
  7. registra a versão em extraction.json (EXTRACTED, ou FAILED com o motivo).
No fim: versions.json (C13 3.1.0), results/HIST-AWS/report.json e $BO_DATA/HIST-AWS/MANIFEST.sha256.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import shutil
import subprocess
import sys
import traceback
from pathlib import Path

from bo.schema import extract, lockfile

from . import atoms, common, fetch, trust

EXTRACTION = "extraction.json"
MANIFEST_SKIP = {"MANIFEST.sha256", "consume_ledger.json", "gate_report.json"}
#: logs voláteis que as ferramentas do REPO gravam na pasta do módulo (make integration): não são saídas
MANIFEST_SKIP_DIRS = {"integration"}


def now() -> str:
    from bo.repo.core import now as _now
    return _now()


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


def load_extraction() -> dict:
    p = common.out_dir() / EXTRACTION
    if p.is_file():
        return json.loads(p.read_text(encoding="utf-8"))
    return {"schema": "bo.hist_aws.extraction/1", "module": common.MODULE, "provider": common.PROVIDER,
            "versions": {}}


def save_extraction(doc: dict) -> None:
    p = common.out_dir() / EXTRACTION
    p.parent.mkdir(parents=True, exist_ok=True)
    doc["updated_at"] = now()
    tmp = p.with_name(p.name + ".part")
    tmp.write_text(json.dumps(doc, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(p)


def rm(p: Path) -> None:
    if p.is_dir() and not p.is_symlink():
        shutil.rmtree(p, ignore_errors=True)
    elif p.exists() or p.is_symlink():
        p.unlink()


def extract_one(item: common.Listed, pins: common.Pins, hist: common.History, tf_version: str,
                keep_binaries: bool = False) -> dict:
    """Uma versão de ponta a ponta. Levanta exceção se algum elo não confere (o chamador registra o motivo)."""
    v = item.version
    started = now()
    work = common.bo_tmp() / "versions" / v
    cache = common.bo_tmp() / "plugin-cache" / v
    rm(work)
    work.mkdir(parents=True)
    if not item.darwin_arm64:
        raise trust.TrustError(f"o registro não publica {common.PLATFORM} para {v} (selection.darwin_arm64=false)")
    f = None
    try:
        # 1-2. metadado, assinatura e zip
        f = fetch.metadata(v, pins)
        meta = json.loads(f.registry_json.read_text(encoding="utf-8"))
        keys = [k["ascii_armor"] for k in (meta.get("signing_keys") or {}).get("gpg_public_keys") or []]
        st = trust.gpg_verify(f.sums, f.sig, keys, work)
        sums = trust.parse_shasums(f.sums.read_text(encoding="utf-8"))
        zfn = trust.zip_name(v)
        if zfn not in sums:
            raise trust.TrustError(f"SHA256SUMS assinado sem {zfn}")
        if meta.get("shasum") != sums[zfn]:
            raise trust.TrustError("shasum do registro diverge do SHA256SUMS assinado")
        if [str(p) for p in meta.get("protocols") or []] != list(item.protocols):
            raise trust.TrustError(f"protocolos do registro {meta.get('protocols')} != selection {item.protocols}")
        fetch.get_zip(f)
        zsha = common.sha256_file(f.zip)
        if zsha != sums[zfn]:
            raise trust.TrustError(f"{zfn}: sha256 {zsha} != SHA256SUMS assinado {sums[zfn]}")
        zbytes = f.zip.stat().st_size
        dest = cache / "registry.terraform.io" / "hashicorp" / common.NAME / v / common.PLATFORM
        dest.parent.mkdir(parents=True, exist_ok=True)
        un = trust.unpack(f.zip, dest)

        # 3. lock e extração no sandbox da SCHEMALIB
        lp = lockfile.LockedProvider(common.ADDRESS, v, v, tuple(sorted({un["h1"], *trust.zh_hashes(sums, v)})))
        lock = work / "terraform.lock.hcl"
        lock.write_text(lockfile.render([lp]), encoding="utf-8")
        sdir = common.schema_dir(v)
        rm(sdir)
        receipt = extract.extract(common.SOURCE, lock, out=sdir, cache=cache, version=v)

        # 4. conferências
        raw_sha = (sdir / "schema.json.sha256").read_text(encoding="utf-8").split()[0]
        if gz_sha256(sdir / "schema.json.gz") != raw_sha:
            raise trust.TrustError("schema.json.gz não descomprime no sha256 de schema.json.sha256")
        if receipt["lock"]["hashes"] != list(lp.hashes):
            raise trust.TrustError("o recibo do extract não usou o lock do módulo")
        if receipt["terraform"]["version"] != tf_version:
            raise trust.TrustError(f"terraform {receipt['terraform']['version']} != pins.json {tf_version}")
        binfile = receipt["provider_binary"]["file"]
        member = un["files"].get(binfile) or {}
        if receipt["provider_binary"]["sha256"] != member.get("sha256"):
            raise trust.TrustError("binário carregado pelo terraform != membro do zip assinado")
        if v == pins.version and raw_sha != pins.schema_sha256:
            raise trust.TrustError(f"pin {v}: schema {raw_sha} != pins.json {pins.schema_sha256}")
        if v == hist.pin and hist.pin_schema_sha256 and raw_sha != hist.pin_schema_sha256:
            raise trust.TrustError(f"pin {v}: schema {raw_sha} != history_versions {hist.pin_schema_sha256}")
        ps = receipt["schema_json"]

        # receipt.json do extract fica (versão do terraform, hashes do lock, sha256 do binário, sandbox), mas
        # com o caminho do lock (pasta de trabalho apagada) trocado pelo portátil do trust.json
        receipt["lock"]["path"] = common.portable(sdir / "trust.json") + "#lock"
        receipt["lock"]["sha256"] = common.sha256_file(lock)
        (sdir / "receipt.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=1) + "\n",
                                           encoding="utf-8")
        trust_doc = {
            "schema": "bo.hist_aws.trust/1", "provider": common.ADDRESS, "version": v,
            "platform": common.PLATFORM, "origin": f.origin, "urls": f.urls,
            "registry": {"path": common.portable(f.registry_json), "sha256": common.sha256_file(f.registry_json),
                         "shasum": meta.get("shasum"), "protocols": meta.get("protocols"),
                         "key_ids": [k.get("key_id") for k in (meta.get("signing_keys") or {})
                                     .get("gpg_public_keys") or []]},
            "shasums": {"path": common.portable(f.sums), "sha256": common.sha256_file(f.sums),
                        "entries": len(sums), "zh": len(trust.zh_hashes(sums, v))},
            "signature": {"path": common.portable(f.sig), "sha256": common.sha256_file(f.sig)},
            "gpg": {"validsig_subkey": st["validsig"], "primary_fpr": st["primary_fpr"],
                    "sig_created": st["sig_created"], "expkeysig": st["expkeysig"], "goodsig": st["goodsig"],
                    "ancora": common.HASHICORP_FPR},
            "zip": {"file": zfn, "sha256": zsha, "bytes": zbytes, "igual_ao_shasums": True,
                    "igual_ao_registro": True, "reaproveitado_de": None if f.zip_is_ours else common.portable(f.zip),
                    "apagado": False},
            "unpacked": {"h1": un["h1"], "files": un["files"], "apagado": False},
            "binary": {"file": binfile, "sha256": receipt["provider_binary"]["sha256"],
                       "bytes": receipt["provider_binary"]["bytes"], "igual_ao_membro_do_zip": True},
            "lock": {"version": v, "constraints": v, "hashes": list(lp.hashes),
                     "sha256": common.sha256_file(lock)},
            "schema_json_sha256": raw_sha,
            "terraform_version": receipt["terraform"]["version"],
        }

        # 5. átomos
        br = atoms.make(sdir / "schema.json.gz", v, work / "build", common.atoms_path(v))

        # 6. limpeza dos binários (fica só o schema e os hashes)
        if not keep_binaries:
            rm(cache)
            rm(extract.bo_tmp() / "extract" / f"{common.NAME}-{v}")
            if f.zip_is_ours:
                rm(f.zip)
            trust_doc["zip"]["apagado"] = bool(f.zip_is_ours)
            trust_doc["unpacked"]["apagado"] = True
        (sdir / "trust.json").write_text(json.dumps(trust_doc, ensure_ascii=False, indent=1, sort_keys=True)
                                         + "\n", encoding="utf-8")
        return {
            "status": "EXTRACTED", "version": v, "released_at": item.released_at,
            "published_at": item.published_at, "reasons": list(item.reasons),
            "schema_sha256": raw_sha, "schema_bytes": ps["bytes"], "format_version": ps["format_version"],
            "resource_types": ps["resource_types"], "data_sources": ps["data_sources"],
            "schema_gz": common.portable(sdir / "schema.json.gz"),
            "schema_gz_sha256": common.sha256_file(sdir / "schema.json.gz"),
            "atoms_file": common.portable(common.atoms_path(v)),
            "atoms": br["atoms"], "types": br["types"], "write_only": br["write_only"], "flags": br["flags"],
            "atoms_jsonl_sha256": br["atoms_jsonl_sha256"], "atoms_gz_sha256": br["atoms_gz_sha256"],
            "provider_schema_canonical_sha256": br["schema_sha256"],
            "binary_sha256": trust_doc["binary"]["sha256"], "zip_sha256": zsha, "h1": un["h1"],
            "gpg_primary_fpr": st["primary_fpr"], "terraform": receipt["terraform"]["version"],
            "origin": f.origin, "started_at": started, "finished_at": now(),
        }
    finally:
        if not keep_binaries:
            rm(cache)
            rm(extract.bo_tmp() / "extract" / f"{common.NAME}-{v}")
            if f is not None and f.zip_is_ours and f.zip is not None:
                rm(f.zip)
            rm(work)


def manifest_files(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*")
                  if p.is_file() and p.name not in MANIFEST_SKIP and not p.name.endswith(".part")
                  and "__pycache__" not in p.parts and p.name != ".DS_Store"
                  and p.relative_to(root).parts[0] not in MANIFEST_SKIP_DIRS)


SCHEMA_FILES = ("schema.json.gz", "schema.json.sha256", "receipt.json", "trust.json", "SOURCE.txt")


def manifest_entries(root: Path, ext: dict) -> list[tuple[Path, str]]:
    """(arquivo, caminho no manifesto): as saídas em root (relativo) + os schemas extraídos (portátil)."""
    out = [(p, p.relative_to(root).as_posix()) for p in manifest_files(root)]
    for v in sorted((v for v, r in ext["versions"].items() if r.get("status") == "EXTRACTED"),
                    key=common.semver_key):
        out += [(common.schema_dir(v) / n, common.portable(common.schema_dir(v) / n)) for n in SCHEMA_FILES]
    return out


def write_manifest(root: Path, ext: dict) -> Path:
    lines = [f"{common.sha256_file(p)}  {label}" for p, label in manifest_entries(root, ext)]
    mf = root / "MANIFEST.sha256"
    mf.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return mf


def versions_doc(hist: common.History, ext: dict) -> dict:
    """C13 versions (3.1.0): toda versão listada, na ordem do PINS; schema_sha256 só nas extraídas."""
    out = []
    for it in hist.versions:
        e = {"version": it.version, "released_at": it.released_at}
        r = ext["versions"].get(it.version) or {}
        if r.get("status") == "EXTRACTED":
            e["schema_sha256"] = r["schema_sha256"]
        out.append(e)
    return {"schema": "bo.versions/1", "contract": "C13", "contract_version": "3.1.0", "module": common.MODULE,
            "generated_at": now(), "provider": common.PROVIDER, "versions": out}


def atom_ids(path: Path) -> set:
    return {a["atom_id"] for a in atoms.read_atoms(path)}


def report(hist: common.History, ext: dict) -> dict:
    """Contagens por versão e diferença de átomos/tipos para a versão extraída anterior (resultado, não ajuste)."""
    rows, prev_ids, prev_types, prev_v = [], None, None, None
    for it in hist.versions:
        r = ext["versions"].get(it.version) or {}
        row = {"version": it.version, "released_at": it.released_at, "reasons": list(it.reasons),
               "status": r.get("status", "MISSING")}
        if r.get("status") == "EXTRACTED":
            ids = atom_ids(common.out_dir() / Path(r["atoms_file"]).name)
            types = {i.split(":", 2)[1] for i in ids}
            row.update({k: r[k] for k in ("resource_types", "data_sources", "types", "atoms", "write_only",
                                          "schema_sha256", "atoms_gz_sha256", "format_version")})
            row["types_with_attributes"] = len(types)
            if prev_ids is not None:
                row["delta_vs"] = prev_v
                row["atoms_added"] = len(ids - prev_ids)
                row["atoms_removed"] = len(prev_ids - ids)
                row["types_added"] = len(types - prev_types)
                row["types_removed"] = len(prev_types - types)
            prev_ids, prev_types, prev_v = ids, types, it.version
        else:
            row["motivo"] = r.get("motivo", "versão não processada")
        rows.append(row)
    n_ok = sum(r["status"] == "EXTRACTED" for r in rows)
    return {"schema": "bo.hist_aws.report/1", "module": common.MODULE, "provider": common.PROVIDER,
            "generated_at": now(), "listed": len(rows), "extracted": n_ok, "not_extracted": len(rows) - n_ok,
            "pin": hist.pin, "rows": rows,
            "nota": ("delta = átomos/tipos que aparecem ou somem entre versões amostradas consecutivas; uma remoção "
                     "pode ser renome ou mudança de bloco (classificação de eventos é do DRIFT, não daqui).")}


def finalize(hist: common.History, ext: dict) -> dict:
    out = common.out_dir()
    vd = versions_doc(hist, ext)
    (out / "versions.json").write_text(json.dumps(vd, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    rep = report(hist, ext)
    rdir = common.bo_repo() / "results" / common.MODULE
    rdir.mkdir(parents=True, exist_ok=True)
    (rdir / "report.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    write_manifest(out, ext)
    return rep


def run(only: list[str] | None = None, keep_binaries: bool = False, finalize_only: bool = False,
        retry_failed: bool = True) -> dict:
    hist = common.read_history()
    pins = common.read_pins()
    if hist.pin != pins.version:
        raise SystemExit(f"pipeline: pin do history_versions {hist.pin} != pins.json {pins.version}")
    _, tv = terraform()
    if tv["terraform_version"] != pins.terraform_version:
        raise SystemExit(f"pipeline: terraform {tv['terraform_version']} != pins.json {pins.terraform_version}")
    if tv["platform"] != common.PLATFORM:
        raise SystemExit(f"pipeline: plataforma {tv['platform']} != {common.PLATFORM}")
    ext = load_extraction()
    ext["terraform"] = pins.terraform_version
    ext["platform"] = common.PLATFORM
    ext["history_versions_sha256"] = common.sha256_file(common.history_path())
    listed = {it.version for it in hist.versions}
    for v in list(ext["versions"]):
        if v not in listed:
            del ext["versions"][v]
    if not finalize_only:
        for it in hist.versions:
            if only and it.version not in only:
                continue
            prev = ext["versions"].get(it.version) or {}
            if not only and prev.get("status") == "EXTRACTED" and common.atoms_path(it.version).is_file():
                continue
            if prev.get("status") == "FAILED" and not retry_failed:
                continue
            print(f"[{now()}] {it.version}: extraindo", flush=True)
            try:
                rec = extract_one(it, pins, hist, pins.terraform_version, keep_binaries)
                print(f"[{now()}] {it.version}: {rec['resource_types']} tipos, {rec['atoms']} átomos", flush=True)
            except (Exception, SystemExit) as e:   # noqa: BLE001 - o motivo vira dado, a lista segue
                msg = f"{type(e).__name__}: {e}"
                rec = {"status": "FAILED", "version": it.version, "released_at": it.released_at,
                       "motivo": msg[:2000], "trace_tail": traceback.format_exc().splitlines()[-3:],
                       "finished_at": now()}
                rm(common.atoms_path(it.version))
                print(f"[{now()}] {it.version}: FALHOU: {msg[:300]}", flush=True)
            ext["versions"][it.version] = rec
            save_extraction(ext)
    save_extraction(ext)
    return finalize(hist, ext)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="bo.hist_aws.pipeline", description=__doc__.split("\n")[0])
    ap.add_argument("--only", action="append", help="só esta versão (repetível); reextrai mesmo se já feita")
    ap.add_argument("--keep-binaries", action="store_true", help="não apaga zip/cache (depuração)")
    ap.add_argument("--finalize-only", action="store_true", help="só regrava versions.json, relatório e manifesto")
    ap.add_argument("--no-retry-failed", action="store_true")
    a = ap.parse_args(argv)
    r = run(a.only, a.keep_binaries, a.finalize_only, not a.no_retry_failed)
    print(json.dumps({"listed": r["listed"], "extracted": r["extracted"], "not_extracted": r["not_extracted"]},
                     ensure_ascii=False))
    return 0 if r["not_extracted"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
