"""Nível OBSERVED (C25 1.4.0, adendo de 04/11 §2) e emenda 0.1.11 do GRAIN, com fatos sintéticos no formato do C25.

Consolidação R1–R5 do PREREG (04/11 17:05): R1 nada é sobrescrito; R2 disputa já existente resolvida por observação
vale o lado reproduzido; R3 observação contra publicado sem disputa prévia é CONTRADICTORY; R4 observação sozinha
preenche. T64/T59b (0.2.0): item sem id da lista do pai = COMPONENT anônimo do dono, chave = conteúdo. Item com id que não existe sem o
pai = COMPONENT do pai (G2-CHILD). Cascata do namespace só com evidência por tipo."""

import random

from bo.grain import instance as I
from bo.grain import rules as R
from bo.grain import c25_aspects as A
from bo.grain.evidence import C25Adapter, consolidate, from_dict

RS = R.load()
PROV = "oci"
N = [0]


def rec(rt, kind, value, level="published", bp=None, **extra):
    N[0] += 1
    r = {"evidence_id": f"SE-syn-{N[0]:04d}", "provider": PROV, "pin": {"provider_version": "0.0.1"},
         "api_resource": {"service": "core", "resource": "X"}, "terraform_resource_type": rt, "fact_kind": kind,
         "status": "stated", "level": level, "value": dict(value, **({"block_path": bp} if bp else {}))}
    if bp:
        r["block_path"] = bp
    if level == "observed":
        r.update({"observation_ref": {"path": "$BO_DATA/OBS-GAPS/observations.jsonl", "record_id": "run-x/q/2"},
                  "run_id": "run-x", "repetitions": 2, "control": {"description": "lista vazia lida antes e depois",
                                                                   "result": "sem itens"},
                  "observed_at": "2026-11-04T15:50:00-03:00"})
    r.update(extra)
    return r


def api(rt, kind, value_kind, bp=None, level="published", **extra):
    return rec(rt, kind, {"kind": value_kind, "layer": "api", "rule": "R-X"}, level=level, bp=bp, **extra)


def entity(rt, resource):
    return [rec(rt, "identity", {"key_fields": ["id"], "layer": "api", "rule": "R-ID-SPEC", "scope": "independent",
                                 "status": "present"}),
            api(rt, "lifecycle_controller", "self"), api(rt, "owner", "self"), api(rt, "effective_scope", "self"),
            rec(rt, "api_bridge", {"aspect": "api_resource_bridge", "resource": resource, "service": "core",
                                   "rule": "R-BRIDGE-SPEC"})]


# ------------------------------------------------------------------ R-GRAIN-OBS

def _claims(obs_kind="self", pub_kind="parent", rep=2, control=True):
    pub = api("t_a", "lifecycle_controller", pub_kind)
    obs = api("t_a", "lifecycle_controller", obs_kind, level="observed", disputes=[pub["evidence_id"]])
    obs["repetitions"] = rep
    if not control:
        obs["control"] = {}
    return pub, obs


def test_observed_level_is_read_and_cited():
    pub, obs = _claims()
    ev = C25Adapter([obs]).evidence("t_a")
    src = ev.claims["lifecycle_controller"][0]["source"]
    assert src["level"] == "observed" and src["qualified"] is True and "OBSERVED run run-x" in src["note"]
    items = ev.sources()
    assert items[0]["level"] == "observed" and "qualified" not in items[0]     # citação no formato do C00


def test_r3_observed_against_published_without_prior_dispute_is_contradictory():
    for order in ((0, 1), (1, 0)):
        pub, obs = _claims()
        recs = [(pub, obs)[i] for i in order]
        ev = C25Adapter(recs).evidence("t_a")
        assert ev.fact("lifecycle_controller").state == "CONTRADICTORY"
        assert len(ev.claims["lifecycle_controller"]) == 2                  # R1: os dois continuam citados


