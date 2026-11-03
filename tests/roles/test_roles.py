"""Testes do ROLES: cada regra em átomos sintéticos (com rótulos de provedor inventados), casos negativos,
o controle negativo da simetria (código que olha o provedor TEM de ser pego) e as saídas reais."""

import json
import os
from collections import Counter

import pytest

from bo.roles import build, engine, symmetry

RULES = engine.load(build.rules_path())


def atom(provider, rtype, path, tf="string", configurable=True, computed=False, sensitive=False,
         write_only=False, blocks=()):
    req = False
    d = {"atom_id": f"{provider}:{rtype}:{path}", "provider": provider, "provider_version": "1.0.0",
         "resource_type": rtype, "path": path,
         "block_path": [{"block": b, "nesting_mode": m} for b, m in blocks],
         "tf_type": tf, "nesting": blocks[-1][1] if blocks else "none", "required": req,
         "optional": configurable, "computed": computed, "sensitive": sensitive, "deprecated": False,
         "configurable": configurable}
    if write_only:
        d["write_only"] = True
    return d


def fact(atom_id, kind, value, n=1):
    return {"fact_id": f"DF-t-{abs(hash((atom_id, kind, n))) % 10**8}", "fact_kind": kind, "status": "stated",
            "value": value}


# um "mundo" sintético com dois provedores inventados e tipos que se citam
WORLD = [
    atom("px", "px_store_bucket", "id", computed=True),
    atom("px", "px_store_bucket", "bucket"),
    atom("px", "px_store_bucket", "tags", tf=["map", "string"]),
    atom("px", "px_store_bucket", "tags_all", tf=["map", "string"], configurable=False, computed=True),
    atom("px", "px_store_bucket", "arn", configurable=False, computed=True),
    atom("px", "px_store_bucket", "created_at", configurable=False, computed=True),
    atom("px", "px_store_bucket", "start_time"),
    atom("px", "px_store_bucket_policy", "bucket"),
    atom("px", "px_store_bucket_policy", "policy"),
    atom("px", "px_store_object", "content"),
    atom("px", "px_store_object", "content_type"),
    atom("px", "px_net_subnet", "name"),
    atom("px", "px_net_subnet", "vpc_id"),
    atom("px", "px_net_subnet", "owner_id", configurable=False, computed=True),
    atom("px", "px_net_subnet", "security_group_ids", tf=["set", "string"]),
    atom("px", "px_net_subnet", "secondary.name", blocks=[("secondary", "list")]),
    atom("px", "px_net_subnet", "rule.id", blocks=[("rule", "list")]),
    atom("px", "px_net_vpc", "name"),
    atom("px", "px_db_instance", "identifier"),
    atom("px", "px_db_instance", "master_password"),
    atom("px", "px_db_instance", "password_length", tf="number"),
    atom("px", "px_db_instance", "password_enabled", tf="bool"),
    atom("px", "px_db_instance", "secret_arn"),
    atom("px", "px_db_instance", "token_wo", write_only=True),
    atom("px", "px_db_instance", "pin_wo", write_only=True),
    atom("px", "px_db_instance", "client_id", sensitive=True),
    atom("px", "px_db_instance", "role"),
    atom("px", "px_iam_role", "name"),
    atom("px", "px_vm_instance", "user_data"),
    atom("px", "px_vm_instance", "user_data_replace_on_change", tf="bool"),
    atom("px", "px_vm_instance", "metadata", tf=["map", "string"]),
    atom("px", "px_vm_instance", "environment.variables", tf=["map", "string"], blocks=[("environment", "list")]),
    atom("px", "px_vm_instance", "tag.key", blocks=[("tag", "set")]),
    atom("px", "px_vm_instance", "tag.propagate_at_launch", tf="bool", blocks=[("tag", "set")]),
    atom("px", "px_vm_instance", "private_key.content", blocks=[("private_key", "list")]),
    atom("px", "px_vm_instance", "network_tags", tf=["set", "string"]),
    atom("px", "px_vm_instance", "propagate_tags"),
    atom("px", "px_vm_instance", "launch_template.id", blocks=[("launch_template", "list")]),
    atom("qy", "qy_secret_vault_secret", "secret_id"),
    atom("qy", "qy_secret_vault_secret", "time_created", configurable=False, computed=True),
    atom("qy", "qy_secret_vault_secret", "time_of_last_rotation", configurable=False, computed=True),
    atom("qy", "qy_secret_vault_secret", "self_link", configurable=False, computed=True),
    atom("qy", "qy_secret_vault_secret", "vault_ocid"),
    atom("qy", "qy_secret_vault_secret", "labels", tf=["map", "string"]),
    atom("qy", "qy_secret_vault_secret", "name", configurable=False, computed=True),
    atom("qy", "qy_secret_vault_secret", "uid", configurable=False, computed=True),
    atom("qy", "qy_secret_vault_secret", "update_stamp", configurable=False, computed=True),
    atom("qy", "qy_secret_vault_secret", "target"),
    atom("qy", "qy_secret_vault_secret", "env", tf=["map", "string"]),
    atom("qy", "qy_secret_vault_secret", "settings", tf=["map", "string"]),
    atom("qy", "qy_vault", "name"),
    atom("qy", "qy_maint_assignment_vault", "vault_id"),
    atom("qy", "qy_store_thing", "vault_name"),
    atom("qy", "qy_store_thing", "kind", configurable=False, computed=True),
]

