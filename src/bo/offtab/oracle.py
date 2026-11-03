"""Tabela da Oracle ("Compare OCI with AWS, Azure, and Google Cloud").

A página www.oracle.com/cloud/service-comparison/ põe a tabela num iframe (ocimapping.html, aplicação Oracle JET).
Os dados não vêm de ./data/ocimapping.json (404 em 2026-11-03): estão embutidos no pacote mapping-bundle.js como
literal de string JavaScript do módulo 7417 (e.exports='{...}'). O pacote foi salvo como .txt e NUNCA é executado:
aqui só se localiza o literal, decodificam-se os escapes JavaScript (\\n, \\\\, \\', \\", \\uXXXX; qualquer outro
escape reprova) e o texto resultante vai para json.loads.

Cada linha (serviceRow) é um "cross_platform_service" com categoria e listas de serviços de OCI, AWS, Azure e
Google Cloud (cada uma com serviceStatus). É a única das três tabelas com pivô neutro (o conceito da linha), mas foi
montada pela Oracle e o buildDate é 2024-10-31: ela é mais velha que as outras duas.
"""

from __future__ import annotations

import json
from pathlib import Path

from . import sources as S

PROVIDERS = ("oci", "aws", "azure", "gcp")
_ESC = {"n": "\n", "\\": "\\", "'": "'", '"': '"', "t": "\t", "r": "\r", "/": "/"}


class LayoutError(ValueError):
    pass


def js_string(lit: str) -> str:
    """Decodifica o corpo de um literal JavaScript entre aspas simples (sem as aspas)."""
    out, i, n = [], 0, len(lit)
    while i < n:
        c = lit[i]
        if c == "\\":
            if i + 1 >= n:
                raise LayoutError("escape no fim do literal")
            d = lit[i + 1]
            if d == "u":
                hexd = lit[i + 2:i + 6]
                if len(hexd) != 4 or any(x not in "0123456789abcdefABCDEF" for x in hexd):
                    raise LayoutError(f"\\u malformado na posição {i}")
                out.append(chr(int(hexd, 16)))
                i += 6
                continue
            if d not in _ESC:
                raise LayoutError(f"escape JavaScript não previsto \\{d} na posição {i}")
            out.append(_ESC[d])
            i += 2
            continue
        if c == "'":
            raise LayoutError(f"aspas simples sem escape na posição {i}: o literal terminou antes do marcador")
        out.append(c)
        i += 1
    return "".join(out)


def extract(bundle: str) -> dict:
    a = bundle.find(S.ORACLE["module_marker"])
    if a < 0 or bundle.find(S.ORACLE["module_marker"], a + 1) >= 0:
        raise LayoutError("marcador do módulo 7417 ausente ou repetido")
    a += len(S.ORACLE["module_marker"])
    b = bundle.find(S.ORACLE["module_end"], a)
    if b < 0:
        raise LayoutError("fim do módulo 7417 não achado")
    doc = json.loads(js_string(bundle[a:b]))
    if not isinstance(doc, dict) or not isinstance(doc.get("serviceRow"), list):
        raise LayoutError("JSON embutido sem serviceRow")
    return doc


def rows_of(doc: dict, data_sha256: str) -> list[dict]:
    out = []
    for i, r in enumerate(doc["serviceRow"], 1):
        rec = {"row": str(i), "cross_platform_service_id": r["cross_platform_service_id"],
               "category": r["cross_platform_service_category"], "cross_platform_service": r["cross_platform_service"],
               "description": r.get("description") or ""}
        for p in PROVIDERS:
            rec[p] = [{"service": (s.get("service") or "").strip(), "status": s.get("serviceStatus")}
                      for s in (r.get(p) or []) if (s.get("service") or "").strip()]
        rec.update({"source_url": S.ORACLE["url"], "retrieved_utc": S.ORACLE["retrieved_utc"],
                    "source_html_sha256": S.ORACLE["html_sha256"], "data_sha256": data_sha256,
                    "build_date": doc.get("buildDate")})
        out.append(rec)
    return out


def chain_ok(folder: Path) -> list[str]:
    """A página principal aponta o iframe, o iframe aponta o pacote, o pacote declara o caminho do JSON."""
    errs = []
    main = (folder / "oracle-service-comparison.html").read_text(encoding="utf-8")
    if 'src="/a/ocom/docs/ocimapping/ocimapping.html"' not in main:
        errs.append("oracle-service-comparison.html não contém o iframe ocimapping.html")
    frame = (folder / "ocimapping.html").read_text(encoding="utf-8")
    if "js/mapping-bundle.js" not in frame:
        errs.append("ocimapping.html não carrega js/mapping-bundle.js")
    doc = (folder / "service-comparison.htm").read_text(encoding="utf-8")
    if "https://www.oracle.com/cloud/service-comparison/" not in doc:
        errs.append("service-comparison.htm (docs) não aponta a página de comparação")
    return errs


def parse_dir(folder: Path | None = None) -> tuple[list[dict], dict]:
    folder = folder or S.oracle_dir()
    p = folder / S.ORACLE["data_file"]
    sha = S.sha256_file(p)
    doc = extract(p.read_text(encoding="utf-8"))
    return rows_of(doc, sha), {"build_date": doc.get("buildDate"), "data_sha256": sha}
