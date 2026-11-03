"""Compromissos do REQUIREMENTS que listam o GRAIN como consumidor, reproduzidos nos mundos sintéticos."""

import copy
import json

from bo.grain import battery as B
from bo.grain import fixtures as F
from bo.grain import instance as I
from bo.grain import rules as R
from bo.grain import schema as S
from bo.grain.evidence import FixtureAdapter

RS = R.load()
W = B.all_worlds()


def occs(world, cfg, ev=None):
    return I.decompose_config(world["configs"][cfg], FixtureAdapter(ev or world["evidence"]),
                              F.schema_blocks(world["schema"]), RS)


def dec(world, ev=None):
    return B.run_schema(W[world], RS, ev).decisions


# ---- contêiner e namespace

def test_cmt_bkt_p01_facet_same_inline_or_separate():
    d = dec("bucket")
    for cid in ("a_bucket.versioning", "a_bucket_versioning"):
        assert d[cid].grain == "FACET" and d[cid].owner["targets"] == ["a_bucket"]
        assert d[cid].scope == {"kind": "parent", "target": "a_bucket"}
    assert d["a_bucket"].grain == "ENTITY"


def test_cmt_bkt_p02_namespace_setting_scope_is_namespace_containers():
    d = dec("namespace")["e_account.versioning"]
    assert d.grain == "FACET" and d.owner["targets"] == ["e_account"]
    assert d.scope == {"kind": "container", "target": "e_account"}
    o = [x for x in occs(W["namespace"], "resolved") if x.label == "versioning"]
    conts = [x for x in occs(W["namespace"], "resolved") if x.label == "object container"]
    assert len(o) == 1 and len(conts) == 2
    assert all(o[0].parent != c.occ_id for c in conts)  # não é faceta de nenhum contêiner


def test_cmt_bkt_p03_container_component_of_namespace():
    d = dec("namespace")
    assert d["e_container"].grain == "COMPONENT" and d["e_container"].parent == "e_account"
    assert d["e_container"].lifecycle["kind"] == "parent"


def test_cmt_bkt_n03_owner_diverging_from_evidence_rejected():
    res = B.run_schema(W["namespace"], RS)
    units, _ = S.to_c19(res)
    assert S.verify_units(units, res) == []
    bad = copy.deepcopy([u for u in units if u["unit_id"].endswith("e_account.versioning")])
    bad[0]["owner"] = {"kind": "parent", "ref": "CU-provider_e-e_container"}
    errs = S.verify_units(bad, res)
    assert errs and "owner" in errs[0]


def test_cmt_bkt_u02_unresolved_container_reference():
    o = [x for x in occs(W["namespace"], "unresolved") if x.label == "retention"]
    assert len(o) == 1 and o[0].grain == "UNKNOWN" and "owner" in o[0].missing


def test_cmt_lc_u01_no_lifecycle_evidence():
    d = dec("namespace")["e_orphan_setting"]
    assert d.grain == "UNKNOWN" and d.missing == ["lifecycle_controller"]


# ---- interface de rede

def _count(oc, label):
    return sum(1 for o in oc if o.label == label)


def test_cmt_nic_p01_p02_counts():
    for cfg, n in (("inline_2", 2), ("separate_2", 2), ("inline_1", 1), ("separate_1", 1)):
        oc = occs(W["nic"], cfg)
        assert _count(oc, "compute instance") + _count(oc, "network interface") == n + 1, cfg
        assert _count(oc, "interface attachment") == n, cfg
        assert all(o.grain == "BINDING" for o in oc if o.label == "interface attachment")


def test_cmt_nic_p03_second_nic_only_adds():
    for pk in ("inline", "separate"):
        one = set(I.canonical_rows(occs(W["nic"], f"{pk}_1")))
        two = set(I.canonical_rows(occs(W["nic"], f"{pk}_2")))
        assert one < two
        assert len(two - one) == 2  # uma interface e uma anexação


def test_cmt_nic_p04_inline_equals_separate():
    for n in (1, 2):
        assert I.canonical_rows(occs(W["nic"], f"inline_{n}")) == I.canonical_rows(occs(W["nic"], f"separate_{n}"))


