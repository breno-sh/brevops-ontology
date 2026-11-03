"""Testes do DOCS-GCP: analisador, padrões (positivos e negativos), resolução de caminho e as saídas gravadas."""

import json
import random

import pytest

from bo.docs_gcp import extract as X
from bo.docs_gcp import mdparse as MD
from bo.docs_gcp import resolve as R
from bo.docs_gcp import sources as S
from bo.schema import core as SC

PAGE = """---
subcategory: "Exemplo"
description: |-
  Página sintética.
---

# google_exemplo_thing

Texto.

## Example Usage

```hcl
* `nao_e_item` - dentro de código
```

## Argument Reference

The following arguments are supported:

* `name` - (Required) The name. Must be 1-63 characters long.
    Changing this forces a new resource to be created.

* `mode` -
  (Optional)
  The mode.
  Possible values are: `FAST`, `SLOW`.
  Default value is `FAST`.

* `cfg` - (Optional) Config. Structure is [documented below](#nested_cfg).

- - -

* `ttl` - (Optional) Time to live in seconds. Defaults to 900s.

-> Nota solta que não é do item.

<a name="nested_cfg"></a>The `cfg` block supports:

* `size` - (Optional) Size in GB. Must be between 10 and 100.

* `kind` - (Optional) Either `A1` or `B2`. Conflicts with `size`.

## Attributes Reference

* `id` - an identifier for the resource with format `things/{{name}}`

* `cfg.0.state` - The state.

## Timeouts

- `create` - Default is 20 minutes.

## Import

Thing can be imported using any of these accepted formats:

* `things/{{name}}`
* `{{name}}`
"""


def fake_type():
    block = {"attributes": {"name": {"type": "string", "required": True}, "mode": {"type": "string", "optional": True},
                            "ttl": {"type": "string", "optional": True}, "id": {"type": "string", "computed": True}},
             "block_types": {"cfg": {"nesting_mode": "list", "block": {"attributes": {
                 "size": {"type": "number", "optional": True}, "kind": {"type": "string", "optional": True},
                 "state": {"type": "string", "computed": True}}}},
                 "timeouts": {"nesting_mode": "single", "block": {"attributes": {
                     "create": {"type": "string", "optional": True}}}}}}
    return SC.type_schema("google", "8.9.0", "google_exemplo_thing", block)


@pytest.fixture(scope="module")
def page():
    return MD.parse_text(PAGE, "website/docs/r/exemplo_thing.html.markdown")


def test_front_matter_e_tipos(page):
    assert page.subcategory == "Exemplo" and page.subcategory_line == 2
    assert page.types == [("google_exemplo_thing", 7)]


def test_itens_e_codigo(page):
    names = [b.name for b in page.bullets]
    assert "nao_e_item" not in names
    assert names == ["name", "mode", "cfg", "ttl", "size", "kind", "id", "cfg.0.state", "create"]
    ttl = page.bullets[names.index("ttl")]
    assert not any("Nota solta" in t for _, t in ttl.lines)


def test_import(page):
    assert [f for _, f in page.imports.formats] == ["things/{{name}}", "{{name}}"]
    assert "imported using" in page.imports.sentence


def test_resolucao(page):
    idx = R.TypeIndex.of(fake_type())
    paths, how = R.bullet_paths(page, idx)
    got = {b.name: paths[i] for i, b in enumerate(page.bullets)}
    assert got["size"] == [("cfg.size", "ATOM")]
    assert got["cfg"] == [("cfg", "BLOCK")]
    assert got["cfg.0.state"] == [("cfg.state", "ATOM")]
    assert got["create"] == [("timeouts.create", "ATOM")]
    assert "LINK" in how.values()


def _kinds(page, name):
    b = [b for b in page.bullets if b.name == name][0]
    it = X.item_from_lines(b.lines)
    return it, X.findings(it)


def test_flags_e_padroes(page):
    it, fs = _kinds(page, "name")
    assert it.flags == ["required"]
    assert {(f.kind, json.dumps(f.value, sort_keys=True)) for f in fs} >= {
        ("range", json.dumps({"max": 63, "min": 1, "of": "length"}, sort_keys=True)),
        ("forces_replacement", "true")}
    it, fs = _kinds(page, "mode")
    assert it.flags == ["optional"] and it.description.startswith("The mode.")
    d = {f.kind: f.value for f in fs}
    assert d["allowed_values"] == {"values": ["FAST", "SLOW"], "closed": True}
    assert d["default"] == "FAST"
    it, fs = _kinds(page, "ttl")
    d = {f.kind: f.value for f in fs}
    assert d["unit"] == "seconds" and d["default"] == "900s"
    it, fs = _kinds(page, "size")
    d = {f.kind: f.value for f in fs}
    assert d["unit"] == "GB" and d["range"] == {"min": 10, "max": 100, "of": "value"}
    it, fs = _kinds(page, "kind")
    d = {f.kind: f.value for f in fs}
    assert d["allowed_values"]["values"] == ["A1", "B2"] and d["conflicts_with"] == {"attributes": ["size"]}
    it, fs = _kinds(page, "create")
    assert {f.kind: f.value for f in fs}["default"] == {"quantity": 20, "unit": "minutes"}
    it, fs = _kinds(page, "id")
    assert {f.kind: f.value for f in fs}["format"] == {"aspect": "identifier", "template": "things/{{name}}"}


def S_(t):
    return X.Sentence(t, 1, 0, len(t))