def test_r4_observed_alone_fills_the_field_with_observed_level():
    obs = api("t_a", "lifecycle_controller", "self", level="observed")
    ev = C25Adapter([obs]).evidence("t_a")
    f = ev.fact("lifecycle_controller")
    assert f.known and f.value["kind"] == "self" and ev.sources()[0]["level"] == "observed"


def _dispute(status=None, win="spec"):
    d = {"provider": PROV, "terraform_resource_type": "t_a", "fact": "lifecycle_controller",
         "doc": {"kind": "self", "rule": "R-DOC"}, "spec": {"kind": "parent", "rule": "R-SPEC"}, "evidence": []}
    if status:
        d.update(status=status, resolved_to=win, observation="SE-obs-1")
    return d


def _translate(dispute):
    doc = rec("t_a", "lifecycle_controller", {"kind": "self", "layer": "api", "rule": "R-DOC"})
    spec = rec("t_a", "lifecycle_controller", {"kind": "parent", "layer": "api", "rule": "R-SPEC"})
    obs = api("t_a", "lifecycle_controller", "parent", level="observed")
    out, why = A.translate([doc, spec, obs], None, set(), A.load_resolved_disputes([dispute]))
    return from_dict(out["t_a"]), why.get("t_a", [])


def test_r2_resolved_dispute_takes_reproduced_side_and_keeps_loser_cited():
    ev, why = _translate(_dispute(A.RESOLVED, "spec"))
    f = ev.fact("lifecycle_controller")
    assert f.known and f.value["kind"] == "parent"
    lost = [c for c in ev.claims["lifecycle_controller"] if c.get("status") == "unknown"]
    assert lost and "R-GRAIN-R2" in lost[0]["source"]["note"] and any("R2" in w for w in why)


def test_r2_open_dispute_stays_contradictory():
    ev, _ = _translate(_dispute())
    assert ev.fact("lifecycle_controller").state == "CONTRADICTORY"


def test_two_observations_diverging_stay_contradictory():
    a = api("t_a", "lifecycle_controller", "self", level="observed")
    b = api("t_a", "lifecycle_controller", "parent", level="observed")
    claims = C25Adapter([a, b]).evidence("t_a").claims["lifecycle_controller"]
    assert consolidate("lifecycle_controller", claims).state == "CONTRADICTORY"


# ------------------------------------------------------------------ T64: objeto-valor (regras da security list)

SL, BP = "t_sl", "rules"


def _sl_records(observed=True):
    recs = entity(SL, "SecurityList") + [
        rec(SL, "api_bridge", {"aspect": "api_resource_bridge", "field_type": "list[Rule]", "item_model": "Rule",
                               "resource": "security_list.rules", "rule": "R-BRIDGE-SPEC-BLOCK", "service": "core"},
            bp=BP),
        rec(SL, "identity", {"aspect": "block_identity", "element_name_candidates": [], "key_fields": [],
                             "nesting_mode": "set", "rule": "R-BLOCK-ID", "schema_identity": "absent"}, bp=BP)]
    for k in ("lifecycle_controller", "owner", "effective_scope"):
        recs.append(rec(SL, k, {"kind": "parent", "layer": "api", "rule": "R-OWN-SPEC-BLOCK",
                                "configured_by": "update do pai"}, bp=BP))
    if observed:
        recs.append(rec(SL, "identity", {"aspect": "item_identity", "has_id": False, "replaced_whole": True,
                                         "duplicates_accepted": True}, level="observed", bp=BP))
    return recs


def _sl_cfg(rules, seed=None):
    rs = list(rules)
    if seed is not None:
        random.Random(seed).shuffle(rs)
    return {"provider": PROV, "resources": [{"type": SL, "name": "web", "values": {"name": "web", BP: rs}}]}


RULES = [{"protocol": "6", "source": "203.0.113.0/24", "tcp": {"min": 22, "max": 22}},
         {"protocol": "6", "source": "203.0.113.0/24", "tcp": {"min": 22, "max": 22}},      # duplicata aceita
         {"protocol": "17", "source": {"$unknown": "var.cidr"}}]


