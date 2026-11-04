"""Gate de cobertura do oráculo STO (chamado pelo despachante: python -I -m bo.pilot.oracle_coverage --slice sto).

Reprova (saída 1) se:
  - algum caso obrigatório (MANDATORY.json) não tem positivo, negativo e desconhecido na calibração E nas retidas;
  - alguma das 12 direções não tem configuração aceitável, contraexemplo e desconhecido nas duas partições;
  - algum provedor some de um caso obrigatório na calibração;
  - a fração retida é < 30% no total, em algum caso obrigatório ou em alguma direção;
  - a partição retida não está só cifrada e fora do repositório: o cifrado não bate com o índice, o certificado não
    é o do índice, o diretório selado fica dentro de $BO_REPO, existe texto claro de item retido (por hash) em
    $BO_REPO/pilot/sto, $BO_DATA/PILOT-STO-ORACLE ou $BO_TMP, ou um id retido aparece em arquivo do repositório;
  - uma fixture de calibração listada não existe ou um item de calibração coincide (hash) com um retido.
Grava $BO_DATA/PILOT-STO-ORACLE/coverage_report.json.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

from .build import MODULE, canon, cert_fingerprint, data, item_hash, now_iso, repo, sealed_dir, sha_file, sto

MIN_HELD = 0.30
POLS = ("positive", "negative", "unknown")


def _scan_plaintext(paths, held_hashes):
    hits = []
    for root in paths:
        if not root.exists():
            continue
        for f in root.rglob("*.json"):
            if "sealed" in f.parts and f.name == "SEALED_INDEX.json":
                continue
            try:
                doc = json.loads(f.read_text(encoding="utf-8"))
            except (ValueError, UnicodeDecodeError, OSError):
                continue
            cands = []
            if isinstance(doc, dict):
                if doc.get("schema") == "bo.pilot.sto.fixture/1":
                    cands.append(doc)
                if "source" in doc and "target" in doc:
                    cands.append({"source": doc["source"], "target": doc["target"]})
                for k in ("fixtures", "entries"):
                    for it in doc.get(k, []) if isinstance(doc.get(k), list) else []:
                        if isinstance(it, dict):
                            cands.append(it.get("fixture", it))
                            if "source" in it:
                                cands.append({"source": it["source"], "target": it["target"]})
            for c in cands:
                if item_hash(c) in held_hashes:
                    hits.append(str(f))
                    break
    return hits


def run(slice_):
    errs, notes = [], []
    if slice_ != "sto":
        return [f"fatia {slice_!r} não é deste módulo (PILOT-STO-ORACLE só cobre 'sto')"], notes, {}
    root, base = repo(), sto()
    man = json.loads((base / "oracle" / "MANDATORY.json").read_text(encoding="utf-8"))
    ea = json.loads((base / "expected_answers.json").read_text(encoding="utf-8"))
    sd = sealed_dir()
    idx = json.loads((sd / "SEALED_INDEX.json").read_text(encoding="utf-8"))

    # 1. retidas só cifradas, fora do repositório, íntegras
    try:
        sd.resolve().relative_to(root.resolve())
        errs.append(f"diretório selado dentro do repositório: {sd}")
    except ValueError:
        pass
    if sha_file(sd / "heldout.cms.pem") != idx["ciphertext_sha256"]:
        errs.append("heldout.cms.pem não bate com o sha do índice")
    if not (sd / "heldout.cms.pem").read_text(encoding="ascii", errors="replace").startswith("-----BEGIN CMS-----"):
        errs.append("heldout.cms.pem não é um envelope CMS")
    if cert_fingerprint(sd / "recipient_cert.pem") != idx["recipient_fingerprint_sha256"]:
        errs.append("certificado do destinatário diverge do índice")
    if "PRIVATE KEY" in (sd / "recipient_cert.pem").read_text(encoding="ascii", errors="replace"):
        errs.append("há chave privada no diretório selado")
    extra = sorted(p.name for p in sd.iterdir() if p.name not in ("heldout.cms.pem", "SEALED_INDEX.json", "recipient_cert.pem"))
    if extra:
        errs.append(f"arquivo inesperado no diretório selado: {extra}")
    if ea.get("heldout", {}).get("ciphertext_sha256") != idx["ciphertext_sha256"]:
        errs.append("expected_answers.json aponta para outro selo")
    held_hashes = {it["sha256"] for it in idx["items"]}
    tmp = Path(os.environ.get("BO_TMP", str(data() / "tmp" / MODULE)))
    leaks = _scan_plaintext([base, data() / MODULE, tmp], held_hashes)
    if leaks:
        errs.append(f"texto claro de item retido encontrado: {leaks[:5]}")
    held_ids = [it["item_id"] for it in idx["items"]]
    try:
        tracked = subprocess.run(["git", "-C", str(root), "grep", "-l", "-F", "-e", held_ids[0]] + sum(
            (["-e", i] for i in held_ids[1:]), []), capture_output=True, text=True).stdout.split()
    except OSError:
        tracked = []
    if tracked:
        errs.append(f"id de item retido em arquivo do repositório: {tracked[:5]}")
    if any(not i.startswith(("FX-STO-H-", "DX-H-")) for i in held_ids):
        errs.append("id de item retido sem o prefixo opaco")

    # 2. calibração existe e não coincide com retidas
    for fid, f in ea["fixtures"].items():
        p = root / f["file"]
        if not p.is_file():
            errs.append(f"fixture de calibração ausente: {f['file']}")
            continue
        if item_hash(json.loads(p.read_text(encoding="utf-8"))) in held_hashes:
            errs.append(f"fixture de calibração igual a uma retida: {fid}")
    for eid, e in ea["directions"].items():
        p = root / e["file"]
        if not p.is_file():
            errs.append(f"entrada de calibração ausente: {e['file']}")
            continue
        d = json.loads(p.read_text(encoding="utf-8"))
        if item_hash({"source": d["source"], "target": d["target"]}) in held_hashes:
            errs.append(f"entrada de calibração igual a uma retida: {eid}")

    # 3. polaridades por caso obrigatório e por direção, nas duas partições
    cov = {"calib": defaultdict(Counter), "heldout": defaultdict(Counter)}
    prov = defaultdict(set)
    for f in ea["fixtures"].values():
        cov["calib"][f["case"]][f["polarity"]] += 1
        prov[f["case"]].add(f["provider"])
    for e in ea["directions"].values():
        cov["calib"][e["direction"]][e["polarity"]] += 1
    for it in idx["items"]:
        key = it["case"] if it["kind"] == "fixture" else it["direction"]
        cov["heldout"][key][it["polarity"]] += 1
    keys = list(man["mandatory_cases"]) + list(man["directions"])
    for k in keys:
        for part in ("calib", "heldout"):
            for pol in POLS:
                if cov[part][k][pol] == 0:
                    errs.append(f"{k}: sem {pol} na partição {part}")
        n_c, n_h = sum(cov["calib"][k].values()), sum(cov["heldout"][k].values())
        if n_c + n_h == 0 or n_h / (n_c + n_h) < MIN_HELD:
            errs.append(f"{k}: fração retida {n_h}/{n_c + n_h} < {MIN_HELD:.0%}")
    for mc in man["mandatory_cases"]:
        miss = {"aws", "google", "azurerm", "oci"} - prov[mc]
        if miss:
            errs.append(f"{mc}: provedor(es) ausente(s) na calibração: {sorted(miss)}")
    n_cal = len(ea["fixtures"]) + len(ea["directions"])
    n_held = len(idx["items"])
    frac = n_held / (n_cal + n_held)
    if frac < MIN_HELD:
        errs.append(f"fração retida total {frac:.3f} < {MIN_HELD}")
    stats = {"calib_items": n_cal, "heldout_items": n_held, "heldout_fraction": round(frac, 4),
             "by_key": {k: {part: dict(cov[part][k]) for part in cov} for k in keys}}
    return errs, notes, stats


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    slice_ = argv[argv.index("--slice") + 1] if "--slice" in argv else "sto"
    errs, notes, stats = run(slice_)
    rep = {"schema": "bo.pilot.sto.coverage/1", "module": MODULE, "checked_at": now_iso(), "slice": slice_,
           "result": "OK" if not errs else "FAIL", "errors": errs, "stats": stats}
    out = data() / MODULE / "coverage_report.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(canon(rep))
    for e in errs:
        print("  FALHA", e)
    if stats:
        print(f"oracle_coverage --slice {slice_}: {len(stats['by_key'])} chaves (casos obrigatórios + direções); "
              f"calibração {stats['calib_items']}, retidas {stats['heldout_items']} ({stats['heldout_fraction']:.1%})")
    print("RESULTADO: " + ("OK" if not errs else f"REPROVADO ({len(errs)})"))
    return 0 if not errs else 1


if __name__ == "__main__":
    sys.exit(main())
