"""Integração com DADO REAL: decompose_schema sobre o service_evidence.jsonl do SERVICE-EVIDENCE e os átomos
C01 do SCHEMA-*, para os tipos da fatia sto (a mesma do PILOT-STO-GLOSS). É o teste que faltava (CC-1): os
testes sintéticos usavam a convenção do próprio GRAIN e não pegaram que o arquivo real vem por aspecto.

Sem os arquivos o teste REPROVA (não pula): passar por vacuidade seria verde falso.
"""

import copy
import json
import os
import subprocess
import sys

import pytest

from bo.grain import realdata as RD
from bo.grain import rules as R
from bo.grain import relations as REL
from bo.grain import schema as S
from bo.grain.common import data_root
from bo.grain.evidence import C25Adapter

SE = data_root() / "SERVICE-EVIDENCE" / "service_evidence.jsonl"


@pytest.fixture(scope="module")
def records():
    assert SE.is_file(), f"dado real ausente: {SE}"
    return RD.load_evidence(SE)


@pytest.fixture(scope="module")
def real(records):
    return RD.run(records=records)


def test_no_evidence_error_and_every_candidate_decided(real):
    for prov, p in real["providers"].items():
        assert p["candidates"] > 0 and p["evidence_records"] > 0, prov
        ood = p["_res"].out_of_domain
        assert sum(p["grains"].values()) == p["candidates"] - len(ood), prov
        assert all(c.endswith(".timeouts") or ".timeouts." in c for c in ood), ood   # T45: só configuração do Terraform
        for cid, d in p["top_level"].items():
            assert d is not None, f"{prov}: {cid} sem candidato"
        for u in p["_units"]:
            if u["kind"] == "UNKNOWN":
                assert u["missing_evidence"] and u["rule_applied"].startswith("GRAIN-G0-"), u["unit_id"]


def test_container_of_each_provider_is_decided_with_traceable_reasons(real):
    """Cada provedor decide o contêiner: há registro C19 com grão e regra. Onde o grão é UNKNOWN, cada campo
    que falta tem motivo rastreável a um fato do SERVICE-EVIDENCE (aspecto sem tradução ou status unknown)."""
    for prov, p in real["providers"].items():
        c = p["container"]
        assert c["grain"] in R.GRAINS and c["rule"].startswith("GRAIN-"), (prov, c)
        if c["grain"] == "UNKNOWN":
            fields = {r.split(":")[0] for r in c["reasons"]}
            for m in c["missing"]:
                assert m in fields or m == "identity" and c["identity_class"] in ("UNRESOLVED", "ABSENT", "ORPHAN"), \
                    (prov, m, c["reasons"])


def test_nested_blocks_never_facet_by_omission(real):
    for prov, p in real["providers"].items():
        for cid, d in p["nested_facet_like"].items():
            pytest.fail(f"{prov}: {cid} saiu FACET sem fato de aspecto da API para o bloco: {d}")


def test_real_c19_validates(real, tmp_path):
    units = [u for p in real["providers"].values() for u in p["_units"]]
    atoms = [a for p in real["providers"].values() for a in p["_atoms"]]
    pu, pa = tmp_path / "canonical_units.jsonl", tmp_path / "canonical_atoms.jsonl"
    pu.write_text("".join(json.dumps(u) + "\n" for u in units))
    pa.write_text("".join(json.dumps(a) + "\n" for a in atoms))
    r = subprocess.run([sys.executable, "-I", "-m", "bo.contracts.validate", "C19", str(pu), str(pa)],
                       capture_output=True, text=True, env=dict(os.environ))
    assert r.returncode == 0, r.stdout[-2000:] + r.stderr[-2000:]


def _fact(eid, prov, rt, kind, value):
    return {"evidence_id": eid, "provider": prov, "pin": {"provider_version": "0.0.1"},
            "api_resource": {"service": "UNKNOWN", "resource": "UNKNOWN"}, "terraform_resource_type": rt,
            "fact_kind": kind, "status": "stated", "level": "derived", "derived_from": ["SE-controle"], "value": value}


