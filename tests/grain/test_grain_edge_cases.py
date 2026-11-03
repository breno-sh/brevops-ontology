"""Casos de borda do procedimento: ciclo, ocorrência duplicada, ordem como identidade, embalagem só-schema."""

import copy

from bo.grain import battery as B
from bo.grain import fixtures as F
from bo.grain import instance as I
from bo.grain import rules as R
from bo.grain import schema as S
from bo.grain.evidence import FixtureAdapter

RS = R.load()


def test_dependency_cycle_is_unknown():
    w = {"provider": "provider_z", "schema": {"z_a": F.res(["b_id", "name"]), "z_b": F.res(["a_id", "name"])},
         "evidence": {}}
    for me, other, f, p in (("z_a", "z_b", "peer", "b_id"), ("z_b", "z_a", "peer", "a_id")):
        e = F.ev_element(me, "nm", "name", {}, via=f, ref_field=f, ref_target=other, tag=me)
        e["field_map"][f]["path"] = p
        w["evidence"][me] = e
    d = B.run_schema(w, RS).decisions
    assert all(x.grain == "UNKNOWN" and x.rule == "GRAIN-G0-CYCLE" and x.missing == ["identity"] for x in d.values())


def _fw_rules(rules):
    w = B.all_worlds()["firewall"]
    cfg = {"provider": w["provider"], "resources": [{"type": "c_rule_set", "name": "rs1", "values": {
        "name": "set-one", "rule": [dict(zip(["direction", "protocol", "ports", "cidr", "action"], r)) for r in rules]}}]}
    return I.decompose_config(cfg, FixtureAdapter(w["evidence"]), F.schema_blocks(w["schema"]), RS)


def test_duplicate_occurrence_same_config_merges():
    r = ("ingress", "tcp", "443", "10.0.0.0/8", "allow")
    oc = [o for o in _fw_rules([r, r]) if o.label == "network rule"]
    assert len(oc) == 1 and len(oc[0].tf) == 2 and oc[0].grain == "COMPONENT"


def test_duplicate_occurrence_conflicting_config_is_unknown():
    a = ("ingress", "tcp", "443", "10.0.0.0/8", "allow")
    b = ("ingress", "tcp", "443", "10.0.0.0/8", "deny")
    oc = [o for o in _fw_rules([a, b]) if o.label == "network rule"]
    assert len(oc) == 2 and all(o.grain == "UNKNOWN" and o.rule == "GRAIN-G0-DUPLICATE" for o in oc)


def test_order_as_identity_only_when_declared():
    """Onde o provedor deriva o índice da ordem, a ordem É campo de identidade (CMT-NIC-P05, 2ª parte)."""
    w = B.all_worlds()["bucket"]
    ev = copy.deepcopy(w["evidence"])
    e = ev["a_bucket.lifecycle_rule"]
    e["identity"] = [F.c(status="present", scope="within_parent", key_fields=["position"], anonymous=True, tag="ord")]
    e["element_name_key"] = [F.c(status="absent", tag="ord")]
    e["field_map"]["position"] = {"path": "$index", "norm": "ordinal"}
    ad, bl = FixtureAdapter(ev), F.schema_blocks(w["schema"])
    cfg = F.bucket_configs()["inline"]
    rev = copy.deepcopy(cfg)
    rev["resources"][0]["values"]["lifecycle_rule"].reverse()
    k1 = {o.key["position"]: o.config["expiration_days"] for o in I.decompose_config(cfg, ad, bl, RS)
          if o.label == "lifecycle rule"}
    k2 = {o.key["position"]: o.config["expiration_days"] for o in I.decompose_config(rev, ad, bl, RS)
          if o.label == "lifecycle rule"}
    assert set(k1) == set(k2) == {0, 1} and k1 != k2
    # e sem a declaração, reordenar não muda nada (a posição não entra)
    assert I.canonical_rows(I.decompose_config(cfg, FixtureAdapter(w["evidence"]), bl, RS)) == \
        I.canonical_rows(I.decompose_config(rev, FixtureAdapter(w["evidence"]), bl, RS))


def test_cardinality_does_not_decide():
    """Bloco single com identidade dentro do pai é COMPONENT; bloco list sem identidade é FACET."""
    w = {"provider": "provider_y", "schema": {"y_vm": F.res(["name"], {
        "boot_disk": F.blk(["disk_name", "size"], nesting="single"),
        "labels_set": F.blk(["k", "v"], nesting="list")})}, "evidence": {
        "y_vm": F.ev_entity("vm", "vm_name", "name", tag="vm"),
        "y_vm.boot_disk": F.ev_element("disk", "disk_name", "disk_name", {"size": ("size", "int")}, tag="dk"),
        "y_vm.labels_set": F.ev_aspect("labels", {}, tag="lb")}}
    d = B.run_schema(w, RS).decisions
    assert d["y_vm.boot_disk"].grain == "COMPONENT" and d["y_vm.labels_set"].grain == "FACET"


def test_schema_and_atoms_paths_agree():
    for name, w in sorted(B.all_worlds().items()):
        a = S.decompose_schema(S.candidates_from_tf_schema(w["provider"], w["schema"]), FixtureAdapter(w["evidence"]),
                               RS)
        b = S.decompose_schema(S.candidates_from_atoms(S.atoms_from_tf_schema(w["provider"], w["schema"])),
                               FixtureAdapter(w["evidence"]), RS)
        assert S.to_c19(a) == S.to_c19(b), name


def test_multi_owner_facet_instance_parent_is_binding_occurrence():
    w = B.all_worlds()["multi_owner"]
    cfg = {"provider": w["provider"], "resources": [
        {"type": "g_network", "name": "n1", "values": {"name": "net-one"}},
        {"type": "g_network", "name": "n2", "values": {"name": "net-two"}},
        {"type": "g_peering", "name": "p", "values": {"left_id": {"$ref": "g_network.n1"},
                                                      "right_id": {"$ref": "g_network.n2"}}},
        {"type": "g_exchange_setting", "name": "x", "values": {"left_id": {"$ref": "g_network.n1"},
                                                               "right_id": {"$ref": "g_network.n2"},
                                                               "export_routes": True}}]}
    oc = I.decompose_config(cfg, FixtureAdapter(w["evidence"]), F.schema_blocks(w["schema"]), RS)
    peer = [o for o in oc if o.grain == "BINDING"]
    fac = [o for o in oc if o.label == "route exchange"]
    assert len(peer) == 1 and len(fac) == 1 and fac[0].grain == "FACET" and fac[0].parent == peer[0].occ_id
    # sem o vínculo na configuração, a faceta de dois donos fica UNKNOWN com owner
    cfg2 = dict(cfg, resources=[r for r in cfg["resources"] if r["type"] != "g_peering"])
    fac2 = [o for o in I.decompose_config(cfg2, FixtureAdapter(w["evidence"]), F.schema_blocks(w["schema"]), RS)
            if o.label == "route exchange"]
    assert fac2[0].grain == "UNKNOWN" and "owner" in fac2[0].missing
