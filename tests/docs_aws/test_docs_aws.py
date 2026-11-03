"""Testes do DOCS-AWS: parser de markdown, sinais textuais, resolução para átomos, consolidação e privacidade.

Os casos usam páginas e schemas sintéticos (nada da cópia baixada); o último bloco confere os arquivos gravados
quando eles existem em $BO_DATA/DOCS-AWS.
"""

import json
import os
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

import pytest

from bo.docs_aws import build, cues as C, mdparse
from bo.docs_aws.resolve import TypeIndex, norm_heading, norm_path, resolve
from bo.repo import privacy
from bo.schema import core as schema_core

PAGE = """---
subcategory: "S3 (Simple Storage)"
layout: "aws"
page_title: "AWS: aws_thing"
---

# Resource: aws_thing

~> **Note:** `aws_alias_thing` is known as `aws_thing`.

## Example Usage

```terraform
resource "aws_thing" "x" {
  * `not_an_item` - inside a fence
}
```

## Argument Reference

* `name` - (Required, Forces new resource) Name of the thing. Must be between 1 and 63 characters in length.
* `size` - (Optional) Size of the volume, in GiB. Defaults to `8`. Valid values between `1` and `16384`.
* `mode` - (Optional) Mode. Valid values: `FAST`, `SLOW`.
* `kind` - (Optional, Default `basic`) Kind of thing.
* `old` - (Optional, **Deprecated**) Old field.
* `rule` - (Optional) Configuration block. See below.

### `rule` Block

The `rule` configuration block supports the following arguments:

* `days` - (Optional) Number of days before expiration.
* `status` - (Required) Status of the rule. Valid values:
  * `Enabled` - on
  * `Disabled` - off

## Timeouts

* `create` - (Default `30m`)

## Attribute Reference

* `arn` - ARN of the thing.

## Import

### Identity Schema

#### Required

* `name` (String) Name.

#### Optional

* `region` (String) Region.

Using `terraform import`, import things using the `name` and `region` separated by a comma (`,`). For example:

```console
% terraform import aws_thing.example name,region
```
"""


def schema_block():
    return {"attributes": {"name": {"type": "string", "required": True},
                           "size": {"type": "number", "optional": True},
                           "mode": {"type": "string", "optional": True},
                           "kind": {"type": "string", "optional": True},
                           "old": {"type": "string", "optional": True, "deprecated": True},
                           "arn": {"type": "string", "computed": True},
                           "id": {"type": "string", "computed": True}},
            "block_types": {"rule": {"nesting_mode": "list", "block": {"attributes": {
                "days": {"type": "number", "optional": True},
                "status": {"type": "string", "required": True}}}},
                "timeouts": {"nesting_mode": "single", "block": {"attributes": {
                    "create": {"type": "string", "optional": True}}}}}}


def type_index():
    ts = schema_core.type_schema("aws", "6.71.0", "aws_thing", schema_block())
    return ts, TypeIndex.build(ts.atoms, ts.blocks)


# ---------------------------------------------------------------- mdparse

def test_parse_frontmatter_title_items_and_fences():
    p = mdparse.parse(PAGE, "website/docs/r/thing.html.markdown")
    assert p.frontmatter["subcategory"] == ("S3 (Simple Storage)", 2)
    assert p.title == ("Resource: aws_thing", 7)
    names = [i.name for i in p.items]
    assert "not_an_item" not in names
    assert names[:6] == ["name", "size", "mode", "kind", "old", "rule"]
    days = next(i for i in p.items if i.name == "days")
    assert (days.hint, days.hint_kind) == ("rule", "intro")
    create = next(i for i in p.items if i.name == "create")
    assert create.section == "timeouts" and create.hint == "timeouts"
    enabled = next(i for i in p.items if i.name == "Enabled")
    assert p.items[enabled.parent].name == "status"
    ident = [i.name for i in p.items if i.section == "identity"]
    assert ident == ["name", "region"]
    assert p.aliases and p.aliases[0][2:] == ("aws_alias_thing", "aws_thing")


# ---------------------------------------------------------------- cues

def test_split_paren_and_flags():
    paren, rest = C.split_paren("(Optional, Forces new resource, Default `x`) Rest of text.")
    assert paren == "Optional, Forces new resource, Default `x`" and rest == "Rest of text."
    cs, unused = C.flag_cues("Optional, Forces new resource, **Deprecated:**, Default `5`, Required if `a` is set, "
                             "Conflicts with `b` and `c`, Redis only", "number")
    kinds = {c.kind: c.value for c in cs}
    assert kinds["forces_replacement"] is True and kinds["deprecation"] is True
    assert kinds["default"] == 5 and kinds["conflicts_with"] == ["b", "c"]
    assert kinds["required_when"].startswith("Required if")
    assert unused == ["Redis only"]