def test_positive_control_decides_when_the_missing_facts_exist(records):
    """Controle positivo no dado real: acrescentando SÓ os fatos que faltam (marcados como controle), o mesmo
    caminho decide o contêiner (ENTITY) e a configuração separada de versionamento (FACET do contêiner).
    Mostra que o UNKNOWN acima vem da evidência, não do adaptador."""
    extra = [
        _fact("SE-ctl-01", "aws", "aws_s3_bucket", "identity", {"aspect": "api_resource_bridge",
                                                                  "resource": "Bucket", "service": "s3"}),
        _fact("SE-ctl-02", "aws", "aws_s3_bucket", "lifecycle_controller", "self"),
        _fact("SE-ctl-03", "aws", "aws_s3_bucket", "owner", "self"),
        _fact("SE-ctl-04", "aws", "aws_s3_bucket", "effective_scope", "self"),
        _fact("SE-ctl-05", "aws", "aws_s3_bucket_versioning", "owner", {"kind": "parent", "via": "bucket"}),
        _fact("SE-ctl-06", "aws", "aws_s3_bucket_versioning", "effective_scope", {"kind": "parent", "via": "bucket"}),
    ]
    sl = {"aws": ["aws_s3_bucket", "aws_s3_bucket_versioning"]}
    rep = RD.run(slice_types=sl, records=list(records) + extra)
    top = rep["providers"]["aws"]["top_level"]
    assert top["aws_s3_bucket"]["grain"] == "ENTITY", top["aws_s3_bucket"]
    v = top["aws_s3_bucket_versioning"]
    assert v["grain"] == "FACET" and v["identity_class"] == "BORROWED", v
    # e sem o fato de ciclo de vida do contêiner, volta a UNKNOWN (não há default)
    # (o SERVICE-EVIDENCE já publica o ciclo de vida de API do contêiner: tira-se esse fato também)
    no_lc = [r for r in records if not (r.get("terraform_resource_type") == "aws_s3_bucket"
                                        and r.get("fact_kind") == "lifecycle_controller")]
    rep2 = RD.run(slice_types=sl, records=no_lc + [e for e in extra if e["evidence_id"] != "SE-ctl-02"])
    assert rep2["providers"]["aws"]["top_level"]["aws_s3_bucket"]["grain"] == "UNKNOWN"


def test_identity_scope_never_becomes_config_owner(records):
    """owner/identity_scope diz quem é dono da IDENTIDADE: nunca vira owner da configuração."""
    recs = [r for r in records if r.get("provider") == "aws" and r.get("terraform_resource_type") == "aws_s3_bucket"]
    assert any((r.get("value") or {}).get("aspect") == "identity_scope" for r in recs if isinstance(r.get("value"),
                                                                                                    dict))
    only_scope = [r for r in recs if r.get("fact_kind") == "owner" and isinstance(r.get("value"), dict)
                  and r["value"].get("aspect") == "identity_scope"]
    ev = C25Adapter(only_scope).evidence("aws_s3_bucket")
    assert ev.fact("owner").state != "KNOWN"
    # e com a spec (R-OWN-SPEC, camada de API) o dono é o próprio contêiner
    assert C25Adapter(recs).evidence("aws_s3_bucket").fact("owner").value["kind"] == "self"


def test_suspend_destroy_effect_means_facet_of_parent():
    rec = _fact("SE-ctl-10", "aws", "x_versioning_like", "lifecycle_controller",
                {"aspect": "destroy_effect", "effect": "suspend"})
    ev = C25Adapter([rec]).evidence("x_versioning_like")
    assert ev.fact("lifecycle_controller").value["kind"] == "parent"
    assert ev.fact("api_resource").value["status"] == "aspect"
    for eff in ("not_deleted", "state_only"):
        r2 = copy.deepcopy(rec)
        r2["value"]["effect"] = eff
        assert C25Adapter([r2]).evidence("x_versioning_like").fact("lifecycle_controller").state == "UNKNOWN"


def test_c25_1_1_forms_record_block_path_and_api_bridge():
    """C25 1.1.0: block_path no registro (não em value) e fact_kind api_bridge são lidos como os anteriores."""
    def f(eid, kind, value, bp=None):
        r = _fact(eid, "aws", "x_store", kind, value)
        if bp:
            r["block_path"] = bp
        return r
    recs = [
        f("SE-n1", "identity", {"aspect": "block_identity", "schema_identity": "absent", "key_fields": [],
                                "element_name_candidates": []}, bp="versioning"),
        f("SE-n2", "owner", {"aspect": "block_config_owner", "kind": "parent", "via": "x_store", "layer": "terraform"},
          bp="versioning"),
        f("SE-n3", "api_bridge", {"resource": "Store", "service": "objstore"}),
    ]
    ad = C25Adapter(recs)
    blk = ad.evidence("x_store.versioning")
    assert blk.fact("identity").value == {"status": "absent"}
    assert blk.fact("owner").value["kind"] == "parent"
    assert ad.evidence("x_store").fact("api_resource").value["resource"] == "Store"


def test_cc1d_translate_whole_real_file_every_provider(records):
    """CC-1d: a tradução roda sobre TODOS os fatos reais de cada provedor (antes, TypeError no azurerm na T09)."""
    from bo.grain import c25_aspects as A
    by = {}
    for r in records:
        by.setdefault(r.get("provider"), []).append(r)
    for prov, recs in sorted(by.items()):
        ev, why = A.translate(recs)
        assert ev, prov


