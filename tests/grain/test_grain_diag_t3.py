"""Emenda 0.2.4 (motivo: results/PILOT-EXIT/DIAG_T3.json, falhas F1-F5 do E2 na tentativa 3).

Cada regra tem um caso SINTÉTICO (provedor fictício, fatos no formato do C25) e, quando o dado real do pin já
reproduz a classe, um caso de calibração sobre o SERVICE-EVIDENCE com configuração escrita aqui (nenhuma fixture
retida é lida).
  F1/F2 (R-GRAIN-T03): recurso separado com id composto (referência ao conjunto-pai + campos próprios) e sem ciclo
        de vida próprio na API é COMPONENT do pai; embutido x separado dão o mesmo grão e o mesmo pai.
  F3 (R-GRAIN-T51c): pai por atributo de nome com valor simbólico = o símbolo; a ocorrência de elemento nomeado
        expõe o nome, resolvido ou não o pai.
  F4 (R-GRAIN-T59c): repetição idêntica de elemento anônimo = multiconjunto só com evidência de que a repetição é
        aceita; evidência de repetição inválida ou idempotente funde com nota; sem evidência, UNKNOWN.
  F5 (R-GRAIN-T51c): ponta simbólica de vínculo é identidade válida, = (símbolo, alvo), mesmo sem alvo tipado.
"""

import pytest

from bo.grain import engine as E
from bo.grain import instance as I
from bo.grain import rules as R
from bo.grain import schema as S
from bo.grain.common import data_root
from bo.grain.evidence import C25Adapter

RS = R.load()
PROV = "provider_t3"
N = [0]


def rec(rt, kind, value, level="published", bp=None, **extra):
    N[0] += 1
    r = {"evidence_id": f"SE-t3-{N[0]:04d}", "provider": PROV, "pin": {"provider_version": "0.0.1"},
         "api_resource": {"service": "net", "resource": "X"}, "terraform_resource_type": rt, "fact_kind": kind,
         "status": "stated", "level": level, "value": dict(value, **({"block_path": bp} if bp else {}))}
    if bp:
        r["block_path"] = bp
    if level == "observed":
        r.update({"observation_ref": {"path": "$BO_DATA/OBS-GAPS/observations.jsonl", "record_id": "run-t3/q/2"},
                  "run_id": "run-t3", "repetitions": 2, "control": {"description": "lista lida antes e depois",
                                                                    "result": "sem itens"},
                  "observed_at": "2026-11-05T00:30:00-03:00"})
    r.update(extra)
    return r


def api(rt, kind, value_kind, **kw):
    return rec(rt, kind, {"kind": value_kind, "layer": "api", "rule": "R-X"}, **kw)


def entity(rt, resource):
    return [rec(rt, "identity", {"key_fields": ["name"], "layer": "api", "rule": "R-ID-SPEC", "scope": "independent",
                                 "status": "present"}),
            api(rt, "lifecycle_controller", "self"), api(rt, "owner", "self"), api(rt, "effective_scope", "self"),
            rec(rt, "api_bridge", {"aspect": "api_resource_bridge", "resource": resource, "service": "net",
                                   "rule": "R-BRIDGE-SPEC"})]


def ref(rt, attr, target, ambiguous=None):
    tt = ambiguous or [target]
    return rec(rt, "identity", {"aspect": "reference_target", "attribute": attr, "resolved": None if ambiguous
                                else target, "target_types": tt, "references": {} if ambiguous else {attr: target},
                                "rule": "R-REF-TARGET"})


def atom(rt, path, tf_type="string", block=None):
    bp = [{"block": block, "nesting_mode": "list"}] if block else []
    return {"atom_id": f"{PROV}:{rt}:{(block + '.') if block else ''}{path}", "provider": PROV, "resource_type": rt,
            "path": f"{block}.{path}" if block else path, "block_path": bp, "tf_type": tf_type}


def schema_dec(atoms, recs):
    cands = S.candidates_from_atoms(atoms)
    return S.decompose_schema(cands, C25Adapter(recs, candidates={c.cid for c in cands}), RS)


def occs(cfg, recs, blocks=None):
    return I.decompose_config(cfg, C25Adapter(recs), blocks or {}, RS)


def by_tf(oc):
    return {n: o for o in oc for n in o.tf}