def test_default_literal_typed_described_and_with_unit():
    by = lambda text, t="string": [c for c in C.text_cues(text, t) if c.kind == "default"]  # noqa: E731
    assert by("Defaults to `8`.", "number")[0].value == 8
    assert by("Default is `true`.", "bool")[0].value is True
    assert by("Default is false.", "bool")[0].value is False
    assert by("Defaults to the Region set in the provider configuration.")[0].value == {
        "described": "the Region set in the provider configuration"}
    assert by("The default is 256 MiB and the minimum is 64 MiB.", "number")[0].value == {"described": "256 MiB"}


def test_allowed_values_and_not_mutual_exclusion():
    av = lambda text: [c for c in C.text_cues(text, "string") if c.kind == "allowed_values"]  # noqa: E731
    assert av("Valid values are `A`, `B` and `C`.")[0].value == ["A", "B", "C"]
    assert av("Valid values: Enabled, Disabled.")[0].value == ["Enabled", "Disabled"]
    assert av("Only one of `lambda` or `custom_control` can be specified.") == []
    amb = av("See the API Reference for more information about supported values.")
    assert amb and amb[0].unknown == "ambiguous"
    assert av("The minimum supported value is 21 GiB and the maximum supported value is 200 GiB.") == []


def test_range_value_length_count():
    rg = lambda text: [c.value for c in C.text_cues(text, "number") if c.kind == "range"]  # noqa: E731
    assert rg("Valid values between `1` and `16384`.") == [{"min": 1, "max": 16384, "of": "value"}]
    assert rg("Must be between 1 and 63 characters in length.") == [{"min": 1, "max": 63, "of": "length"}]
    assert rg("Must have a length between 0 and 4096.") == [{"min": 0, "max": 4096, "of": "length"}]
    assert rg("Maximum of 400 instance types.") == [{"max": 400, "of": "count"}]
    assert rg("The minimum supported value is 21 GiB.") == [{"min": 21, "of": "value"}]


def test_unit_primary_beats_incidental():
    un = lambda text: [c.value for c in C.text_cues(text, "number") if c.kind == "unit"]  # noqa: E731
    assert un("Size of the volume, in GiB.") == ["GiB"]
    assert un("Number of days before expiration.") == ["day"]
    assert un("It can take 10 minutes to enable for new tables.") == []
    assert un("Timeout (in seconds) for idle flows. Maximum value is 432000 seconds (5 days).") == ["second"]
    assert un("The default value is 5MB.") == ["MB"]


def test_format_and_forcenew_and_deprecation_text():
    cs = C.text_cues("ARN of the bucket. Changing this forces a new resource to be created.", "string")
    assert ("format", "ARN") in {(c.kind, c.value) for c in cs}
    assert any(c.kind == "forces_replacement" for c in cs)
    assert not [c for c in C.text_cues("Valid values are `X` (deprecated) and `Y`.", "string")
                if c.kind == "deprecation"]
    assert not [c for c in C.text_cues("SHA-1 hashes have been deprecated.", "string") if c.kind == "deprecation"]
    assert [c for c in C.text_cues("This argument is deprecated in favor of `b`.", "string")
            if c.kind == "deprecation"]


def test_sentences_keep_abbreviations_and_ticks():
    s = C.sentences("Use e.g. `a.b`. Then 1.5 GB. Done.")
    assert s == ["Use e.g. `a.b`.", "Then 1.5 GB.", "Done."]


# ---------------------------------------------------------------- resolve

def test_resolution_rules():
    ts, ix = type_index()
    assert resolve(ix, "name", None, "top", None, None).paths == ["name"]
    assert resolve(ix, "days", "rule", "intro", None, None).paths == ["rule.days"]
    assert resolve(ix, "days", None, "top", "rule", None).rule == "R1"
    assert resolve(ix, "create", "timeouts", "text_heading", None, None).paths == ["timeouts.create"]
    r = resolve(ix, "rule", None, "top", None, None)
    assert r.rule == "block" and r.block == "rule"
    assert resolve(ix, "nope", None, "top", None, None).rule == "not_in_schema"
    assert resolve(ix, "x", None, "top", None, "some_object_attr").rule == "nested_child"
    assert norm_path("rule.0.days") == "rule.days" and norm_path("a[0].b") == "a.b"
    assert norm_heading("Source IP Blocks") == "source_ip"


def test_shared_block_is_derived():
    block = {"block_types": {
        "a": {"nesting_mode": "list", "block": {"block_types": {"stmt": {"nesting_mode": "list", "block": {
            "attributes": {"v": {"type": "string", "optional": True}}}}}}},
        "b": {"nesting_mode": "list", "block": {"block_types": {"stmt": {"nesting_mode": "list", "block": {
            "attributes": {"v": {"type": "string", "optional": True}}}}}}}}}
    ts = schema_core.type_schema("aws", "6.71.0", "aws_x", block)
    ix = TypeIndex.build(ts.atoms, ts.blocks)
    r = resolve(ix, "v", "stmt", "tick_heading", None, None)
    assert r.rule == "R3-shared" and r.level == "derived" and r.paths == ["a.stmt.v", "b.stmt.v"]