FACTS = {
    "px:px_store_bucket:bucket": [fact("px:px_store_bucket:bucket", "description", "Name of the bucket.")],
    "px:px_store_bucket_policy:bucket": [fact("px:px_store_bucket_policy:bucket", "description",
                                              "Name of the bucket to which to apply the policy.")],
    "px:px_store_bucket_policy:policy": [fact("px:px_store_bucket_policy:policy", "description",
                                              "The text of the policy.")],
    "px:px_db_instance:role": [fact("px:px_db_instance:role", "description",
                                    "Resource name (ARN) of the execution role used by the instance.")],
    "px:px_vm_instance:metadata": [fact("px:px_vm_instance:metadata", "description",
                                        "Key/value pairs; the user_data key is passed to cloud-init.")],
    "px:px_vm_instance:launch_template.id": [fact("px:px_vm_instance:launch_template.id", "description",
                                                  "ID of the launch template.")],
    "qy:qy_secret_vault_secret:update_stamp": [fact("qy:qy_secret_vault_secret:update_stamp", "format",
                                                    "RFC3339")],
    "qy:qy_secret_vault_secret:target": [fact("qy:qy_secret_vault_secret:target", "format",
                                              {"aspect": "identifier", "template": "{{x}}"})],
    "qy:qy_secret_vault_secret:settings": [fact("qy:qy_secret_vault_secret:settings", "description",
                                                "Environment variables passed to the function.")],
    "qy:qy_store_thing:kind": [dict(fact("qy:qy_store_thing:kind", "format", "RFC3339"), status="unknown")],
}

