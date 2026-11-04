"""HIST-OCI de ponta a ponta: para cada versão da lista histórica do PINS, pacote assinado conferido -> schema
extraído em sandbox sem credenciais -> átomos C01 por versão -> binários apagados.

  python -I -m bo.hist_oci.pipeline [--only V ...] [--redo] [--no-download]

  1. a lista sai de universe/history_versions.json (entrada do oci, C13 3.1.0); nada é digitado;
  2. por versão: cadeia de confiança (bo.hist_oci.chain): metadado do registro, SHA256SUMS assinado pela chave
     primária da Oracle, zip == SHA256SUMS == registro, h1 da pasta desempacotada == h1 dos membros do zip;
  3. lock da versão (h1 + zh) em $BO_DATA/HIST-OCI/locks/; bo.schema.extract com esse lock e o cache de plugin
     próprio (init -lockfile=readonly, schema sem rede, env -i, HOME temporário, sandbox-exec);
     confere sha256 da saída == schema.json.sha256 e binário carregado == membro do zip assinado; no pin,
     sha256 == schema_sha256 da lista histórica (== pins.json pela regra C13-HIST-PIN);
  4. átomos (bo.hist_oci.atoms) validados no C01 e gravados em atoms_<versão>.jsonl.gz (gzip determinístico);
  5. zip, pasta desempacotada e pasta de trabalho do extract apagados; confirma que nada ficou;
  6. relatório por versão em extraction/<versão>.json; no fim, versions.json (C13), extraction.json (estado de
     todas as versões, motivo de cada falta, truncamento à esquerda) e MANIFEST.sha256.
Versão que falha fica registrada com o motivo (estado not_extracted), nunca some da lista.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
import traceback
from pathlib import Path

from bo.schema import extract as libx
from bo.schema import lockfile

from . import atoms, chain, common, manifest

RETRIES = 3


def _dump(p: Path, obj) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".part")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(p)


def lock_path(version: str) -> Path:
    return common.out_dir() / "locks" / f"{common.NAME}-{version}.terraform.lock.hcl"


def record_path(version: str) -> Path:
    return common.out_dir() / "extraction" / f"{version}.json"


def _with_retries(fn, what: str):
    last = None
    for i in range(RETRIES):
        try:
            return fn()
        except (OSError, TimeoutError) as e:          # rede/disco transitórios; Unavailable/TrustError não
            last = e
            time.sleep(5 * (i + 1))
    raise RuntimeError(f"{what}: {RETRIES} tentativas falharam: {type(last).__name__}: {last}")


def one(lv: common.Listed, download: bool = True) -> dict:
    """Extrai uma versão. Devolve o registro (estado extracted) ou levanta a exceção (o chamador registra)."""
    from bo.contracts import validate as V
    from bo.repo.core import now
    v = lv.version
    rec = {"schema": "bo.hist_oci.extraction/1", "module": common.MODULE, "provider": common.PROVIDER,
           "version": v, "released_at": lv.released_at, "published_at": lv.published_at,
           "reasons": list(lv.reasons), "started_at": now()}
    if not lv.darwin_arm64:
        raise RuntimeError(f"o índice do registro não lista {common.PLATFORM} para {v}")
    ch = _with_retries(lambda: chain.verify(v, download), f"cadeia de {v}")
    lp = ch.pop("_locked")
    lk = lock_path(v)
    lk.parent.mkdir(parents=True, exist_ok=True)
    lk.write_text(lockfile.render([lp]), encoding="utf-8")
    rec["chain"] = ch

    sdir = common.tfschema_dir(v)
    receipt = libx.extract(f"{common.NAMESPACE}/{common.NAME}", lk, out=sdir, cache=common.plugin_cache(),
                           version=v)
    raw_sha = (sdir / "schema.json.sha256").read_text(encoding="utf-8").split()[0]
    gz = sdir / "schema.json.gz"
    if common.gz_sha256(gz) != raw_sha or receipt["schema_json"]["sha256"] != raw_sha:
        raise RuntimeError("schema.json.gz não descomprime no sha256 de schema.json.sha256/recibo")
    if lv.schema_sha256 and raw_sha != lv.schema_sha256:
        raise RuntimeError(f"schema extraído {raw_sha} != schema_sha256 da lista histórica {lv.schema_sha256}")
    if receipt["lock"]["hashes"] != list(lp.hashes):
        raise RuntimeError("o recibo do extract não usou o lock da versão")
    binfile = receipt["provider_binary"]["file"]
    member = ch["unpacked"]["files"].get(binfile, {})
    if receipt["provider_binary"]["sha256"] != member.get("sha256"):
        raise RuntimeError("binário carregado pelo terraform != membro do zip assinado")
    rec["extract"] = {"schema_json_sha256": raw_sha, "schema_json_bytes": receipt["schema_json"]["bytes"],
                      "format_version": receipt["schema_json"]["format_version"],
                      "schema_dir": common.portable(sdir),
                      "receipt_sha256": common.sha256_file(sdir / "receipt.json"),
                      "terraform": receipt["terraform"]["version"],
                      "terraform_binary_sha256": receipt["terraform"]["sha256"],
                      "provider_binary": {"file": binfile, "sha256": receipt["provider_binary"]["sha256"],
                                          "bytes": receipt["provider_binary"]["bytes"]},
                      "binario_igual_ao_zip_assinado": True,
                      "igual_a_lista_historica": bool(lv.schema_sha256) or None,
                      "sandbox": receipt["sandbox"]["network"],
                      "lock": {"path": common.portable(lk), "sha256": common.sha256_file(lk)}}

    bdir = common.bo_tmp() / "build" / v
    if bdir.exists():
        shutil.rmtree(bdir)
    bdir.mkdir(parents=True)
    br = atoms.make(gz, v, bdir / "atoms.jsonl", bdir / "types.jsonl")
    if br["types"] != receipt["schema_json"]["resource_types"]:
        raise RuntimeError(f"{br['types']} tipos != {receipt['schema_json']['resource_types']} do recibo")
    res = V.validate("C01_atoms", bdir / "atoms.jsonl")
    if not res.ok:
        raise RuntimeError(f"C01 não confere: {res.errors[:5]}")
    ap = common.atoms_path(v)
    common.write_gz(bdir / "atoms.jsonl", ap, f"atoms_{v}.jsonl")
    rec["atoms"] = {"path": common.portable(ap), "gz_sha256": common.sha256_file(ap),
                    "jsonl_sha256": common.sha256_file(bdir / "atoms.jsonl"),
                    "atoms": br["atoms"], "types": br["types"], "data_sources": br["data_sources"],
                    "write_only": br["write_only"], "flags": atoms.flag_totals(bdir / "atoms.jsonl"),
                    "c01_ok": True}
    shutil.rmtree(bdir, ignore_errors=True)
    rec["binarios"] = chain.cleanup_binaries(v)
    rec["status"] = "extracted"
    rec["finished_at"] = now()
    return rec


def run(only: list[str] | None = None, redo: bool = False, download: bool = True) -> dict:
    from bo.repo.core import now
    hist = common.read_history()
    listed = [lv for lv in hist.versions if not only or lv.version in only]
    if only and len(listed) != len(set(only)):
        raise SystemExit(f"pipeline: versões fora da lista histórica: {sorted(set(only) - {x.version for x in listed})}")
    common.out_dir().mkdir(parents=True, exist_ok=True)
    for lv in listed:
        rp = record_path(lv.version)
        if rp.is_file() and not redo:
            old = json.loads(rp.read_text(encoding="utf-8"))
            if old.get("status") == "extracted" and common.atoms_path(lv.version).is_file():
                print(f"  {lv.version}: já extraída (use --redo para refazer)", flush=True)
                continue
        t0 = time.time()
        try:
            rec = one(lv, download)
            print(f"  {lv.version}: {rec['atoms']['types']} tipos, {rec['atoms']['atoms']} átomos, "
                  f"schema {rec['extract']['schema_json_sha256'][:12]} ({time.time() - t0:.0f} s)", flush=True)
        except BaseException as e:                       # noqa: BLE001 (registrar e seguir; Ctrl-C sobe)
            if isinstance(e, KeyboardInterrupt):
                chain.cleanup_binaries(lv.version)
                raise
            tb = traceback.extract_tb(e.__traceback__)[-1]
            rec = {"schema": "bo.hist_oci.extraction/1", "module": common.MODULE, "provider": common.PROVIDER,
                   "version": lv.version, "released_at": lv.released_at, "published_at": lv.published_at,
                   "reasons": list(lv.reasons), "status": "not_extracted",
                   "motivo": f"{type(e).__name__}: {str(e)[:600]}",
                   "onde": f"{Path(tb.filename).name}:{tb.lineno}", "finished_at": now()}
            common.atoms_path(lv.version).unlink(missing_ok=True)
            try:
                rec["binarios"] = chain.cleanup_binaries(lv.version)
            except Exception as e2:                       # noqa: BLE001
                rec["binarios"] = {"erro": str(e2)[:300]}
            print(f"  {lv.version}: NÃO extraída: {rec['motivo'][:200]}", flush=True)
        _dump(record_path(lv.version), rec)
    return finalize(hist)


def finalize(hist: common.History | None = None) -> dict:
    """versions.json (C13), extraction.json e MANIFEST.sha256 a partir dos registros por versão."""
    from bo.repo.core import now
    hist = hist or common.read_history()
    recs = []
    for lv in hist.versions:
        rp = record_path(lv.version)
        if rp.is_file():
            recs.append(json.loads(rp.read_text(encoding="utf-8")))
        else:
            recs.append({"version": lv.version, "status": "pending", "motivo": "ainda não processada"})
    vers = []
    for lv, r in zip(hist.versions, recs):
        e = {"version": lv.version, "released_at": lv.released_at}
        if r.get("status") == "extracted":
            e["schema_sha256"] = r["extract"]["schema_json_sha256"]
        vers.append(e)
    gen = now()
    vdoc = {"schema": "bo.versions/1", "contract": "C13", "contract_version": "3.1.0", "module": common.MODULE,
            "generated_at": gen, "provider": common.PROVIDER, "versions": vers}
    _dump(common.out_dir() / "versions.json", vdoc)
    lt = dict(hist.left_truncation)
    ext = {
        "schema": "bo.hist_oci.extraction_index/1", "module": common.MODULE, "provider": common.PROVIDER,
        "source": hist.source, "pin": hist.pin, "platform": common.PLATFORM, "generated_at": gen,
        "history_versions": {"path": hist.doc_path, "sha256": hist.doc_sha256},
        "window": hist.window, "cutoff": hist.cutoff,
        "left_truncation": {**lt, "declarado": (
            f"Truncamento à esquerda: a janela começa em {hist.window['start']}, mas o oci só aparece no Registry "
            f"como {common.NAMESPACE}/{common.NAME} a partir da {lt['index_first_version']} "
            f"({lt['index_first_published_at']}); antes disso não há versão em vigor no índice "
            f"(version_in_force = {lt['version_in_force']}). Nada antes da primeira versão amostrada é observado; "
            "eventos de schema anteriores a ela não entram, e quem estimar sobrevivência a partir daqui trata a "
            "primeira observação como entrada tardia, não como nascimento.")},
        "counts": {
            "listed": len(recs),
            "extracted": sum(r.get("status") == "extracted" for r in recs),
            "not_extracted": sum(r.get("status") == "not_extracted" for r in recs),
            "pending": sum(r.get("status") == "pending" for r in recs)},
        "versions": [{
            "version": r["version"], "status": r.get("status"),
            **({"motivo": r["motivo"]} if r.get("status") != "extracted" else {
                "schema_sha256": r["extract"]["schema_json_sha256"],
                "atoms_file": Path(r["atoms"]["path"]).name, "atoms_gz_sha256": r["atoms"]["gz_sha256"],
                "atoms_jsonl_sha256": r["atoms"]["jsonl_sha256"], "types": r["atoms"]["types"],
                "atoms": r["atoms"]["atoms"], "data_sources": r["atoms"]["data_sources"],
                "write_only": r["atoms"]["write_only"],
                "provider_binary_sha256": r["extract"]["provider_binary"]["sha256"],
                "zip_sha256": r["chain"]["zip"]["sha256"], "shasums_sha256": r["chain"]["shasums"]["sha256"],
                "gpg_primary_fpr": r["chain"]["gpg"]["primary_fpr"],
                "binarios_apagados": not r["binarios"]["restantes"]}),
        } for r in recs],
    }
    ext["crosscheck_pin"] = crosscheck_pin(hist, recs)
    _dump(common.out_dir() / "extraction.json", ext)
    manifest.write_data()
    return ext


def crosscheck_pin(hist: common.History, recs: list[dict]) -> dict:
    """Conferência informativa (não é entrada do módulo): os átomos do pin gerados aqui, a partir de um binário
    baixado de novo, são byte a byte os átomos do SCHEMA-OCI ($BO_DATA/SCHEMA-OCI/atoms.jsonl)?"""
    other = common.bo_data() / "SCHEMA-OCI" / "atoms.jsonl"
    r = next((x for x in recs if x.get("version") == hist.pin), {})
    if r.get("status") != "extracted":
        return {"pin": hist.pin, "resultado": "pin não extraído"}
    if not other.is_file():
        return {"pin": hist.pin, "resultado": "SCHEMA-OCI sem atoms.jsonl para comparar"}
    a, b = r["atoms"]["jsonl_sha256"], common.sha256_file(other)
    return {"pin": hist.pin, "hist_oci_atoms_jsonl_sha256": a, "schema_oci_atoms_jsonl_sha256": b,
            "igual": a == b, "schema_sha256": r["extract"]["schema_json_sha256"],
            "nota": "informativa: o SCHEMA-OCI não é dependência; diferença seria achado, não ajuste"}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="bo.hist_oci.pipeline", description=__doc__.split("\n")[0])
    ap.add_argument("--only", nargs="+", help="só estas versões (da lista histórica)")
    ap.add_argument("--redo", action="store_true", help="refaz versões já extraídas")
    ap.add_argument("--no-download", action="store_true")
    ap.add_argument("--finalize", action="store_true", help="só regrava versions.json, extraction.json e manifesto")
    a = ap.parse_args(argv)
    ext = finalize() if a.finalize else run(a.only, a.redo, not a.no_download)
    print(json.dumps(ext["counts"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
