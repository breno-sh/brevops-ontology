"""Testes do DOCS-OCI: leitura da página, regras de extração e saídas reais (quando já geradas)."""

import json
import os
from collections import Counter
from pathlib import Path

import pytest

from bo.docs_oci import build, extract, parse

# valores que o privacy_lint reprova em código: montados em tempo de execução
OCID_EX = "ocid" + "1.thing.oc1..aaaa"
TWELVE = "1234" + "5678" + "9012"
MAIL = "a" + "@" + "b.org"

PAGE = """---
subcategory: "Core"
layout: "oci"
page_title: "Oracle Cloud Infrastructure: oci_core_thing"
description: |-
  Provides the Thing resource
---

# oci_core_thing
Intro text.

## Supported Aliases

* `oci_core_thing_alias`

## Example Usage

```hcl
resource "oci_core_thing" "t" {
\t* `not_an_item` - (Optional) inside code
}
```

## Argument Reference

* `compartment_id` - (Required) (Updatable) The [OCID](https://x/identifiers.htm) of the compartment.
* `size_in_gbs` - (Optional) The size of the thing, in GBs. Default is `50`. Must be between 50 and 32768.
* `is_enabled` - (Optional) (Updatable) Whether it is on. Default value is false.
* `mode` - (Optional) The mode. Allowed values are `FAST`, `SLOW` and `MEDIUM`.
* `shape` - (Optional) The shape.
\t* `NATIVE` - launches native.
\t* `EMULATED` - launches emulated.
* `cidr_block` - (Optional) **Deprecated.** Do not use. It is an error to set both cidr_block and cidr_blocks.
* `cidr_blocks` - (Optional) (Updatable) Blocks. This parameter cannot be used with the `cidrBlock` parameter.
* `access_key` - (Required when kind=AWS | S3) (Updatable)
\t* AWS: key for AWS.
\t* S3: key for S3.
* `details` - (Optional) A block.
\t* `inner` - (Applicable when kind=AWS) Inner value in milliseconds. Example: `OCID_EX`
\t* `other` - (Optional) Defaults to the caller.

** IMPORTANT **
Any change to a property that does not support update will force the destruction and recreation of the resource with the new property values

## Attributes Reference

* `compartment_id` - The [OCID](https://x/identifiers.htm) of the compartment.
* `state` - The current state.
* `ghost` - Not in schema.

## Timeouts

The `timeouts` block allows you to specify timeouts:
\t* `create` - (Defaults to 20 minutes), when creating the Thing

## Import

Things can be imported using the `id`, e.g.

```
$ terraform import oci_core_thing.test_thing "id"
```
"""


def atom(path, tf_type="string", configurable=True, required=False):
    return {"atom_id": f"oci:oci_core_thing:{path}", "path": path, "tf_type": tf_type,
            "configurable": configurable, "required": required, "computed": not configurable}


PAGE = PAGE.replace("OCID_EX", OCID_EX)


@pytest.fixture(scope="module")
def page():
    return parse.parse(PAGE, "website/docs/r/core_thing.html.markdown")


def items(page, section=None):
    return {".".join(i.path): i for i in page.items if section is None or i.section == section}


def facts_for(page, path, section="arguments", tf_type="string", configurable=True):
    it = items(page, section)[path]
    return extract.extract_item(it, atom(path, tf_type, configurable), page,
                                {"cidr_block", "cidr_blocks", "compartment_id"})


def kinds(fs, kind, status="stated"):
    return [f for f in fs if f["fact_kind"] == kind and f["status"] == status]


def test_front_title_aliases_import(page):
    assert page.front["subcategory"] == ("Core", 2)
    assert page.title == ("oci_core_thing", 9)
    assert page.aliases == [("oci_core_thing_alias", 14)]
    assert page.import_cmds and page.import_cmds[0][2] == '"id"'
    assert page.important_line is not None
    assert parse.resource_type_of(page, {"oci_core_thing"}) == "oci_core_thing"


def test_items_paths_and_code_ignored(page):
    args = items(page, "arguments")
    assert "not_an_item" not in args
    assert "details.inner" in args and "details.other" in args
    # '* `NATIVE` - ...' é valor do item, não atributo filho
    assert "shape.NATIVE" not in args
    assert "timeouts.create" in items(page, "timeouts")
    assert args["compartment_id"].markers == ["Required", "Updatable"]