def test_cmt_nic_p05_reordered_blocks_same_occurrence_keys():
    a = I.canonical_rows(occs(W["nic"], "inline_2"))
    b = I.canonical_rows(occs(W["nic"], "inline_2_reordered"))
    assert a == b


def test_cmt_nic_n03_interface_not_counted_as_instance():
    oc = occs(W["nic"], "inline_2")
    assert _count(oc, "compute instance") == 1


def test_cmt_nic_u02_symbolic_attachment_reference():
    o = [x for x in occs(W["nic"], "separate_unresolved") if x.label == "interface attachment"]
    assert len(o) == 1 and o[0].grain == "UNKNOWN" and "identity" in o[0].missing


# ---- firewall

def test_cmt_fw_p01_rule_component_inline_or_separate():
    d = dec("firewall")
    assert d["c_rule_set"].grain == "ENTITY"
    for cid in ("c_rule_set.rule", "c_rule"):
        assert d[cid].grain == "COMPONENT" and d[cid].parent == "c_rule_set" and d[cid].identity.anonymous
    rows = {k: I.canonical_rows(occs(W["firewall"], k)) for k in ("inline", "separate", "inline_reordered",
                                                                  "separate_reordered", "inline_cidr_alias")}
    assert len({json.dumps(v) for v in rows.values()}) == 1


def test_rule_with_two_references_owned_by_set_is_component_not_binding():
    d = dec("firewall")["c_rule_from_set"]
    assert d.grain == "COMPONENT" and d.identity.cls == "REF_TUPLE_PLUS"


# ---- acesso

def test_cmt_iam_p01_assignment_is_binding_of_three():
    d = dec("iam")["d_assignment"]
    assert d.grain == "BINDING" and set(d.endpoints) == {"scope", "permission_set", "principal"}
    o = [x for x in occs(W["iam"], "assignment") if x.grain == "BINDING"]
    ends = {x.occ_id for x in occs(W["iam"], "assignment") if x.grain == "ENTITY"}
    assert len(o) == 1 and set(o[0].endpoints.values()) == ends and o[0].occ_id not in ends


def test_cmt_lc_n01_binding_does_not_control_endpoints():
    d = dec("iam")
    for cid in ("d_principal", "d_role", "d_project"):
        assert d[cid].lifecycle["kind"] == "self" and d[cid].parent is None


# ---- banco

def test_cmt_db_p03_shared_parameter_set_is_entity():
    d = dec("db")["f_param_group"]
    assert d.grain == "ENTITY"
    oc = occs(W["db"], "db")
    ps = [o for o in oc if o.label == "db parameter set"]
    assert len(ps) == 1 and not any(o.parent == ps[0].occ_id for o in oc)


def test_cmt_db_p04_backup_retention_facet_snapshot_entity():
    d = dec("db")
    assert d["f_db_instance.backup"].grain == "FACET" and d["f_db_instance.backup"].parent == "f_db_instance"
    assert d["f_snapshot"].grain == "ENTITY" and d["f_snapshot"].lifecycle["kind"] == "self"


# ---- faceta com vários donos

def test_multi_owner_facet_goes_to_binding():
    d = B.run_schema(W["multi_owner"], RS).decisions
    assert d["g_peering"].grain == "BINDING"
    assert d["g_exchange_setting"].grain == "FACET" and d["g_exchange_setting"].parent == "g_peering"


def test_multi_owner_facet_without_binding_is_unknown():
    d = B.run_schema(W["multi_owner_nobinding"], RS).decisions["g_exchange_setting"]
    assert d.grain == "UNKNOWN" and d.missing == ["owner"]


# ---- balanceador

def test_cmt_lb_p03_embedded_equals_separate_graph():
    e, s = occs(W["lb"], "embedded"), occs(W["lb"], "separate")
    assert I.canonical_rows(e) == I.canonical_rows(s)
    rules = [o for o in e if o.label == "routing rule"]
    assert len(rules) == 2 and all(o.refs["pool"] for o in rules)
    assert all(o.grain == "COMPONENT" for o in e if o.label in ("listener", "routing rule", "pool", "frontend"))


def test_suite_all_in_scope_reproduced():
    from bo.grain import suite
    r = suite.run()
    assert r["failed"] == 0 and r["reproduced"] >= 20 and not r["checks_without_commitment"]
