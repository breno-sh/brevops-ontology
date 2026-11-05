"""Testes do piloto NET (PILOT-NET-E2E) com alegações SINTÉTICAS (o mapeamento real só entra pelos gates)."""

from __future__ import annotations

import ipaddress
import itertools
import json
import os
from pathlib import Path

import pytest

from bo.pilot.net import axioms as AX
from bo.pilot.net import carry as CY
from bo.pilot.net import claims as CL
from bo.pilot.net import lift as LF
from bo.pilot.net import loss_policy as LP
from bo.pilot.net import oracle as O
from bo.pilot.net import pipeline as P
from bo.pilot.net import reason as RS
from bo.pilot.net import synthetic as SY
from bo.pilot.net import translate as TR
from bo.pilot.net import vocab as V

FX = {fx["fixture_id"]: fx for fx in O.fixtures()}


@pytest.fixture(scope="module")
def tmpdir_mod():
    d = P.tmp() / "pytest_net"
    d.mkdir(parents=True, exist_ok=True)
    return d


@pytest.fixture(scope="module")
def cs(tmpdir_mod):
    m, v = SY.write(tmpdir_mod / "claims", "2026-11-04T10:00:00-03:00")
    return CL.load(m, v, "synthetic")


@pytest.fixture(scope="module")
def run(tmpdir_mod):
    return P.run(claims_mode="synthetic", out=tmpdir_mod / "run", recorded_at="2026-11-04T10:00:00-03:00")


def rows(tmpdir_mod):
    return [json.loads(l) for l in (tmpdir_mod / "run" / "cases.jsonl").read_text().splitlines() if l.strip()]


# --------------------------------------------------------------------------------------------- entradas

def test_only_calibration_fixtures_are_read():
    assert FX and all(fx["split"] == "calib" for fx in FX.values())
    with pytest.raises(SystemExit):
        O.fixtures(O.repo() / "pilot" / "net" / "fixtures_calib", "retained")


def test_synthetic_claims_pass_proof_obligations(cs):
    assert cs.ok_count() == len(cs.records) and all(r["claim_id"].startswith("CLM-SYNTH-") for r in cs.records)


def test_evidence_ids_exist_in_service_evidence():
    se = Path(os.environ["BO_DATA"]) / "SERVICE-EVIDENCE" / "service_evidence.jsonl"
    ids = {json.loads(l)["evidence_id"] for l in se.read_text().splitlines() if l.strip()}
    cited = {e for a in AX.AXIOMS for e in a["evidence"] if e.startswith("SE-")}
    cited |= {e for ev in V.STRUCTURAL_EVIDENCE.values() for e in ev if e.startswith("SE-")}
    assert cited and cited <= ids, sorted(cited - ids)
    assert all(a["level"] in ("published", "derived") for a in AX.AXIOMS)


# --------------------------------------------------------------------------------------------- lifting

def test_inline_and_standalone_lift_to_same_rules():
    a, b = LF.lift(FX["NETC-C01-AWS-INLINE"]), LF.lift(FX["NETC-C01-AWS-SEP"])

    def sig(L):
        return sorted((r.facts["direction"].value, r.matches[0]["protocol"].value, json.dumps(r.matches[0]["dst_ports"].value),
                       json.dumps(sorted(r.facts["remote"].value))) for r in L.rules.values())
    assert sig(a) == sig(b)


def test_symbolic_input_stays_symbolic():
    L = LF.lift(FX["NETC-C08-AWS-ATTACH-SYM"])
    assert [a.status for a in L.attachments] == ["symbolic"]


# --------------------------------------------------------------------------------------------- controles

