"""HIST-GCP de ponta a ponta: lista do PINS -> cadeia assinada -> extração em sandbox -> átomos -> versions.json.

  python -I -m bo.hist_gcp.pipeline [--only V ...] [--force] [--min-free-gib N]

Para cada versão de universe/history_versions.json (google), em ordem:
  * df -h da pasta de dados antes de baixar (para se faltar espaço; o binário é apagado depois de cada versão);
  * sem build darwin_arm64 no índice do PINS e na rota de download: INDISPONÍVEL, com o motivo que os dois dizem;
  * com build: SHA256SUMS assinado conferido (bo.hist_gcp.signed), lock zh:, extração pelo binário assinado
    (bo.hist_gcp.extract), átomos C01 pela biblioteca (bo.hist_gcp.atoms) validados no validador único;
  * receipt por versão em $BO_DATA/HIST-GCP/receipts/ (caminhos portáteis, sem log).
Versão já extraída é reaproveitada (cadeia reconferida sem rede, sha do schema e dos átomos conferidos), salvo
--force. No fim: versions.json (C13 3.1.0), extraction.json (situação e motivo por versão) e MANIFEST.sha256.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from . import atoms as A
from . import common as C
from . import extract as E
from . import signed as S

EXTRACTION_SCHEMA = "bo.hist_gcp.extraction/1"


def df_h(p: Path) -> str:
    r = subprocess.run(["/bin/df", "-h", str(p)], capture_output=True, text=True, check=False)
    return r.stdout.strip().splitlines()[-1] if r.stdout.strip() else "df indisponível"


def validate_atoms(gz: Path, version: str) -> dict:
    """C01 no validador único sobre o JSONL descomprimido (o validador não lê .gz)."""
    from bo.contracts import validate as V
    tmp = C.bo_tmp() / "validate" / f"atoms_{version}.jsonl"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_bytes(C.gunzip_bytes(gz))
    try:
        res = V.validate("C01_atoms", tmp)
        return {"ok": res.ok, "records": res.n, "errors": res.errors[:10]}
    finally:
        tmp.unlink(missing_ok=True)


def unavailable_reason(sel: dict, chain: dict) -> str:
    idx = chain["index"]
    others = ", ".join(idx["platforms"])
    err = "; ".join(chain.get("registry_errors") or []) or "sem corpo de erro"
    return (f"sem build {C.OS_ARCH} publicado: o índice v1 do Registry guardado pelo PINS ({idx['index']}, "
            f"sha256 {idx['index_sha256'][:12]}…) lista para {sel['version']} só as plataformas [{others}]; "
            f"history_versions.json traz darwin_arm64=false; a rota {S.download_url(sel['version'])} respondeu "
            f"HTTP {chain['http_status']} ({err}). A extração exige o binário assinado executado nesta máquina "
            f"({C.OS_ARCH}); nenhum schema foi produzido nem inferido para esta versão.")


def receipt_doc(sel: dict, chain: dict, ext: dict, at: dict, val: dict, key: dict) -> dict:
    v = sel["version"]
    return {
        "schema": "bo.hist_gcp.receipt/1", "module": C.ID,
        "provider": {"address": C.ADDRESS, "name": C.PROVIDER, "version": v,
                     "released_at": sel["released_at"], "published_at": sel["published_at"],
                     "reasons": sel["reasons"], "protocols": sel["protocols"]},
        "signed": {"download_meta": C.portable(C.download_dir(v) / "registry-download-darwin_arm64.json"),
                   "download_meta_sha256": C.sha256_file(C.download_dir(v) / "registry-download-darwin_arm64.json"),
                   "sha256sums": C.portable(chain["sha256sums"]), "sha256sums_sha256": chain["sha256sums_sha256"],
                   "signature": C.portable(chain["signature"]), "signature_sha256": chain["signature_sha256"],
                   "gpg": chain["gpg"], "vendor_key": {"path": C.portable(key["path"]), "sha256": key["sha256"]},
                   "zip": chain["meta"]["filename"], "zip_sha256": chain["zips"][C.OS_ARCH],
                   "platforms_in_sha256sums": len(chain["zips"]),
                   "index_platforms": chain["index"]["platforms"]},
        **ext,
        "atoms": {"path": C.portable(C.atoms_path(v)), **at, "C01_validate": {"ok": val["ok"], "records": val["records"]}},
    }


def reuse(sel: dict, hist: dict, key: dict) -> dict | None:
    """Receipt de uma extração anterior, se tudo ainda confere sem rede; senão None."""
    v = sel["version"]
    rp, ap = C.receipt_path(v), C.atoms_path(v)
    if not (rp.exists() and ap.exists() and (C.raw_schema_dir(v) / "schema.json.gz").exists()):
        return None
    rec = json.loads(rp.read_text(encoding="utf-8"))
    chain = S.verify_local(v, hist, key)
    if chain["sha256sums_sha256"] != rec["signed"]["sha256sums_sha256"]:
        return None
    raw = C.gunzip_bytes(C.raw_schema_dir(v) / "schema.json.gz")
    if C.sha256_bytes(raw) != rec["schema_json"]["sha256"] or C.sha256_file(ap) != rec["atoms"]["gz_sha256"]:
        return None
    if not rec["atoms"]["C01_validate"]["ok"]:
        return None
    return rec


def one(sel: dict, hist: dict, key: dict, tf: dict, force: bool, min_free: float) -> dict:
    v = sel["version"]
    if not force:
        rec = reuse(sel, hist, key)
        if rec is not None:
            print(f"[{C.now()}] {v}: reaproveitada (cadeia, schema e átomos conferidos)", flush=True)
            return {"status": "extracted", "receipt": rec}
    print(f"[{C.now()}] {v}: df -h -> {df_h(C.bo_data())}", flush=True)
    if E.disk_free_gib(C.bo_data()) < min_free:
        raise C.HistError(f"{v}: menos de {min_free} GiB livres em {C.portable(C.bo_data())}; parei antes de baixar")
    chain = S.fetch_and_verify(v, hist, key)
    if not chain["available"]:
        if sel["darwin_arm64"]:
            raise C.HistError(f"{v}: history_versions diz darwin_arm64=true, mas não há build")
        for stale in (C.atoms_path(v), C.receipt_path(v), C.lock_path(v)):
            stale.unlink(missing_ok=True)
        reason = unavailable_reason(sel, chain)
        print(f"[{C.now()}] {v}: INDISPONÍVEL ({C.OS_ARCH} ausente)", flush=True)
        return {"status": "unavailable", "reason": reason, "evidence": {
            "index": chain["index"]["index"], "index_sha256": chain["index"]["index_sha256"],
            "index_platforms": chain["index"]["platforms"], "history_darwin_arm64": sel["darwin_arm64"],
            "download_route": S.download_url(v), "http_status": chain["http_status"],
            "registry_errors": chain.get("registry_errors"),
            "response": C.portable(C.download_dir(v) / "registry-download-darwin_arm64.response.json")}}
    if not sel["darwin_arm64"]:
        raise C.HistError(f"{v}: há build {C.OS_ARCH}, mas history_versions diz darwin_arm64=false")
    ext = E.run(v, chain, tf)
    at = A.write(C.raw_schema_dir(v) / "schema.json.gz", v, C.atoms_path(v))
    val = validate_atoms(C.atoms_path(v), v)
    if not val["ok"]:
        raise C.HistError(f"{v}: C01 reprovou: {val['errors'][:3]}")
    rec = receipt_doc(sel, chain, ext, at, val, key)
    C.write_json(C.receipt_path(v), rec)
    print(f"[{C.now()}] {v}: {at['types']} tipos, {at['atoms']} átomos, schema {ext['schema_json']['sha256'][:12]}…, "
          f"binário apagado; df -h -> {df_h(C.bo_data())}", flush=True)
    return {"status": "extracted", "receipt": rec}


def versions_doc(hist: dict, results: dict, generated_at: str) -> dict:
    out = []
    for s in hist["selection"]:
        e = {"version": s["version"], "released_at": s["released_at"]}
        r = results[s["version"]]
        if r["status"] == "extracted":
            e["schema_sha256"] = r["receipt"]["schema_json"]["sha256"]
        out.append(e)
    return {"schema": "bo.versions/1", "contract": "C13", "contract_version": "3.1.0", "module": C.ID,
            "generated_at": generated_at, "provider": C.PROVIDER, "versions": out}


def extraction_doc(hist: dict, pn: dict, tf: dict, key: dict, results: dict, generated_at: str) -> dict:
    rows = []
    for s in hist["selection"]:
        v = s["version"]
        r = results[v]
        row = {"version": v, "released_at": s["released_at"], "published_at": s["published_at"],
               "reasons": s["reasons"], "status": r["status"]}
        if r["status"] == "extracted":
            rec = r["receipt"]
            row.update({"schema_sha256": rec["schema_json"]["sha256"],
                        "atoms": C.portable(C.atoms_path(v)), "atoms_gz_sha256": rec["atoms"]["gz_sha256"],
                        "atoms_jsonl_sha256": rec["atoms"]["jsonl_sha256"],
                        "receipt": C.portable(C.receipt_path(v)), "receipt_sha256": C.sha256_file(C.receipt_path(v)),
                        "counts": {k: rec["atoms"][k] for k in ("types", "atoms", "required", "optional", "computed",
                                                                 "configurable", "sensitive", "deprecated",
                                                                 "write_only", "data_sources")},
                        "provider_binary_sha256": rec["provider_binary"]["sha256"],
                        "provider_binary_h1": rec["provider_binary"]["h1"]})
        else:
            row.update({"reason": r["reason"], "evidence": r["evidence"]})
        rows.append(row)
    n_ok = sum(1 for r in rows if r["status"] == "extracted")
    first = next((r["version"] for r in rows if r["status"] == "extracted"), None)
    return {
        "schema": EXTRACTION_SCHEMA, "module": C.ID, "generated_at": generated_at, "provider": C.PROVIDER,
        "address": C.ADDRESS, "os_arch": C.OS_ARCH,
        "inputs": {"history_versions": {"path": C.portable(hist["path"]), "sha256": hist["sha256"],
                                        "contract_version": hist["contract_version"]},
                   "pins": {"path": C.portable(pn["path"]), "sha256": pn["sha256"]},
                   "vendor_key": {"path": C.portable(key["path"]), "sha256": key["sha256"],
                                  "primary_fingerprint": key["primary_fingerprint"]}},
        "terraform": {"version": tf["version"], "binary_sha256": tf["binary_sha256"], "zip_sha256": tf["zip_sha256"]},
        "left_truncation": hist["left_truncation"],
        "first_extracted": first,
        "totals": {"listed": len(rows), "extracted": n_ok, "unavailable": len(rows) - n_ok},
        "versions": rows,
        "note": ("Versões na ordem do history_versions.json (PINS). 'extracted': schema do binário assinado, "
                 "átomos em atoms_<versão>.jsonl.gz e receipt. 'unavailable': motivo e evidência; no versions.json "
                 "a versão aparece sem schema_sha256 e não há arquivo de átomos. Com a primeira versão listada "
                 "indisponível, a primeira observação de schema é first_extracted, depois do truncamento à esquerda "
                 "declarado pelo PINS."),
    }


def finalize(hist: dict, results: dict) -> dict:
    pn = C.pins()
    tf = C.terraform_binary()
    key = C.vendor_key()
    gen = C.now()
    out = C.out_dir()
    vd = versions_doc(hist, results, gen)
    C.write_json(out / "versions.json", vd)
    C.write_json(out / "extraction.json", extraction_doc(hist, pn, tf, key, results, gen))
    n = C.write_manifest(out)
    return {"versions": len(vd["versions"]), "manifest_files": n}


def run(only: list[str] | None, force: bool, min_free: float) -> dict:
    hist = C.history()
    key = C.vendor_key()
    tf = C.terraform_binary()
    results = {}
    for sel in hist["selection"]:
        v = sel["version"]
        if only and v not in only:
            rec = reuse(sel, hist, key)
            prev = json.loads((C.out_dir() / "extraction.json").read_text(encoding="utf-8")) \
                if (C.out_dir() / "extraction.json").exists() else {"versions": []}
            old = [r for r in prev["versions"] if r["version"] == v and r["status"] == "unavailable"]
            if rec is not None:
                results[v] = {"status": "extracted", "receipt": rec}
            elif old:
                results[v] = {"status": "unavailable", "reason": old[0]["reason"], "evidence": old[0]["evidence"]}
            continue
        results[v] = one(sel, hist, key, tf, force, min_free)
    if len(results) != len(hist["selection"]):
        missing = [s["version"] for s in hist["selection"] if s["version"] not in results]
        print(f"[{C.now()}] versões ainda sem extração: {', '.join(missing)} (versions.json não gravado)")
        return {"pending": missing}
    return finalize(hist, results)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="bo.hist_gcp.pipeline", description=__doc__.split("\n")[0])
    ap.add_argument("--only", nargs="+", help="só estas versões (as outras são reaproveitadas)")
    ap.add_argument("--force", action="store_true", help="refaz a extração mesmo se a anterior confere")
    ap.add_argument("--min-free-gib", type=float, default=20.0)
    a = ap.parse_args(argv)
    r = run(a.only, a.force, a.min_free_gib)
    print(json.dumps(r, ensure_ascii=False))
    return 0 if "pending" not in r else 3


if __name__ == "__main__":
    sys.exit(main())
