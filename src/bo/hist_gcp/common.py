"""Caminhos, lista histórica do google (PINS), pin do Terraform e utilitários do HIST-GCP.

Nada aqui é constante digitada de versão: a lista sai de universe/history_versions.json (C13 3.1.0, PINS), o
Terraform e o pin do google saem de universe/pins.json, e a chave pública da HashiCorp sai do instantâneo do
PINS ($BO_DATA/PINS/registry_index/vendor_keys/), conferida contra o MANIFEST.sha256 dele.

Onde cada coisa mora:
  $BO_DATA/HIST-GCP/                      saídas do módulo (átomos por versão, versions.json, extraction.json,
                                          receipts/, locks/, MANIFEST.sha256)
  $BO_DATA/downloads/hist-gcp/google-V/   dado baixado ou derivado de binário baixado (não confiável, com
                                          SOURCE.txt): resposta da rota de download do Registry, SHA256SUMS,
                                          assinatura e a saída crua do 'providers schema -json'
  $BO_TMP                                 trabalho do terraform, plugin cache (binários apagados ao fim)
"""

from __future__ import annotations

import base64
import datetime as _dt
import gzip
import hashlib
import json
import os
import re
from pathlib import Path
from zoneinfo import ZoneInfo

ID = "HIST-GCP"
PROVIDER = "google"
SOURCE = "hashicorp/google"
ADDRESS = "registry.terraform.io/hashicorp/google"
OS_ARCH = "darwin_arm64"
TZ = ZoneInfo("America/Recife")

#: arquivos da pasta do módulo que não são saída (livros e relatórios voláteis das ferramentas do REPO)
MANIFEST_SKIP = {"MANIFEST.sha256", "consume_ledger.json", "gate_report.json", ".DS_Store"}
#: subpastas voláteis que as ferramentas do REPO gravam na pasta do módulo (logs do make integration)
MANIFEST_SKIP_DIRS = {"integration"}


class HistError(SystemExit):
    """Entrada que não confere (assinatura, hash, pin, lista): reprova sem seguir com dado não conferido."""


def now() -> str:
    return _dt.datetime.now(TZ).isoformat(timespec="seconds")


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


def download_dir(version: str) -> Path:
    return bo_data() / "downloads" / "hist-gcp" / f"{PROVIDER}-{version}"


def raw_schema_dir(version: str) -> Path:
    return download_dir(version) / "schema"


def atoms_path(version: str) -> Path:
    return out_dir() / f"atoms_{version}.jsonl.gz"


def receipt_path(version: str) -> Path:
    return out_dir() / "receipts" / f"{PROVIDER}-{version}.json"


def lock_path(version: str) -> Path:
    return out_dir() / "locks" / f"{PROVIDER}-{version}.terraform.lock.hcl"


def history_path() -> Path:
    return bo_repo() / "universe" / "history_versions.json"


def pins_path() -> Path:
    return bo_repo() / "universe" / "pins.json"


def pins_index_dir() -> Path:
    return bo_data() / "PINS" / "registry_index"


def portable(p: Path | str) -> str:
    """Caminho com $BO_DATA/$BO_REPO no lugar do prefixo absoluto (C00); a HOME vira ~."""
    s = str(p)
    for var, root in (("$BO_DATA", str(bo_data())), ("$BO_REPO", str(bo_repo()))):
        if s == root or s.startswith(root + "/"):
            return var + s[len(root):]
    home = str(Path.home())
    if s.startswith(home + "/"):
        return "~" + s[len(home):]
    return s


def unportable(s: str) -> Path:
    for var, root in (("$BO_DATA", bo_data()), ("$BO_REPO", bo_repo())):
        if s == var or s.startswith(var + "/"):
            return Path(str(root) + s[len(var):])
    if s.startswith("~/"):
        return Path.home() / s[2:]
    return Path(s)


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def gunzip_bytes(p: Path) -> bytes:
    with gzip.open(p, "rb") as g:
        return g.read()


def gzip_bytes(raw: bytes, inner_name: str) -> bytes:
    """gzip determinístico (mtime 0, nível 9, nome interno fixo): mesmos bytes de entrada, mesmos bytes de saída."""
    import io
    buf = io.BytesIO()
    with gzip.GzipFile(filename=inner_name, mode="wb", fileobj=buf, mtime=0, compresslevel=9) as g:
        g.write(raw)
    return buf.getvalue()


def dumps(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=1) + "\n"


def write_json(p: Path, obj) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(dumps(obj), encoding="utf-8")
    return p


# ---------------------------------------------------------------- semver (ordem; o PINS tem a mesma regra)

def semver_key(v: str) -> tuple:
    from bo.pins import semver
    return semver.key(v)


# ---------------------------------------------------------------- entradas do PINS

def history() -> dict:
    """A entrada do google no history_versions.json: selection, versions_doc, pin, índices e truncamento."""
    p = history_path()
    doc = json.loads(p.read_text(encoding="utf-8"))
    if doc.get("contract") != "C13" or doc.get("schema") != "bo.history_versions/1":
        raise HistError(f"{portable(p)}: não é um C13 history_versions")
    hits = [x for x in doc.get("providers", []) if x.get("provider") == PROVIDER]
    if len(hits) != 1:
        raise HistError(f"{portable(p)}: esperava 1 provider {PROVIDER}, achei {len(hits)}")
    h = hits[0]
    if h.get("source") != ADDRESS:
        raise HistError(f"{portable(p)}: source {h.get('source')!r} != {ADDRESS}")
    sel = [s["version"] for s in h["selection"]]
    vd = [v["version"] for v in h["versions_doc"]["versions"]]
    if sel != vd:
        raise HistError("history_versions: selection e versions_doc não listam as mesmas versões (C13-HIST-SEL)")
    return {**h, "path": p, "sha256": sha256_file(p), "contract_version": doc["contract_version"],
            "cutoff": doc["cutoff"], "window": doc["window"]}


