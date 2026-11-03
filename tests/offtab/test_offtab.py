"""Testes do OFFTAB: regras de parse, separação de menções, decodificação do literal da Oracle, alegações e auditoria.

Os testes que leem as entradas reais (HTML do Google e da Microsoft, pacote da Oracle) conferem as contagens
223/205/160; os de regra usam HTML e texto sintéticos.
"""

from __future__ import annotations

import pytest

from bo.offtab import audit as A
from bo.offtab import claims as C
from bo.offtab import htmltables as H
from bo.offtab import mentions as MN
from bo.offtab import microsoft as M
from bo.offtab import oracle as O
from bo.offtab import sources as S


# ------------------------------------------------------------------ htmltables
def test_cell_segments_split_on_br_and_list_and_skip_script():
    html = ("<h2>Sec</h2><h3>Sub</h3><table><tr><th>AWS service</th><th>Azure service</th></tr>"
            "<tr><td><a>A</a> <br><br> B</td><td><ul><li>X</li><li> Y </li></ul><script>Z()</script></td></tr>"
            "</table>")
    t = H.tables(html)[0]
    assert (t.h2, t.h3) == ("Sec", "Sub")
    assert t.header() == ["AWS service", "Azure service"]
    assert [c.text() for c in t.body()[0]] == ["A ; B", "X ; Y"]


def test_h2_resets_h3():
    html = "<h2>A</h2><h3>a1</h3><h2>B</h2><table><tr><th>x</th></tr></table>"
    assert (H.tables(html)[0].h2, H.tables(html)[0].h3) == ("B", "")


# ------------------------------------------------------------------ Microsoft: regra de coluna
def _ms_table(second: str) -> str:
    return (f"<h2>S</h2><table><tr><th>AWS service</th><th>{second}</th><th>Description</th></tr>"
            "<tr><td>a</td><td>b</td><td>d</td></tr></table>")


def test_ms_rule_azure_prefix_only():
    assert len(M.parse_page("p", _ms_table("Azure service"), "0" * 64)) == 1
    # "Microsoft or Azure service" contém "azure" mas não começa com ela: fora das 205, vai para o suplemento
    assert M.parse_page("p", _ms_table("Microsoft or Azure service"), "0" * 64) == []
    assert len(M.parse_page("p", _ms_table("Microsoft or Azure service"), "0" * 64, supplement=True)) == 1
    assert M.parse_page("p", _ms_table("Azure service"), "0" * 64, supplement=True) == []


def test_ms_kind():
    assert C.ms_kind("Concept|AWS|Azure") == "concept"
    assert C.ms_kind("AWS EBS volume type|Azure managed disk|Use for") == "sku"
    assert C.ms_kind("AWS service|Azure service|Description") == "service"


# ------------------------------------------------------------------ menções
@pytest.mark.parametrize("cell,want", [
    ("AWS CodeBuild, AWS CodeDeploy, AWS CodePipeline", ["AWS CodeBuild", "AWS CodeDeploy", "AWS CodePipeline"]),
    ("Azure SQL Database, Azure Database for MySQL, or Azure Database for PostgreSQL",
     ["Azure SQL Database", "Azure Database for MySQL", "Azure Database for PostgreSQL"]),
    ("Amazon EBS provisioned IOPS volumes (io1/io2, io2 Block Express, gp3)",
     ["Amazon EBS provisioned IOPS volumes (io1/io2, io2 Block Express, gp3)"]),
    ("Azure DevOps ; GitHub ; GitHub Actions", ["Azure DevOps", "GitHub", "GitHub Actions"]),
    ("Data Factory in Microsoft Fabric or Azure Data Factory", ["Data Factory in Microsoft Fabric or Azure Data Factory"]),
    ("", []),
    ("Built-in service discovery in Azure Container Apps, optionally with Dapr service invocation ; Istio add-on",
     ["Built-in service discovery in Azure Container Apps, optionally with Dapr service invocation", "Istio add-on"]),
    ("None", []),
    ("No single equivalent. Use a combination of Azure Private Link, and Azure API Management.", []),
])
def test_split_cell(cell, want):
    assert MN.split_cell(cell) == want


@pytest.mark.parametrize("cell,cls", [
    ("", MN.EMPTY), ("  ", MN.EMPTY), ("None", MN.NONE), ("No equivalent", MN.NONE),
    ("No direct equivalent", MN.NONE), ("No single equivalent. Use X.", MN.NONE),
    ("Claims no access to customer data, even by request. Metadata access is logged.", MN.PROSE),
    ("AWS Storage Gateway: Tape Gateway", MN.SERVICES), ("Azure Migrate: App Containerization", MN.SERVICES),
    ("Amazon Nonesuch", MN.SERVICES),
])
def test_classify(cell, cls):
    assert MN.classify(cell) == cls


def test_compound_and_ids():
    assert MN.compound("Amazon CloudWatch and AWS X-Ray")
    assert not MN.compound("AWS Lambda")
    assert MN.service_id("aws", "AWS Resource Groups & Tag Editor") == "awssvc:aws-resource-groups-and-tag-editor"
    assert MN.service_id("azure", "Cost Management + Billing") == "azuresvc:cost-management-plus-billing"
    with pytest.raises(ValueError):
        MN.slug("--")


# ------------------------------------------------------------------ Oracle: literal JavaScript (nunca executado)
def test_js_string_decodes_known_escapes():
    assert O.js_string(r"{\n  \"a\": \'b\\cé\'}") == "{\n  \"a\": 'b\\cé'}"


