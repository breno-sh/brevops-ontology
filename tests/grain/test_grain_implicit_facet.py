"""Faceta implícita (emenda 0.1.8, T57): só com fato da spec de operação única sobre o pai.

Embutido: os blocos de regra pendem direto do contêiner. Separado: o recurso de configuração é FACET do
contêiner e as regras pendem dele. Com o fato da spec (a API só aceita as regras como membros de UM objeto-faceta,
configurado por UMA operação sobre o pai), a forma embutida ganha a faceta implícita e as duas formas dão a mesma
estrutura. Controles negativos: sem a operação citada, ou com operação própria do bloco, não há faceta implícita.
"""

import copy
import json
import os
import subprocess
import sys

import pytest

from bo.grain import battery as B
from bo.grain import fixtures as F
from bo.grain import realdata as RD
from bo.grain import rules as R
from bo.grain import schema as S
from bo.grain.common import data_root
from bo.grain.evidence import C25Adapter

RS = R.load()
P = "provider_w"


def _fact(eid, rt, kind, value, bp=None):
    r = {"evidence_id": eid, "provider": P, "pin": {"provider_version": "0.0.1"},
         "api_resource": {"service": "s", "resource": "x"}, "terraform_resource_type": rt, "fact_kind": kind,
         "status": "stated", "level": "published", "doc": {"repo": "spec/example", "tag": "v1", "file": "spec.json",
                                                            "line": 1, "sentence": "frase sintética da spec"},
         "value": value}
    if bp:
        r["block_path"] = bp
    return r


IMPLICIT = {"aspect": "spec_facet_member", "facet": "lifecycle_configuration", "facet_resource": "LifecycleConfiguration",
            "operation": "PutLifecycleConfiguration", "member": "Rules", "parent_resource": "Container",
            "single_operation": True}


def world(implicit=True, own_op=False, with_op=True):
    schema = {"w_box": F.res(["name"], {"rule": F.blk(["id", "days"], nesting="list")}),
              "w_box_lc": F.res(["box"], {"rule": F.blk(["id", "days"], nesting="list")})}
    ev = {"w_box": F.ev_entity("Container", "box_name", "name", service="s", resource="Container", tag="box"),
          "w_box.rule": F.ev_element("LifecycleRule", "rule_id", "id", {"days": ("days", "int")}, tag="r"),
          "w_box_lc": F.ev_aspect("LifecycleConfiguration", {}, via="box", ref_field="box", ref_target="w_box",
                                  tag="lc"),
          "w_box_lc.rule": F.ev_element("LifecycleRule", "rule_id", "id", {"days": ("days", "int")}, tag="r")}
    if implicit:
        imp = dict(IMPLICIT)
        if not with_op:
            imp.pop("operation")
        recs = [_fact("SE-w1", "w_box", "identity", imp, bp="rule")]
        if own_op:
            recs.append(_fact("SE-w2", "w_box", "lifecycle_controller",
                              {"aspect": "spec_operation", "operation": "CreateRule", "role": "create"}, bp="rule"))
        tr = C25Adapter(recs).by_cid.get("w_box.rule", {})
        if tr.get("implicit_facet"):
            ev["w_box.rule"] = dict(ev["w_box.rule"], implicit_facet=tr["implicit_facet"])
    return {"provider": P, "schema": schema, "evidence": ev}


def test_implicit_facet_makes_inline_equal_separate():
    res = B.run_schema(world(), RS)
    fid = "w_box:lifecycle_configuration"
    d = res.decisions[fid]
    assert d.grain == "FACET" and d.parent == "w_box" and d.label == "LifecycleConfiguration"
    assert res.decisions["w_box.rule"].parent == fid
    assert S.signature(res, ["w_box", "w_box.rule"]) == S.signature(res, ["w_box", "w_box_lc.rule"])
    u = next(x for x in S.to_c19(res)[0] if x["unit_id"] == f"CU-{P}-{fid}")
    ev = [e for e in u["evidence"] if e.get("ref") == "implicit=true"]
    assert ev and "PutLifecycleConfiguration" in ev[0]["note"] and "SE-w1" in ev[0]["note"]
    assert any(e.get("ref") == "SE-w1" for e in u["evidence"])          # a citação da spec vai junto


def test_implicit_facet_id_is_deterministic():
    a = [u["unit_id"] for u in S.to_c19(B.run_schema(world(), RS))[0]]
    b = [u["unit_id"] for u in S.to_c19(B.run_schema(world(), RS))[0]]
    assert a == b and f"CU-{P}-w_box:lifecycle_configuration" in a


@pytest.mark.parametrize("kw", [{"implicit": False}, {"with_op": False}, {"own_op": True}])
def test_no_implicit_facet_without_single_operation_or_with_own_operation(kw):
    res = B.run_schema(world(**kw), RS)
    assert "w_box:lifecycle_configuration" not in res.decisions
    assert res.decisions["w_box.rule"].parent == "w_box"
    assert S.signature(res, ["w_box", "w_box.rule"]) != S.signature(res, ["w_box", "w_box_lc.rule"])


def test_implicit_facet_c19_validates(tmp_path):
    units, atoms = S.to_c19(B.run_schema(world(), RS))
    pu, pa = tmp_path / "canonical_units.jsonl", tmp_path / "canonical_atoms.jsonl"
    pu.write_text("".join(json.dumps(u) + "\n" for u in units))
    pa.write_text("".join(json.dumps(a) + "\n" for a in atoms))
    r = subprocess.run([sys.executable, "-I", "-m", "bo.contracts.validate", "C19", str(pu), str(pa)],
                       capture_output=True, text=True, env=dict(os.environ))
    assert r.returncode == 0, r.stdout[-1500:]


def test_implicit_facet_real_s3():
    """No dado real (S3), o SERVICE-EVIDENCE emite spec_facet_member para o lifecycle_rule embutido
    (PutBucketLifecycleConfiguration{Rules} sobre Bucket): o bloco pende da faceta implícita, com o mesmo rótulo de
    API da faceta separada. Sem esse fato, não há faceta implícita."""
    p = data_root() / "SERVICE-EVIDENCE" / "service_evidence.jsonl"
    assert p.is_file()
    recs = RD.load_evidence(p)
    sl = {"aws": ["aws_s3_bucket", "aws_s3_bucket_lifecycle_configuration"]}
    res = RD.run(slice_types=sl, records=recs)["providers"]["aws"]["_res"]
    par = res.nodes["aws_s3_bucket.lifecycle_rule"].parent                # pai estrutural (o grão vem do gêmeo)
    assert par and par.startswith("aws_s3_bucket:") and res.decisions[par].grain == "FACET"
    assert res.decisions[par].label == res.decisions["aws_s3_bucket_lifecycle_configuration"].label
    no = [r for r in recs if not (isinstance(r.get("value"), dict) and r["value"].get("aspect") == "spec_facet_member"
                                   and r.get("terraform_resource_type") == "aws_s3_bucket")]
    res2 = RD.run(slice_types=sl, records=no)["providers"]["aws"]["_res"]
    assert res2.nodes["aws_s3_bucket.lifecycle_rule"].parent == "aws_s3_bucket"
