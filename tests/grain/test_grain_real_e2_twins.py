"""E2 com DADO REAL (CC-1b): regra embutida = regra separada, para SG ingress, SG egress e NSG security_rule.

O SERVICE-EVIDENCE liga o bloco embutido ao tipo gêmeo (twin_type) e dá o alvo das referências
(reference_target). Pela T09 o bloco herda a evidência de API do gêmeo; a referência do gêmeo ao tipo do bloco
vira o pai estrutural. Confere, só com o arquivo real: mesma assinatura (grão, regra, o que falta, chave, rótulo)
e mesmas relações; o bloco timeouts fica fora do domínio. Depois, um controle que acrescenta SÓ ao tipo gêmeo e
ao contêiner os fatos que faltam: o bloco, sem nenhum fato novo próprio, decide igual ao separado (COMPONENT do
contêiner, relação de pai). Sem os arquivos reais, reprova.
"""

import pytest

from bo.grain import realdata as RD
from bo.grain import relations as REL
from bo.grain import schema as S
from bo.grain.common import data_root

PAIRS = [("aws", "aws_security_group", "aws_security_group.ingress", "aws_vpc_security_group_ingress_rule",
          "security_group_id"),
         ("aws", "aws_security_group", "aws_security_group.egress", "aws_vpc_security_group_egress_rule",
          "security_group_id"),
         ("azurerm", "azurerm_network_security_group", "azurerm_network_security_group.security_rule",
          "azurerm_network_security_rule", "network_security_group_name")]
SLICE = {"aws": ["aws_security_group", "aws_vpc_security_group_ingress_rule", "aws_vpc_security_group_egress_rule"],
         "azurerm": ["azurerm_network_security_group", "azurerm_network_security_rule"]}


@pytest.fixture(scope="module")
def records():
    p = data_root() / "SERVICE-EVIDENCE" / "service_evidence.jsonl"
    assert p.is_file(), f"dado real ausente: {p}"
    recs = RD.load_evidence(p)
    assert any((r.get("value") or {}).get("aspect") == "twin_type" for r in recs if isinstance(r.get("value"), dict))
    return recs


@pytest.fixture(scope="module")
def real(records):
    return RD.run(slice_types=SLICE, records=records)


def _rel(res, top, cid):
    rels, errs = REL.relations(res, [top, cid])
    lab = res.decisions[cid].label
    return [(h.split(":")[0], b) for a, h, b in rels if a and a[-1] == lab], errs


@pytest.mark.parametrize("prov,top,inline,sep,ref", PAIRS)
def test_e2_real_inline_equals_standalone(real, prov, top, inline, sep, ref):
    res = real["providers"][prov]["_res"]
    assert res.candidates[inline].virtual or res.candidates[inline].block_path
    assert res.nodes[inline].ev.twin == sep
    a, b = res.decisions[inline], res.decisions[sep]
    assert (a.grain, a.rule, a.missing, a.label) == (b.grain, b.rule, b.missing, b.label)
    assert S.signature(res, [top, inline]) == S.signature(res, [top, sep])
    assert _rel(res, top, inline) == _rel(res, top, sep)
    assert f"{top}.timeouts" in res.out_of_domain and f"{top}.timeouts" not in res.decisions


def _fact(eid, prov, rt, kind, value):
    return {"evidence_id": eid, "provider": prov, "pin": {"provider_version": "0.0.1"},
            "api_resource": {"service": "x", "resource": "x"}, "terraform_resource_type": rt, "fact_kind": kind,
            "status": "stated", "level": "derived", "derived_from": ["SE-controle"], "value": value}