def _occs(recs, cfg):
    return I.decompose_config(cfg, C25Adapter(recs), {SL: {BP}}, RS)


def test_item_without_id_is_anonymous_component_keyed_by_content():
    """0.2.0 (T59b): item sem id do provedor é COMPONENT anônimo do dono; ocorrência = (pai, caminho, conteúdo,
    índice de multiplicidade); a duplicata aceita é outro membro; nada depende da posição."""
    oc = _occs(_sl_records(), _sl_cfg(RULES))
    top = [o for o in oc if o.tf == [f"{SL}.web"]][0]
    rules = [o for o in oc if any(f"/{BP}#" in n for n in o.tf)]
    assert top.grain == "ENTITY"
    assert len(rules) == 3 and all(o.grain == "COMPONENT" and o.parent == top.occ_id for o in rules)
    assert len({o.occ_id for o in rules}) == 3
    assert sorted(o.key["$dup"] for o in rules) == [0, 0, 1]


def test_item_without_id_identity_does_not_depend_on_position():
    ids = []
    for seed in (None, 1, 2, 3):
        oc = _occs(_sl_records(), _sl_cfg(RULES, seed))
        ids.append(sorted(o.occ_id for o in oc if any(f"/{BP}#" in n for n in o.tf)))
    assert all(x == ids[0] for x in ids)


def test_without_observation_list_item_stays_unknown():
    oc = _occs(_sl_records(observed=False), _sl_cfg(RULES))
    rules = [o for o in oc if any(f"/{BP}#" in n for n in o.tf)]
    assert rules and all(o.grain == "UNKNOWN" and "api_resource" in o.missing for o in rules)


# ------------------------------------------------------------------ T64: regra do NSG (id + depende do pai)

NSG, RULE = "t_nsg", "t_nsg_rule"


def _nsg_records(requires_parent=True):
    recs = entity(NSG, "NetworkSecurityGroup") + [
        api(RULE, "lifecycle_controller", "self"), api(RULE, "owner", "self"), api(RULE, "effective_scope", "self"),
        rec(RULE, "api_bridge", {"aspect": "api_resource_bridge", "resource": "SecurityRule", "service": "core",
                                 "rule": "R-BRIDGE-SPEC"}),
        rec(RULE, "identity", {"aspect": "reference_target", "attribute": "nsg_id", "resolved": NSG,
                               "target_types": [NSG], "references": {"nsg_id": NSG}, "rule": "R-REF-TARGET"}),
        rec(RULE, "identity", {"aspect": "item_identity", "has_id": True, "requires_parent": requires_parent,
                               "parent_attribute": "nsg_id", "parent_type": NSG}, level="observed")]
    return recs


def _nsg_cfg():
    return {"provider": PROV, "resources": [
        {"type": NSG, "name": "web", "values": {"name": "web"}},
        {"type": RULE, "name": "r1", "values": {"nsg_id": {"$ref": f"{NSG}.web"}, "direction": "INGRESS"}}]}


def test_nsg_rule_with_id_that_needs_the_nsg_is_component_of_the_nsg():
    oc = I.decompose_config(_nsg_cfg(), C25Adapter(_nsg_records()), {}, RS)
    nsg = [o for o in oc if o.tf == [f"{NSG}.web"]][0]
    r = [o for o in oc if o.tf == [f"{RULE}.r1"]][0]
    assert nsg.grain == "ENTITY"
    assert r.grain == "COMPONENT" and r.rule == "GRAIN-G2-CHILD" and r.parent == nsg.occ_id


def test_nsg_rule_without_parent_dependency_is_not_component():
    """Controle: com id e sem requires_parent, a regra tem identidade independente e não pende do NSG."""
    oc = I.decompose_config(_nsg_cfg(), C25Adapter(_nsg_records(requires_parent=False)), {}, RS)
    r = [o for o in oc if o.tf == [f"{RULE}.r1"]][0]
    assert r.grain != "COMPONENT"


