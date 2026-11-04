"""bo.schema.crosscheck com evidência: um caso por causa, um caso sem causa (reprova) e evidência adulterada."""
import gzip
import hashlib
import json

import pytest

from bo.schema import crosscheck as cc


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def make_extract(root, address, version, resources, data_sources=(), cache=None):
    """Pasta do bo.schema.extract + pacote no cache de plugin, com o h1 recalculado dentro do lock."""
    name = address.rsplit("/", 1)[-1]
    d = root / "tfschema" / f"{name}-{version}"
    d.mkdir(parents=True)
    blk = {"block": {"attributes": {"v": {"type": "string", "optional": True}}}}
    doc = {"format_version": "1.0", "provider_schemas": {address: {
        "resource_schemas": {r: blk for r in resources}, "data_source_schemas": {x: blk for x in data_sources}}}}
    raw = json.dumps(doc).encode()
    with gzip.open(d / "schema.json.gz", "wb") as f:
        f.write(raw)
    (d / "schema.json.sha256").write_text(f"{sha(raw)}  schema.json\n")
    pkg = (cache or root / "cache") / address / version / "darwin_arm64"
    pkg.mkdir(parents=True)
    binary = f"terraform-provider-{name}_v{version}_x5"
    (pkg / binary).write_bytes(b"binario de teste " + name.encode())
    (pkg / "LICENSE.txt").write_text("licença")
    receipt = {"schema": "bo.schema_extract/1",
               "provider": {"address": address, "version": version, "name": name},
               "lock": {"hashes": [cc.h1_of_dir(pkg), "zh:00"], "mode": "-lockfile=readonly"},
               "terraform": {"version": "1.15.8"},
               "provider_binary": {"file": binary, "os_arch": "darwin_arm64", "sha256": sha((pkg / binary).read_bytes())},
               "schema_json": {"sha256": sha(raw)}}
    (d / "receipt.json").write_text(json.dumps(receipt))
    return d


def make_docs(root, provider, version, pages):
    """pages: {(categoria, slug): texto}. Grava docs/ + MANIFEST.json e devolve (pasta docs, índice)."""
    base = root / "prefetch" / provider / version
    docs, files, idx = base / "docs", [], []
    for (cat, slug), text in pages.items():
        sub = {"resources": "r", "data-sources": "d"}[cat]
        rel = f"docs/{sub}/{slug}.html.markdown"
        f = base / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(text)
        files.append({"path": rel, "sha256": sha(f.read_bytes())})
        idx.append({"slug": slug, "category": cat, "language": "hcl", "path": "website/" + rel})
    docs.mkdir(parents=True, exist_ok=True)
    reg = cc.REGISTRY[provider]
    (base / "MANIFEST.json").write_text(json.dumps({"provider": f"registry.terraform.io/{reg}", "version": version,
                                                    "files": files}))
    return docs, {"version": version, "docs": idx}


def page(title: str) -> str:
    return f"---\nsubcategory: \"X\"\npage_title: \"P: {title}\"\n---\n\n{title}\n\nTexto.\n"


def run(root, provider, version, resources, pages, data_sources=(), beta=None):
    sdir = make_extract(root, f"registry.terraform.io/{cc.REGISTRY[provider]}", version, resources, data_sources)
    bdir = make_extract(root, cc.BETA["google"], version, beta) if beta is not None else None
    docs, index = make_docs(root, provider, version, pages)
    types = {r: "sha-" + r for r in resources}
    ev = cc.gather(provider, version, types, index, sdir, docs, bdir, root / "cache")
    return cc.compare(types, cc.documented(index, provider, version), ev), ev


def causes(rep):
    return sorted((e.get("tipo") or e.get("pagina"), e["causa"]) for e in rep["explicadas"])


