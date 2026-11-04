"""Download (dado não confiável) do que a cadeia de confiança de uma versão precisa, sem credenciais.

  metadado do registro  GET registry.terraform.io/v1/providers/hashicorp/aws/<v>/download/darwin/arm64
  SHA256SUMS e .sig     GET releases.hashicorp.com/terraform-provider-aws/<v>/... (URLs do metadado, host conferido)
  zip darwin_arm64      GET releases.hashicorp.com/... (transitório: apagado depois da extração)

Tudo vai para $BO_DATA/downloads/hist-aws/<v>/ com SOURCE.txt. Para o pin (6.71.0 hoje), a pré-busca em
$BO_DATA/downloads/prefetch/aws/<v>/ é reaproveitada: o SHA256SUMS dela tem de bater com o shasums_sha256 do
pins.json, e o zip já baixado por outro módulo é só lido (nunca apagado aqui).
Nada baixado é executado; o metadado é lido como JSON e os nomes de arquivo são conferidos contra o esperado.
"""

from __future__ import annotations

import json
import shutil
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

from . import common
from .trust import TrustError, zip_name

UA = "brevops-ontology-hist-aws/1 (pesquisa; sem credenciais)"
ALLOWED_HOSTS = {"registry.terraform.io", "releases.hashicorp.com"}


def _check_url(url: str, host: str | None = None) -> str:
    u = urllib.parse.urlparse(url)
    if u.scheme != "https" or u.hostname not in ALLOWED_HOSTS or (host and u.hostname != host):
        raise TrustError(f"URL fora dos hosts permitidos: {u.scheme}://{u.hostname}")
    return url


def http_get(url: str, dest: Path, tries: int = 4, timeout: int = 120) -> int:
    """GET HTTPS para dest (atômico, via .part). Sem cabeçalho de autenticação; devolve os bytes gravados."""
    _check_url(url)
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + ".part")
    last = None
    for k in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=timeout) as r, open(part, "wb") as f:
                if r.status != 200:
                    raise TrustError(f"HTTP {r.status}")
                shutil.copyfileobj(r, f, 1 << 20)
            part.rename(dest)
            return dest.stat().st_size
        except (OSError, TrustError) as e:   # urllib.error.URLError é OSError
            last = e
            part.unlink(missing_ok=True)
            time.sleep(2 * (k + 1))
    raise TrustError(f"download falhou depois de {tries} tentativas: {url} ({last})")


@dataclass
class Fetched:
    version: str
    registry_json: Path
    sums: Path
    sig: Path
    zip: Path | None = None
    zip_is_ours: bool = False          # baixado por este módulo (e então apagado depois)
    origin: str = "download"           # download | prefetch
    urls: dict = field(default_factory=dict)


def _registry_url(version: str) -> str:
    os_, arch = common.PLATFORM.split("_")
    return f"{common.REGISTRY}/v1/providers/{common.SOURCE}/{version}/download/{os_}/{arch}"


def metadata(version: str, pins: common.Pins) -> Fetched:
    """Metadado do registro, SHA256SUMS e assinatura (pré-busca do pin, ou download)."""
    name = f"terraform-provider-{common.NAME}_{version}_SHA256SUMS"
    pf = common.prefetch_dir(version)
    if version == pins.version and (pf / name).is_file():
        sums_sha = common.sha256_file(pf / name)
        if sums_sha != pins.shasums_sha256:
            raise TrustError(f"pré-busca: SHA256SUMS {sums_sha} != pins.json {pins.shasums_sha256}")
        f = Fetched(version, pf / f"registry-download-{common.PLATFORM}.json", pf / name, pf / f"{name}.sig",
                    origin="prefetch")
        f.urls = {"registry": _registry_url(version)}
        return f
    d = common.download_dir(version)
    d.mkdir(parents=True, exist_ok=True)
    reg = d / f"registry-download-{common.PLATFORM}.json"
    if not reg.is_file():
        http_get(_registry_url(version), reg, timeout=60)
    meta = json.loads(reg.read_text(encoding="utf-8"))
    if meta.get("filename") != zip_name(version):
        raise TrustError(f"registro devolveu filename {meta.get('filename')!r}, esperado {zip_name(version)}")
    for k in ("shasums_url", "shasums_signature_url", "download_url"):
        _check_url(meta[k], "releases.hashicorp.com")
    if Path(urllib.parse.urlparse(meta["shasums_url"]).path).name != name:
        raise TrustError("shasums_url com nome inesperado")
    if Path(urllib.parse.urlparse(meta["download_url"]).path).name != zip_name(version):
        raise TrustError("download_url com nome inesperado")
    sums, sig = d / name, d / f"{name}.sig"
    if not sums.is_file():
        http_get(meta["shasums_url"], sums, timeout=60)
    if not sig.is_file():
        http_get(meta["shasums_signature_url"], sig, timeout=60)
    f = Fetched(version, reg, sums, sig)
    f.urls = {"registry": _registry_url(version), "shasums": meta["shasums_url"],
              "signature": meta["shasums_signature_url"], "zip": meta["download_url"]}
    write_source(d, version, f.urls)
    return f


def existing_zip(version: str) -> Path | None:
    """Zip da plataforma já baixado por outro módulo (ex.: o espelho do SCHEMA-AWS para o pin): só leitura."""
    fn = zip_name(version)
    root = common.bo_data() / "downloads"
    for c in sorted(root.glob(f"*/mirror/registry.terraform.io/hashicorp/{common.NAME}/{fn}")):
        return c
    return None


def get_zip(f: Fetched) -> Fetched:
    """O zip da plataforma: reaproveita um já baixado (não é nosso, não se apaga) ou baixa para a pasta do módulo."""
    other = existing_zip(f.version)
    if other is not None:
        f.zip, f.zip_is_ours = other, False
        return f
    meta = json.loads(f.registry_json.read_text(encoding="utf-8"))
    url = _check_url(meta["download_url"], "releases.hashicorp.com")
    if Path(urllib.parse.urlparse(url).path).name != zip_name(f.version):
        raise TrustError("download_url com nome inesperado")
    dest = common.download_dir(f.version) / zip_name(f.version)
    if not dest.is_file():
        http_get(url, dest, timeout=600)
    f.zip, f.zip_is_ours = dest, True
    f.urls.setdefault("zip", url)
    return f


def write_source(d: Path, version: str, urls: dict) -> None:
    (d / "SOURCE.txt").write_text(
        f"Downloads do HIST-AWS para {common.ADDRESS} {version} ({common.PLATFORM}).\n"
        + "".join(f"  {k}: {v}\n" for k, v in sorted(urls.items()))
        + "Metadado do Terraform Registry (API pública v1) e release assinado da HashiCorp, sem credenciais.\n"
        "Dado não confiável: o JSON só é lido; SHA256SUMS conferido por GPG (chave primária "
        f"{common.HASHICORP_FPR}); o zip só é lido e desempacotado, conferido por sha256 e h1, e apagado depois "
        "da extração. Gerado por: python -I -m bo.hist_aws.pipeline (módulo HIST-AWS).\n", encoding="utf-8")
