"""Identificadores: DOI, ISBN, URL arquivada no Wayback, commit do GitHub, arXiv, norma.

Regra do módulo (N9 da revisão GPT-6): todo item tem DOI que resolve no Crossref ou identificador
alternativo declarado e verificado. Uma norma (std:) só vale acompanhada de uma cópia arquivada
(wayback:) na mesma entrada.
"""
from __future__ import annotations

import html
import os
import re
import unicodedata
from pathlib import Path

DOI_RX = re.compile(r"^10\.\d{4,9}/\S+$")
WAYBACK_RX = re.compile(r"^https?://web\.archive\.org/web/(\d{14})/(https?://\S+)$")
COMMIT_RX = re.compile(r"^github:([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)@([0-9a-f]{40})$")
ARXIV_RX = re.compile(r"^\d{4}\.\d{4,5}(v\d+)?$")
RESOLVABLE = {"wayback", "commit", "arxiv"}
ALT_SCHEMES = {"isbn", "wayback", "commit", "arxiv", "std"}

LEDGER_REL = "results/LIT/id_resolution.json"


def repo_root() -> Path:
    v = os.environ.get("BO_REPO")
    if v:
        return Path(v)
    return Path(__file__).resolve().parents[3]


def norm_doi(d: str) -> str:
    d = d.strip()
    d = re.sub(r"^(https?://(dx\.)?doi\.org/|doi:)", "", d, flags=re.I)
    return d.lower()


def isbn13_ok(raw: str) -> bool:
    digits = re.sub(r"[-\s]", "", raw)
    if not re.fullmatch(r"\d{13}", digits):
        return False
    total = sum(int(c) * (1 if i % 2 == 0 else 3) for i, c in enumerate(digits[:12]))
    return (10 - total % 10) % 10 == int(digits[12])


def id_key(scheme: str, value: str) -> str:
    """Chave canônica no livro de resolução."""
    if scheme == "doi":
        return "doi:" + norm_doi(value)
    if scheme == "isbn":
        return "isbn:" + re.sub(r"[-\s]", "", value)
    return f"{scheme}:{value}"


def validate_format(scheme: str, value: str) -> str | None:
    """None se o formato está certo; senão, o motivo."""
    if scheme == "doi":
        return None if DOI_RX.match(norm_doi(value)) else "DOI malformado"
    if scheme == "isbn":
        return None if isbn13_ok(value) else "ISBN-13 com dígito verificador errado"
    if scheme == "wayback":
        return None if WAYBACK_RX.match(value) else "URL arquivada fora do formato web.archive.org/web/<14 dígitos>/<url>"
    if scheme == "commit":
        return None if COMMIT_RX.match(value) else "commit fora do formato github:dono/repo@<sha de 40>"
    if scheme == "arxiv":
        return None if ARXIV_RX.match(value) else "id arXiv malformado"
    if scheme == "std":
        return None if len(value) >= 6 else "norma sem número"
    return f"esquema desconhecido: {scheme}"


def norm_text(s: str) -> str:
    s = html.unescape(html.unescape(s or ""))
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.replace("--", "-").lower()
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def tokens(s: str) -> set[str]:
    return set(norm_text(s).split())