def test_official_c25_stub_pair_opens_new_dispute_contradictory():
    """Par do stub oficial do C25 1.4.0 (SE-oci-0008 publicado has_id=true x SE-oci-0009 observado has_id=false, sem
    disputa prévia no spec_disputes): R3, o campo fica CONTRADICTORY e os dois continuam citados."""
    import json
    from pathlib import Path
    stub = Path(__file__).resolve().parents[2] / "contracts" / "stubs" / "C25" / "service_evidence.jsonl"
    recs = [json.loads(x) for x in stub.read_text(encoding="utf-8").splitlines() if x.strip()]
    pair = [r for r in recs if r.get("evidence_id") in ("SE-oci-0008", "SE-oci-0009")]
    assert len(pair) == 2
    ev = C25Adapter(pair).evidence("oci_core_security_list.ingress_security_rules")
    assert ev.fact("identity").state == "CONTRADICTORY"
    assert {s["ref"] for s in ev.sources()} >= {"SE-oci-0008", "SE-oci-0009"}


# ------------------------------------------------------------------ cascata do namespace só com evidência

def _ns_records(cascade=None):
    recs = entity("t_ns", "Group") + entity("t_db", "Db") + [
        rec("t_db", "owner", {"aspect": "parent", "scope_kind": "compartment", "parent_terraform_types": ["t_ns"],
                              "parent_api_type": "svc/groups", "rule": "R-OWN-PARENT"}),
        rec("t_db", "identity", {"aspect": "reference_target", "attribute": "ns_id", "resolved": "t_ns",
                                 "target_types": ["t_ns"], "references": {"ns_id": "t_ns"}, "rule": "R-REF-TARGET"})]
    recs[5]["value"]["key_fields"] = ["name", "ns_id"]                  # identidade de API com o namespace na chave
    if cascade is not None:
        recs.append(rec("t_ns", "lifecycle_controller", {"aspect": "namespace_cascade", "cascade": cascade,
                                                         "rule": "R-OBS"}, level="observed"))
    return recs


def _ns_cfg():
    return {"provider": PROV, "resources": [
        {"type": "t_ns", "name": "g", "values": {"name": "g"}},
        {"type": "t_db", "name": "d", "values": {"name": "d", "ns_id": {"$ref": "t_ns.g"}}}]}


def _db_decision(recs):
    from bo.grain import engine as E
    nodes, _, _ = I.build_nodes(_ns_cfg(), C25Adapter(recs), {})
    return E.decide_graph(list(nodes.values()), RS)["t_db.d"]


def test_namespace_without_cascade_evidence_has_no_cascade_delete_by():
    for c in (None, False):
        d = _db_decision(_ns_records(c))
        assert d.grain == "ENTITY" and d.cascade == [], (c, d.grain, d.rule, d.cascade)


def test_namespace_with_cascade_evidence_has_cascade_delete_by():
    d = _db_decision(_ns_records(True))
    assert d.grain == "ENTITY" and d.cascade == ["t_ns.g"], (d.grain, d.rule, d.cascade)


# ------------------------------------------------------------------ 0.2.0: T59b na instância, T51b, G1 com EXTERNAL

SG, R_IN = "t_sg", "t_sg.ingress"


def _sg_records():
    recs = entity(SG, "SecurityGroup") + [
        rec(SG, "identity", {"key_fields": ["rule_id"], "layer": "api", "rule": "R-ID-SPEC", "scope": "within_parent",
                             "status": "present"}, bp="ingress")]
    for k in ("lifecycle_controller", "owner", "effective_scope"):
        recs.append(rec(SG, k, {"kind": "parent", "layer": "api", "rule": "R-X"}, bp="ingress"))
    recs.append(rec(SG, "api_bridge", {"aspect": "api_resource_bridge", "resource": "SecurityGroupRule",
                                       "service": "core", "rule": "R-BRIDGE-SPEC"}, bp="ingress"))
    return recs