EXPECTED = {
    "px:px_store_bucket:id": ("IDENTIFIER", "ROLE-IDENTIFIER-TOP-ID"),
    "px:px_store_bucket:bucket": ("NAME", "ROLE-NAME-OWN-NOUN"),
    "px:px_store_bucket:tags": ("TAG", "ROLE-TAG-MAP"),
    "px:px_store_bucket:tags_all": ("TAG", "ROLE-TAG-MAP"),
    "px:px_store_bucket:arn": ("IDENTIFIER", "ROLE-IDENTIFIER-SELF"),
    "px:px_store_bucket:created_at": ("TIMESTAMP", "ROLE-TIMESTAMP-NAME"),
    "px:px_store_bucket:start_time": ("CONFIG", "ROLE-DEFAULT-CONFIG"),
    "px:px_store_bucket_policy:bucket": ("REFERENCE", "ROLE-REFERENCE-NOUN-TYPE-DOCS"),
    "px:px_store_bucket_policy:policy": ("CONFIG", "ROLE-DEFAULT-CONFIG"),
    "px:px_store_object:content": ("SECRET", "ROLE-WITHHELD-OBJECT-CONTENT"),
    "px:px_store_object:content_type": ("CONFIG", "ROLE-DEFAULT-CONFIG"),
    "px:px_net_subnet:name": ("NAME", "ROLE-NAME-LEAF"),
    "px:px_net_subnet:vpc_id": ("REFERENCE", "ROLE-REFERENCE-ID-TAIL"),
    "px:px_net_subnet:owner_id": ("REFERENCE", "ROLE-REFERENCE-COMPUTED-ID"),
    "px:px_net_subnet:security_group_ids": ("REFERENCE", "ROLE-REFERENCE-ID-TAIL"),
    "px:px_net_subnet:secondary.name": ("CONFIG", "ROLE-DEFAULT-CONFIG"),
    "px:px_net_subnet:rule.id": ("CONFIG", "ROLE-DEFAULT-CONFIG"),
    "px:px_net_vpc:name": ("NAME", "ROLE-NAME-LEAF"),
    "px:px_iam_role:name": ("NAME", "ROLE-NAME-LEAF"),
    "px:px_db_instance:identifier": ("NAME", "ROLE-NAME-LEAF"),
    "px:px_db_instance:master_password": ("SECRET", "ROLE-SECRET-NAME"),
    "px:px_db_instance:password_length": ("CONFIG", "ROLE-DEFAULT-CONFIG"),
    "px:px_db_instance:password_enabled": ("CONFIG", "ROLE-DEFAULT-CONFIG"),
    "px:px_db_instance:secret_arn": ("REFERENCE", "ROLE-REFERENCE-ID-TAIL"),
    "px:px_db_instance:token_wo": ("SECRET", "ROLE-SECRET-NAME"),
    "px:px_db_instance:pin_wo": ("SECRET", "ROLE-SECRET-WRITEONLY"),
    "px:px_db_instance:client_id": ("SECRET", "ROLE-SECRET-SENSITIVE"),
    "px:px_db_instance:role": ("REFERENCE", "ROLE-REFERENCE-NOUN-TYPE-DOCS"),
    "px:px_vm_instance:user_data": ("SECRET", "ROLE-WITHHELD-USERDATA"),
    "px:px_vm_instance:user_data_replace_on_change": ("CONFIG", "ROLE-DEFAULT-CONFIG"),
    "px:px_vm_instance:metadata": ("SECRET", "ROLE-WITHHELD-USERDATA-DOCS"),
    "px:px_vm_instance:environment.variables": ("SECRET", "ROLE-WITHHELD-ENV-BLOCK"),
    "px:px_vm_instance:tag.key": ("TAG", "ROLE-TAG-BLOCK"),
    "px:px_vm_instance:tag.propagate_at_launch": ("CONFIG", "ROLE-DEFAULT-CONFIG"),
    "px:px_vm_instance:private_key.content": ("SECRET", "ROLE-SECRET-BLOCK-CONTENT"),
    "px:px_vm_instance:network_tags": ("CONFIG", "ROLE-DEFAULT-CONFIG"),
    "px:px_vm_instance:propagate_tags": ("CONFIG", "ROLE-DEFAULT-CONFIG"),
    "px:px_vm_instance:launch_template.id": ("REFERENCE", "ROLE-REFERENCE-DOCS-ID-OF"),
    "qy:qy_secret_vault_secret:secret_id": ("NAME", "ROLE-NAME-OWN"),
    "qy:qy_secret_vault_secret:time_created": ("TIMESTAMP", "ROLE-TIMESTAMP-NAME"),
    "qy:qy_secret_vault_secret:time_of_last_rotation": ("TIMESTAMP", "ROLE-TIMESTAMP-NAME-FIRST"),
    "qy:qy_secret_vault_secret:self_link": ("IDENTIFIER", "ROLE-IDENTIFIER-SELF"),
    "qy:qy_secret_vault_secret:vault_ocid": ("REFERENCE", "ROLE-REFERENCE-ID-TAIL"),
    "qy:qy_secret_vault_secret:labels": ("TAG", "ROLE-TAG-MAP"),
    "qy:qy_secret_vault_secret:name": ("IDENTIFIER", "ROLE-IDENTIFIER-NAME-COMPUTED"),
    "qy:qy_secret_vault_secret:uid": ("IDENTIFIER", "ROLE-IDENTIFIER-SELF"),
    "qy:qy_secret_vault_secret:update_stamp": ("TIMESTAMP", "ROLE-TIMESTAMP-DOCS"),
    "qy:qy_secret_vault_secret:target": ("REFERENCE", "ROLE-REFERENCE-DOCS-FORMAT"),
    "qy:qy_secret_vault_secret:env": ("SECRET", "ROLE-WITHHELD-ENV"),
    "qy:qy_secret_vault_secret:settings": ("SECRET", "ROLE-WITHHELD-ENV-DOCS"),
    "qy:qy_vault:name": ("NAME", "ROLE-NAME-LEAF"),
    # vault é sufixo do tipo, mas é exatamente o nome de OUTRO tipo: aponta para ele
    "qy:qy_maint_assignment_vault:vault_id": ("REFERENCE", "ROLE-REFERENCE-ID-TAIL"),
    "qy:qy_store_thing:vault_name": ("REFERENCE", "ROLE-REFERENCE-NAME-TAIL-TYPE"),
    # fato com status unknown não conta
    "qy:qy_store_thing:kind": ("CONFIG", "ROLE-DEFAULT-CONFIG"),
}


def run(atoms=WORLD, facts=FACTS):
    return {r["atom_id"]: r for r, _ in build.classify_all(atoms, facts, RULES)}


def test_every_synthetic_atom_gets_expected_role():
    got = run()
    assert set(EXPECTED) == {a["atom_id"] for a in WORLD}
    bad = {k: (got[k]["role"], got[k]["rule_id"]) for k, v in EXPECTED.items()
           if (got[k]["role"], got[k]["rule_id"]) != v}
    assert not bad, bad


def test_every_rule_is_exercised_by_the_synthetic_world():
    fired = {r["rule_id"] for r in run().values()}
    assert {r.id for r in RULES.rules} - fired == set()