@pytest.mark.parametrize("prov,top,inline,sep,ref", PAIRS)
def test_e2_control_twin_facts_decide_both(records, prov, top, inline, sep, ref):
    extra = [_fact("SE-t1", prov, top, "lifecycle_controller", "self"), _fact("SE-t2", prov, top, "owner", "self"),
             _fact("SE-t3", prov, top, "effective_scope", "self"),
             _fact("SE-t4", prov, top, "api_bridge", {"resource": "RuleSet", "service": "net"}),
             _fact("SE-t5", prov, sep, "lifecycle_controller", {"kind": "parent", "via": ref}),
             _fact("SE-t6", prov, sep, "owner", {"kind": "parent", "via": ref}),
             _fact("SE-t7", prov, sep, "effective_scope", {"kind": "parent", "via": ref})]
    # o controle SUBSTITUI os fatos de api, ciclo de vida, dono e alcance do contêiner e do separado
    drop = {(k, x) for k in ("api_bridge", "lifecycle_controller", "owner", "effective_scope") for x in (top, sep)}
    recs = [r for r in records if r.get("provider") == prov and (r["fact_kind"], r.get("terraform_resource_type"))
            not in drop]
    if prov == "azurerm":   # o contêiner do NSG (grupo de recursos) não está na fatia: a identidade fica sem alvo
        recs = [r for r in recs if not (r.get("terraform_resource_type") in (top, sep) and isinstance(r.get("value"),
                dict) and r["value"].get("attribute") == "resource_group_name")]
        recs = [r for r in recs if not (r.get("terraform_resource_type") == top and isinstance(r.get("value"), dict)
                                        and r["value"].get("aspect") == "parent")]
        extra.append(_fact("SE-t8", prov, top, "identity", {"status": "present", "scope": "independent",
                                                            "key_fields": ["name", "resource_group_name"]}))
        recs = [r for r in recs if not (r.get("terraform_resource_type") == top and isinstance(r.get("value"), dict)
                                        and r["value"].get("aspect") == "resource_identity_schema")]
    rep = RD.run(slice_types={prov: SLICE[prov]}, records=recs + extra)
    res = rep["providers"][prov]["_res"]
    a, b = res.decisions[inline], res.decisions[sep]
    assert b.grain == "COMPONENT" and b.parent == top, (b.grain, b.rule, b.missing, b.identity.cls)
    assert (a.grain, a.rule, a.missing, a.parent) == (b.grain, b.rule, b.missing, b.parent)
    assert S.signature(res, [top, inline]) == S.signature(res, [top, sep])
    ra, rb = _rel(res, top, inline), _rel(res, top, sep)
    assert not ra[1] and not rb[1] and ra[0] == rb[0] and ("parent", (res.decisions[top].label,)) in ra[0]


@pytest.mark.parametrize("prov,top,inline,sep,ref", PAIRS)
def test_e2_real_decided_component_both_sides(real, prov, top, inline, sep, ref):
    """Com os fatos de API da regra (SE ce1e590: spec da AWS; G2-CHILD no Azure), embutido e separado decidem
    COMPONENT do conjunto, com o mesmo pai, e não iguais em UNKNOWN."""
    res = real["providers"][prov]["_res"]
    a, b = res.decisions[inline], res.decisions[sep]
    assert a.grain == b.grain == "COMPONENT" and a.parent == b.parent == top, (a.grain, a.missing, b.grain, b.missing)


def test_e2_sto_lifecycle_rule_pairing_descends_to_block(records):
    """E2 STO: o lifecycle_rule embutido corresponde ao bloco rule DENTRO do recurso separado (a faceta do conjunto
    de regras). O SERVICE-EVIDENCE (iteração 2) declara o gêmeo com twin_block_path: o par desce ao bloco."""
    sl = {"aws": ["aws_s3_bucket", "aws_s3_bucket_lifecycle_configuration"]}
    res = RD.run(slice_types=sl, records=records)["providers"]["aws"]["_res"]
    assert res.decisions["aws_s3_bucket_lifecycle_configuration"].grain == "FACET"
    p = RD.e2_pair(res, "aws_s3_bucket.lifecycle_rule", "aws_s3_bucket_lifecycle_configuration")
    assert p["separate"] == "aws_s3_bucket_lifecycle_configuration.rule", p
    a, b = p["inline_sig"], p["separate_sig"]
    # com a faceta implícita (spec_facet_member), o pai dos dois é uma FACET; o resto da assinatura de bloco é
    # herdado do gêmeo (T09), então só diverge se o bloco gêmeo tiver evidência própria diferente
    assert a == b, (a, b)


def test_e2_sto_lifecycle_rule_full_path_equal(records):
    """Com a faceta implícita (T57) e o gêmeo de bloco (T09), o caminho completo também é igual:
    contêiner → configuração de ciclo de vida (FACET) → regra (COMPONENT), embutido e separado."""
    sl = {"aws": ["aws_s3_bucket", "aws_s3_bucket_lifecycle_configuration"]}
    res = RD.run(slice_types=sl, records=records)["providers"]["aws"]["_res"]
    a = S.signature(res, ["aws_s3_bucket", "aws_s3_bucket.lifecycle_rule"])
    b = S.signature(res, ["aws_s3_bucket", "aws_s3_bucket_lifecycle_configuration.rule"])
    assert a == b and any(r[0] == "COMPONENT" for r in a), (a, b)