def test_so_beta_from_verified_beta_schema(work):
    rep, ev = run(work, "google", "8.9.0", ["google_a"],
                  {("resources", "a"): page("# google_a"), ("resources", "b"): page("# google_b"),
                   ("resources", "c_iam"): page("# google_c_iam")},
                  beta=["google_a", "google_b", "google_c_iam_member"])
    assert rep["veredito"] == "PASS" and ev.proof["beta"]["h1"].startswith("h1:")
    assert causes(rep) == [("google_b", "so_beta"), ("google_c_iam", "so_beta")]


def test_beta_warning_in_docs_is_not_a_cause(work):
    """O aviso 'beta' da página não explica nada: sem o schema beta conferido, a página fica sem causa."""
    text = "---\npage_title: \"P\"\n---\n\nThis resource is in beta, and should be used with the terraform-provider-google-beta provider.\n"
    rep, _ = run(work, "google", "8.9.0", ["google_a"],
                 {("resources", "a"): page("# google_a"), ("resources", "bb"): text})
    assert "so_beta" not in rep["por_causa"]
    assert causes(rep) == [("google_bb", "pagina_sem_tipo_no_schema")]      # pelo nome do arquivo, nunca pelo aviso


def test_alias():
    rep = cc.compare({"aws_lb": "s", "aws_alb": "s", "aws_vpc": "v"}, {"aws_lb", "aws_vpc"})
    assert causes(rep) == [("aws_alb", "alias_bloco_identico")] and rep["veredito"] == "PASS"
    assert cc.compare({"aws_lb": "s", "aws_alb": "outro"}, {"aws_lb"})["veredito"] == "FAIL"


def test_nome_divergente_pairs_page_and_type(work):
    rep, _ = run(work, "oci", "9.11.0", ["oci_x", "oci_ds_private_endpoint"],
                 {("resources", "x"): page("# oci_x"),
                  ("resources", "ds_data_science_private_endpoint"): page("# oci_ds_private_endpoint")})
    assert rep["veredito"] == "PASS"
    assert causes(rep) == [("oci_ds_data_science_private_endpoint", "nome_divergente"),
                           ("oci_ds_private_endpoint", "nome_divergente")]


def test_nome_divergente_needs_exact_name(work):
    """Semelhança não conta: título que só lembra o tipo não forma par."""
    rep, _ = run(work, "oci", "9.11.0", ["oci_x", "oci_ds_private_endpoint"],
                 {("resources", "x"): page("# oci_x"),
                  ("resources", "ds_pe"): page("# oci_ds_private_endpoints")})
    assert causes(rep) == [("oci_ds_pe", "pagina_sem_tipo_no_schema"),
                           ("oci_ds_private_endpoint", "tipo_sem_documentacao")]


def test_data_source_published_as_resource(work):
    rep, _ = run(work, "oci", "9.11.0", ["oci_x"],
                 {("resources", "x"): page("# oci_x"), ("resources", "cg_items"): page("# Data Source: oci_cg_items")},
                 data_sources=["oci_cg_items"])
    assert rep["veredito"] == "PASS" and causes(rep) == [("oci_cg_items", "data_source_publicado_como_recurso")]


def test_page_without_type_in_schema(work):
    rep, _ = run(work, "oci", "9.11.0", ["oci_x"],
                 {("resources", "x"): page("# oci_x"), ("resources", "gone"): page("# oci_gone"),
                  ("resources", "ds_gone"): page("# Data Source: oci_ds_gone")})
    # 'Data Source:' cujo X não é data source do schema não é data_source_publicado_como_recurso
    assert rep["veredito"] == "PASS" and causes(rep) == [("oci_ds_gone", "pagina_sem_tipo_no_schema"),
                                                         ("oci_gone", "pagina_sem_tipo_no_schema")]


def test_type_without_documentation(work):
    rep, _ = run(work, "oci", "9.11.0", ["oci_x", "oci_core_default_route_table"], {("resources", "x"): page("# oci_x")})
    assert rep["veredito"] == "PASS" and causes(rep) == [("oci_core_default_route_table", "tipo_sem_documentacao")]