@pytest.mark.parametrize("bad", [r"\x41", "a'b", "\\"])
def test_js_string_rejects(bad):
    with pytest.raises(O.LayoutError):
        O.js_string(bad)


def test_extract_requires_single_marker():
    m, e = S.ORACLE["module_marker"], S.ORACLE["module_end"]
    body = r'{\"buildDate\": \"x\", \"serviceRow\": []}'
    assert O.extract(f"xx{m}{body}{e}yy")["serviceRow"] == []
    with pytest.raises(O.LayoutError):
        O.extract(f"{m}{body}{e}{m}{body}{e}")


# ------------------------------------------------------------------ alegações e auditoria (sintético)
def _row(vendor, pivot, cells, row="1", table_set="main"):
    return {"vendor": vendor, "table_set": table_set, "row": row, "pivot": pivot, "kind": "service", "context": {},
            "cells": {p: {"column": p, "text": " ; ".join(ms), "mentions": ms,
                      "status": MN.SERVICES if ms else MN.EMPTY} for p, ms in cells.items()},
            "source_url": "https://example.org/t", "retrieved_utc": "2026-11-03T04:31:11Z", "html_sha256": "a" * 64}


def test_claims_are_related_without_transport_and_assess_ok():
    from bo.semantics.obligations import assess
    rows = [_row("oracle", "oci", {"oci": ["O1", "O2"], "aws": ["A1"], "azure": [], "gcp": ["G1"]})]
    recs = C.correspondences(rows)
    assert len(recs) == 4                       # 2 OCI x (1 AWS + 1 GCP)
    assert {r["mapping_cardinality"] for r in recs} == {"n:1"}
    for r in recs:
        assert r["predicate_id"] == "skos:relatedMatch" and r["transport_fidelity"] == "none"
        assert r["subject_id"].startswith("ocisvc:")
        assert assess(r).verdict == "OK"
    assert len({r["claim_id"] for r in recs}) == 4


def test_claim_file_validates_with_official_validator(tmp_path):
    from bo.contracts import sssom as CS
    from bo.contracts.rules import check_correspondences
    rows = [_row("google", "gcp", {"gcp": ["Cloud Run"], "aws": ["AWS Fargate", "AWS App Runner"], "azure": []})]
    recs = C.correspondences(rows)
    text = CS.write_tsv(recs, "https://example.org/ms", {**MN.CURIE_MAP, "semapv": "https://w3id.org/semapv/vocab/",
                                                          "skos": "http://www.w3.org/2004/02/skos/core#",
                                                          "bo": "https://w3id.org/brevops/ontology#"})
    meta, back, cols = CS.read_tsv(text)
    assert check_correspondences(back, meta, cols) == []
    # prefixo fora do curie_map tem de reprovar (o teste não passa por vacuidade)
    meta2 = dict(meta, curie_map={k: v for k, v in meta["curie_map"].items() if k != "awssvc"})
    assert any("awssvc" in e for e in check_correspondences(back, meta2, cols))


def test_reach_ignores_table_whose_pivot_is_target():
    rows = [_row("oracle", "oci", {"oci": ["O1"], "aws": [], "azure": ["Z1"], "gcp": []}),
            _row("microsoft", "aws", {"aws": ["A1"], "azure": ["Z2"]}, row="2")]
    r = A.reach(rows)
    assert "gcp->oci" not in r and "azure->oci" not in r      # só a Oracle tem coluna oci, e ela é o pivô
    assert r["azure->aws"]["n_services"] == 1                  # Z2 vem da Microsoft (pivô aws): fora; Z1 entra
    assert r["azure->aws"]["n_reached"] == 0
    assert r["aws->azure"]["fraction"] == 1.0


def test_row_gaps_counts_only_main():
    rows = [_row("google", "gcp", {"gcp": ["P"], "aws": [], "azure": ["Z"]}),
            _row("google", "gcp", {"gcp": ["Q"], "aws": ["A"], "azure": []}, row="2"),
            _row("microsoft", "aws", {"aws": ["A"], "azure": []}, row="S1", table_set="supplement")]
    g = A.row_gaps(rows)
    assert (g["google:aws"]["n_missing"], g["google:aws"]["n_rows"]) == (1, 2)
    assert g["microsoft:azure"]["n_rows"] == 0


# ------------------------------------------------------------------ entradas reais
def test_real_counts_and_shas():
    from bo.offtab import google as G
    g, gsha = G.parse_file()
    m, mshas = M.parse_dir()
    o, meta = O.parse_dir()
    assert (len(g), len(m), len(o)) == (223, 205, 160)
    assert gsha == S.GOOGLE["html_sha256"]
    assert mshas == S.MS_PAGES
    assert meta["data_sha256"] == S.ORACLE["data_sha256"]
    assert len(M.supplement()) == 30
    assert O.chain_ok(S.oracle_dir()) == []


def test_tampered_html_changes_rows_or_sha(tmp_path):
    """Uma mudança de um byte no HTML muda o sha256 (o repro compara com o fixado)."""
    src = S.GOOGLE_HTML.read_bytes()
    p = tmp_path / "page.html"
    p.write_bytes(src.replace(b"Cloud Build", b"Cloud Bxild", 1))
    from bo.offtab import google as G
    rows, sha = G.parse_file(p)
    assert sha != S.GOOGLE["html_sha256"]
    assert rows[0]["google_cloud_product"] == "Cloud Bxild"