def test_controls_differ_only_in_knowledge(cs, tmpdir_mod):
    L = [LF.lift(FX["NETC-C02-AWS-RET"])]
    k1 = RS.run("c1_table", L, cs)[L[0].fixture_id]
    k2 = RS.run("c2_taxonomy", L, cs)[L[0].fixture_id]
    k3 = RS.run("c3_full", L, cs, tmpdir_mod / "rc")[L[0].fixture_id]
    rid = next(iter(L[0].rules))
    sid = next(iter(L[0].sets))
    assert not k1.values
    assert k2.value(rid, "direction") == "ingress" and k2.value(rid, "effect") is None
    assert k3.value(rid, "effect") == "allow" and "AX-NET-01" in k3.justification(rid, "effect")
    assert k3.value(sid, "no_match_ingress") == "deny" and k3.value(sid, "no_match_egress") == "deny"
    assert k2.value(sid, "no_match_ingress") is None
    assert k3.value(rid, "state") == "stateful" and k2.value(rid, "state") is None


def test_oci_allows_but_only_aws_is_exclusive(cs, tmpdir_mod):
    """OCI: a frase publicada diz que a regra permite e que sem regra nada passa; não diz que só pode permitir."""
    assert not [e for e in AX.by_id()["AX-NET-01"]["evidence"] if e.startswith("SE-oci-")]
    for t in ("oci_core_security_list", "oci_core_network_security_group"):
        assert "bo:PermissionListRuleSet" not in AX.REALIZATION_CLASSES[t]
        assert {"bo:AllowCapableRuleSet", "bo:NoMatchDenyRuleSet"} <= set(AX.REALIZATION_CLASSES[t])
    L = [LF.lift(FX["NETC-C09-OCI-NOMATCH"])]
    k3 = RS.run("c3_full", L, cs, tmpdir_mod / "rc")[L[0].fixture_id]
    sid = next(iter(L[0].sets))
    assert k3.value(sid, "no_match_ingress") == "deny" and "AX-NET-03" in k3.justification(sid, "no_match_ingress")
    assert k3.value(sid, "precedence") is None
    assert all(k3.value(rid, "effect") is None for rid in L[0].rules)


def test_shacl_rejects_duplicate_priority(cs, tmpdir_mod):
    L = [LF.lift(FX["NETC-C05-AZ-DUP"])]
    k3 = RS.run("c3_full", L, cs, tmpdir_mod / "rc")[L[0].fixture_id]
    assert any("AX-NET-06" in m for ms in k3.violations.values() for m in ms)


def test_same_input_loss_and_transforms_across_controls(run):
    assert run["invariants"]["ok"] and run["invariants"]["same_case_set"]
    assert set(run["counts"]) == {"c1_table", "c2_taxonomy", "c3_full"}


def test_no_control_carries_deny_to_allow(run, tmpdir_mod):
    for r in rows(tmpdir_mod):
        if r["judge"]:
            assert not r["judge"]["negatives_carried"], r["case_id"]


def test_primary_control_has_no_silent_loss(run, tmpdir_mod):
    bad = [r["case_id"] for r in rows(tmpdir_mod) if r["control"] == "c3_full" and r["judge"]
           and r["judge"]["silent_losses"]]
    assert not bad


def test_every_case_has_typed_status(run, tmpdir_mod):
    assert {r["status"] for r in rows(tmpdir_mod)} <= {"TRANSLATED", "UNSUPPORTED", "REFUSED", "RENDER_BLOCKED"}


def test_invalid_source_refused_by_c3(run, tmpdir_mod):
    st = {r["direction"]: r["status"] for r in rows(tmpdir_mod)
          if r["fixture_id"] == "NETC-C05-AZ-DUP" and r["control"] == "c3_full"}
    assert set(st.values()) == {"REFUSED"}


# --------------------------------------------------------------------------------------------- transporte

def test_carry_without_claim_is_unproven(cs):
    o = CY.carry(cs, "aws:aws_security_group_rule:protocol", "tcp", "google:google_compute_firewall:priority")
    assert o.result == "blocked" and o.code == "UNPROVEN"


def test_carry_sentinel_any_address(cs):
    o = CY.carry(cs, "azurerm:azurerm_network_security_rule:source_address_prefix", "*",
                 "google:google_compute_firewall:source_ranges")
    assert o.ok and o.value == "0.0.0.0/0"


