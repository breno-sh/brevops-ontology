"""Nível OBSERVED (C25 1.4.0, adendo de 04/11 §2) e emenda 0.1.11 do GRAIN, com fatos sintéticos no formato do C25.

R-GRAIN-OBS: observação repetível (2+ repetições) e com controle prevalece sobre a doc na disputa, que fica registrada;
sem repetição ou controle, ou observações divergentes, CONTRADICTORY.
T64: item sem id, lista substituída inteira e duplicata aceita = objeto-valor: COMPONENT anônimo, chave = conteúdo,
duplicata = outro membro. Item com id que não existe sem o pai = COMPONENT do pai (G2-CHILD)."""

import random

from bo.grain import instance as I
from bo.grain import rules as R
from bo.grain.evidence import C25Adapter, consolidate, disputes

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


def test_observed_repeatable_with_control_wins_dispute_and_records_it():
    for order in ((0, 1), (1, 0)):
        pub, obs = _claims()
        recs = [(pub, obs)[i] for i in order]
        ev = C25Adapter(recs).evidence("t_a")
        f = ev.fact("lifecycle_controller")
        assert f.known and f.value["kind"] == "self"
        assert disputes("lifecycle_controller", ev.claims["lifecycle_controller"]) == [pub["evidence_id"]]
        assert any(c["source"]["level"] != "observed" for c in ev.claims["lifecycle_controller"])  # nada apagado


def test_observed_without_repetition_or_control_stays_contradictory():
    for kw in ({"rep": 1}, {"control": False}):
        pub, obs = _claims(**kw)
        assert C25Adapter([pub, obs]).evidence("t_a").fact("lifecycle_controller").state == "CONTRADICTORY"


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
        pub = recs[-4]                       # block_identity da doc: sem identidade
        recs.append(rec(SL, "identity", {"aspect": "item_identity", "has_id": False, "replaced_whole": True,
                                         "duplicates_accepted": True}, level="observed", bp=BP,
                        disputes=[pub["evidence_id"]]))
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


def test_value_object_rules_are_anonymous_components_keyed_by_content():
    oc = _occs(_sl_records(), _sl_cfg(RULES))
    rules = [o for o in oc if any(f"/{BP}#" in n for n in o.tf)]
    top = [o for o in oc if o.tf == [f"{SL}.web"]][0]
    assert top.grain == "ENTITY"
    assert len(rules) == 3 and all(o.grain == "COMPONENT" and o.parent == top.occ_id for o in rules)
    assert len({o.occ_id for o in rules}) == 3                     # a duplicata é outro membro
    assert all("$content" in o.key for o in rules)


def test_value_object_identity_does_not_depend_on_position():
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


def test_official_c25_stub_pair_observed_wins_over_published():
    """Par do stub oficial do C25 1.4.0 (SE-oci-0008 publicado has_id=true x SE-oci-0009 observado has_id=false):
    a observação repetível com controle prevalece e a disputa fica registrada."""
    import json
    from pathlib import Path
    stub = Path(__file__).resolve().parents[2] / "contracts" / "stubs" / "C25" / "service_evidence.jsonl"
    recs = [json.loads(x) for x in stub.read_text(encoding="utf-8").splitlines() if x.strip()]
    pair = [r for r in recs if r.get("evidence_id") in ("SE-oci-0008", "SE-oci-0009")]
    assert len(pair) == 2
    ev = C25Adapter(pair).evidence("oci_core_security_list.ingress_security_rules")
    f = ev.fact("identity")
    assert f.known and f.value.get("anonymous") is True and f.value["key_fields"] == ["$content"]
    assert disputes("identity", ev.claims["identity"]) == ["SE-oci-0008"]