def test_docs_rules_cite_the_fact_and_schema_rules_do_not():
    got = run()
    r = got["px:px_store_bucket_policy:bucket"]
    assert r["evidence"] == [{"level": "derived", "ref": FACTS["px:px_store_bucket_policy:bucket"][0]["fact_id"]}]
    assert "evidence" not in got["px:px_net_subnet:vpc_id"]


def test_rules_file_is_coherent_and_last_rule_is_default():
    assert engine.validate(RULES) == []
    assert RULES.rules[-1].id == "ROLE-DEFAULT-CONFIG" and RULES.rules[-1].when == {}
    assert RULES.rules[0].role == "SECRET"


def test_validate_rejects_unknown_condition_and_role(tmp_path):
    raw = dict(RULES.raw)
    raw["rules"] = [{"id": "ROLE-X", "role": "LABEL", "text": "x", "when": {"provider_is": "x"}},
                    {"id": "ROLE-DEFAULT-CONFIG", "role": "CONFIG", "text": "padrão", "when": {}}]
    import yaml
    p = tmp_path / "r.yaml"
    p.write_text(yaml.safe_dump(raw, allow_unicode=True), encoding="utf-8")
    with pytest.raises(ValueError) as e:
        engine.load(p)
    assert "LABEL" in str(e.value) and "provider_is" in str(e.value)


def test_word_hits_catch_provider_prefix_but_not_substrings():
    assert symmetry.word_hits("lexicon: [px_bucket]", {"px"}) == ["px"]
    assert symmetry.word_hits("id_tails: [ocid, ocids]", {"oci"}) == []


def test_relabel_invariance_holds_for_neutral_code():
    base = symmetry.comparable(build.classify_all(WORLD, FACTS, RULES))
    a2, f2, back = symmetry.relabel(WORLD, FACTS, {"px": "qy", "qy": "px"})
    got = symmetry.comparable(build.classify_all(a2, f2, RULES), back)
    assert got == base


def test_relabel_control_catches_code_that_looks_at_provider(monkeypatch):
    """Controle negativo: se o motor decidisse pelo provedor, a permutação TEM de acusar."""
    base = symmetry.comparable(build.classify_all(WORLD, FACTS, RULES))
    real = engine.classify

    def biased(x, r):
        rule, used = real(x, r)
        if x.provider == "px" and rule.role == "CONFIG":
            return next(z for z in r.rules if z.role == "SECRET"), used
        return rule, used

    monkeypatch.setattr(engine, "classify", biased)
    a2, f2, back = symmetry.relabel(WORLD, FACTS, {"px": "qy", "qy": "px"})
    got = symmetry.comparable(build.classify_all(a2, f2, RULES), back)
    assert got != base


def test_kind_normalization():
    assert engine.kind("string") == "string"
    assert engine.kind(["set", "string"]) == "coll_string"
    assert engine.kind(["list", ["object", {"a": "string"}]]) == "coll_other"
    assert engine.kind(["map", "string"]) == "map_string"
    assert engine.kind(["object", {"a": "string"}]) == "object"


def test_type_forms_and_own_suffixes():
    assert engine.own_suffixes(["store", "bucket", "policy"]) == {"policy", "bucket_policy", "store_bucket_policy"}
    assert engine.type_forms(["kms", "crypto", "key"]) == {"kms_crypto_key", "crypto_key", "kms_key"}


REAL = build.out_path()


@pytest.mark.skipif(not REAL.exists(), reason="roles.jsonl ainda não gerado")
def test_real_output_one_role_per_atom_and_known_rules():
    ids = set()
    rules = {r.id: r.role for r in RULES.rules}
    c = Counter()
    with open(REAL, encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            assert r["atom_id"] not in ids
            ids.add(r["atom_id"])
            assert rules[r["rule_id"]] == r["role"]
            c[r["atom_id"].split(":", 1)[0]] += 1
    n = Counter()
    for _, ap, _ in build.input_pairs():
        with open(ap, encoding="utf-8") as f:
            for line in f:
                n[json.loads(line)["provider"]] += 1
    assert c == n and len(c) == 4


@pytest.mark.skipif(not (build.results_dir() / "by_provider.json").exists(), reason="by_provider ainda não gerado")
def test_by_provider_counts_add_up():
    d = json.loads((build.results_dir() / "by_provider.json").read_text(encoding="utf-8"))
    for p, roles in d["data"]["roles"].items():
        assert sum(roles.values()) == d["data"]["atoms"][p]
    for m in d["metrics"]:
        oc = m["operational_coverage"]
        assert oc["lower"] == oc["est"] == oc["upper"]
    assert os.environ.get("BO_DATA") is None or str(REAL).startswith(os.environ["BO_DATA"])
