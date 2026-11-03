"""Linhas normalizadas das três tabelas, alegações C09 (skos:relatedMatch, sem transporte) e catálogo de serviços.

Por que relatedMatch: cada fornecedor diz que os serviços da linha são "comparáveis" e avisa que a paridade é
aproximada (Microsoft: "not every matched service has exact feature-for-feature parity"; Oracle: "best fit"). Isso
não sustenta exact/close/broad/narrow, que exigem normalização, contrato de perda ou predicado de pertença
(obrigações do SEMANTICS). relatedMatch não transporta valor (RELATED-NT): transport_fidelity = none, sem
translation_fn, value_domain_relation = unknown. A frase do fornecedor sustenta só o "related" (DOC_SUPPORTED com
citação: URL, data de coleta, sha256 do HTML e número da linha).

Direção: o sujeito é sempre o pivô da tabela (Google: produto Google Cloud; Microsoft: serviço AWS; Oracle: serviço
OCI); o objeto é a contraparte que o fornecedor lista. Linha com vários serviços dos dois lados vira o produto
cartesiano, com mapping_cardinality (1:1, 1:n, n:1, n:n) dizendo que a afirmação original era sobre o grupo.
"""

from __future__ import annotations

from collections import defaultdict

from . import mentions as MN
from . import sources as S

VENDOR_CODE = {"google": "G", "microsoft": "M", "oracle": "O"}
VENDOR_LABEL = {"google": "Google Cloud (tabela do fornecedor)", "microsoft": "Microsoft Learn (tabela do fornecedor)",
                "oracle": "Oracle (tabela do fornecedor)"}
PROVIDER_ORDER = ("aws", "azure", "gcp", "oci")


def _date(utc: str) -> str:
    return utc[:10]


def ms_kind(table_header: str) -> str:
    cols = [c.lower() for c in table_header.split("|")]
    if cols and cols[0] == "concept":
        return "concept"
    if any(c.startswith("aws") and "volume type" in c for c in cols):
        return "sku"
    return "service"


def table_rows(google_rows, ms_rows, ms_supplement, oracle_rows) -> list[dict]:
    out = []
    for r in google_rows:
        out.append({
            "vendor": "google", "table_set": "main", "row": r["row"], "pivot": "gcp", "kind": "service",
            "context": {"service_category": r["service_category"], "service_type": r["service_type"]},
            "cells": {"gcp": {"column": "google_cloud_product", "text": r["google_cloud_product"],
                              "mentions": [MN.clean(r["google_cloud_product"])] if r["google_cloud_product"] else []},
                      "aws": {"column": "aws_offering", "text": r["aws_offering"],
                              "mentions": MN.split_cell(r["aws_offering"])},
                      "azure": {"column": "azure_offering", "text": r["azure_offering"],
                                "mentions": MN.split_cell(r["azure_offering"])}},
            "source_url": S.GOOGLE["url"], "retrieved_utc": r["retrieved_utc"],
            "html_sha256": r["source_html_sha256"]})
    for set_name, rows in (("main", ms_rows), ("supplement", ms_supplement)):
        for r in rows:
            out.append({
                "vendor": "microsoft", "table_set": set_name, "row": r["row"], "pivot": "aws",
                "kind": ms_kind(r["table_header"]),
                "context": {"page": r["page"], "section_h2": r["section_h2"], "section_h3": r["section_h3"],
                            "area": r["area"], "table_header": r["table_header"]},
                "cells": {"aws": {"column": "aws_service", "text": r["aws_service"],
                                  "mentions": MN.split_cell(r["aws_service"])},
                          "azure": {"column": "azure_service", "text": r["azure_service"],
                                    "mentions": MN.split_cell(r["azure_service"])}},
                "source_url": r["source_url"], "retrieved_utc": r["retrieved_utc"],
                "html_sha256": r["source_html_sha256"]})
    for r in oracle_rows:
        out.append({
            "vendor": "oracle", "table_set": "main", "row": r["row"], "pivot": "oci", "kind": "service",
            "context": {"category": r["category"], "cross_platform_service": r["cross_platform_service"],
                        "cross_platform_service_id": r["cross_platform_service_id"], "build_date": r["build_date"]},
            "cells": {p: {"column": p, "text": " ; ".join(s["service"] for s in r[p]),
                          "mentions": [s["service"] for s in r[p]], "statuses": [s["status"] for s in r[p]]}
                      for p in ("oci", "aws", "azure", "gcp")},
            "source_url": r["source_url"], "retrieved_utc": r["retrieved_utc"], "html_sha256": r["source_html_sha256"],
            "data_sha256": r["data_sha256"]})
    for tr in out:
        for p, cell in tr["cells"].items():
            if tr["vendor"] == "oracle":
                keep = [k for k, m in enumerate(cell["mentions"]) if MN.classify(m) == MN.SERVICES]
                cell["mentions"] = [cell["mentions"][k] for k in keep]
                cell["statuses"] = [cell["statuses"][k] for k in keep]
                cell["status"] = MN.SERVICES if keep else (MN.EMPTY if not cell["text"] else MN.NONE)
            else:
                cell["status"] = MN.classify(cell["text"])
    return out


