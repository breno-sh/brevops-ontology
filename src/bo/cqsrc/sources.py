"""Fontes fixadas: os quatro mods de compliance do Steampipe (Turbot), lidos como dado, nunca executados.

O arquivo .tar.gz de cada mod fica em $BO_DATA/downloads/steampipe-mods/<mod>/ com SOURCE.txt; o extrator lê
os .pp/.sp direto do tarball (tarfile, sem extrair para o disco), depois de conferir o sha256 fixado aqui.
"""

from __future__ import annotations

import os
from pathlib import Path

LICENSE = "Apache-2.0 (arquivo LICENSE dentro do tarball)"

MODS = {
    # mod: (repositório, tag anotada, commit, data do commit, sha256 do tarball do codeload)
    "aws": ("turbot/steampipe-mod-aws-compliance", "v1.14.0", "c652ac6e183e31be662b9b0b4dbc2b29f21e2e4a",
            "2026-10-26T19:53:44Z", "06e506786acee2dd8db94bc76af4d3eb64bb702cf48d7091519253bf534dcd5e"),
    "gcp": ("turbot/steampipe-mod-gcp-compliance", "v1.3.2", "3ac653021a284b68c69b14c75afa2ebc1feff665",
            "2026-05-28T19:17:52Z", "c7006afcf46663f319ad7c1ccd6c9cec43883bcaf3563b8fa0337819d8235308"),
    "azure": ("turbot/steampipe-mod-azure-compliance", "v2.5.3", "f4b9a098d019421cfb4cf234f7384860e7c97170",
              "2026-10-27T00:05:18Z", "826806ce04c9051fb6b2ac000ea1a1b7c9f462ef116213f9d466d78a9e91c201"),
    "oci": ("turbot/steampipe-mod-oci-compliance", "v1.1.0", "1e6cfcb5e267501436e2ae93fdfd9c76108c7023",
            "2025-11-14T08:22:02Z", "2382b65cbafa4304bd6d7a9857bf3dcceec49a6c06eb6500307fe86403dfc5bb"),
}
PROVIDER_OF_MOD = {"aws": "aws", "gcp": "google", "azure": "azurerm", "oci": "oci"}
# quando e por quem o arquivo foi obtido (registrado em SOURCE.txt)
RETRIEVED_AT = "2026-11-03T01:33:00-03:00"
RETRIEVED_BY = "CQSRC"


def data_root() -> Path:
    return Path(os.environ.get("BO_DATA", "/Users/breno/doutorado/brevops-data"))


def downloads_dir() -> Path:
    return data_root() / "downloads" / "steampipe-mods"


def archive_name(mod: str) -> str:
    return f"{mod}-{MODS[mod][1]}.tar.gz"


def archive_path(mod: str) -> Path:
    return downloads_dir() / mod / archive_name(mod)


def codeload_url(mod: str) -> str:
    repo, _, commit, _, _ = MODS[mod]
    return f"https://codeload.github.com/{repo}/tar.gz/{commit}"


def blob_url(mod: str, relpath: str, line: int) -> str:
    repo, _, commit, _, _ = MODS[mod]
    return f"https://github.com/{repo}/blob/{commit}/{relpath}#L{line}"


def source_txt(mod: str) -> str:
    repo, tag, commit, date, sha = MODS[mod]
    return (
        f"fonte: mod de compliance do Steampipe/Powerpipe para {mod} (Turbot), benchmarks CIS Foundations\n"
        f"uri: https://github.com/{repo}\n"
        f"tag: {tag} (tag anotada)\n"
        f"commit: {commit}\n"
        f"data_do_commit: {date}\n"
        f"arquivo: {archive_name(mod)}\n"
        f"origem_do_arquivo: {codeload_url(mod)}\n"
        f"sha256: {sha}\n"
        f"licenca: {LICENSE}\n"
        f"baixado_em: {RETRIEVED_AT}\n"
        f"baixado_por: {RETRIEVED_BY}\n"
        "uso: dado não confiável; lido só como texto pelo leitor mínimo de HCL (bo.cqsrc.hcl_lite) direto do "
        "tarball; nada é avaliado nem executado (nem SQL, nem HCL, nem script)\n"
    )