# =========================================================================== F1/F2: T03 (id composto)

SET, RULE, RULE2 = "t3_set", "t3_set_rule", "t3_set_rule_v2"
TEMPLATE = ["set_id", "direction", "protocol", "port", "_"]


def _rule_records(typed=True, api_self=False, template=TEMPLATE):
    recs = entity(SET, "RuleSet") + [
        rec(RULE, "identity", {"aspect": "id_template", "attributes": list(template), "rule": "R-ID-ATTRS",
                               "template": "_".join(template)}, level="derived"),
        rec(RULE, "import_key", {"aspect": "import_formats", "id_attributes": list(template), "identity":
                                 {"optional": [], "required": []}, "supported": True, "rule": "R-IMPORT-DOC"}),
        rec(RULE, "api_bridge", {"aspect": "api_resource_bridge", "resource": "UNKNOWN", "rule": "R-BRIDGE"}),
        rec(RULE, "owner", {"kind": "self", "layer": "terraform", "rule": "R-OWN-TOP", "via": []}, level="derived"),
        rec(RULE, "effective_scope", {"kind": "self", "layer": "terraform", "rule": "R-SCOPE-SELF"},
            level="derived")]
    if typed:
        recs.append(ref(RULE, "set_id", SET))
    if api_self:
        recs.append(api(RULE, "lifecycle_controller", "self"))
    return recs


def _rule_atoms():
    return ([atom(SET, "name"), atom(SET, "description"), atom(SET, "direction", block="rule"),
             atom(SET, "protocol", block="rule"), atom(SET, "port", "number", block="rule")]
            + [atom(RULE, p) for p in ("set_id", "direction", "protocol")] + [atom(RULE, "port", "number")])


def test_f1_t03_separate_rule_with_typed_parent_is_component_of_the_set():
    res = schema_dec(_rule_atoms(), _rule_records())
    d = res.decisions[RULE]
    assert d.grain == "COMPONENT" and d.parent == SET and d.rule == "GRAIN-G2-COMPONENT", (d.grain, d.rule, d.missing)
    ev = res.nodes[RULE].ev
    for f in ("identity", "lifecycle_controller", "owner", "effective_scope"):
        assert any("R-GRAIN-T03" in str((c.get("source") or {}).get("note")) for c in ev.claims[f]), f
    assert sorted(d.identity.key_fields) == ["direction", "port", "protocol", "set_id"]


def test_f1_t03_own_api_lifecycle_blocks_the_inheritance():
    """Controle: com ciclo de vida próprio afirmado na API, o id composto não dá ciclo de vida pelo pai."""
    res = schema_dec(_rule_atoms(), _rule_records(api_self=True))
    d = res.decisions[RULE]
    assert d.grain != "COMPONENT", (d.grain, d.rule)
    ev = res.nodes[RULE].ev
    assert not any("R-GRAIN-T03" in str((c.get("source") or {}).get("note"))
                   for c in ev.claims.get("lifecycle_controller", []))


def test_f1_t03_single_attribute_template_is_not_translated():
    """Controle: id de um atributo só é id opaco (não é composto): sem tradução, como antes."""
    res = schema_dec(_rule_atoms(), _rule_records(template=["rule_id"]))
    d = res.decisions[RULE]
    assert d.grain == "UNKNOWN" and "identity" in d.missing, (d.grain, d.missing)


def test_f1_t03_untyped_parent_field_stays_unknown_in_schema_and_resolves_by_config_reference():
    """Sem alvo tipado no SE, o esquema não sabe qual campo é o pai: UNKNOWN (nunca ENTITY). Na instância, o campo
    da chave composta cujo valor é referência a um recurso da configuração é o pai (R-GRAIN-T03, derivado)."""
    res = schema_dec(_rule_atoms(), _rule_records(typed=False))
    d = res.decisions[RULE]
    assert d.grain == "UNKNOWN" and d.grain != "ENTITY", (d.grain, d.rule)
    cfg = {"provider": PROV, "resources": [
        {"type": SET, "name": "web", "values": {"name": "web"}},
        {"type": RULE, "name": "r1", "values": {"set_id": {"$ref": f"{SET}.web"}, "direction": "in",
                                                "protocol": "tcp", "port": 443}}]}
    t = by_tf(occs(cfg, _rule_records(typed=False)))
    o, s = t[f"{RULE}.r1"], t[f"{SET}.web"]
    assert o.grain == "COMPONENT" and o.parent == s.occ_id and o.occ_id, (o.grain, o.rule, o.missing)