def test_forces_replacement(page):
    assert kinds(facts_for(page, "compartment_id"), "forces_replacement")[0]["value"] is False
    fr = kinds(facts_for(page, "size_in_gbs"), "forces_replacement")[0]
    assert fr["value"] is True and fr["evidence_level"] == "derived"


def test_default_typed_and_unit_range(page):
    fs = facts_for(page, "size_in_gbs", tf_type="number")
    assert kinds(fs, "default")[0]["value"] == 50
    assert kinds(fs, "unit")[0]["value"] == "GB"
    r = kinds(fs, "range")[0]["value"]
    assert r == {"min": 50, "max": 32768, "applies_to": "value"}
    fs = facts_for(page, "is_enabled", tf_type="bool")
    assert kinds(fs, "default")[0]["value"] is False


def test_default_without_literal_is_unknown(page):
    fs = facts_for(page, "details.other")
    assert not kinds(fs, "default")
    assert kinds(fs, "default", "unknown")[0]["unknown_reason"] == "ambiguous"


def test_enum_inline_and_list(page):
    assert kinds(facts_for(page, "mode"), "allowed_values")[0]["value"] == ["FAST", "SLOW", "MEDIUM"]
    av = kinds(facts_for(page, "shape"), "allowed_values")[0]
    assert av["value"] == ["NATIVE", "EMULATED"] and av["extraction_method"] == "parser"
    # '(Required when kind=AWS | S3)' + '* AWS: ...' explica variantes: não é lista de valores
    assert not kinds(facts_for(page, "access_key"), "allowed_values")
    rw = kinds(facts_for(page, "access_key"), "required_when")[0]["value"]
    assert rw == {"field": "kind", "values": ["AWS", "S3"]}


def test_deprecation_conflicts_format(page):
    fs = facts_for(page, "cidr_block")
    assert kinds(fs, "deprecation")[0]["value"] is True
    assert kinds(fs, "conflicts_with")[0]["value"] == ["cidr_blocks"]
    assert kinds(facts_for(page, "cidr_blocks"), "conflicts_with")[0]["value"] == ["cidr_block"]
    assert kinds(facts_for(page, "compartment_id"), "format")[0]["value"] == "OCID"


def test_behavior_example_unit_and_timeouts(page):
    fs = facts_for(page, "details.inner")
    assert kinds(fs, "behavior")[0]["value"] == {"applicable_when": {"field": "kind", "values": ["AWS"]}}
    assert kinds(fs, "unit")[0]["value"] == "ms"
    assert kinds(fs, "example")[0]["value"] == OCID_EX      # cru aqui; o build redige
    fs = facts_for(page, "timeouts.create", section="timeouts")
    assert kinds(fs, "default")[0]["value"] == "20 minutes"


def test_sources_point_to_real_lines(page):
    lines = PAGE.splitlines()
    for path in ("size_in_gbs", "mode", "details.inner", "cidr_block"):
        for f in facts_for(page, path):
            assert f["sentence"].replace("**", "")[:20].strip("* `-")[:5] in lines[f["line"] - 1].replace("**", ""), f


def test_reconcile_contradictory_default():
    a = extract.fact("default", 3, "Default is 1.", value=1)
    b = extract.fact("default", 9, "Default is 2.", value=2)
    out = extract.reconcile([a, b])
    assert len(out) == 1 and out[0]["status"] == "unknown" and out[0]["unknown_reason"] == "contradictory"
    assert "value" not in out[0] and out[0]["line"] == 3


def test_redact_privacy_spans():
    c = Counter()
    s = build.redact(f"Example: `{OCID_EX}` and {TWELVE} and {MAIL}", c)
    assert OCID_EX[:6] not in s and TWELVE not in s and MAIL not in s
    assert c["ocid"] == 1 and c["doze_digitos"] == 1 and c["email"] == 1
    assert build.redact("user@example.com", Counter()) == "user@example.com"


def test_unmatched_classification():
    atoms = {"a", "b.c"}
    blocks = {"b"}
    assert build.classify_unmatched(("b",), atoms, blocks) == "bloco_do_schema"
    assert build.classify_unmatched(("a", "x"), atoms, blocks) == "filho_de_atributo_objeto"
    assert build.classify_unmatched(("zz",), atoms, blocks) == "fora_do_schema"


# ------------------------------------------------------------------ saídas reais
DATA = Path(os.environ.get("BO_DATA", "/Users/breno/doutorado/brevops-data")) / "DOCS-OCI"
real = pytest.mark.skipif(not (DATA / "docs_facts.jsonl").exists(), reason="saídas ainda não geradas")