def _card(n_s: int, n_o: int) -> str:
    return f"{'1' if n_s == 1 else 'n'}:{'1' if n_o == 1 else 'n'}"


def _sentence(tr: dict) -> str:
    parts = [f"{p}: {tr['cells'][p]['text'] or '(vazio)'}" for p in PROVIDER_ORDER if p in tr["cells"]]
    return f"{tr['vendor']} linha {tr['row']} | " + " | ".join(parts)


def correspondences(rows: list[dict]) -> list[dict]:
    recs = []
    for tr in rows:
        piv = tr["pivot"]
        subj = tr["cells"][piv]["mentions"]
        code = VENDOR_CODE[tr["vendor"]] + ("S" if tr["table_set"] == "supplement" else "")
        rowtag = tr["row"] if tr["row"].startswith("S") else f"R{int(tr['row']):03d}"
        ev = {"source": tr["source_url"], "date": _date(tr["retrieved_utc"]), "retrieved_utc": tr["retrieved_utc"],
              "html_sha256": tr["html_sha256"], "row": tr["row"], "table_set": tr["table_set"],
              "sentence": _sentence(tr)}
        if "data_sha256" in tr:
            ev["data_sha256"] = tr["data_sha256"]
        for q in PROVIDER_ORDER:
            if q == piv or q not in tr["cells"]:
                continue
            objs = tr["cells"][q]["mentions"]
            for i, s in enumerate(subj, 1):
                for j, o in enumerate(objs, 1):
                    cid = f"OFFTAB-{code}-{rowtag}-S{i}-{q.upper()}{j}"
                    recs.append({
                        "subject_id": MN.service_id(piv, s), "predicate_id": "skos:relatedMatch",
                        "object_id": MN.service_id(q, o), "mapping_justification": "semapv:ManualMappingCuration",
                        "claim_id": cid, "claim_version_id": f"{cid}@1", "event_id": f"EV-{cid}-1",
                        "semantic_relation": "related",
                        "value_domain_relation": {"orientation": "subject_to_object", "relation": "unknown"},
                        "transport_fidelity": "none", "guard": {"all": []},
                        "proof": {"type": "vendor_comparison_table", "evidence": [ev], "tests": []},
                        "evidence_state": "DOC_SUPPORTED", "basis": "direct",
                        "subject_concept": "bo:UNGLOSSED", "object_concept": "bo:UNGLOSSED",
                        "subject_label": s, "object_label": o, "subject_category": tr["kind"],
                        "object_category": tr["kind"], "author_label": VENDOR_LABEL[tr["vendor"]],
                        "mapping_provider": tr["source_url"], "mapping_date": _date(tr["retrieved_utc"]),
                        "mapping_cardinality": _card(len(subj), len(objs)),
                        "comment": f"OFFTAB só auditoria; {tr['vendor']} {tr['table_set']} linha {tr['row']}; "
                                   f"pivô {piv}; não define universo nem classe",
                    })
    return recs


def catalog(rows: list[dict]) -> list[dict]:
    """Um registro por id de serviço: rótulos vistos, tipo, onde aparece (fornecedor, linha, coluna)."""
    by = {}
    for tr in rows:
        for p, cell in tr["cells"].items():
            for k, m in enumerate(cell["mentions"]):
                sid = MN.service_id(p, m)
                e = by.setdefault(sid, {"service_id": sid, "provider": p, "labels": set(), "kinds": set(),
                                        "compound": False, "statuses": set(), "occurrences": []})
                e["labels"].add(m)
                e["kinds"].add(tr["kind"])
                e["compound"] = e["compound"] or MN.compound(m)
                if cell.get("statuses"):
                    st = cell["statuses"][k]
                    e["statuses"].add(st if st is not None else "null")
                e["occurrences"].append({"vendor": tr["vendor"], "table_set": tr["table_set"], "row": tr["row"],
                                         "column": cell["column"], "pivot": p == tr["pivot"]})
    out = []
    for sid in sorted(by):
        e = by[sid]
        vendors = sorted({o["vendor"] for o in e["occurrences"]})
        out.append({"service_id": sid, "provider": e["provider"], "labels": sorted(e["labels"]),
                    "kinds": sorted(e["kinds"]), "compound": e["compound"], "statuses": sorted(e["statuses"]),
                    "vendors": vendors, "n_occurrences": len(e["occurrences"]), "occurrences": e["occurrences"]})
    return out


def provider_counts(cat: list[dict]) -> dict:
    c = defaultdict(int)
    for e in cat:
        c[e["provider"]] += 1
    return dict(sorted(c.items()))
