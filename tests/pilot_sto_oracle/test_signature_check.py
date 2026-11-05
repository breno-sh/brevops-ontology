"""O build reprova quando o mesmo (tipo, evidência) dá respostas diferentes entre calibração e retidas (DIAG_T3 F6).

Caso SINTÉTICO que reproduz a divergência: a mesma concessão separada do Google (tipo sem fato de dono na API),
com o contêiner resolvido, respondida UNKNOWN numa partição e FACET do contêiner na outra. A mensagem traz só a
assinatura (provedor, tipo, classe de evidência, referência, resposta), nunca id, nome ou valor de caso."""
from types import SimpleNamespace

import pytest

from bo.pilot_sto_oracle import build, cases


def _fx(fid, bname, gname):
    return {"fixture_id": fid, "provider": "google", "case": "MC-DEC-SCOPE", "polarity": "unknown",
            "terraform": {"resource": {
                "google_storage_bucket": {bname: {"name": "fx-" + bname, "location": "US", "uniform_bucket_level_access": True}},
                "google_storage_bucket_iam_member": {gname: {"bucket": f"${{google_storage_bucket.{bname}.name}}",
                                                             "role": "roles/storage.objectViewer", "member": "allUsers"}}}},
            "context": {}, "read": {"completeness": "complete", "not_read": [], "withheld": []}}


def _unknown_check(gname):
    return {"kind": "decomposition", "unit": f"setting:access_grant@NO-API-OWNER:google_storage_bucket_iam_member.{gname}",
            "expect": {"kind": "UNKNOWN", "owner": "UNKNOWN", "effective_scope": "UNKNOWN", "lifecycle_controller": "UNKNOWN",
                       "missing_evidence": ["owner"]}}


def _facet_check(bname):
    cu = f"container:google_storage_bucket.{bname}"
    return {"kind": "decomposition", "unit": f"setting:access_grant@{cu}",
            "expect": {"kind": "FACET", "owner": cu, "effective_scope": [cu], "lifecycle_controller": "parent", "missing_evidence": []}}


def _gen(*items):
    return SimpleNamespace(fixtures=[{"fixture": f, "checks": c} for f, c in items], entries=[])


@pytest.fixture(scope="module")
def oracle():
    return build.load_oracle()


def test_synthetic_divergence_fails_the_build(oracle):
    calib = _gen((_fx("FX-SYN-CALIB-01", "site", "site_public"), [_unknown_check("site_public")]))
    held = _gen((_fx("FX-STO-H-SECRET01", "site_qzkvw", "site_qzkvw_public"), [_facet_check("site_qzkvw")]))
    div = build.signature_divergences(build.signatures(calib, oracle), build.signatures(held, oracle))
    assert len(div) == 1
    key, answers = div[0]["signature"], div[0]
    assert key == ["google", "google_storage_bucket_iam_member", "TERRAFORM_ONLY", "resolved"]
    assert answers["calib"] == [["UNKNOWN", "UNKNOWN"]] and answers["heldout"] == [["FACET", "container"]]
    with pytest.raises(SystemExit) as ex:
        build.cross_check(calib, held, oracle)
    msg = str(ex.value) + repr(div)
    for leak in ("SECRET01", "qzkvw", "FX-SYN", "site"):
        assert leak not in msg


def test_same_answers_pass(oracle):
    calib = _gen((_fx("A", "site", "site_public"), [_unknown_check("site_public")]))
    held = _gen((_fx("B", "other", "other_public"), [_unknown_check("other_public")]))
    rep = build.cross_check(calib, held, oracle)
    assert rep["result"] == "PASS" and rep["divergent"] == 0 and rep["keys_shared"] == 1


def test_divergence_inside_one_split_also_fails(oracle):
    held = _gen((_fx("B", "a", "a_public"), [_unknown_check("a_public")]),
                (_fx("C", "b", "b_public"), [_facet_check("b")]))
    assert build.signature_divergences(build.signatures(_gen(), oracle), build.signatures(held, oracle))


def test_generator_uses_the_single_owner_rule_in_both_splits(oracle, monkeypatch):
    """Se a regra de dono mudar, as DUAS partições mudam juntas: o gerador não tem regra própria."""
    real = oracle.owner_rule

    def owner_rule(p, by):
        d = real(p, by)
        if by.split(".", 1)[0] == "aws_s3_bucket_versioning":
            return dict(d, **{"class": "TERRAFORM_ONLY"})
        return d
    monkeypatch.setattr(oracle, "owner_rule", owner_rule)
    for split in ("calib", "heldout"):
        g = cases.generate(split, oracle)
        units = [c["unit"] for f in g.fixtures if f["fixture"]["provider"] == "aws"
                 for c in f["checks"] if c["kind"] == "decomposition"]
        assert any(u.startswith("setting:versioning@NO-API-OWNER:aws_s3_bucket_versioning.") for u in units), split