def test_no_cause_fails(work):
    """Página cujo título nomeia um tipo que já tem página, e linha '# ' fora de TITLE: as duas ficam sem causa."""
    rep, _ = run(work, "oci", "9.11.0", ["oci_x", "oci_y"],
                 {("resources", "x"): page("# oci_x"), ("resources", "weird"): page("# Um Título Qualquer"),
                  ("resources", "dup"): page("# oci_x")})
    assert rep["veredito"] == "FAIL"
    assert rep["paginas_sem_tipo"] == ["oci_dup", "oci_weird"]
    assert rep["tipos_sem_pagina"] == []
    assert ("oci_y", "tipo_sem_documentacao") in causes(rep)


def test_type_named_by_some_resource_title_is_not_undocumented(work):
    rep, _ = run(work, "oci", "9.11.0", ["oci_x", "oci_y"],
                 {("resources", "x"): page("# oci_x"), ("resources", "z"): page("# oci_y"),
                  ("resources", "w"): page("# oci_y")})
    # a 1ª página forma o par; a 2ª nomeia um tipo que já tem par: sem causa (nunca tipo_sem_documentacao)
    assert ("oci_y", "nome_divergente") in causes(rep) and ("oci_w", "nome_divergente") in causes(rep)
    assert rep["paginas_sem_tipo"] == ["oci_z"] and rep["veredito"] == "FAIL"


def test_without_evidence_old_behavior_and_keys(work):
    rep = cc.compare({"aws_a": "1", "aws_b": "2"}, {"aws_a"})
    assert set(rep) == {"tipos_schema", "paginas_indice", "iguais", "explicadas", "tipos_sem_pagina",
                        "paginas_sem_tipo", "veredito"}
    assert rep["veredito"] == "FAIL" and rep["tipos_sem_pagina"] == ["aws_b"]
    assert cc.gather("aws", "1.0.0", {}, {}, None, None, None) is None


def test_tampered_doc_is_rejected(work):
    sdir = make_extract(work, "registry.terraform.io/oracle/oci", "9.11.0", ["oci_x"])
    docs, index = make_docs(work, "oci", "9.11.0", {("resources", "x"): page("# oci_x")})
    (docs / "r" / "x.html.markdown").write_text(page("# oci_outro"))
    with pytest.raises(cc.EvidenceError):
        cc.gather("oci", "9.11.0", {"oci_x": "s"}, index, sdir, docs, None, work / "cache")


@pytest.mark.parametrize("tamper", ["h1", "binary", "schema", "version", "readonly"])
def test_unverified_beta_schema_is_rejected(work, tamper):
    sdir = make_extract(work, "registry.terraform.io/hashicorp/google", "8.9.0", ["google_a"])
    bdir = make_extract(work, cc.BETA["google"], "8.9.0", ["google_a", "google_b"])
    r = json.loads((bdir / "receipt.json").read_text())
    if tamper == "h1":
        r["lock"]["hashes"] = ["h1:outro=", "zh:00"]
    elif tamper == "binary":
        r["provider_binary"]["sha256"] = "0" * 64
    elif tamper == "schema":
        (bdir / "schema.json.sha256").write_text("0" * 64 + "  schema.json\n")
    elif tamper == "version":
        r["provider"]["version"] = "8.8.0"
    else:
        r["lock"]["mode"] = "init comum"
    (bdir / "receipt.json").write_text(json.dumps(r))
    docs, index = make_docs(work, "google", "8.9.0", {("resources", "a"): page("# google_a"),
                                                       ("resources", "b"): page("# google_b")})
    with pytest.raises(cc.EvidenceError):
        cc.gather("google", "8.9.0", {"google_a": "s"}, index, sdir, docs, bdir, work / "cache")