def _sg_cfg(rules, seed=None):
    rs = list(rules)
    if seed is not None:
        random.Random(seed).shuffle(rs)
    return {"provider": PROV, "resources": [{"type": SG, "name": "web", "values": {"name": "web", "ingress": rs}}]}


def test_t59b_block_with_provider_assigned_id_gets_content_occurrence():
    """Bloco cuja chave de API (rule_id) o provedor atribui depois da criação: sem o valor na configuração, a
    ocorrência é por conteúdo, e não depende da posição (A12 fechada)."""
    rules = [{"proto": "tcp", "port": 443}, {"proto": "tcp", "port": 80}]
    ids = []
    for seed in (None, 1, 2):
        oc = I.decompose_config(_sg_cfg(rules, seed), C25Adapter(_sg_records()), {SG: {"ingress"}}, RS)
        r = [o for o in oc if any("/ingress#" in n for n in o.tf)]
        assert len(r) == 2 and all(o.grain == "COMPONENT" and o.occ_id for o in r)
        ids.append(sorted(o.occ_id for o in r))
    assert all(x == ids[0] for x in ids)


def test_t59b_does_not_apply_when_key_is_symbolic():
    """Controle: chave própria simbólica (variável) não é id do provedor; a ocorrência segue sem identidade."""
    rules = [{"proto": "tcp", "port": 443, "rule_id": {"$unknown": "var.rid"}}]
    oc = I.decompose_config(_sg_cfg(rules), C25Adapter(_sg_records()), {SG: {"ingress"}}, RS)
    r = [o for o in oc if any("/ingress#" in n for n in o.tf)]
    assert r and r[0].grain == "UNKNOWN"


def test_r6_resolved_by_publication_takes_reproduced_side():
    d = _dispute("resolvida-por-publicação", "doc")
    doc = rec("t_a", "lifecycle_controller", {"kind": "self", "layer": "api", "rule": "R-DOC"})
    spec = rec("t_a", "lifecycle_controller", {"kind": "parent", "layer": "api", "rule": "R-SPEC"})
    out, _ = A.translate([doc, spec], None, set(), A.load_resolved_disputes([d]))
    g = from_dict(out["t_a"]).fact("lifecycle_controller")
    assert g.known and g.value["kind"] == "self"


# ------------------------------------------------------------------ 0.2.1: T51b (C19 3.2.0)

def _vm_cfg(sym):
    return {"provider": PROV, "resources": [{"type": "t_vm", "name": "a", "values": {"name": "a",
                                                                                    "sg_ids": [{"$unknown": sym}]}}]}


def _vm_records():
    return entity("t_vm", "Vm") + entity(NSG, "NetworkSecurityGroup") + [
        rec("t_vm", "identity", {"aspect": "attachment_attribute", "attribute": "sg_ids", "binds_to": NSG,
                                 "rule": "R-ATTACH-SPEC", "spec_field": "F", "spec_operation": "Op"})]


def test_t51b_symbolic_typed_reference_is_external_endpoint():
    oc = I.decompose_config(_vm_cfg("var.sg"), C25Adapter(_vm_records()), {}, RS)
    lk = [o for o in oc if any(":sg_ids#" in n for n in o.tf)]
    assert len(lk) == 1 and lk[0].grain == "BINDING" and set(lk[0].endpoints) == {"holder", "target"}


def test_t51b_computed_value_is_not_a_symbol():
    """Controle (CMT-NIC-U02): valor computado/desconhecido que não é var., data. nem module. não vira ponta."""
    oc = I.decompose_config(_vm_cfg("computed"), C25Adapter(_vm_records()), {}, RS)
    lk = [o for o in oc if any(":sg_ids#" in n for n in o.tf)]
    assert len(lk) == 1 and lk[0].grain == "UNKNOWN"


def test_t51b_c19_endpoint_shape():
    from bo.grain.engine import EXT
    from bo.grain.schema import _endpoint
    e = _endpoint("target", f"{EXT}{NSG}#sym:var.sg", {})
    assert e == {"role": "target", "kind": "EXTERNAL", "symbol": "var.sg", "target_type": NSG}