@pytest.mark.parametrize("text", [
    "Uses the default network if not set.",          # adjetivo, não valor
    "The default provider project is used.",
    "This can be updated without forcing recreation of the resource.",
    "Either A or B is selected by the model.",        # letras soltas não são enum
    "Up to nine fractional digits.",
])
def test_negativos(text):
    fs = (X.find_default(S_(text)) + X.find_enum(S_(text)) + X.find_forcenew(S_(text)))
    assert not [f for f in fs if f.unknown_reason is None], [(f.kind, f.value) for f in fs]


def test_default_nao_literal_vira_unknown():
    fs = X.find_default(S_("Defaults to the model serving container's IP."))
    assert len(fs) == 1 and fs[0].unknown_reason == "ambiguous" and fs[0].value is None


def test_frases_com_linha():
    it = X.item_from_lines([(10, "* `a` - (Optional) First one. Second"), (11, "  one here. e.g. `x` stays."),
                            (12, "  Third.")])
    assert [(s.text, s.line) for s in it.sentences] == [("First one.", 10), ("Second one here. e.g. `x` stays.", 10),
                                                        ("Third.", 12)]


# ---------------------------------------------------------------- saídas gravadas (dados reais da tag)

@pytest.fixture(scope="module")
def facts():
    p = S.out_dir() / "docs_facts.jsonl"
    if not p.exists():
        pytest.skip("docs_facts.jsonl ainda não gerado")
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines()]


def _get(facts, atom, kind):
    return [f for f in facts if f["atom_id"] == "google:" + atom and f["fact_kind"] == kind and f["status"] == "stated"]


def test_fatos_conhecidos(facts):
    assert _get(facts, "google_compute_instance:hostname", "forces_replacement")
    assert [f["value"] for f in _get(facts, "google_compute_instance:can_ip_forward", "default")] == [False]
    assert {tuple(f["value"]["values"]) for f in _get(facts, "google_compute_instance:desired_status",
                                                       "allowed_values")} == {("RUNNING", "SUSPENDED", "TERMINATED")}
    assert not [f for f in facts if f["fact_kind"] == "format" and f["status"] == "stated"
                and f["value"].get("aspect") == "import_id"]   # importação mora no type_subcategory (C03 3.1.0)
    assert [f["value"] for f in _get(facts, "google_compute_subnetwork:purpose", "default")] == ["PRIVATE"]
    assert all(f["as_of"] == "2026-10-26" for f in facts if f["fact_kind"] == "default" and f["status"] == "stated")


def test_proveniencia_linha_confere(facts):
    """A frase de origem está na linha citada (ou na seguinte) do arquivo da tag, numa amostra de 2000 fatos."""
    random.seed(20261103)
    sample = random.sample([f for f in facts if "source" in f and "omitido" not in f["source"]["sentence"]], 2000)
    cache, bad = {}, []
    for f in sample:
        s = f["source"]
        if s["file"] not in cache:
            cache[s["file"]] = (S.download_dir() / s["file"]).read_text(encoding="utf-8").splitlines()
        lines = cache[s["file"]]
        near = " ".join(X.clean_line(x) for x in lines[s["line"] - 1:s["line"] + 1])
        if s["sentence"][:12] not in near and not s["sentence"].startswith("subcategory"):
            bad.append((s["file"], s["line"]))
    assert not bad, bad[:5]


def test_unknown_sem_valor_e_ids_unicos(facts):
    assert len({f["fact_id"] for f in facts}) == len(facts)
    for f in facts:
        assert (f["status"] == "unknown") == ("value" not in f)


def test_subcategoria(facts):
    recs = [json.loads(x) for x in (S.out_dir() / "type_subcategory.jsonl").read_text(encoding="utf-8").splitlines()]
    by = {r["type_id"]: r for r in recs}
    ci = by["google:google_compute_instance"]
    assert ci["subcategory"]["value"] == "Compute Engine" and ci["subcategory"]["source"]["line"] == 16
    assert ci["title"] == {"text": "google_compute_instance", "line": 21}
    imp = ci["import"]
    assert imp["status"] == "stated" and imp["value"] == [
        "projects/{{project}}/zones/{{zone}}/instances/{{name}}", "{{project}}/{{zone}}/{{name}}", "{{name}}"]
    assert imp["source"]["line"] == 831 and imp["key_sentence"]["line"] == 829
    assert imp["methods"] == ["import_block_id", "terraform_import_cli"]
    net = by["google:google_compute_network"]["import"]
    assert "import_block_identity" in net["methods"] and net["identity"] == {"required": ["name"],
                                                                            "optional": ["project"]}
    assert len(recs) == len(S.load_types())


def test_import_sintetico(page):
    assert page.imports.section_line is not None and page.imports.methods == []
    pg = MD.parse_text(PAGE.replace("* `{{name}}`\n", "* `{{name}}`\n\n```\n$ terraform import google_x.a {{name}}\n```\n"),
                       "x")
    assert pg.imports.methods == ["terraform_import_cli"]
    pg = MD.parse_text(PAGE.split("## Import")[0] + "## Import\n\nThis resource does not support import.\n", "x")
    assert pg.imports.unsupported == (pg.imports.section_line + 2, "This resource does not support import.")


@pytest.mark.parametrize("text", [
    "Changing this forces a new resource to be created.",
    "Changes to this field will recreate the cloud function.",
    "Any changes on the configured value will force the table to be recreated.",
    "Changing this field at any other time forces recreation of the subnetwork.",
])
def test_forcenew_positivos(text):
    assert [f.value for f in X.find_forcenew(S_(text))] == [True]
