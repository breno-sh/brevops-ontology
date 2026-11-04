"""Alegações por direção: espelho SKOS, inversa do registro, veredito e versão."""
from bo.pilot.sto import claims as CL
from bo.pilot.sto import lift as L
from bo.pilot.sto import translate as TR

import synth


def _lf(fx, cs, ev):
    return L.lift(fx, cs, ev)


def test_mirror_and_orientation():
    rows, ver = synth.rows()
    rows.append(synth.row("CLM-T-BROAD", "aws:aws_s3_bucket:x", "google:google_storage_bucket:y", "exact", "lossless"))
    rows[-1]["semantic_relation"] = "broad"
    cs = CL.synthetic(rows, ver)
    v = cs.views("google:google_storage_bucket:y", "google", "aws")[0]
    assert v.inverse and v.relation == "narrow" and v.claim_ref == "CLM-T-BROAD~inv"
    f = cs.views("aws:aws_s3_bucket:x", "aws", "google")[0]
    assert not f.inverse and f.relation == "broad"


def test_verdict_other_version_is_unproven():
    rows, ver = synth.rows()
    ver = [dict(v, claim_version_id=v["claim_id"] + "@9") if v["claim_id"].endswith("AWSGCP-NAME") else v for v in ver]
    cs = CL.synthetic(rows, ver)
    c = [x for x in cs.claims if x.claim_id.endswith("AWSGCP-NAME")][0]
    assert c.verdict == "UNPROVEN"


def test_inverse_transform_and_blocks(ev):
    from bo.pilot.sto import canary as CN
    cs = CN.claimset()
    fx = CN.source("google")
    lf = _lf(fx, cs, ev)
    v = [x for x in lf.values if x.atom_id.endswith("versioning.enabled")][0]
    c = TR.transport(lf, v, "aws", cs)
    assert c.result == "carried" and c.out_value == "Enabled" and c.view.inverse
    assert c.transform["name"] == "bool_to_enum"
    assert any(x.get("kind") == "semantic" for x in c.losses)          # inversa parcial vira perda declarada
    rows, ver = CN.rows(verdict="UNPROVEN")
    cs2 = CL.synthetic(rows, ver, concepts=cs.concept_of)
    c2 = TR.transport(_lf(fx, cs2, ev), v, "aws", cs2)
    assert c2.result == "blocked" and c2.code == "UNPROVEN"


def test_guard_false_and_related(ev):
    from bo.pilot.sto import canary as CN
    rows, ver = CN.rows()
    for r in rows:
        if r["claim_id"] == "CLM-CANARY-AWSGCP-NAME":
            r["guard"] = {"all": [{"term": "subject.bucket", "op": "eq", "value": "outro-nome"}],
                          "term_types": {"subject.bucket": {"datatype": "string"}}}
        if r["claim_id"] == "CLM-CANARY-AWSAZ-NAME":
            r["semantic_relation"] = "related"
    cs = CL.synthetic(rows, ver, concepts=CN.claimset().concept_of)
    lf = _lf(CN.source("aws"), cs, ev)
    v = [x for x in lf.values if x.atom_id == "aws:aws_s3_bucket:bucket"][0]
    g = TR.transport(lf, v, "google", cs)
    assert g.result == "blocked" and g.code == "CONDITION_FALSE" and g.guard["result"] == "FALSE"
    z = TR.transport(lf, v, "azurerm", cs)
    assert z.result == "blocked" and z.code == "RELATED_ONLY"
