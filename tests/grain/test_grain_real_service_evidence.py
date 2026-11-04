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
    rep2 = RD.run(slice_types=sl, records=list(records) + [e for e in extra if e["evidence_id"] != "SE-ctl-02"])
    assert rep2["providers"]["aws"]["top_level"]["aws_s3_bucket"]["grain"] == "UNKNOWN"


def test_identity_scope_never_becomes_config_owner(records):
    """owner/identity_scope diz quem é dono da IDENTIDADE: nunca vira owner da configuração."""
    recs = [r for r in records if r.get("provider") == "aws" and r.get("terraform_resource_type") == "aws_s3_bucket"]
    assert any((r.get("value") or {}).get("aspect") == "identity_scope" for r in recs if isinstance(r.get("value"),
                                                                                                    dict))
    ev = C25Adapter(recs).evidence("aws_s3_bucket")
    assert ev.fact("owner").state != "KNOWN"


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