def test_effective_set_subtraction_matches_brute_force():
    allow = ("ingress", "tcp", (20, 30), "10.0.0.0/24")
    deny = ("ingress", "tcp", (25, 26), "10.0.0.128/25")
    parts = TR._sub(allow, deny)
    ips = [str(ipaddress.ip_address("10.0.0.0") + i) for i in range(0, 256, 7)]
    for ip, port in itertools.product(ips, range(18, 33)):
        in_a = 20 <= port <= 30 and ipaddress.ip_address(ip) in ipaddress.ip_network("10.0.0.0/24")
        in_d = 25 <= port <= 26 and ipaddress.ip_address(ip) in ipaddress.ip_network("10.0.0.128/25")
        got = any(p[2][0] <= port <= p[2][1] and ipaddress.ip_address(ip) in ipaddress.ip_network(p[3]) for p in parts)
        assert got == (in_a and not in_d), (ip, port)


def test_loss_policy_is_closed():
    d = LP.declared([{"code": "STATE_NOT_EXPRESSIBLE", "field": "state", "detail": "x"}],
                    [{"flow_id": "f1", "state": "new"}, {"flow_id": "f1r", "state": "return"}])
    assert d == [{"loss_id": "LOSS-NET-STATE", "flows": ["f1r"], "from_codes": ["STATE_NOT_EXPRESSIBLE"]}]
    with pytest.raises(ValueError):
        LP.declared([{"code": "INVENTADO", "field": "x", "detail": "x"}], [])


def test_no_silent_insert_catches_mutations(run, tmpdir_mod):
    from bo.pilot_net_e2e import no_silent_insert as NSI
    out = tmpdir_mod / "run"
    plans = {p["plan_id"]: p for p in map(json.loads, (out / "lowering_plan.jsonl").read_text().splitlines())}
    r = next(r for r in rows(tmpdir_mod) if r["render_status"] == "RENDERED")
    files = {p.name: p.read_text() for p in (out / "hcl" / r["case_id"]).glob("*.tf")}
    prov = r["direction"].split("->")[1]
    assert NSI.check_case(plans[r["plan_id"]], files, prov) == []
    assert all(m["caught"] for m in NSI.mutations(plans[r["plan_id"]], files, prov))


def test_oci_attachment_renders_as_list_term(run, tmpdir_mod):
    """C00 3.1.0 (termo list) + HARNESS-OCI e2e0133: as direções x -> oci renderizam (antes, CC-NET-E2E-1)."""
    oci = [r for r in rows(tmpdir_mod) if r["direction"].endswith("->oci") and r["translate_status"] == "TRANSLATED"]
    assert oci and all(r["render_status"] == "RENDERED" for r in oci)
    plans = [json.loads(l) for l in (tmpdir_mod / "run" / "lowering_plan.jsonl").read_text().splitlines()]
    sub = [v for p in plans if p["target_provider"] == "oci" for st in p["steps"] for v in st["values"]
           if v["field"] == "security_list_ids"]
    assert sub and all(v["term"]["kind"] == "list" for v in sub)


def test_every_carried_plan_value_has_a_trace(run, tmpdir_mod):
    """E1: todo valor 'carried' do plano tem traço C23 carried com o mesmo átomo de saída."""
    out = tmpdir_mod / "run"
    carried = {}
    for l in (out / "translation_trace.jsonl").read_text().splitlines():
        t = json.loads(l)
        if t["result"] == "carried":
            carried.setdefault(t["case_id"], set()).add(t["output"]["atom_id"])
    import re
    for r in rows(tmpdir_mod):
        if not r["plan_id"]:
            continue
    plans = {p["plan_id"]: p for p in map(json.loads, (out / "lowering_plan.jsonl").read_text().splitlines())}
    for r in rows(tmpdir_mod):
        p = plans.get(r["plan_id"])
        for st in (p or {}).get("steps", []):
            for v in st["values"]:
                if v["origin"] == "carried":
                    f = re.sub(r"\.[0-9]+(?=\.|$)", "", v["field"])
                    assert f"{p['target_provider']}:{st['resource_type']}:{f}" in carried.get(r["case_id"], set()), \
                        (r["case_id"], v["field"])