# ---------------------------------------------------------------- build: consolidação, importação, privacidade

def _cand(kind, value, line=10, unknown=None):
    return {"kind": kind, "value": value, "sentence": "sentença de teste", "line": line, "method": "regex",
            "unknown": unknown}


def test_consolidate_rules():
    red = Counter()
    f = "website/docs/r/x.html.markdown"
    order = [
        ("aws:aws_x:a", [(_cand("default", 1, 3), f, 3, "published"), (_cand("default", 2, 9), f, 9, "published")]),
        ("aws:aws_x:b", [(_cand("range", {"min": 50, "of": "value"}, 4), f, 4, "published"),
                         (_cand("range", {"max": 99, "of": "value"}, 4), f, 4, "published"),
                         (_cand("description", "Texto.", 4), f, 4, "published")]),
        ("aws:aws_x:c", []),
        ("aws:aws_x:d", []),
    ]
    facts = build.consolidate(order, "6.71.0", "2026-10-28", red, shared={"aws:aws_x:d"})
    by = {(x["atom_id"], x["fact_kind"], x["status"]): x for x in facts}
    assert by[("aws:aws_x:a", "default", "unknown")]["unknown_reason"] == "contradictory"
    assert len([x for x in facts if x["atom_id"] == "aws:aws_x:b" and x["fact_kind"] == "range"]) == 2
    assert by[("aws:aws_x:c", "description", "unknown")]["unknown_reason"] == "not_documented"
    assert not [x for x in facts if x["atom_id"] == "aws:aws_x:d"]
    assert len({x["fact_id"] for x in facts}) == len(facts)


def test_import_and_subcategory_records():
    red = Counter()
    p = mdparse.parse(PAGE, "website/docs/r/thing.html.markdown")
    imp = build.import_record(p, red)
    assert imp["status"] == "stated" and imp["supported"] is True
    assert imp["id_attributes"] == ["name", "region"] and imp["separators"] == [","]
    assert imp["identity"] == {"required": ["name"], "optional": ["region"]}
    assert imp["methods"] == ["terraform_import_cli"]
    sc = build.subcategory_record(p, red)
    assert sc["value"] == "S3 (Simple Storage)" and sc["source"]["line"] == 2


def test_redaction_and_fact_key_pass_privacy():
    red = Counter()
    arn = "ar" + "n:aws:iam::" + "".join(str(i % 10) for i in range(1, 13)) + ":role/x"
    out = build.redact(f"Use `{arn}` here", red)
    assert "⟨redigido:" in out and not privacy.scan_text(out, "x")
    keys = [build.fact_key(f"aws:aws_t:a{i}") for i in range(5000)]
    assert all(not re.search(r"\d{12}", k) and len(k) == 10 for k in keys)


def test_fact_rows_validate_against_c03(tmp_path):
    red = Counter()
    f = "website/docs/r/x.html.markdown"
    order = [("aws:aws_x:a", [(_cand("default", 1, 3), f, 3, "published"),
                              (_cand("description", "Texto do atributo.", 3), f, 3, "derived"),
                              (_cand("allowed_values", None, 3, unknown="ambiguous"), f, 3, "published")]),
             ("aws:aws_x:b", [])]
    facts = build.consolidate(order, "6.71.0", "2026-10-28", red, shared=set())
    p = tmp_path / "docs_facts.jsonl"
    p.write_text("".join(json.dumps(x) + "\n" for x in facts), encoding="utf-8")
    r = subprocess.run([sys.executable, "-I", "-m", "bo.contracts.validate", "docs_facts", str(p)],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


# ---------------------------------------------------------------- arquivos gravados (quando existem)

OUT = Path(os.environ.get("BO_DATA", "/Users/breno/doutorado/brevops-data")) / "DOCS-AWS"


@pytest.mark.skipif(not (OUT / "docs_facts.jsonl").exists(), reason="docs_facts.jsonl ainda não gerado")
def test_written_files_are_consistent():
    facts = [json.loads(x) for x in open(OUT / "docs_facts.jsonl", encoding="utf-8")]
    ids = [x["fact_id"] for x in facts]
    assert len(ids) == len(set(ids))
    assert all(x["provider_version"] == "6.71.0" for x in facts)
    assert all(x["source"]["tag"] == "v6.71.0" for x in facts if "source" in x)
    assert all(x.get("as_of") == "2026-10-28" for x in facts if x["fact_kind"] == "default" and
               x["status"] == "stated")
    assert all("model_id" not in x and x["evidence_level"] != "interpreted" for x in facts)
    shared = [json.loads(x) for x in open(OUT / "shared_block_map.jsonl", encoding="utf-8")]
    have = {x["atom_id"] for x in facts}
    assert all(a in have for r in shared for a in r["repeats"])   # repetições também estão em docs_facts
    types = [json.loads(x) for x in open(OUT / "type_subcategory.jsonl", encoding="utf-8")]
    res = [t for t in types if t["kind"] == "resource" and t["in_schema"]]
    assert len(res) == 1746