def test_f1_t03_two_config_references_in_template_do_not_promote():
    """Controle: dois campos da chave composta com referência na configuração: o pai é ambíguo, nada é promovido."""
    recs = _rule_records(typed=False, template=["set_id", "other_set_id", "port"])
    cfg = {"provider": PROV, "resources": [
        {"type": SET, "name": "a", "values": {"name": "a"}}, {"type": SET, "name": "b", "values": {"name": "b"}},
        {"type": RULE, "name": "r1", "values": {"set_id": {"$ref": f"{SET}.a"}, "other_set_id": {"$ref": f"{SET}.b"},
                                                "port": 443}}]}
    o = by_tf(occs(cfg, recs))[f"{RULE}.r1"]
    assert o.grain == "UNKNOWN", (o.grain, o.rule)


def _packaging_records():
    """Conjunto com regras embutidas (bloco 'rule', identidade anônima por conteúdo, ciclo de vida do pai) e as duas
    variantes de recurso separado: v1 = id composto (T03), v2 = id de API próprio com ciclo de vida do pai."""
    recs = _rule_records()
    recs += [rec(SET, "identity", {"aspect": "item_identity", "has_id": False, "layer": "api"}, level="observed",
                 bp="rule")]
    for k in ("lifecycle_controller", "owner", "effective_scope"):
        recs.append(rec(SET, k, {"kind": "parent", "layer": "api", "rule": "R-X"}, bp="rule"))
    recs.append(rec(SET, "api_bridge", {"aspect": "api_resource_bridge", "resource": "Rule", "service": "net",
                                        "rule": "R-BRIDGE-SPEC"}, bp="rule"))
    recs += [rec(RULE2, "identity", {"key_fields": ["rule_id"], "layer": "api", "rule": "R-ID-SPEC",
                                     "scope": "independent", "status": "present"}),
             ref(RULE2, "set_id", SET)]
    for k in ("lifecycle_controller", "owner", "effective_scope"):
        recs.append(rec(RULE2, k, {"kind": "parent", "layer": "api", "rule": "R-X", "via": "set_id"}))
    return recs


def _sig(oc, tf_prefix):
    """(grão, ocorrência do pai) das regras de um conjunto: o que tem de ser igual entre embalagens."""
    return sorted((o.grain, o.parent) for o in oc if any(n.startswith(tf_prefix) for n in o.tf))


@pytest.mark.parametrize("variant", [RULE, RULE2])
def test_f2_inline_equals_each_separate_variant(variant):
    rules = [("in", "tcp", 443), ("in", "tcp", 22)]
    inline = {"provider": PROV, "resources": [{"type": SET, "name": "web", "values": {
        "name": "web", "rule": [{"direction": d, "protocol": p, "port": n} for d, p, n in rules]}}]}
    sep = {"provider": PROV, "resources": [{"type": SET, "name": "web", "values": {"name": "web"}}] + [
        {"type": variant, "name": f"r{i}", "values": {"set_id": {"$ref": f"{SET}.web"}, "direction": d,
                                                       "protocol": p, "port": n}} for i, (d, p, n) in enumerate(rules)]}
    recs = _packaging_records()
    a, b = occs(inline, recs, {SET: {"rule"}}), occs(sep, recs)
    sa, sb = _sig(a, f"{SET}.web/rule#"), _sig(b, f"{variant}.")
    assert len(sa) == len(sb) == 2 and sa == sb and all(g == "COMPONENT" for g, _ in sa), (sa, sb)


# ---- calibração (SE real do pin): as duas variantes de regra separada do provedor de F1

def _real(provider):
    p = data_root() / "SERVICE-EVIDENCE" / "service_evidence.jsonl"
    if not p.is_file():
        pytest.skip(f"dado real ausente: {p}")
    from bo.grain import realdata as RD
    return [r for r in RD.load_evidence(p) if r.get("provider") == provider]


