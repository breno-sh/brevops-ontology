"""Funções puras do DRIFT: nomes, pares por menção, bloco mudado, guias e análise em memória."""
import pytest

from bo.drift import common, core, guides
from conftest import atom


@pytest.mark.parametrize("a,b,ok", [
    ("name", "db_name", True),
    ("enable_auto_scaling", "auto_scaling_enabled", True),
    ("dns_zone_id", "dns_zone_ids", True),
    ("process_not_allowed", "processes_not_allowed", True),
    ("registries", "registry", True),
    ("local_authentication_disabled", "local_authentication_enabled", False),
    ("x.azure_keyvault_secrets_provider", "key_vault_secrets_provider", True),
    ("data_factory_name", "data_factory_id", False),
    ("log_group_name", "log_destination", False),
    ("path", "id", False),
    ("name", "name", False),
])
def test_lexically_related(a, b, ok):
    assert core.lexically_related(a, b) is ok


def test_mention_pairs_atributo_e_bloco():
    assert core.mention_pairs("cfg.name", "cfg.db_name", "name", "db_name")
    assert not core.mention_pairs("cfg.name", "other.db_name", "name", "db_name")
    # renome de bloco: os filhos levam o mesmo sufixo
    assert core.mention_pairs("proxy.host", "gateway.host", "proxy", "gateway")
    assert not core.mention_pairs("proxy.host", "gateway.port", "proxy", "gateway")
    assert core.mention_pairs("a.old.leaf", "new.leaf", "a.old", "new")


def test_changed_block():
    b = [{"block": "d", "max_items": 1, "nesting_mode": "list"}, {"block": "c", "nesting_mode": "list"}]
    a = [{"block": "d", "max_items": 1, "nesting_mode": "list"}, {"block": "c", "nesting_mode": "set"}]
    assert core.changed_block(b, a) == "d.c"


def test_semver():
    assert common.semver_key("5.10.0") > common.semver_key("5.9.3")
    assert common.major("6.71.0") == 6


@pytest.mark.parametrize("name,major", [
    ("version-5-upgrade.html.markdown", 5), ("version_8_upgrade.html.markdown", 8),
    ("4.0-upgrade-guide.html.markdown", 4), ("terraform_version_12_upgrade.html.markdown", None),
    ("index.html.markdown", None)])
def test_guide_major(name, major):
    assert guides.guide_major(name) == major


def test_parse_guide_secoes(work):
    p = work / "version-3-upgrade.html.markdown"
    p.write_text("# T\n## Resource: `google_thing`\n### Field moved\n`a_b` has been renamed to `b`.\n"
                 "`google_thing.x` replaced by `y`.\n## Data Source: `google_thing`\n`c` renamed to `d`.\n"
                 "## Provider\n`e` renamed to `f`.\n", encoding="utf-8")
    ss = guides.parse_guide("google", p, 3, "hashicorp/terraform-provider-google", "v8.9.0", "website/x")
    got = [(s.line, s.mentions, s.cue, sorted(s.resources)) for s in ss]
    assert got == [(4, ("a_b", "b"), "rename", ["google_thing"]),
                   (5, ("x", "y"), "replace", ["google_thing"])]


def _snap(atoms):
    return core.snapshot(atoms, "oci")


def test_analyze_eventos_e_ids_deterministicos():
    v1 = [atom("oci", "oci_t", "a"), atom("oci", "oci_t", "b", tf_type=["list", "string"])]
    v2 = [atom("oci", "oci_t", "a", required=True, optional=False), atom("oci", "oci_t", "c")]
    s1, m1 = _snap(v1)
    s2, m2 = _snap(v2)
    r = core.analyze("oci", ["1.0.0", "2.0.0"], [s1, s2], [m1, m2])
    kinds = sorted((e["event_type"], e.get("atom_id", ""), (e.get("change") or {}).get("field", ""))
                   for e in r.events)
    assert kinds == [("addition", "oci:oci_t:c", ""), ("contract_change", "oci:oci_t:a", "optional"),
                     ("contract_change", "oci:oci_t:a", "required"), ("removal", "oci:oci_t:b", "")]
    r2 = core.analyze("oci", ["1.0.0", "2.0.0"], [s1, s2], [m1, m2])
    assert [e["event_id"] for e in r.events] == [e["event_id"] for e in r2.events]
    recs = {x["atom_id"]: x for x in core.atom_history_records(r)}
    assert recs["oci:oci_t:b"]["history"][0]["tf_type"] == ["list", "string"]
    assert recs["oci:oci_t:b"]["first_seen"] == recs["oci:oci_t:b"]["last_seen"] == "1.0.0"


def test_snapshot_recusa_atomo_repetido_ou_de_outro_provider():
    with pytest.raises(ValueError):
        core.snapshot([atom("oci", "oci_t", "a"), atom("oci", "oci_t", "a")], "oci")
    with pytest.raises(ValueError):
        core.snapshot([atom("aws", "aws_t", "a")], "oci")


def test_analyze_recusa_versoes_fora_de_ordem():
    s, m = _snap([atom("oci", "oci_t", "a")])
    with pytest.raises(ValueError):
        core.analyze("oci", ["2.0.0", "1.0.0"], [s, s], [m, m])
