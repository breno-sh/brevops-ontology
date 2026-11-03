"""bo.schema_oci.crossdiff: classificação do que a bo.schema.crosscheck deixa sem causa (sem mudar o veredito)."""
from bo.schema import crosscheck as cc
from bo.schema_oci import crossdiff


def _page(root, rel, text):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def test_classifica_as_cinco_classes(work):
    docs = work / "docs"
    _page(docs, "r/x_renomeado.html.markdown", "---\nlayout: x\n---\n\n# oci_x_nome_certo\nTexto.\n")
    _page(docs, "r/x_lista.html.markdown", "# Data Source: oci_x_lista\n")
    _page(docs, "r/x_sumiu.html.markdown", "# oci_x_sumiu\n")
    _page(docs, "r/x_vazio.html.markdown", "sem título nenhum\n")
    index = {"version": "1.0.0", "docs": [
        {"slug": s, "category": "resources", "language": "hcl", "path": f"website/docs/r/{s}.html.markdown"}
        for s in ("x_igual", "x_renomeado", "x_lista", "x_sumiu", "x_vazio")]}
    types = {"oci_x_igual": "h1", "oci_x_nome_certo": "h2", "oci_x_orfao": "h3"}
    rep = cc.compare(types, cc.documented(index, "oci", "1.0.0"))
    assert rep["veredito"] == "FAIL"
    out = crossdiff.classify(rep, crossdiff.resource_pages(index), docs, set(types), {"oci_x_lista"})
    pag = {r["pagina"]: r["classe"] for r in out["paginas_sem_tipo"]}
    tip = {r["tipo"]: r["classe"] for r in out["tipos_sem_pagina"]}
    assert pag == {"oci_x_renomeado": "pagina_com_slug_divergente", "oci_x_lista": "pagina_de_data_source_em_r",
                   "oci_x_sumiu": "pagina_de_tipo_ausente", "oci_x_vazio": "pagina_sem_titulo"}
    assert tip == {"oci_x_nome_certo": "pagina_com_slug_divergente", "oci_x_orfao": "tipo_sem_documentacao"}
    ds = next(r for r in out["paginas_sem_tipo"] if r["pagina"] == "oci_x_lista")
    assert ds["data_source_no_schema"] is True
    assert out["contagem"] == {"pagina:pagina_com_slug_divergente": 1, "pagina:pagina_de_data_source_em_r": 1,
                               "pagina:pagina_de_tipo_ausente": 1, "pagina:pagina_sem_titulo": 1,
                               "tipo:pagina_com_slug_divergente": 1, "tipo:tipo_sem_documentacao": 1}


def test_slug_com_prefixo_oci_normalizado():
    idx = {"docs": [{"slug": "oci_a_b", "category": "resources", "language": "hcl", "path": "p"},
                    {"slug": "a_c", "category": "resources", "language": "hcl", "path": "q"},
                    {"slug": "a_d", "category": "data-sources", "language": "hcl", "path": "r"}]}
    assert sorted(crossdiff.resource_pages(idx)) == ["oci_a_b", "oci_a_c"]


def test_titulo_lido_so_como_texto(work):
    _page(work, "p.md", "# oci_tipo\n")
    assert crossdiff.page_title(work / "p.md") == {"existe": True, "data_source": False, "nomeia": "oci_tipo",
                                                    "tem_titulo": True}
    assert crossdiff.page_title(work / "nao.md")["existe"] is False
