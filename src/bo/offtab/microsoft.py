"""Tabelas da Microsoft ("Azure for AWS professionals"): todas as tabelas com uma coluna AWS e uma coluna Azure,
página a página em ordem alfabética do arquivo, com o contexto h2/h3 de cada tabela.

Regras de coluna (pelo cabeçalho, sem distinguir maiúsculas): AWS = primeira coluna que começa com "aws"; Azure =
primeira que começa com "azure"; area = coluna "Area"; description = coluna "Description". Célula com vários
serviços (<br>, lista) vira segmentos unidos por " ; ". Essa regra reproduz as 205 linhas publicadas.

Achado (03/11): a regra das 205 deixa de fora as tabelas cujo lado Microsoft se chama "Microsoft service" ou
"Microsoft or Azure service": 24 linhas em security-identity (Entra ID e identity platform frente a Cognito, IAM e
STS) e 6 em data-ai (Fabric frente ao SageMaker), 30 ao todo. Elas saem em supplement(), marcadas
table_set = "supplement", e nunca entram na contagem de 205.
"""

from __future__ import annotations

from pathlib import Path

from . import htmltables as H
from . import sources as S

COLUMNS = ("row", "page", "section_h2", "section_h3", "area", "aws_service", "azure_service", "description",
           "table_header", "source_url", "retrieved_utc", "source_html_sha256")


class LayoutError(ValueError):
    pass


def _col(header: list[str], pred) -> int | None:
    for i, h in enumerate(header):
        if pred(h.lower()):
            return i
    return None


def _azure_col(hd: list[str], supplement: bool) -> int | None:
    iz = _col(hd, lambda h: h.startswith("azure"))
    if not supplement:
        return iz
    # suplemento: só tabelas sem coluna Azure cuja coluna do lado Microsoft começa com "microsoft"
    return None if iz is not None else _col(hd, lambda h: h.startswith("microsoft"))


def parse_page(page: str, html: str, html_sha256: str, start: int = 1, supplement: bool = False) -> list[dict]:
    out = []
    for t in H.tables(html):
        hd = t.header()
        ia = _col(hd, lambda h: h.startswith("aws"))
        iz = _azure_col(hd, supplement)
        if ia is None or iz is None:
            continue
        iarea = _col(hd, lambda h: h == "area")
        idesc = _col(hd, lambda h: h == "description")
        for r in t.body():
            if len(r) != len(hd):
                raise LayoutError(f"{page} tabela {t.index}: linha com {len(r)} células, cabeçalho com {len(hd)}")
            v = [c.text() for c in r]
            out.append({
                "row": str(start + len(out)), "page": page, "section_h2": t.h2, "section_h3": t.h3,
                "area": v[iarea] if iarea is not None else "", "aws_service": v[ia], "azure_service": v[iz],
                "description": v[idesc] if idesc is not None else "", "table_header": "|".join(hd),
                "source_url": S.ms_url(page), "retrieved_utc": S.MS_RETRIEVED, "source_html_sha256": html_sha256,
            })
    return out


def parse_dir(folder: Path = S.MS_DIR, supplement: bool = False) -> tuple[list[dict], dict]:
    rows, shas = [], {}
    for page in sorted(S.MS_PAGES):
        p = folder / f"{page}.html"
        shas[page] = S.sha256_file(p)
        rows += parse_page(page, p.read_text(encoding="utf-8"), shas[page], start=len(rows) + 1,
                           supplement=supplement)
    return rows, shas


def supplement(folder: Path = S.MS_DIR) -> list[dict]:
    """As linhas fora das 205 (lado Microsoft rotulado "Microsoft ..."); row = S<n> para não colidir."""
    rows, _ = parse_dir(folder, supplement=True)
    for i, r in enumerate(rows, 1):
        r["row"] = f"S{i}"
    return rows