def _real_occs(provider, cfg, types):
    from bo.grain.realdata import load_atoms
    atoms = load_atoms(provider, set(types))
    blocks = {}
    for a in atoms:
        cid = a["resource_type"]
        for p in a["path"].split(".")[:-1]:
            blocks.setdefault(cid, set()).add(p)
            cid = f"{cid}.{p}"
    return I.decompose_config(cfg, C25Adapter(_real(provider)), blocks, RS)


def test_f2_calibration_aws_inline_equals_both_separate_variants():
    sg = {"type": "aws_security_group", "name": "web", "values": {"name": "fx-web", "description": "x"}}
    inline = dict(sg, values=dict(sg["values"], ingress=[{"protocol": "tcp", "from_port": 443, "to_port": 443,
                                                          "cidr_blocks": ["203.0.113.0/24"]}]))
    v1 = {"type": "aws_security_group_rule", "name": "r", "values": {
        "security_group_id": {"$ref": "aws_security_group.web"}, "type": "ingress", "protocol": "tcp",
        "from_port": 443, "to_port": 443, "cidr_blocks": ["203.0.113.0/24"]}}
    v2 = {"type": "aws_vpc_security_group_ingress_rule", "name": "r", "values": {
        "security_group_id": {"$ref": "aws_security_group.web"}, "ip_protocol": "tcp", "from_port": 443,
        "to_port": 443, "cidr_ipv4": "203.0.113.0/24"}}
    types = ["aws_security_group", "aws_security_group_rule", "aws_vpc_security_group_ingress_rule"]
    sig = {}
    for k, cfg in (("inline", [inline]), ("v1", [sg, v1]), ("v2", [sg, v2])):
        oc = by_tf(_real_occs("aws", {"provider": "aws", "resources": cfg}, types))
        top = oc["aws_security_group.web"]
        r = [o for n, o in oc.items() if n in ("aws_security_group.web/ingress#0", f"{cfg[-1]['type']}.r")]
        assert len(r) == 1, (k, sorted(oc))
        sig[k] = (r[0].grain, r[0].parent == top.occ_id)
    assert sig["inline"] == sig["v1"] == sig["v2"] == ("COMPONENT", True), sig


# =========================================================================== F3: pai simbólico por nome

NSG, NRULE = "t3_nsg", "t3_nsg_rule"


def _named_records():
    recs = entity(NSG, "NetworkSecurityGroup") + [
        rec(NRULE, "identity", {"key_fields": ["nsg_name", "name"], "layer": "api", "rule": "R-ID-SPEC",
                                "scope": "within_parent", "status": "present"}),
        ref(NRULE, "nsg_name", NSG)]
    for k in ("lifecycle_controller", "owner", "effective_scope"):
        recs.append(rec(NRULE, k, {"kind": "parent", "layer": "api", "rule": "R-X", "via": "nsg_name"}))
    return recs


def _named_cfg(parent_value):
    return {"provider": PROV, "resources": [
        {"type": NRULE, "name": "allow", "values": {"name": "allow-web", "nsg_name": parent_value, "port": 443}}]}


def test_f3_symbolic_name_parent_is_the_symbol_and_occurrence_is_the_name():
    o = by_tf(occs(_named_cfg({"$unknown": "var.nsg_name"}), _named_records()))[f"{NRULE}.allow"]
    assert o.grain == "COMPONENT" and o.occ_id, (o.grain, o.rule, o.missing)
    assert o.parent_symbol == "var.nsg_name"
    assert o.name_key == {"name": "allow-web"}


def test_f3_name_key_survives_an_unresolved_parent():
    """Valor que não é símbolo (computado): o pai não resolve (UNKNOWN), mas a ocorrência continua o nome."""
    o = by_tf(occs(_named_cfg({"$unknown": "computed"}), _named_records()))[f"{NRULE}.allow"]
    assert o.grain == "UNKNOWN" and o.parent_symbol is None
    assert o.name_key == {"name": "allow-web"}


def test_f3_same_symbol_same_parent_across_rules():
    cfg = _named_cfg({"$unknown": "var.nsg_name"})
    cfg["resources"].append({"type": NRULE, "name": "deny", "values": {"name": "deny-all", "nsg_name": {
        "$unknown": "var.nsg_name"}, "port": 22}})
    t = by_tf(occs(cfg, _named_records()))
    a, b = t[f"{NRULE}.allow"], t[f"{NRULE}.deny"]
    assert a.parent == b.parent and a.parent and a.occ_id != b.occ_id