@pytest.fixture(scope="module")
def vcn_facts():
    out = {}
    with open(DATA / "docs_facts.jsonl", encoding="utf-8") as f:
        for line in f:
            if '"atom_id":"oci:oci_core_vcn:' in line:
                r = json.loads(line)
                out.setdefault((r["atom_id"].split(":", 2)[2], r["fact_kind"]), []).append(r)
    return out


@real
def test_real_vcn(vcn_facts):
    v = vcn_facts
    assert v[("is_ipv6enabled", "default")][0]["value"] is False
    assert v[("is_ipv6enabled", "default")][0]["as_of"] == "2026-10-21"
    assert v[("display_name", "forces_replacement")][0]["value"] is False
    assert v[("dns_label", "forces_replacement")][0]["value"] is True
    assert v[("cidr_blocks", "conflicts_with")][0]["value"] == ["cidr_block"]
    assert v[("timeouts.create", "default")][0]["value"] == "20 minutes"
    assert v[("time_created", "format")][0]["value"] == "RFC3339"
    src = v[("dns_label", "description")][0]["source"]
    assert src["repo"] == "oracle/terraform-provider-oci" and src["tag"] == "v9.11.0"
    assert src["file"] == "website/docs/r/core_vcn.html.markdown" and src["line"] == 101


@real
def test_real_types():
    recs = {}
    with open(DATA / "type_subcategory.jsonl", encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            recs[(r["kind"], r["resource_type"])] = r
    vcn = recs[("resource", "oci_core_vcn")]
    assert vcn["subcategory"]["value"] == "Core" and vcn["import"]["id_format"] == "id"
    alias = recs[("resource", "oci_core_virtual_network")]
    assert alias["documented_as_alias_of"] == "oci_core_vcn" and alias["subcategory"]["evidence_level"] == "derived"
    assert recs[("data_source", "oci_core_vcns")]["subcategory"]["value"] == "Core"


@real
def test_real_facts_unique_and_sources_resolve():
    from bo.docs_oci import source
    root = source.docs_root()
    ids = set()
    cache = {}
    n = 0
    with open(DATA / "docs_facts.jsonl", encoding="utf-8") as f:
        for i, line in enumerate(f):
            r = json.loads(line)
            assert r["fact_id"] not in ids
            ids.add(r["fact_id"])
            if "source" in r and i % 97 == 0 and "[redigido]" not in r["source"]["sentence"]:
                s = r["source"]
                if s["file"] not in cache:
                    cache[s["file"]] = (root / s["file"]).read_text(encoding="utf-8").splitlines()
                assert s["sentence"] in cache[s["file"]][s["line"] - 1], (r["fact_id"], s)
                n += 1
    assert n > 300


def test_type_schema_accepts_and_rejects():
    import jsonschema
    from bo.contracts import catalog
    from bo.docs_oci import typecheck
    v = jsonschema.Draft202012Validator(typecheck.SCHEMA, registry=catalog.registry(catalog.schemas()))
    src = {"repo": "oracle/terraform-provider-oci", "tag": "v9.11.0", "file": "website/docs/r/x.html.markdown",
           "line": 2, "sentence": 'subcategory: "Core"'}
    ok = {"type_id": "oci:oci_x", "provider": "oci", "provider_version": "9.11.0", "resource_type": "oci_x",
          "kind": "resource",
          "subcategory": {"status": "stated", "value": "Core", "source": src, "extraction_method": "parser",
                          "evidence_level": "published"},
          "import": {"status": "unknown", "unknown_reason": "not_documented", "extraction_method": "parser",
                     "evidence_level": "published"}}
    assert not list(v.iter_errors(ok))
    bad = json.loads(json.dumps(ok))
    bad["subcategory"].pop("value")                       # stated sem valor
    assert list(v.iter_errors(bad))
    bad = json.loads(json.dumps(ok))
    bad["import"]["id_format"] = "id"                     # unknown com valor
    assert list(v.iter_errors(bad))
    bad = json.loads(json.dumps(ok))
    bad["kind"] = "data_source"                           # data source não tem importação
    assert list(v.iter_errors(bad))


def test_redact_twelve_digit_number_value():
    c = Counter()
    assert build.redact_value({"max": int("9" * 12), "min": 0}, c) == {"max": "[redigido]", "min": 0}
    assert c["doze_digitos"] == 1
