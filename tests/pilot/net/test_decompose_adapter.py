"""Adaptador de decomposição do E2 (bo.pilot.net.decompose): chave de ocorrência e repetição (v4-r2, F3 e F4).

Casos SINTÉTICOS derivados das fixtures de calibração (nenhuma retida é lida). Cada caso reproduz a classe do
diagnóstico do PILOT-EXIT (DIAG_T3: F3 pai por atributo de nome simbólico; F4 regra idêntica repetida), não o
valor de nenhuma retida.
"""

from __future__ import annotations

import copy

import pytest

from bo.pilot.net import decompose as DC
from bo.pilot.net import oracle as O

FX = {fx["fixture_id"]: fx for fx in O.fixtures()}


def _variant(fid: str, new_id: str) -> dict:
    fx = copy.deepcopy(FX[fid])
    fx["fixture_id"] = new_id
    fx.pop("expected", None)
    return fx


def _res(fx, addr):
    t, n = addr.split(".", 1)
    return next(r for r in fx["config"]["resources"] if r["type"] == t and r["name"] == n)


def _rules(units):
    return [u for u in units if u["domain_unit"] == "filter_rule"]


def _cmp():
    no = O.load()
    from net_oracle import decomposing as ND
    return no, ND


# ------------------------------------------------------------------------------ F3: pai por atributo de nome

def test_f3_azurerm_symbolic_parent_name_resolves_to_symbol_and_keys_by_name():
    fx = _variant("NETC-C01-AZ-SEP", "SYN-F3-AZ-SYM-PARENT")
    for a in ("azurerm_network_security_rule.allow-web", "azurerm_network_security_rule.deny-in",
              "azurerm_network_security_rule.deny-out"):
        _res(fx, a)["values"]["network_security_group_name"] = "sym:var.nsg_name"
    rs = _rules(DC.decompose(fx))
    assert len(rs) == 3
    for u in rs:
        assert u["parent"] == "var.nsg_name", u
        assert set(u["occurrence"]) == {"name"}, u
    assert sorted(u["occurrence"]["name"] for u in rs) == ["allow-web", "deny-in", "deny-out"]


def test_f3_google_symbolic_network_resolves_to_symbol_and_keys_by_name():
    fx = _variant("NETC-C04-GCP-DENY-WINS", "SYN-F3-GCP-SYM-PARENT")
    for r in fx["config"]["resources"]:
        if r["type"] == "google_compute_firewall":
            r["values"]["network"] = "sym:var.network"
    rs = _rules(DC.decompose(fx))
    assert rs and all(u["parent"] == "var.network" for u in rs)
    assert all(set(u["occurrence"]) == {"name"} for u in rs)


def test_f3_named_element_keeps_name_key_even_when_parent_unresolved():
    # pai por nome LITERAL que não está na configuração: o pai fica UNKNOWN, a ocorrência continua o nome
    fx = _variant("NETC-C01-AZ-SEP", "SYN-F3-AZ-EXTERNAL-PARENT")
    _res(fx, "azurerm_network_security_rule.allow-web")["values"]["network_security_group_name"] = "fx-outside"
    u = next(u for u in _rules(DC.decompose(fx)) if u["occurrence"].get("name") == "allow-web")
    assert u["parent"] == "UNKNOWN"
    assert u["occurrence"] == {"name": "allow-web"}


def test_f3_id_attribute_symbol_unchanged_from_calibration():
    # pai por atributo de ID (não de nome) com símbolo: comportamento da calibração (NETC-C01-AWS-SYM) mantido
    fx = FX["NETC-C01-AWS-SYM"]
    no, _ = _cmp()
    assert no.compare_decomposition(fx["expected"]["decomposition"], DC.decompose(fx))["equal"]


def test_f3_literal_name_parent_still_resolves_to_address():
    fx = FX["NETC-C01-AZ-SEP"]
    assert all(u["parent"] == "azurerm_network_security_group.web" for u in _rules(DC.decompose(fx)))