def test_f3_calibration_azurerm_rule_with_symbolic_nsg_name():
    cfg = {"provider": "azurerm", "resources": [{"type": "azurerm_network_security_rule", "name": "allow", "values": {
        "name": "allow-web", "network_security_group_name": {"$unknown": "var.nsg_name"},
        "resource_group_name": "fx-rg", "priority": 100, "direction": "Inbound", "access": "Allow",
        "protocol": "Tcp"}}]}
    o = by_tf(_real_occs("azurerm", cfg, ["azurerm_network_security_rule", "azurerm_network_security_group"]))[
        "azurerm_network_security_rule.allow"]
    assert o.grain == "COMPONENT" and o.parent_symbol == "var.nsg_name" and o.name_key.get("name") == "allow-web", (
        o.grain, o.rule, o.missing, o.parent_symbol, o.name_key)


# =========================================================================== F4: multiconjunto por evidência

LST = "t3_list"


def _list_records(dups):
    v = {"aspect": "item_identity", "has_id": False, "layer": "api"}
    if dups is not None:
        v["duplicates_accepted"] = dups
    recs = entity(LST, "SecurityList") + [rec(LST, "identity", v, level="observed", bp="rules")]
    for k in ("lifecycle_controller", "owner", "effective_scope"):
        recs.append(rec(LST, k, {"kind": "parent", "layer": "api", "rule": "R-X"}, bp="rules"))
    recs.append(rec(LST, "api_bridge", {"aspect": "api_resource_bridge", "resource": "Rule", "service": "net",
                                        "rule": "R-BRIDGE-SPEC"}, bp="rules"))
    return recs


def _list_cfg(rules):
    return {"provider": PROV, "resources": [{"type": LST, "name": "web", "values": {"name": "web", "rules": rules}}]}


R1 = {"protocol": "6", "source": "203.0.113.0/24", "port": 22}
R2 = {"protocol": "6", "source": "203.0.113.0/24", "port": 443}


def _rule_occs(dups, rules):
    return [o for o in occs(_list_cfg(rules), _list_records(dups), {LST: {"rules"}})
            if any("/rules#" in n for n in o.tf)]


def test_f4_accepted_repetition_is_a_multiset():
    r = _rule_occs(True, [R1, dict(R1), R2])
    assert len(r) == 3 and all(o.grain == "COMPONENT" and o.occ_id for o in r)
    assert len({o.occ_id for o in r}) == 3
    rep = [o for o in r if o.multiplicity]
    assert len(rep) == 2 and {o.multiplicity["count"] for o in rep} == {2}
    assert all("R-GRAIN-T59C" in o.multiplicity["rule"] for o in rep)


def test_f4_repetition_without_evidence_is_unknown_never_silently_deduplicated():
    r = _rule_occs(None, [R1, dict(R1), R2])
    rep = [o for o in r if o.rule == "GRAIN-G0-REPEAT"]
    assert len(rep) == 2 and all(o.grain == "UNKNOWN" and o.missing == ["identity"] for o in rep), [
        (o.grain, o.rule) for o in r]
    single = [o for o in r if o.rule != "GRAIN-G0-REPEAT"]
    assert len(single) == 1 and single[0].grain == "COMPONENT"


def test_f4_rejected_repetition_is_fused_with_a_note():
    r = _rule_occs(False, [R1, dict(R1)])
    assert len(r) == 1 and len(r[0].tf) == 2 and r[0].grain == "COMPONENT"
    assert any("repetição" in n for n in r[0].notes) and r[0].multiplicity["evidence"] == "rejected"


def test_f4_multiset_is_reorder_invariant():
    ids = []
    for rules in ([R1, dict(R1), R2], [R2, R1, dict(R1)], [dict(R1), R2, R1]):
        ids.append(sorted(o.occ_id for o in _rule_occs(True, rules)))
    assert ids[0] == ids[1] == ids[2]


