"""Caminhos, pin do google, lock assinado e hash h1 do SCHEMA-GCP.

A versão e as somas vêm do universe/pins.json (PINS), nunca de constante digitada. A cadeia de confiança:
  pins.json.providers[google].shasums_sha256 == sha256 do SHA256SUMS da pré-busca (assinado; GPG conferido na
  pré-busca e de novo pelo terraform init) -> hashes zh: (zip por plataforma) do lock -> terraform init
  -lockfile=readonly reprova pacote fora do lock -> h1 (dirhash) da pasta desempacotada no plugin_cache,
  recalculado aqui e comparado ao lock, sem rede.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
from pathlib import Path

from bo.schema import lockfile

ID = "SCHEMA-GCP"
PROVIDER = "google"
SOURCE = "hashicorp/google"
ADDRESS = "registry.terraform.io/hashicorp/google"
OS_ARCH = "darwin_arm64"


def bo_repo() -> Path:
    return Path(os.environ.get("BO_REPO", "/Users/breno/doutorado/brevops-ontology"))


def bo_data() -> Path:
    return Path(os.environ.get("BO_DATA", "/Users/breno/doutorado/brevops-data"))


def bo_tmp() -> Path:
    return Path(os.environ.get("BO_TMP") or bo_data() / "tmp" / ID)


def out_dir() -> Path:
    return bo_data() / ID


def results_dir() -> Path:
    return bo_repo() / "results" / ID


def plugin_cache() -> Path:
    return out_dir() / "plugin_cache"


def lock_path() -> Path:
    return plugin_cache() / "terraform.lock.hcl"


def prefetch_dir(version: str) -> Path:
    return bo_data() / "downloads" / "prefetch" / PROVIDER / version


def tfschema_dir(version: str) -> Path:
    return bo_data() / "downloads" / "tfschema" / f"{PROVIDER}-{version}"


def portable(p: Path | str) -> str:
    """Caminho com $BO_DATA/$BO_REPO no lugar do prefixo absoluto (C00)."""
    s = str(p)
    for var, root in (("$BO_DATA", str(bo_data())), ("$BO_REPO", str(bo_repo()))):
        if s == root or s.startswith(root + "/"):
            return var + s[len(root):]
    return s


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


class PinError(SystemExit):
    """Entrada que não confere com o pin: reprova, sem seguir com dado não conferido."""


def read_pin(pins: Path | None = None) -> dict:
    """{'version', 'source', 'shasums_sha256', 'schema_sha256', 'terraform'} do google no pins.json."""
    pins = pins or bo_repo() / "universe" / "pins.json"
    doc = json.loads(Path(pins).read_text(encoding="utf-8"))
    hits = [p for p in doc.get("providers", []) if p.get("provider") == PROVIDER]
    if len(hits) != 1:
        raise PinError(f"{pins}: esperava 1 provider {PROVIDER}, achei {len(hits)}")
    p = hits[0]
    if p.get("source") != ADDRESS:
        raise PinError(f"{pins}: source {p.get('source')!r} != {ADDRESS}")
    return {**p, "terraform": doc["terraform"], "pins_path": str(pins), "pins_sha256": sha256_file(Path(pins))}


_SUMS_LINE = re.compile(r"^([0-9a-f]{64})  (\S+)$")


def parse_sha256sums(text: str, version: str) -> dict[str, str]:
    """{plataforma: sha256 do zip} do SHA256SUMS do release (o manifest.json não é pacote)."""
    out = {}
    pref = f"terraform-provider-{PROVIDER}_{version}_"
    for line in text.splitlines():
        if not line.strip():
            continue
        m = _SUMS_LINE.match(line)
        if not m:
            raise PinError(f"SHA256SUMS: linha fora do formato: {line[:80]!r}")
        sha, fname = m.groups()
        if not fname.startswith(pref):
            raise PinError(f"SHA256SUMS: arquivo de outro release: {fname}")
        if fname.endswith(".zip"):
            out[fname[len(pref):-4]] = sha
    return out


def signed_inputs(pin: dict) -> dict:
    """Confere a pré-busca contra o pin e devolve as somas por plataforma e o h1 da pré-busca."""
    v = pin["version"]
    pf = prefetch_dir(v)
    sums = pf / f"terraform-provider-{PROVIDER}_{v}_SHA256SUMS"
    got = sha256_file(sums)
    if got != pin["shasums_sha256"]:
        raise PinError(f"SHA256SUMS da pré-busca ({got[:12]}…) != pins.json ({pin['shasums_sha256'][:12]}…)")
    zips = parse_sha256sums(sums.read_text(encoding="utf-8"), v)
    if OS_ARCH not in zips:
        raise PinError(f"SHA256SUMS sem o pacote {OS_ARCH}")
    ver = json.loads((pf / "verification.json").read_text(encoding="utf-8"))
    if not (ver.get("gpg_valid_signature") and ver.get("sha256_matches_SHA256SUMS")
            and ver.get("zip_sha256") == zips[OS_ARCH]):
        raise PinError("verification.json da pré-busca não confirma assinatura e soma do zip")
    pre = lockfile.find(lockfile.read(pf / "terraform.lock.hcl"), SOURCE)
    if pre.version != v:
        raise PinError(f"lock da pré-busca na versão {pre.version}, pin {v}")
    h1 = [h for h in pre.hashes if h.startswith("h1:")]
    if len(h1) != 1:
        raise PinError(f"lock da pré-busca com {len(h1)} hash(es) h1")
    return {"sha256sums": sums, "sha256sums_sha256": got, "zips": zips, "h1": h1[0],
            "gpg_fingerprint": ver.get("gpg_signer_fingerprint"), "prefetch_lock": pf / "terraform.lock.hcl"}


def locked_provider(pin: dict, sig: dict) -> lockfile.LockedProvider:
    """O lock do google: h1 da pré-busca + zh: de todas as plataformas do SHA256SUMS assinado."""
    hashes = sorted([sig["h1"]] + [f"zh:{s}" for s in sig["zips"].values()])
    return lockfile.LockedProvider(ADDRESS, pin["version"], pin["version"], tuple(hashes))


def write_lock(lp: lockfile.LockedProvider, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(lockfile.render([lp]), encoding="utf-8")
    return dest


def dirhash_h1(d: Path) -> str:
    """Hash 'h1:' do terraform (golang.org/x/mod/sumdb/dirhash.Hash1) da pasta desempacotada do provider.

    Linhas '<sha256 hex>  <caminho relativo com />\\n' em ordem de caminho; h1 = base64(sha256(linhas)).
    """
    files = sorted(p.relative_to(d).as_posix() for p in d.rglob("*") if p.is_file())
    summary = hashlib.sha256()
    for rel in files:
        if "\n" in rel:
            raise ValueError(f"dirhash: nome com quebra de linha: {rel!r}")
        summary.update(f"{sha256_file(d / rel)}  {rel}\n".encode("utf-8"))
    return "h1:" + base64.b64encode(summary.digest()).decode("ascii")


def provider_dir(cache: Path, version: str) -> Path:
    return cache / ADDRESS / version / OS_ARCH


def read_sha_file(p: Path) -> str:
    """O sha256 de um arquivo '<sha>  nome'."""
    sha = p.read_text(encoding="utf-8").split()[0]
    if not re.fullmatch(r"[0-9a-f]{64}", sha):
        raise PinError(f"{p}: sha256 fora do formato")
    return sha
