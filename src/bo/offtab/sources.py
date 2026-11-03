"""Fontes do OFFTAB: caminhos, URLs, datas de coleta e sha256 fixados.

Os sha256 abaixo são os do HTML coletado (Google e Microsoft em 2026-10-28, Oracle em 2026-11-03). O repro confere
três coisas por arquivo: sha256 do disco = sha256 fixado aqui = sha256 do SOURCE.txt da pasta (e, para Google e
Microsoft, = coluna source_html_sha256 de cada linha do CSV publicado).

Observação de catálogo: o HTML do Google mora em bakeoff/downloads/gcloud-comparison/, pasta irmã da entrada
declarada azure-aws-comparison/; o README de tabelas_oficiais/ (entrada declarada) aponta para ela como a
origem bruta. Ela é lida, nunca escrita, e vai para agent_provenance.inputs do summary.json.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

PESQ = Path("/Users/breno/doutorado/pesquisa/superficie/reports/ontologia_neutra")
TABELAS = PESQ / "tabelas_oficiais"
MS_DIR = PESQ / "bakeoff" / "downloads" / "azure-aws-comparison"
GOOGLE_DIR = PESQ / "bakeoff" / "downloads" / "gcloud-comparison"


def bo_data() -> Path:
    return Path(os.environ.get("BO_DATA") or "/Users/breno/doutorado/brevops-data")


def oracle_dir() -> Path:
    return bo_data() / "downloads" / "oci-service-comparison"


def out_dir() -> Path:
    return bo_data() / "OFFTAB"


GOOGLE_CSV = TABELAS / "google_aws_azure_gcp_service_comparison.csv"
MS_CSV = TABELAS / "microsoft_aws_to_azure_services_comparison.csv"
GOOGLE_HTML = GOOGLE_DIR / "page.html"

GOOGLE = {
    "vendor": "google",
    "title": "Compare AWS and Azure services to Google Cloud",
    "url": "https://cloud.google.com/docs/get-started/aws-azure-gcp-service-comparison",
    "url_csv": "https://cloud.google.com/docs/get-started/aws-azure-gcp-service-comparison "
               "(served from docs.cloud.google.com)",
    "retrieved_utc": "2026-10-28T19:00:34Z",
    "html_sha256": "d5db33c55f14e178c4cc872364cf08b45bdf9d6b488dd928ae9d827571d09663",
    "rows": 223,
}

MS_BASE_URL = "https://learn.microsoft.com/en-us/azure/architecture/aws-professional/"
MS_RETRIEVED = "2026-10-28T19:00:34Z"
# página -> sha256 do HTML (SOURCE.txt de azure-aws-comparison/); accounts e resources não têm tabela
MS_PAGES = {
    "accounts": "d11fb95abf7ef5ac8d2a54f85e315208525c18ff91ed12ad0ee30e32f66f8d2e",
    "analytics": "f5892d9427be3ea1b4c9eef103a1701ee00252289481f081086bc831da8b7419",
    "compute": "e9c3485e160e10aed73226db7e7b468d0bfcb81adfe565368661febf66f46f89",
    "data-ai": "528c60d38fe737cc60605f453be2cc97237e03f8520909e4aefb8f2c355ec493",
    "databases": "9ed5f857b14362e9d9c24d7359c763f70993df8bcf16800c472e2ccd106a0419",
    "index": "c7cb1bef4eff43d58bbb5aff14ca7096081ffdc21ec9a6c9762a3fb96148638b",
    "messaging": "9698f3a559735e9650f01561af7b60e2f0f0adbd95f5205f7928905cfb4d6b97",
    "networking": "6e8e29320eacfcc1eb1e4f90a358d7eb18270d1dc6a0bad3cc8e5e76b3de043c",
    "regions-zones": "5a7b77ff6d0ccc3f81973593d4d51594c28f3932fdf3e85730e3bdbb95adfe4b",
    "resources": "f71342ed9b4ac16b47fa173445589ed9db8d90c2dd74f113cd1416c7f19a37a0",
    "security-identity": "fb1b0d47079417aaed812a1844decaace3fe96713b72501a251302eebe78e973",
    "storage": "198188b16a856e428c5d1c555e01258a2fb9f245561d490441ceb15053f2501e",
}
MICROSOFT = {
    "vendor": "microsoft",
    "title": "Azure for AWS professionals (série de páginas de comparação)",
    "url": MS_BASE_URL,
    "retrieved_utc": MS_RETRIEVED,
    "rows": 205,
}


def ms_url(page: str) -> str:
    return MS_BASE_URL if page == "index" else MS_BASE_URL + page


ORACLE_FILES = {
    "service-comparison.htm": {
        "url": "https://docs.oracle.com/en-us/iaas/Content/GSG/Reference/service-comparison.htm",
        "retrieved_utc": "2026-11-03T04:31:11Z",
        "sha256": "f7240419ce744c1d5f8e7938316687a385274f06f034957757000fd68b0a6c3e"},
    "oracle-service-comparison.html": {
        "url": "https://www.oracle.com/cloud/service-comparison/",
        "retrieved_utc": "2026-11-03T04:31:20Z",
        "sha256": "103aa66383c5d3cdf896c79b4cdcb3bd7bc7487886727f01b624982e640d32ca"},
    "ocimapping.html": {
        "url": "https://www.oracle.com/a/ocom/docs/ocimapping/ocimapping.html",
        "retrieved_utc": "2026-11-03T04:31:35Z",
        "sha256": "2ad881eb055b31e4753cb992331269cd5d5c535e4666ff87d4274ba35d86e5e7"},
    "mapping-bundle.js.txt": {
        "url": "https://www.oracle.com/a/ocom/docs/ocimapping/js/mapping-bundle.js",
        "retrieved_utc": "2026-11-03T04:31:45Z",
        "sha256": "d47e3bd12bf1575a3afd697b755a31788b72eae034772431076f62e7efd66588"},
}
ORACLE = {
    "vendor": "oracle",
    "title": "Compare OCI with AWS, Azure, and Google Cloud",
    "url": "https://www.oracle.com/cloud/service-comparison/",
    "data_file": "mapping-bundle.js.txt",
    "retrieved_utc": ORACLE_FILES["mapping-bundle.js.txt"]["retrieved_utc"],
    "html_sha256": ORACLE_FILES["oracle-service-comparison.html"]["sha256"],
    "data_sha256": ORACLE_FILES["mapping-bundle.js.txt"]["sha256"],
    "module_marker": "7417:e=>{e.exports='",
    "module_end": "'},8247:",
    "build_date": "2024-10-31T14:36:03.799819",
    "rows": 160,
}


def read_source_txt(folder: Path) -> dict:
    """SOURCE.txt -> {arquivo: sha256} (linhas no formato do shasum)."""
    out = {}
    for line in (folder / "SOURCE.txt").read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if len(parts) == 2 and len(parts[0]) == 64 and all(c in "0123456789abcdef" for c in parts[0]):
            out[parts[1]] = parts[0]
    return out


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()
