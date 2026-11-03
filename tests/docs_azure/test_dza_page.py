"""Página sintética: seções, linhas, resolução de bloco pela árvore da página, notas, import e redação."""
from collections import Counter

from bo.docs_azure import build as B
from bo.docs_azure import markdown as MD
from bo.schema import core

# valores falsos montados em tempo de execução (o código-fonte não os contém, por causa do privacy_lint)
D12 = "".join(str(i % 10) for i in range(1, 13))
SUB = "-".join(["12345678", "1234", "1234", "1234", D12])
PAGE = """---
subcategory: "Storage"
page_title: "Azure Resource Manager: azurerm_thing"
---

# azurerm_thing

## Arguments Reference

* `name` - (Required) The name. Changing this forces a new resource to be created.

* `size_in_gb` - (Optional) The size. Possible values are between `1` and `10`.

* `alpha` - (Optional) An `alpha` block as defined below.

* `beta` - (Optional) A `beta` block as defined below.

---

An `alpha` block supports the following:

* `policy` - (Optional) A `policy` block as defined below.

~> **Note:** This must be set when `name` is long.

---

A `policy` block supports the following:

* `days` - (Optional) Number of days. Defaults to `7`.

### Timeouts

* `create` - (Defaults to 30 minutes) Used when creating the Thing.

## Import

Things can be imported using the `resource id`, e.g.

```shell
terraform import azurerm_thing.example /subscriptions/@SUB@/resourceGroups/rg1/providers/Microsoft.X/things/t1
```
""".replace("@SUB@", SUB)

BLOCK = {
    "attributes": {"name": {"type": "string", "required": True}, "size_in_gb": {"type": "number", "optional": True},
                   "id": {"type": "string", "computed": True}},
    "block_types": {
        "alpha": {"nesting_mode": "list", "block": {"block_types": {"policy": {"nesting_mode": "list", "block": {
            "attributes": {"days": {"type": "number", "optional": True}}}}}}},
        "beta": {"nesting_mode": "list", "block": {"block_types": {"policy": {"nesting_mode": "list", "block": {
            "attributes": {"days": {"type": "number", "optional": True}}}}}}},
        "timeouts": {"nesting_mode": "single", "block": {"attributes": {"create": {"type": "string",
                                                                                   "optional": True}}}},
    },
}

META = {"repo": "hashicorp/terraform-provider-azurerm", "tag": "v9.9.9", "version": "9.9.9", "as_of": "2026-10-29"}


def setup(tmp_path):
    p = tmp_path / "thing.html.markdown"
    p.write_text(PAGE, encoding="utf-8")
    pg = MD.parse(p, "website/docs/r/thing.html.markdown")
    ti = B.TypeIndex(core.type_schema("azurerm", "9.9.9", "azurerm_thing", BLOCK))
    return pg, ti


def test_parse_front_sections_lines(tmp_path):
    pg, _ = setup(tmp_path)
    assert pg.front["subcategory"] == ("Storage", 2)
    assert pg.h1 == ("azurerm_thing", 6)
    kinds = [(s.kind, s.blocks) for s in pg.sections]
    assert kinds == [("arg", []), ("arg", ["alpha"]), ("arg", ["policy"]), ("timeouts", ["timeouts"])]
    assert pg.sections[0].items[0].line == 10
    assert pg.imports[0].address == "azurerm_thing.example"


def test_shared_name_resolved_by_page_tree(tmp_path):
    pg, ti = setup(tmp_path)
    st = Counter()
    res = B.resolve_sections(pg, ti, st)
    pol = pg.sections[2]
    paths, derived = res[id(pol)]
    assert paths == {("alpha", "policy")} and derived is False      # beta.policy não é citado pela página


def test_facts_and_unknowns(tmp_path):
    pg, ti = setup(tmp_path)
    red = B.Redactor()
    facts = B.Facts(META, red)
    documented, units = set(), set()
    B.page_facts(pg, ti, facts, Counter(), documented, units)
    recs = facts.records()
    by = {(r["atom_id"], r["fact_kind"]): r for r in recs}
    assert by[("azurerm:azurerm_thing:name", "forces_replacement")]["source"]["line"] == 10
    assert by[("azurerm:azurerm_thing:alpha.policy.days", "default")]["value"] == 7
    assert by[("azurerm:azurerm_thing:alpha.policy.days", "default")]["as_of"] == "2026-10-29"
    assert ("azurerm:azurerm_thing:beta.policy.days", "description") not in by
    assert by[("azurerm:azurerm_thing:size_in_gb", "unit")]["evidence_level"] == "derived"
    assert by[("azurerm:azurerm_thing:timeouts.create", "default")]["value"] == "30 minutes"
    assert "azurerm:azurerm_thing:id" not in documented


def test_import_id_redacted_and_subcategory(tmp_path):
    pg, _ = setup(tmp_path)
    red = B.Redactor()
    rec = B.type_record(pg, "azurerm_thing", META, red, True)
    assert rec["subcategory"]["value"] == "Storage" and rec["subcategory"]["source"]["line"] == 2
    v = rec["import"]["value"][0]
    assert v.startswith("/subscriptions/{subscriptionId}/resourceGroups/rg1")
    assert "12345678-1234" not in rec["import"]["source"]["sentence"]


def test_redactor_removes_what_privacy_lint_flags():
    from bo.repo import privacy
    red = B.Redactor()
    guid = "-".join(["0" * 8, "0" * 4, "0" * 4, "0" * 4, "0" * 12])
    s = red.text(f"id {guid} and acct {D12} and x" + "@" + "corp.com.br")
    assert not privacy.scan_text(s, "x")
    assert "{guid}" in s
    bad = "/subscriptions/" + "0" * 8 + "-0000-0000-0000-" + "0" * 11 + "/x"     # GUID malformado da doc
    assert red.text(bad) == "/subscriptions/{subscriptionId}/x"
