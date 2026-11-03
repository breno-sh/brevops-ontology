"""Templates: regeneração idêntica, versões iguais às do PINS, índice do schema fiel à origem."""
import json

from bo.harness.azurerm import build_templates as B
from bo.harness.azurerm import schema as S
from bo.harness.azurerm._common import repo, templates_dir


def test_regeneration_is_identical():
    assert B.main(["--check"]) == 0


def test_versions_follow_pins():
    pins = json.loads((repo() / "universe" / "pins.json").read_text())
    az = next(p for p in pins["providers"] if p["provider"] == "azurerm")
    t = json.loads((templates_dir() / "TEMPLATES.json").read_text())
    assert t["terraform_version"] == pins["terraform"]["version"]
    assert t["provider_version"] == az["version"]
    sch = S.load()
    assert sch.header["source_schema_sha256"] == az["schema_sha256"]
    v = (templates_dir() / "versions.tf").read_text()
    assert f'version = "= {az["version"]}"' in v and f'required_version = "= {pins["terraform"]["version"]}"' in v


def test_index_flags_match_known_schema_facts():
    sch = S.load()
    rg = S.attrs(sch.node("resource", "azurerm_resource_group"))
    assert rg["name"].required and rg["location"].required and not rg["tags"].required
    sa = S.attrs(sch.node("resource", "azurerm_storage_account"))
    assert sa["primary_access_key"].sensitive and not sa["primary_access_key"].configurable
    sub = S.attrs(sch.node("resource", "azurerm_subnet"))
    assert sub["network_security_group_id_wo"].write_only
    vm = S.blocks(sch.node("resource", "azurerm_linux_virtual_machine"))
    assert vm["os_disk"].min_items == 1
    assert sch.node("data", "azurerm_client_config") is not None
    assert sch.header["resource_types"] == len(sch.resources) and sch.header["data_sources"] == len(sch.data)


def test_declared_boilerplate_is_exactly_versions_tf():
    t = json.loads((templates_dir() / "TEMPLATES.json").read_text())
    paths = sorted(b["path"] for b in t["declared_boilerplate"])
    assert paths == ["provider.azurerm.features", "terraform.required_providers.azurerm.source",
                     "terraform.required_providers.azurerm.version", "terraform.required_version"]
