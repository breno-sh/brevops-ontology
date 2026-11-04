"""Caminhos e leitura das entradas do HIST-AZURE. Nenhuma versão é digitada: todas saem de
universe/history_versions.json (C13 3.1.0, produzido pelo PINS); a versão do terraform sai de universe/pins.json.

Onde fica cada coisa:
  $BO_DATA/HIST-AZURE/                      saídas do módulo (atoms_<v>.jsonl.gz, types_<v>.jsonl.gz,
                                            versions.json, extract_report.json, MANIFEST.sha256)
  $BO_DATA/downloads/hist-azurerm/<v>/      dado baixado não confiável: metadado do registro, SHA256SUMS,
                                            assinatura e o schema extraído (schema/). O zip e o binário
                                            do provider só existem durante a extração e são apagados depois.
  $BO_DATA/downloads/hist-azurerm/plugin-cache/   cache de plugin do terraform, vazio entre versões.
  $BO_DATA/tmp/HIST-AZURE/                  pasta de trabalho (BO_TMP).
"""

from __future__ import annotations

import gzip
import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path

MODULE = "HIST-AZURE"
PROVIDER = "azurerm"
SOURCE = "hashicorp/azurerm"
ADDRESS = "registry.terraform.io/hashicorp/azurerm"
#: impressão digital da chave primária de assinatura da HashiCorp (âncora de confiança; a chave pública
#: vem do registro, que é dado baixado, por isso a assinatura tem de ser desta chave primária).
HASHICORP_FPR = "C874011F0AB405110D02105534365D9472D7468F"
RELEASES = "https://releases.hashicorp.com"
REGISTRY = "https://registry.terraform.io"
PLATFORM = "darwin_arm64"


def bo_repo() -> Path:
    return Path(os.environ.get("BO_REPO") or Path(__file__).resolve().parents[3])


def bo_data() -> Path:
    return Path(os.environ.get("BO_DATA", "/Users/breno/doutorado/brevops-data"))


def bo_tmp() -> Path:
    return Path(os.environ.get("BO_TMP") or bo_data() / "tmp" / MODULE)


def out_dir() -> Path:
    return bo_data() / MODULE


def dl_root() -> Path:
    return bo_data() / "downloads" / "hist-azurerm"


def dl_dir(version: str) -> Path:
    return dl_root() / version


def schema_dir(version: str) -> Path:
    return dl_dir(version) / "schema"


def plugin_cache() -> Path:
    return dl_root() / "plugin-cache"


def unpacked_dir(version: str, platform: str = PLATFORM) -> Path:
    return plugin_cache() / "registry.terraform.io" / "hashicorp" / PROVIDER / version / platform


def atoms_path(version: str) -> Path:
    return out_dir() / f"atoms_{version}.jsonl.gz"


def types_path(version: str) -> Path:
    return out_dir() / f"types_{version}.jsonl.gz"


def report_path() -> Path:
    return out_dir() / "extract_report.json"


def versions_path() -> Path:
    return out_dir() / "versions.json"


def zip_name(version: str, platform: str = PLATFORM) -> str:
    return f"terraform-provider-{PROVIDER}_{version}_{platform}.zip"


def sums_name(version: str) -> str:
    return f"terraform-provider-{PROVIDER}_{version}_SHA256SUMS"


def release_base(version: str) -> str:
    return f"{RELEASES}/terraform-provider-{PROVIDER}/{version}"


def zip_url(version: str, platform: str = PLATFORM) -> str:
    return f"{release_base(version)}/{zip_name(version, platform)}"


def sums_url(version: str) -> str:
    return f"{release_base(version)}/{sums_name(version)}"


def registry_download_url(version: str, platform: str = PLATFORM) -> str:
    os_, arch = platform.split("_", 1)
    return f"{REGISTRY}/v1/providers/{SOURCE}/{version}/download/{os_}/{arch}"


def portable(p: Path | str) -> str:
    s = str(p)
    for var, root in (("$BO_DATA", bo_data()), ("$BO_REPO", bo_repo())):
        r = str(root)
        if s == r or s.startswith(r + "/"):
            return var + s[len(r):]
    return s


def expand(s: str) -> Path:
    return Path(s.replace("$BO_DATA", str(bo_data())).replace("$BO_REPO", str(bo_repo())))


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def gz_sha256(p: Path) -> str:
    """sha256 do conteúdo descomprimido de um .gz."""
    h = hashlib.sha256()
    with gzip.open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def write_gz(src: Path, dest: Path, inner_name: str) -> None:
    """gzip determinístico (mtime 0, nome interno fixo, nível 9): mesmo conteúdo dá os mesmos bytes."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".part")
    with open(src, "rb") as fi, open(tmp, "wb") as fo:
        with gzip.GzipFile(filename=inner_name, mode="wb", fileobj=fo, mtime=0, compresslevel=9) as g:
            for chunk in iter(lambda: fi.read(1 << 20), b""):
                g.write(chunk)
    os.replace(tmp, dest)


def write_json(p: Path, doc) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".part")
    tmp.write_text(json.dumps(doc, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, p)


def semver_key(v: str) -> tuple:
    core = v.split("+", 1)[0].split("-", 1)[0]
    return tuple(int(x) for x in core.split("."))


@dataclass(frozen=True)
class Listed:
    """Uma versão da lista histórica do PINS (selection), com o que o PINS registrou dela."""
    version: str
    released_at: str
    published_at: str
    reasons: tuple
    protocols: tuple
    darwin_arm64: bool
    schema_sha256: str | None       # só a do pin, quando o PINS registrou


@dataclass(frozen=True)
class History:
    path: Path
    sha256: str
    contract_version: str
    pin: str
    listed: tuple                   # Listed, na ordem do PINS
    versions_doc: dict
    left_truncation: dict
    cutoff: dict


def history_path() -> Path:
    return bo_repo() / "universe" / "history_versions.json"


def read_history(path: Path | None = None) -> History:
    p = Path(path or history_path())
    doc = json.loads(p.read_text(encoding="utf-8"))
    hits = [x for x in doc.get("providers", []) if x.get("provider") == PROVIDER]
    if len(hits) != 1:
        raise SystemExit(f"{MODULE}: history_versions.json com {len(hits)} entradas para {PROVIDER}")
    e = hits[0]
    if e["source"] != ADDRESS:
        raise SystemExit(f"{MODULE}: history_versions.json fixa {e['source']}, esperado {ADDRESS}")
    vd = e["versions_doc"]
    sha_by_v = {v["version"]: v.get("schema_sha256") for v in vd["versions"]}
    listed = tuple(Listed(s["version"], s["released_at"], s["published_at"], tuple(s.get("reasons") or ()),
                          tuple(s.get("protocols") or ()), bool(s.get("darwin_arm64")),
                          sha_by_v.get(s["version"])) for s in e["selection"])
    return History(p, sha256_file(p), doc["contract_version"], e["pin"], listed, vd,
                   e.get("left_truncation") or {}, doc.get("cutoff") or {})


def pins_doc() -> dict:
    return json.loads((bo_repo() / "universe" / "pins.json").read_text(encoding="utf-8"))


def terraform_pin() -> str:
    return pins_doc()["terraform"]["version"]


def pin_shasums_sha256(version: str) -> str | None:
    """sha256 do SHA256SUMS que o pins.json fixou, se a versão for a do pin (senão None)."""
    for p in pins_doc().get("providers", []):
        if p.get("provider") == PROVIDER and p.get("version") == version:
            return p.get("shasums_sha256")
    return None