def test_cc1d_twin_with_list_via():
    from bo.grain import c25_aspects as A
    recs = [_fact("SE-v1", "aws", "x_rule", "identity", {"aspect": "reference_target", "attribute": "set_id",
                                                         "resolved": "x_set", "target_types": ["x_set"]}),
            _fact("SE-v2", "aws", "x_rule", "owner", {"kind": "parent", "via": ["set_id", "other_id"]}),
            _fact("SE-v3", "aws", "x_set", "identity", {"aspect": "twin_type", "twin": "x_rule"})]
    recs[2]["block_path"] = "rule"
    ev, _ = A.translate(recs)
    assert ev["x_set.rule"]["owner"][0]["via"] == ["$parent", "other_id"]


def test_cc1e_api_layer_accepted_terraform_layer_refused():
    def run(layer, kind):
        return C25Adapter([_fact("SE-l1", "aws", "x_t", kind, {"kind": "self", "layer": layer, "rule": "R"})]) \
            .evidence("x_t").fact(kind).state
    for k in ("owner", "lifecycle_controller", "effective_scope"):
        assert run("api", k) == "KNOWN"
        assert run("terraform", k) == "UNKNOWN"


def test_cc1e_attachment_scope():
    ad = C25Adapter([_fact("SE-a1", "aws", "x_acl", "effective_scope",
                           {"aspect": "attachment_scope", "attribute": "subnet_ids", "applies_to": "subnets"})])
    ev = ad.evidence("x_acl")
    assert ev.fact("effective_scope").value["kind"] == "self"
    assert ev.field_map["subnet_ids"]["ref"] is True


def test_cc8_spec_disputes_are_contradictory(records):
    """CC-8: as disputas spec × doc do SERVICE-EVIDENCE viram campo CONTRADITÓRIO (nem decisão, nem escolha)."""
    import json as _j
    from bo.grain.common import repo
    p = repo() / "results" / "SERVICE-EVIDENCE" / "spec_disputes.json"
    assert p.is_file(), p
    disputes = _j.loads(p.read_text())["disputes"]
    assert disputes
    by = {}
    for r in records:
        by.setdefault((r.get("provider"), r.get("terraform_resource_type")), []).append(r)
    for d in disputes:
        fld = "api_resource" if d["fact"] == "api_bridge" else d["fact"]
        ev = C25Adapter(by[(d["provider"], d["terraform_resource_type"])]).evidence(d["terraform_resource_type"])
        assert ev.fact(fld).state == "CONTRADICTORY", d


def test_cc8_s3_container_and_facet_from_spec(records):
    """CC-8: com a spec, o contêiner da AWS é ENTITY e o bloqueio de acesso público separado é FACET dele."""
    rep = RD.run(slice_types={"aws": RD.STO_SLICE["aws"]}, records=records)
    top = rep["providers"]["aws"]["top_level"]
    assert top["aws_s3_bucket"]["grain"] == "ENTITY"
    assert top["aws_s3_bucket_public_access_block"]["grain"] == "FACET"
    for c in ("aws_s3_bucket_versioning", "aws_s3_bucket_policy", "aws_s3_bucket_acl"):
        assert top[c]["identity_class"] == "BORROWED", (c, top[c])     # ligado ao contêiner pela chave bucket


def test_t51_external_container_real_azure(records):
    """T51: pai fora da fatia (grupo de recursos) é contêiner externo referenciado: a identidade resolve, sem
    exigir o pai na decomposição. O que faltar depois é evidência, não a fatia."""
    rep = RD.run(slice_types={"azurerm": ["azurerm_network_security_group", "azurerm_storage_account"]},
                 records=records)
    res = rep["providers"]["azurerm"]["_res"]
    for cid in ("azurerm_network_security_group", "azurerm_storage_account"):
        n, d = res.nodes[cid], res.decisions[cid]
        assert n.ref_targets.get("resource_group_name") == "EXT:azurerm_resource_group", n.ref_targets
        assert d.identity.cls == "WITHIN" and "identity" not in d.missing, (cid, d.identity.cls, d.missing)
    units, _ = S.to_c19(res)
    assert all("CU-azurerm-azurerm_resource_group" not in json.dumps(u["unit_id"]) for u in units)


