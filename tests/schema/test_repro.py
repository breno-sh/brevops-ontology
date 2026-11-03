"""bo.schema.repro: limiar de 99,5%, causas mecânicas das diferenças, sha256 do schema e --check."""
import copy
import gzip
import hashlib
import json

import pytest

from bo.schema import repro, ruler, core

from conftest import ADDR, GADGET, schema_doc

N_CLONES = 298          # 300 tipos: 1 diferença = 99,67% (passa), 2 = 99,33% (reprova)
GADGET_COUNTS = {"n_atributos_total": 2, "n_atributos_cfg": 1, "n_provider_populated": 1, "n_atributos_cfg_raw": 2,
                 "n_computed_only": 0, "n_blocos_total": 0}
WIDGET_COUNTS = {"n_atributos_total": 22, "n_atributos_cfg": 15, "n_provider_populated": 5,
                 "n_atributos_cfg_raw": 20, "n_computed_only": 2, "n_blocos_total": 8}


def make_doc():
    d = schema_doc()
    rs = d["provider_schemas"][ADDR]["resource_schemas"]
    for i in range(N_CLONES):
        rs[f"provider_a_g{i:03d}"] = copy.deepcopy(GADGET)
    return d


def write_schema(sdir, doc, version="1.0.0", corrupt=False):
    d = sdir / f"provider_a-{version}"
    d.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(doc).encode()
    with gzip.open(d / "schema.json.gz", "wb") as f:
        f.write(raw)
    sha = hashlib.sha256(raw + (b" " if corrupt else b"")).hexdigest()
    (d / "schema.json.sha256").write_text(f"{sha}  schema.json\n", encoding="utf-8")


def catalog_rows(doc, version="1.0.0"):
    ps = core.providers(doc)["provider_a"]
    rows = []
    for ts in core.iter_types(ps, "provider_a", version):
        counts = WIDGET_COUNTS if ts.resource_type == "provider_a_widget" else GADGET_COUNTS
        rows.append({"tipo": ts.resource_type, "provedor": "provider_a", "provider_version": version,
                     "kind": "resource", "servico": "a", "descricao": "", **counts, "arvore": ruler.tree(ts)})
    return rows


def write_catalog(path, rows):
    path.write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in rows), encoding="utf-8")


@pytest.fixture
def env(work):
    doc = make_doc()
    write_schema(work / "schemas", doc)
    rows = catalog_rows(doc)
    return work, doc, rows


def run(work, rows):
    write_catalog(work / "cat.jsonl", rows)
    return repro.run(work / "cat.jsonl", work / "schemas", work / "out")


def test_full_match_passes(env):
    work, _, rows = env
    rep = run(work, rows)
    assert rep["veredito"] == "PASS", rep["motivos"]
    assert rep["total"] == {"tipos_catalogo": 300, "iguais": 300, "arvore_igual": 300, "comparados": 300,
                            "taxa_iguais": 1.0, "taxa_arvore_igual": 1.0}
    assert rep["contratos"]["ok"] and len(rep["contratos"]["arquivos"]) == 2
    assert rep["por_provedor"]["provider_a"]["atomos"] == 22 + 2 * 299
    assert rep["por_provedor"]["provider_a"]["atributos_nested_type"] == 2
    assert rep["por_provedor"]["provider_a"]["atributos_write_only"] == 1


def reclassify(row):
    row["n_atributos_cfg"] += 1
    row["n_provider_populated"] -= 1


def test_one_explained_difference_passes(env):
    work, _, rows = env
    reclassify(rows[5])
    rep = run(work, rows)
    assert rep["veredito"] == "PASS", rep["motivos"]
    assert rep["diferencas_por_causa"] == {"regua_reclassificada": 1}
    assert rep["total"]["taxa_iguais"] == round(299 / 300, 6)


def test_below_threshold_fails_even_if_explained(env):
    work, _, rows = env
    reclassify(rows[5])
    reclassify(rows[6])
    rep = run(work, rows)
    assert rep["veredito"] == "FAIL"
    assert any("< 99.5%" in m for m in rep["motivos"])


def test_unexplained_difference_fails(env):
    work, _, rows = env
    rows[7]["n_atributos_total"] += 1
    rep = run(work, rows)
    assert rep["veredito"] == "FAIL"
    assert rep["diferencas_por_causa"] == {"nao_explicada": 1}
    assert rep["diferencas"][0]["campos"] == {"n_atributos_total": [3, 2]}


def test_missing_and_extra_types(env):
    work, _, rows = env
    ghost = dict(rows[0], tipo="provider_a_ghost")
    rep = run(work, rows[1:] + [ghost])
    causes = {d["type_id"]: d["causa"] for d in rep["diferencas"]}
    assert causes == {f"provider_a:{rows[0]['tipo']}": "extra_no_schema",
                      "provider_a:provider_a_ghost": "ausente_no_schema"}
    # tipo fora de um dos lados é diferença com causa: conta contra a taxa (299/300 = 99,67%), não reprova sozinho
    assert rep["total"]["iguais"] == 299 and rep["veredito"] == "PASS"


def test_schema_for_other_version_is_absent(env):
    work, doc, _ = env
    rep = run(work, catalog_rows(doc, version="2.0.0"))
    assert rep["veredito"] == "FAIL"
    assert rep["diferencas_por_causa"] == {"schema_ausente": 300}


def test_corrupt_schema_sha_fails(work):
    doc = make_doc()
    write_schema(work / "schemas", doc, corrupt=True)
    rep = run(work, catalog_rows(doc))
    assert rep["veredito"] == "FAIL"
    assert any("sha256" in m for m in rep["motivos"])


def test_tree_difference_is_secondary(env):
    work, _, rows = env
    rows[3]["arvore"]["req"] = ["outro"]
    rep = run(work, rows)
    assert rep["veredito"] == "PASS" and rep["total"]["arvore_igual"] == 299


def test_cli_write_then_check(env, monkeypatch, capsys):
    work, _, rows = env
    write_catalog(work / "cat.jsonl", rows)
    monkeypatch.setenv("BO_TMP", str(work / "tmp"))
    out = work / "rep.json"
    args = ["--catalog", str(work / "cat.jsonl"), "--schemas-dir", str(work / "schemas"), "--out", str(out)]
    assert repro.main(args) == 0
    assert json.loads(out.read_text())["generated_at"]
    assert repro.main(args + ["--check"]) == 0
    rep = json.loads(out.read_text())
    rep["total"]["iguais"] = 1
    out.write_text(json.dumps(rep))
    assert repro.main(args + ["--check"]) == 1
    assert "difere" in capsys.readouterr().out