def test_f4_calibration_oci_security_list_accepts_duplicates():
    rule = {"protocol": "6", "source": "203.0.113.0/24", "tcp_options": {"max": 22, "min": 22}}
    cfg = {"provider": "oci", "resources": [{"type": "oci_core_security_list", "name": "web", "values": {
        "compartment_id": {"$ref": "oci_identity_compartment.fx"}, "vcn_id": {"$ref": "oci_core_vcn.fx"},
        "ingress_security_rules": [rule, dict(rule)], "egress_security_rules": []}}]}
    oc = _real_occs("oci", cfg, ["oci_core_security_list"])
    r = [o for o in oc if any(n.endswith(("/ingress_security_rules#0", "/ingress_security_rules#1")) for n in o.tf)]
    assert len(r) == 2 and len({o.occ_id for o in r}) == 2 and all(o.grain == "COMPONENT" for o in r)
    assert all(o.multiplicity and o.multiplicity["evidence"] == "accepted" for o in r)


# =========================================================================== F5: ponta simbólica do vínculo

HOST = "t3_subnet"


def _host_records(typed):
    recs = entity(HOST, "Subnet") + entity(LST, "SecurityList")
    recs.append(ref(HOST, "list_ids", LST) if typed else ref(HOST, "list_ids", LST, ambiguous=[LST, "t3_default"]))
    recs.append(rec(HOST, "lifecycle_controller", {"attribute": "list_ids", "kind": "parent"}))
    recs.append(rec(HOST, "owner", {"attribute": "list_ids", "kind": "self"}))
    recs.append(rec(HOST, "effective_scope", {"attribute": "list_ids", "kind": "self"}))
    return recs


def _host_cfg(*hosts):
    return {"provider": PROV, "resources": [{"type": HOST, "name": h, "values": {"name": h, "list_ids": els}}
                                            for h, els in hosts]}


def _links(oc):
    return {n: o for o in oc for n in o.tf if ":list_ids#" in n}


@pytest.mark.parametrize("typed", [True, False])
def test_f5_symbolic_endpoint_is_binding_identity(typed):
    lk = _links(occs(_host_cfg(("sa", [{"$unknown": "var.list_id"}])), _host_records(typed)))
    o = lk["t3_subnet.sa:list_ids#0"]
    assert o.grain == "BINDING" and o.occ_id and o.endpoint_symbols == {"target": "var.list_id"}, (
        o.grain, o.rule, o.missing)


def test_f5_identity_is_symbol_and_target():
    lk = _links(occs(_host_cfg(("sa", [{"$unknown": "var.list_id"}]), ("sb", [{"$unknown": "var.list_id"}])),
                     _host_records(False)))
    a, b = lk["t3_subnet.sa:list_ids#0"], lk["t3_subnet.sb:list_ids#0"]
    assert a.endpoints["target"] == b.endpoints["target"] and a.occ_id != b.occ_id
    # o tipo do alvo não entra na identidade da ponta simbólica: tipado e não tipado dão a mesma ponta
    t = _links(occs(_host_cfg(("sa", [{"$unknown": "var.list_id"}])), _host_records(True)))["t3_subnet.sa:list_ids#0"]
    assert t.endpoints["target"] == a.endpoints["target"]


def test_f5_computed_value_is_not_an_endpoint():
    """Controle (CMT-NIC-U02): valor que não existe nem como símbolo (computado) continua UNKNOWN."""
    o = _links(occs(_host_cfg(("sa", [{"$unknown": "computed"}])), _host_records(False)))["t3_subnet.sa:list_ids#0"]
    assert o.grain == "UNKNOWN" and "identity" in o.missing


def test_f5_calibration_oci_subnet_symbolic_security_list():
    cfg = {"provider": "oci", "resources": [{"type": "oci_core_subnet", "name": "sa", "values": {
        "security_list_ids": [{"$unknown": "var.sl_id"}]}}]}
    lk = {n: o for o in _real_occs("oci", cfg, ["oci_core_subnet", "oci_core_security_list"]) for n in o.tf
          if ":security_list_ids#" in n}
    o = lk["oci_core_subnet.sa:security_list_ids#0"]
    assert o.grain == "BINDING" and o.endpoint_symbols.get("target") == "var.sl_id", (o.grain, o.rule, o.missing)


def test_external_symbol_node_identity_ignores_type():
    assert E.EXT and I.symbol_of(f"{E.EXT}t_x#sym:var.a") == I.symbol_of(f"{E.EXT}#sym:var.a") == "var.a"
