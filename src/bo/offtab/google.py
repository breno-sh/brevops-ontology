"""Tabela do Google ("Compare AWS and Azure services to Google Cloud"): uma linha por produto do Google Cloud.

Colunas da página: Service category | Service type | Google Cloud product | Google Cloud product description |
AWS offering | Azure offering. Saída com as mesmas colunas do CSV publicado em tabelas_oficiais/.
"""

from __future__ import annotations

from pathlib import Path

from . import htmltables as H
from . import sources as S

COLUMNS = ("row", "service_category", "service_type", "google_cloud_product", "google_cloud_product_description",
           "aws_offering", "azure_offering", "source_url", "retrieved_utc", "source_html_sha256")
HEADER = ["Service category", "Service type", "Google Cloud product", "Google Cloud product description",
          "AWS offering", "Azure offering"]


class LayoutError(ValueError):
    pass


def parse(html: str, html_sha256: str) -> list[dict]:
    ts = [t for t in H.tables(html) if t.header() == HEADER]
    if len(ts) != 1:
        raise LayoutError(f"esperava 1 tabela com o cabeçalho {HEADER}, achei {len(ts)}")
    out = []
    for r in ts[0].body():
        if len(r) != len(HEADER):
            raise LayoutError(f"linha com {len(r)} células (esperava {len(HEADER)}): {[c.text() for c in r]}")
        vals = [c.text() for c in r]
        out.append({
            "row": str(len(out) + 1), "service_category": vals[0], "service_type": vals[1],
            "google_cloud_product": vals[2], "google_cloud_product_description": vals[3],
            "aws_offering": vals[4], "azure_offering": vals[5], "source_url": S.GOOGLE["url_csv"],
            "retrieved_utc": S.GOOGLE["retrieved_utc"], "source_html_sha256": html_sha256,
        })
    return out


def parse_file(path: Path = S.GOOGLE_HTML) -> tuple[list[dict], str]:
    sha = S.sha256_file(path)
    return parse(path.read_text(encoding="utf-8"), sha), sha