# ------------------------------------------------------------------------- F4: regra idêntica repetida

def _oci_dup(block):
    fx = _variant("NETC-C02-OCI-STATEFUL", f"SYN-F4-OCI-DUP-{block}")
    v = _res(fx, "oci_core_security_list.web")["values"]
    rule = {"protocol": "6", "source": "203.0.113.0/24", "tcp_options": {"max": 443, "min": 443}}
    if block == "egress_security_rules":
        rule = {"protocol": "6", "destination": "198.51.100.0/24", "tcp_options": {"max": 443, "min": 443}}
    v[block] = [copy.deepcopy(rule), copy.deepcopy(rule)]
    return fx


@pytest.mark.parametrize("block", ["ingress_security_rules", "egress_security_rules"])
def test_f4_oci_identical_rules_are_a_multiset_when_evidence_accepts_repetition(block):
    fx = _oci_dup(block)
    rs = [u for u in _rules(DC.decompose(fx)) if u["tf"].get("block_path") == block]
    assert len(rs) == 2, rs
    assert all(u["kind"] != "UNKNOWN" for u in rs)
    assert all(u.get("repetition", {}).get("policy") == "multiset" for u in rs)
    assert all(u["repetition"]["evidence"] and u["repetition"]["count"] == 2 for u in rs)
    _, ND = _cmp()
    keys = list(ND.normalize(rs))
    assert len(keys) == 2 and keys[1].endswith("#2")


def test_f4_multiset_is_reorder_invariant():
    fx = _oci_dup("ingress_security_rules")
    _, ND = _cmp()
    base = DC.decompose(fx)
    assert all(ND.invariant(base, DC.decompose(DC.shuffled(fx, s))) for s in (1, 2, 3))


def test_f4_repetition_without_evidence_is_unknown_never_silently_merged():
    # aws_security_group embutido: o SERVICE-EVIDENCE do pin não diz se a repetição idêntica é aceita
    fx = _variant("NETC-C08-AWS-ATTACH", "SYN-F4-AWS-DUP")
    v = _res(fx, "aws_security_group.web")["values"]
    v["ingress"] = [copy.deepcopy(v["ingress"][0]), copy.deepcopy(v["ingress"][0])]
    rs = _rules(DC.decompose(fx))
    assert len(rs) == 2, rs
    for u in rs:
        assert u["kind"] == "UNKNOWN" and "item_identity" in u["unknown"], u
        assert u["repetition"]["policy"] == "unknown" and u["repetition"]["count"] == 2


def test_f4_repetition_merged_only_when_evidence_says_invalid_or_idempotent(monkeypatch):
    fx = _variant("NETC-C08-AWS-ATTACH", "SYN-F4-AWS-DUP-IDEMP")
    v = _res(fx, "aws_security_group.web")["values"]
    v["ingress"] = [copy.deepcopy(v["ingress"][0]), copy.deepcopy(v["ingress"][0])]
    monkeypatch.setattr(DC, "repetition_evidence", lambda prov, rtype, block: (False, ["SE-synthetic-dup-rejected"]))
    rs = _rules(DC.decompose(fx))
    assert len(rs) == 1 and rs[0]["kind"] != "UNKNOWN"
    assert rs[0]["repetition"] == {"policy": "merged", "count": 2, "evidence": ["SE-synthetic-dup-rejected"]}


def test_same_element_emitted_twice_is_still_one_unit():
    # a fusão continua valendo para o MESMO elemento Terraform emitido duas vezes (não é repetição)
    u = {"domain_unit": "rule_set", "kind": "ENTITY", "parent": None, "occurrence": {"set": "x.y"},
         "tf": {"resource_type": "x"}, "_src": "x.y"}
    out = DC._dedupe([dict(u), dict(u)], "aws")
    assert len(out) == 1 and "repetition" not in out[0] and "_src" not in out[0]


def test_calibration_has_no_repetition_marks():
    for fx in FX.values():
        assert not any("repetition" in u for u in DC.decompose(fx)), fx["fixture_id"]