def test_t51_external_parent_grain_needed_only_when_rule_reads_it():
    from bo.grain import fixtures as F
    from bo.grain import rules as R2
    rs = R2.load()
    # componente de um contêiner externo: G2 não lê o grão do pai -> decide
    comp = F.ev_element("rule", "nm", "name", {}, via="set_id", ref_field="set_id", ref_target="z_set_outside")
    # faceta de um dono externo: G3 lê o grão do dono -> UNKNOWN
    fac = F.ev_aspect("setting", {}, via="set_id", ref_field="set_id", ref_target="z_set_outside")
    w = {"provider": "provider_z", "schema": {"z_rule": F.res(["set_id", "name"]), "z_setting": F.res(["set_id"])},
         "evidence": {"z_rule": comp, "z_setting": fac}}
    from bo.grain import battery as B
    d = B.run_schema(w, rs).decisions
    assert d["z_rule"].grain == "COMPONENT" and d["z_rule"].parent == "EXT:z_set_outside"
    assert d["z_setting"].grain == "UNKNOWN" and "owner" in d["z_setting"].missing
    units, _ = S.to_c19(B.run_schema(w, rs))
    r = next(u for u in units if u["unit_id"].endswith("z_rule"))
    assert r["lifecycle_controller"]["ref"] == "CU-provider_z-z_set_outside"


def test_g4ns_real_azure_namespace_entity_with_cascade(records):
    """G4-NS (0.1.6): identidade qualificada pelo grupo de recursos (marca de namespace: owner/parent com
    scope_kind resource_group) + ciclo de vida de API self = ENTITY; o grupo vira cascade_delete_by."""
    rep = RD.run(slice_types={"azurerm": ["azurerm_network_security_group", "azurerm_storage_account"]},
                 records=records)
    res = rep["providers"]["azurerm"]["_res"]
    units = {u["unit_id"]: u for u in S.to_c19(res)[0]}
    for cid in ("azurerm_network_security_group", "azurerm_storage_account"):
        d = res.decisions[cid]
        assert d.grain == "ENTITY" and d.rule == "GRAIN-G4-NS", (cid, d.grain, d.rule, d.missing)
        assert d.cascade == ["EXT:azurerm_resource_group"] and d.parent is None
        assert d.owner["kind"] == "self" and d.lifecycle["kind"] == "self"
        u = units[f"CU-azurerm-{cid}"]
        assert any(e.get("ref") == "cascade_delete_by=CU-azurerm-azurerm_resource_group" for e in u["evidence"])
    rels, errs = REL.relations(res, ["azurerm_network_security_group"])
    assert not errs and any(h == "cascade_delete_by" for _, h, _ in rels)


def test_g4ns_without_namespace_mark_stays_unknown(records):
    """Sem a marca de namespace (tira o fato owner/parent do grupo), a mesma unidade segue UNKNOWN."""
    recs = [r for r in records if not (r.get("terraform_resource_type") == "azurerm_network_security_group"
                                       and isinstance(r.get("value"), dict) and r["value"].get("aspect") == "parent")]
    rep = RD.run(slice_types={"azurerm": ["azurerm_network_security_group"]}, records=recs)
    d = rep["providers"]["azurerm"]["_res"].decisions["azurerm_network_security_group"]
    assert d.grain != "ENTITY", (d.grain, d.rule)


def test_g4ns_negative_control_true_facet_never_entity(records):
    """Controle negativo: faceta verdadeira (ciclo de vida do pai) não vira ENTITY, nem com marca de namespace."""
    rep = RD.run(slice_types={"aws": RD.STO_SLICE["aws"]}, records=records)
    for c, d in rep["providers"]["aws"]["top_level"].items():
        if c != "aws_s3_bucket":
            assert d["grain"] != "ENTITY", (c, d)
    from bo.grain import battery as B
    from bo.grain import fixtures as F
    from bo.grain import rules as R2
    fac = F.ev_aspect("setting", {}, via="grp", ref_field="grp", ref_target="z_grp_outside")
    fac["field_map"]["grp"]["namespace"] = True
    fac["identity"] = [F.c(status="present", scope="within_parent", key_fields=["nm", "grp"], tag="ns")]
    fac["field_map"]["nm"] = {"path": "name", "norm": "str"}
    fac["api_resource"] = [F.c(status="resource", label="setting", service="s", resource="Setting", tag="ns")]
    w = {"provider": "provider_z", "schema": {"z_setting": F.res(["grp", "name"])}, "evidence": {"z_setting": fac}}
    d = B.run_schema(w, R2.load()).decisions["z_setting"]
    assert d.grain != "ENTITY", (d.grain, d.rule)
    fac["lifecycle_controller"] = [F.c(kind="self", tag="ns")]
    fac["owner"] = [F.c(kind="self", tag="ns")]
    fac["effective_scope"] = [F.c(kind="self", tag="ns")]
    d2 = B.run_schema(w, R2.load()).decisions["z_setting"]
    assert d2.grain == "ENTITY" and d2.rule == "GRAIN-G4-NS"            # o mesmo, com ciclo de vida self: entidade
