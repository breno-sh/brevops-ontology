"""Instantâneo bruto e imutável do índice público: Terraform Registry (v1 e v2) e releases da HashiCorp.

  python -I -m bo.pins.fetch [--force]

Grava em $BO_DATA/PINS/registry_index/ as respostas exatamente como vieram (bytes), com URL, instante e sha256
de cada uma em snapshot.json. Só metadado público: nenhuma conta, nenhuma credencial, nada executado.

Para o pin de cada provider, o SHA256SUMS e a assinatura são REAPROVEITADOS da pré-busca
($BO_DATA/downloads/prefetch/<provider>/<versão>/) depois de conferir o sha256 contra o MANIFEST.json dela; se a
versão fixada não for a da pré-busca, são baixados das URLs que a rota de download do Registry indica. A
assinatura é conferida com a chave pública que o próprio Registry publica. O zip do Terraform CLI é baixado só
para o temporário, conferido contra o SHA256SUMS assinado e comparado com o binário local; depois é apagado."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import shutil
import subprocess
import sys
import time
import urllib.request
import zipfile
from pathlib import Path

from . import config, sig
from . import select as S

UA = "bo-pins/1 (metadado publico; pesquisa academica)"


class FetchError(Exception):
    pass


def sha256(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def get(url: str, tries: int = 3) -> bytes:
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
            with urllib.request.urlopen(req, timeout=120) as r:
                return r.read()
        except Exception as e:  # rede: qualquer falha vira nova tentativa
            last = e
            time.sleep(2 * (i + 1))
    raise FetchError(f"GET {url} falhou: {type(last).__name__}: {last}")


class Snapshot:
    def __init__(self, root: Path):
        self.root = root
        self.files: list[dict] = []

    def put(self, rel: str, data: bytes, origin: str, kind: str, note: str = "") -> Path:
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        rec = {"path": rel, "kind": kind, "origin": origin, "bytes": len(data), "sha256": sha256(data),
               "fetched_at": config.now_iso()}
        if note:
            rec["note"] = note
        self.files.append(rec)
        return p

    def fetch(self, rel: str, url: str, kind: str) -> bytes:
        data = get(url)
        self.put(rel, data, url, kind)
        return data


def prefetch_copy(provider: str, version: str, name: str) -> bytes | None:
    """Arquivo da pré-busca, só se o sha256 bater com o MANIFEST.json dela."""
    d = config.prefetch_dir() / provider / version
    man, f = d / "MANIFEST.json", d / name
    if not (man.exists() and f.exists()):
        return None
    m = json.loads(man.read_bytes())
    want = {x["path"]: x["sha256"] for x in m.get("files", [])}.get(name)
    data = f.read_bytes()
    if want != sha256(data):
        raise FetchError(f"pré-busca {provider}/{version}/{name}: sha256 diverge do MANIFEST.json")
    return data


def fetch_provider(snap: Snapshot, provider: str, verification: dict) -> None:
    ns, typ = config.PROVIDERS[provider]
    base = f"providers/{provider}"
    v1 = snap.fetch(f"{base}/registry-v1-versions.json", f"{config.REGISTRY}/v1/providers/{ns}/{typ}/versions",
                    "registry_v1_versions")
    v2 = snap.fetch(f"{base}/registry-v2-provider-versions.json",
                    f"{config.REGISTRY}/v2/providers/{ns}/{typ}?include=provider-versions", "registry_v2_versions")
    rels, issues = S.releases_from_registry(json.loads(v1), json.loads(v2))
    if issues:
        raise FetchError(f"{provider}: v1 e v2 divergem: {'; '.join(issues)}")
    pin = S.stable_before(rels, config.cutoff_end())
    ver = pin.version
    os_, arch = config.TERRAFORM_PLATFORM
    dl = snap.fetch(f"{base}/registry-download-{ver}-{os_}_{arch}.json",
                    f"{config.REGISTRY}/v1/providers/{ns}/{typ}/{ver}/download/{os_}/{arch}", "registry_download")
    d = json.loads(dl)
    sums_name = f"terraform-provider-{typ}_{ver}_SHA256SUMS"
    sig_name = sums_name + ".sig"
    sums = prefetch_copy(provider, ver, sums_name)
    sigb = prefetch_copy(provider, ver, sig_name)
    if sums is not None and sigb is not None:
        origin = f"prefetch:{provider}/{ver}/"
        snap.put(f"{base}/{sums_name}", sums, origin + sums_name + f" (URL original {d['shasums_url']})", "shasums")
        snap.put(f"{base}/{sig_name}", sigb, origin + sig_name + f" (URL original {d['shasums_signature_url']})",
                 "shasums_sig")
    else:
        sums = snap.fetch(f"{base}/{sums_name}", d["shasums_url"], "shasums")
        sigb = snap.fetch(f"{base}/{sig_name}", d["shasums_signature_url"], "shasums_sig")
    keys = d.get("signing_keys", {}).get("gpg_public_keys", [])
    if not keys:
        raise FetchError(f"{provider} {ver}: Registry sem chave pública de assinatura")
    lines = dict(reversed(ln.split()) for ln in sums.decode().splitlines() if ln.strip())
    if lines.get(d["filename"]) != d["shasum"]:
        raise FetchError(f"{provider} {ver}: shasum do Registry não está no SHA256SUMS para {d['filename']}")
    res = sig.verify(snap.root / base / sums_name, snap.root / base / sig_name, keys[0]["ascii_armor"])
    entry = {"version": ver, "zip": d["filename"], "zip_sha256": d["shasum"], "zip_sha256_in_shasums": True,
             "signature": res, "registry_key_id": keys[0].get("key_id")}
    if not res["good"] and ns == "hashicorp":
        # a cópia da chave servida pelo Registry pode estar vencida; a da HashiCorp (.well-known) é a vigente
        vk = vendor_key(snap)
        vres = sig.verify(snap.root / base / sums_name, snap.root / base / sig_name, vk)
        if vres["primary_fingerprint"] != res["primary_fingerprint"]:
            raise FetchError(f"{provider} {ver}: chave da HashiCorp não é a mesma do Registry")
        entry["signature_vendor_key"] = vres
    if not (entry.get("signature_vendor_key") or res)["good"]:
        raise FetchError(f"{provider} {ver}: assinatura sem GOODSIG com chave vigente")
    verification[provider] = entry


HASHICORP_KEY_URL = "https://www.hashicorp.com/.well-known/pgp-key.txt"
HASHICORP_KEY_REL = "vendor_keys/hashicorp-pgp-key.txt"


def vendor_key(snap: Snapshot) -> str:
    p = snap.root / HASHICORP_KEY_REL
    if not p.exists():
        snap.fetch(HASHICORP_KEY_REL, HASHICORP_KEY_URL, "vendor_key")
    return p.read_text(encoding="utf-8")


def fetch_terraform(snap: Snapshot, verification: dict, local_tf: str | None) -> None:
    v = config.TERRAFORM_VERSION
    snap.fetch("terraform/releases-terraform-latest20.json", f"{config.RELEASES_API}/terraform?limit=20",
               "releases_list")
    rel = json.loads(snap.fetch(f"terraform/releases-terraform-{v}.json", f"{config.RELEASES_API}/terraform/{v}",
                                "release"))
    sums = snap.fetch(f"terraform/terraform_{v}_SHA256SUMS", rel["url_shasums"], "shasums")
    sig_url = next(u for u in rel["url_shasums_signatures"] if u.endswith(".72D7468F.sig"))
    snap.fetch(f"terraform/terraform_{v}_SHA256SUMS.72D7468F.sig", sig_url, "shasums_sig")
    res = sig.verify(snap.root / f"terraform/terraform_{v}_SHA256SUMS",
                     snap.root / f"terraform/terraform_{v}_SHA256SUMS.72D7468F.sig", vendor_key(snap))
    if not res["good"] or not res["primary_fingerprint"].endswith("72D7468F"):
        raise FetchError(f"terraform {v}: SHA256SUMS sem GOODSIG da chave da HashiCorp")
    os_, arch = config.TERRAFORM_PLATFORM
    zname = f"terraform_{v}_{os_}_{arch}.zip"
    lines = dict(reversed(ln.split()) for ln in sums.decode().splitlines() if ln.strip())
    want = lines[zname]
    zbytes = get(f"{config.RELEASES}/terraform/{v}/{zname}")
    if sha256(zbytes) != want:
        raise FetchError(f"{zname}: sha256 do zip não confere com o SHA256SUMS assinado")
    with zipfile.ZipFile(io.BytesIO(zbytes)) as z:
        bin_sha = sha256(z.read("terraform"))
    local = {"zip": zname, "zip_sha256": want, "binary_in_zip_sha256": bin_sha, "local_path": None,
             "local_sha256": None, "local_matches_official": False, "local_version": None}
    if local_tf:
        lp = Path(local_tf).resolve()
        local["local_path"] = str(lp).replace(str(Path.home()), "~")
        local["local_sha256"] = sha256(lp.read_bytes())
        local["local_matches_official"] = local["local_sha256"] == bin_sha
        r = subprocess.run([str(lp), "version", "-json"], capture_output=True, text=True, timeout=60,
                           env={"PATH": "/usr/bin:/bin", "HOME": str(config.bo_tmp()), "CHECKPOINT_DISABLE": "1"})
        local["local_version"] = json.loads(r.stdout).get("terraform_version")
    verification["terraform"] = {"version": v, "signature": res, **local}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="bo.pins.fetch")
    ap.add_argument("--force", action="store_true", help="refaz o instantâneo (o anterior é apagado)")
    ap.add_argument("--terraform", default=shutil.which("terraform"), help="binário local a comparar")
    a = ap.parse_args(argv)
    root = config.index_dir()
    if (root / "snapshot.json").exists() and not a.force:
        print(f"instantâneo já existe em {root} (imutável; use --force para refazer)", file=sys.stderr)
        return 1
    stage = config.bo_tmp() / "registry_index.new"
    shutil.rmtree(stage, ignore_errors=True)
    stage.mkdir(parents=True)
    snap = Snapshot(stage)
    started = config.now_iso()
    verification: dict = {}
    for p in config.PROVIDERS:
        fetch_provider(snap, p, verification)
        print(f"[{config.now_iso()}] {p}: pin {verification[p]['version']} (assinatura "
              f"{verification[p]['signature']['fingerprint'][-16:]})")
    fetch_terraform(snap, verification, a.terraform)
    t = verification["terraform"]
    print(f"[{config.now_iso()}] terraform {t['version']}: zip confere; binário local "
          f"{'igual ao oficial' if t['local_matches_official'] else 'DIFERENTE do oficial'}")
    finished = config.now_iso()
    vbytes = (json.dumps(verification, indent=1, ensure_ascii=False, sort_keys=True) + "\n").encode()
    snap.put("verification.json", vbytes, "derivado: conferências feitas no fetch", "verification")
    doc = {"schema": "bo.pins.registry_snapshot/1", "module": config.MODULE, "started_at": started,
           "fetched_at": finished, "cutoff_date": config.CUTOFF_DATE.isoformat(),
           "cutoff_end_exclusive": config.cutoff_end().isoformat(),
           "providers": {p: "/".join(config.PROVIDERS[p]) for p in config.PROVIDERS},
           "terraform_version": config.TERRAFORM_VERSION, "files": snap.files}
    (stage / "snapshot.json").write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    (stage / "SOURCE.txt").write_text(
        "Instantâneo do índice público do Terraform Registry e dos releases da HashiCorp, gravado por\n"
        "python -I -m bo.pins.fetch (módulo PINS) entre " + started + " e " + finished + " (America/Recife).\n"
        "Fontes: https://registry.terraform.io/v1/providers/<ns>/<tipo>/versions (plataformas e protocolos),\n"
        "https://registry.terraform.io/v2/providers/<ns>/<tipo>?include=provider-versions (published-at),\n"
        "https://registry.terraform.io/v1/providers/<ns>/<tipo>/<versão>/download/darwin/arm64 (shasum, chave),\n"
        "https://api.releases.hashicorp.com/v1/releases/terraform, https://releases.hashicorp.com/terraform/ e a chave\n"
        "pública vigente da HashiCorp em https://www.hashicorp.com/.well-known/pgp-key.txt.\n"
        "SHA256SUMS dos providers reaproveitados da pré-busca quando o sha256 confere com o MANIFEST.json dela.\n"
        "Dado não confiável: nada aqui é executado. Metadado público, sem conta nem credencial.\n"
        "Licença: metadados públicos do Registry (termos de uso da HashiCorp); usados só como fonte de versões e datas.\n",
        encoding="utf-8")
    shutil.rmtree(root, ignore_errors=True)
    root.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(stage), str(root))
    write_manifest(root)
    print(f"[{config.now_iso()}] instantâneo em {root}: {len(snap.files)} arquivo(s)")
    return 0


def write_manifest(root: Path) -> None:
    lines = []
    for f in sorted(p for p in root.rglob("*") if p.is_file() and p.name != "MANIFEST.sha256"):
        lines.append(f"{sha256(f.read_bytes())}  {f.relative_to(root).as_posix()}")
    (root / "MANIFEST.sha256").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