def test_cli_reports_causes_and_counts(work, monkeypatch):
    monkeypatch.setenv("BO_DATA", str(work))
    sdir = make_extract(work, "registry.terraform.io/oracle/oci", "9.11.0", ["oci_x", "oci_y"],
                        cache=work / "downloads" / "terraform-registry" / "plugin-cache")
    docs, index = make_docs(work, "oci", "9.11.0", {("resources", "x"): page("# oci_x")})
    tpath = work / "types.jsonl"
    tpath.write_text("".join(json.dumps({"resource_type": t, "block_sha256": t, "provider_version": "9.11.0"}) + "\n"
                             for t in ("oci_x", "oci_y")))
    ipath = work / "index.json"
    ipath.write_text(json.dumps(index))
    out = work / "cc.json"
    args = ["--provider", "oci", "--types", str(tpath), "--index", str(ipath), "--schema", str(sdir),
            "--docs", str(docs), "--out", str(out)]
    assert cc.main(args) == 0
    rep = json.loads(out.read_text())
    assert rep["por_causa"] == {"tipo_sem_documentacao": 1} and set(rep["causas"]) == set(cc.CAUSES)
    assert rep["evidencia"]["docs"]["paginas_lidas"] == 1
    assert cc.main(args[:6] + ["--no-evidence"]) == 1           # o critério antigo reprova o mesmo caso


def test_type_named_by_title_of_a_matched_page_has_no_cause(work):
    """Um título de recurso nomeia o tipo (numa página casada por slug com outro tipo): não é 'sem documentação'."""
    rep, _ = run(work, "oci", "9.11.0", ["oci_x", "oci_y"], {("resources", "x"): page("# oci_y")})
    assert rep["tipos_sem_pagina"] == ["oci_y"] and rep["veredito"] == "FAIL"


def test_untitled_page_whose_file_names_a_schema_type(work):
    """Sem nenhuma linha '# ' e com o nome do arquivo = data source do schema: pagina_sem_titulo."""
    untitled = "---\npage_title: \"P\"\n---\n\n### sem título de nível 1\n"
    rep, _ = run(work, "oci", "9.11.0", ["oci_x"],
                 {("resources", "x"): page("# oci_x"), ("resources", "cg_items"): untitled},
                 data_sources=["oci_cg_items"])
    assert rep["veredito"] == "PASS" and causes(rep) == [("oci_cg_items", "pagina_sem_titulo")]


def test_untitled_rule_is_not_a_name_exception(work):
    """Com linha '# ' (mesmo fora de TITLE) a regra do nome do arquivo não se aplica: sem causa."""
    rep, _ = run(work, "oci", "9.11.0", ["oci_x"],
                 {("resources", "x"): page("# oci_x"), ("resources", "cg_items"): page("# Um Título Qualquer")},
                 data_sources=["oci_cg_items"])
    assert rep["veredito"] == "FAIL" and rep["paginas_sem_tipo"] == ["oci_cg_items"]
    assert "pagina_sem_titulo" not in rep["por_causa"]


def test_untitled_page_of_removed_type(work):
    """Sem linha '# ' e o nome do arquivo não é tipo do schema: pagina_sem_tipo_no_schema pelo nome do arquivo;
    a frase de remoção da própria página vira o detalhe tipo_removido."""
    removed = ("---\npage_title: \"P: oci_gone_agent\"\n---\n\n"
               "### support for this resource has been removed from v5.28.0\n")
    plain = "---\npage_title: \"P\"\n---\n\nsó texto\n"
    rep, _ = run(work, "oci", "9.11.0", ["oci_x"],
                 {("resources", "x"): page("# oci_x"), ("resources", "gone_agent"): removed,
                  ("resources", "other_gone"): plain})
    assert rep["veredito"] == "PASS"
    ex = {e["pagina"]: e for e in rep["explicadas"]}
    assert ex["oci_gone_agent"]["causa"] == ex["oci_other_gone"]["causa"] == "pagina_sem_tipo_no_schema"
    assert ex["oci_gone_agent"]["tipo_removido"] == {
        "versao": "5.28.0", "frase": "support for this resource has been removed from v5.28.0"}
    assert "tipo_removido" not in ex["oci_other_gone"]