def pins() -> dict:
    """{'terraform': {...}, 'google': {...}, 'path', 'sha256'} do universe/pins.json."""
    p = pins_path()
    doc = json.loads(p.read_text(encoding="utf-8"))
    hits = [x for x in doc.get("providers", []) if x.get("provider") == PROVIDER]
    if len(hits) != 1 or hits[0].get("source") != ADDRESS:
        raise HistError(f"{portable(p)}: provider {PROVIDER} ausente, repetido ou com outro source")
    return {"terraform": doc["terraform"], "google": hits[0], "path": p, "sha256": sha256_file(p)}


def pins_manifest() -> dict[str, str]:
    """{caminho relativo: sha256} do MANIFEST.sha256 do instantâneo do PINS."""
    m = pins_index_dir() / "MANIFEST.sha256"
    out = {}
    for line in m.read_text(encoding="utf-8").splitlines():
        if line.strip():
            sha, rel = line.split(None, 1)
            out[rel.strip()] = sha
    return out


VENDOR_KEY_REL = "vendor_keys/hashicorp-pgp-key.txt"


def vendor_key() -> dict:
    """Chave pública vigente da HashiCorp do instantâneo do PINS, conferida contra o MANIFEST dele."""
    p = pins_index_dir() / VENDOR_KEY_REL
    got = sha256_file(p)
    want = pins_manifest().get(VENDOR_KEY_REL)
    if got != want:
        raise HistError(f"chave da HashiCorp ({got[:12]}…) não confere com o MANIFEST do PINS ({str(want)[:12]}…)")
    ver = json.loads((pins_index_dir() / "verification.json").read_text(encoding="utf-8"))
    fpr = ver["terraform"]["signature"]["primary_fingerprint"]
    if not ver["terraform"]["signature"]["good"]:
        raise HistError("verification.json do PINS: o SHA256SUMS do Terraform não tem GOODSIG da chave vendor")
    return {"armor": p.read_text(encoding="utf-8"), "path": p, "sha256": got, "primary_fingerprint": fpr}


def terraform_binary() -> dict:
    """O terraform do PATH tem de ser o binário oficial conferido pelo PINS (sha do binário dentro do zip
    assinado) e estar na versão do pin."""
    import shutil
    pn = pins()["terraform"]
    found = shutil.which("terraform")
    if not found:
        raise HistError("terraform não está no PATH")
    tf = Path(found).resolve()
    ver = json.loads((pins_index_dir() / "verification.json").read_text(encoding="utf-8"))["terraform"]
    if ver["version"] != pn["version"] or ver["zip_sha256"] != pn["sha256"]:
        raise HistError("verification.json do PINS não é do Terraform fixado no pins.json")
    got = sha256_file(tf)
    if got != ver["binary_in_zip_sha256"]:
        raise HistError(f"terraform do PATH ({got[:12]}…) != binário do zip assinado ({ver['binary_in_zip_sha256'][:12]}…)")
    return {"path": tf, "version": pn["version"], "zip_sha256": pn["sha256"], "binary_sha256": got}


# ---------------------------------------------------------------- hash h1 do terraform

def dirhash_h1(d: Path) -> str:
    """Hash 'h1:' do terraform (golang.org/x/mod/sumdb/dirhash.Hash1) de uma pasta desempacotada.

    Linhas '<sha256 hex>  <caminho relativo com />\\n' em ordem de caminho; h1 = base64(sha256(linhas)).
    """
    files = sorted(p.relative_to(d).as_posix() for p in d.rglob("*") if p.is_file())
    summary = hashlib.sha256()
    for rel in files:
        if "\n" in rel:
            raise ValueError(f"dirhash: nome com quebra de linha: {rel!r}")
        summary.update(f"{sha256_file(d / rel)}  {rel}\n".encode("utf-8"))
    return "h1:" + base64.b64encode(summary.digest()).decode("ascii")


_SHA_LINE = re.compile(r"^([0-9a-f]{64})  (\S+)$")


def read_sha_file(p: Path) -> str:
    """O sha256 de um arquivo '<sha>  nome'."""
    m = _SHA_LINE.match(p.read_text(encoding="utf-8").strip())
    if not m:
        raise HistError(f"{portable(p)}: sha256 fora do formato")
    return m.group(1)


# ---------------------------------------------------------------- manifesto

def manifest_files(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*")
                  if p.is_file() and p.name not in MANIFEST_SKIP and not p.name.startswith("MANIFEST.sha256")
                  and "__pycache__" not in p.parts
                  and p.relative_to(root).parts[0] not in MANIFEST_SKIP_DIRS)


def manifest_text(root: Path) -> str:
    return "".join(f"{sha256_file(p)}  {p.relative_to(root).as_posix()}\n" for p in manifest_files(root))


def write_manifest(root: Path) -> int:
    text = manifest_text(root)
    (root / "MANIFEST.sha256").write_text(text, encoding="utf-8")
    return text.count("\n")
