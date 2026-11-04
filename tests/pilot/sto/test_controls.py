"""Três controles, mesma entrada: o c3 declara o alcance que o c2 deixa em silêncio; o c1 não desce."""
from bo.pilot.sto import common as C
from bo.pilot.sto import oracle_io
from bo.pilot.sto import pipeline as PL


def _entry(eid):
    return [e for e in PL.direction_entries() if e["entry_id"] == eid][0]


def test_scope_widened_is_a_c3_consequence(ctx_syn):
    e = _entry("DX-AWS-AZ-T1-acceptable_declared-01")
    O = oracle_io.load()
    runs = {ctl: PL.run_entry(ctx_syn, e, ctl) for ctl in C.CONTROLS}
    assert len({r.input_sha256 for r in runs.values()}) == 1              # mesma entrada nos três
    c3, c2, c1 = runs["c3_full"], runs["c2_taxonomy"], runs["c1_table"]
    assert c3.status == "LOWERED" and "SCOPE_WIDENED" in c3.translation.effects
    j3 = O.judge(e["source"], c3.target, c3.translation.effects, c3.container_map)
    assert j3["verdict"] == "ACCEPT_WITH_DECLARED_LOSS"
    assert c2.status == "LOWERED" and "SCOPE_WIDENED" not in c2.translation.effects
    j2 = O.judge(e["source"], c2.target, c2.translation.effects, c2.container_map)
    assert j2["verdict"] == "REJECT" and j2["code"] == "SILENT_LOSS"
    assert c1.status == "BLOCKED"
    ax = [a for row in c3.traces for a in row["justifying_axioms"]]
    assert "sto:scopeAnchor ∘ sto:hasContainer ⊑ sto:appliesTo" in ax


def test_translator_never_reads_oracle_target(ctx_syn):
    e = _entry("DX-AWS-GCP-T1-acceptable-01")
    e2 = dict(e, target={"context": e["target"]["context"], "terraform": {"resource": {}}}, declared_losses=["X"],
              variant="negative", note="outra")
    a, b = PL.run_entry(ctx_syn, e, "c3_full"), PL.run_entry(ctx_syn, e2, "c3_full")
    assert a.input_sha256 == b.input_sha256 and C.canon(a.plan) == C.canon(b.plan)


def test_negative_candidate_not_accepted(ctx_syn):
    e = _entry("DX-AWS-GCP-T1-negative-01")
    r = PL.run_entry(ctx_syn, e, "c3_full")
    assert PL.verify_candidate(ctx_syn, r, e["target"])["answer"] != "ACCEPT"
    acc = _entry("DX-AWS-GCP-T1-acceptable-01")
    ra = PL.run_entry(ctx_syn, acc, "c3_full")
    # o próprio alvo do pipeline é aceito pela conferência (controle positivo)
    own = dict(ra.target)
    assert PL.verify_candidate(ctx_syn, ra, own)["answer"] == "ACCEPT"


def test_unit_with_untransported_facet_is_blocked(ctx_syn):
    e = _entry("DX-GCP-AZ-T1-acceptable-01")        # origem com public_access_prevention sem alegação
    r = PL.run_entry(ctx_syn, e, "c3_full")
    assert r.status == "BLOCKED" and r.plan is None


def test_unread_source_blocks_the_unit(ctx_syn):
    e = _entry("DX-AWS-GCP-T1-acceptable-01")
    src = dict(e["source"], read={"completeness": "partial", "not_read": [{"of": "aws_s3_bucket_versioning.src",
                                                                          "what": "versioning_configuration"}],
                                  "withheld": []})
    r = PL.run_entry(ctx_syn, dict(e, source=src), "c3_full")
    assert r.status == "BLOCKED" and r.block[1] == "T-NOT-READ" and r.plan is None
