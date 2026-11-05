"""Emenda 0.2.5 (rodada v4-r2b): o SERVICE-EVIDENCE passou a tipar o campo do pai (4d48d00) e duas decisões de STO
caíram para UNKNOWN. Casos sintéticos (provedor fictício, fatos no formato do C25) e de calibração (SE real do pin).

  T40b: alcance do tipo (type_scope) que não é escopo do provedor vai para o pai pela referência da CHAVE, tipada (T44)
        ou não (T02/T21); a referência tipada ao pai não derruba o alcance para self. Com a chave inteira = a
        referência ao pai, o recurso é um por pai e sai FACET do pai, com alcance = o pai.
  T52c: identidade relativa ao pai (chave = referência tipada ao pai + campos próprios), ciclo de vida PRÓPRIO afirmado
        e sem marca de pai de caminho: o pai qualifica o nome (namespace) e a unidade é ENTITY (G4-NS). Coerente com
        o F1 (sem ciclo de vida próprio: COMPONENT) e com a G2-CHILD (pai de caminho marcado: COMPONENT).
  T46b: reference_example (exemplo oficial) é premissa do reference_target que o SE deriva dele; sozinho não tipa e
        não vira alegação (nem UNKNOWN "sem tradução").
"""

import pytest

from bo.grain import rules as R
from bo.grain import schema as S
from bo.grain.common import data_root
from bo.grain.evidence import C25Adapter

RS = R.load()
PROV = "provider_r2b"
N = [0]
P, F, A = "r2b_box", "r2b_box_guard", "r2b_box_grant"


def rec(rt, kind, value, level="published"):
    N[0] += 1
    return {"evidence_id": f"SE-r2b-{N[0]:04d}", "provider": PROV, "pin": {"provider_version": "0.0.1"},
            "api_resource": {"service": "st", "resource": "X"}, "terraform_resource_type": rt, "fact_kind": kind,
            "status": "stated", "level": level, "value": dict(value)}


def api(rt, kind, k, **kw):
    return rec(rt, kind, dict({"kind": k, "layer": "api", "rule": "R-X"}, **kw))


def ref(rt, attr, target):
    return rec(rt, "identity", {"aspect": "reference_target", "attribute": attr, "resolved": target,
                                "target_types": [target], "references": {attr: target}, "rule": "R-REF-TARGET"},
               level="derived")


def bridge(rt, res):
    return rec(rt, "api_bridge", {"aspect": "api_resource_bridge", "resource": res, "service": "st",
                                  "rule": "R-BRIDGE-SPEC"})


def ident(rt, required):
    return rec(rt, "identity", {"aspect": "resource_identity_schema", "required": list(required), "optional": [],
                                "rule": "R-ID-SCHEMA"})


def parent_records():
    return [rec(P, "identity", {"key_fields": ["name"], "layer": "api", "rule": "R-ID-SPEC", "scope": "independent",
                                "status": "present"}),
            api(P, "lifecycle_controller", "self"), api(P, "owner", "self"), api(P, "effective_scope", "self"),
            bridge(P, "Box")]


def atoms(rt, paths):
    return [{"atom_id": f"{PROV}:{rt}:{p}", "provider": PROV, "resource_type": rt, "path": p, "block_path": [],
             "tf_type": "string"} for p in paths]


def decide(recs, extra_types=()):
    at = atoms(P, ["name"]) + atoms(F, ["box", "on"]) + atoms(A, ["box", "entity", "role"])
    cands = S.candidates_from_atoms(at)
    return S.decompose_schema(cands, C25Adapter(recs, candidates={c.cid for c in cands}), RS)


# ------------------------------------------------------------------ T40b: um por pai = FACET com alcance no pai

def guard_records(typed=True):
    recs = parent_records() + [ident(F, ["box"]), rec(F, "effective_scope", {"aspect": "type_scope", "scope": "box",
                                                                              "rule": "R-SCOPE-DOC"}),
                               api(F, "lifecycle_controller", "parent", via=["box"]),
                               api(F, "owner", "parent", via=["box"]), bridge(F, "Guard")]
    if typed:
        recs.append(ref(F, "box", P))
    return recs


def test_t40b_typed_reference_that_is_the_whole_key_is_facet_with_parent_scope():
    d = decide(guard_records()).decisions[F]
    assert d.grain == "FACET" and d.parent == P, (d.grain, d.rule, d.missing)
    assert d.scope["kind"] == "parent" and d.scope["target"] == P, d.scope


def test_t40b_scope_is_parent_also_with_the_spec_parent_scope_claim():
    """A alegação de alcance da spec (parent via a chave) e a do type_scope dizem o mesmo: não há contradição."""
    recs = guard_records() + [api(F, "effective_scope", "parent", via=["box"])]
    d = decide(recs).decisions[F]
    assert d.grain == "FACET" and "effective_scope" not in d.missing, (d.grain, d.rule, d.missing)


# ------------------------------------------------------------------ T52c: escopo no pai + ciclo de vida próprio

def grant_records(lifecycle="self", path_parent=False):
    recs = parent_records() + [ident(A, ["box", "entity"]), ref(A, "box", P), bridge(A, "BoxGrants"),
                               api(A, "owner", "self"), api(A, "effective_scope", "self")]
    if lifecycle:
        recs.append(api(A, "lifecycle_controller", lifecycle, **({"via": ["box"]} if lifecycle == "parent" else {})))
    if path_parent:
        recs.append(rec(A, "owner", {"aspect": "path_parent", "attribute": "box", "rule": "R-X"}))
    return recs


def test_t52c_scoped_identity_with_own_lifecycle_is_entity_namespaced_by_the_parent():
    d = decide(grant_records()).decisions[A]
    assert d.grain == "ENTITY" and d.rule == "GRAIN-G4-NS", (d.grain, d.rule, d.missing, d.trace)
    assert d.cascade == []                      # sem evidência de cascata, sem cascade_delete_by


def test_t52c_coherent_with_f1_without_own_lifecycle_is_component():
    d = decide(grant_records(lifecycle="parent")).decisions[A]
    assert d.grain == "COMPONENT" and d.parent == P, (d.grain, d.rule, d.missing)


def test_t52c_path_parent_mark_keeps_g2_child():
    d = decide(grant_records(path_parent=True)).decisions[A]
    assert d.grain == "COMPONENT" and d.rule == "GRAIN-G2-CHILD", (d.grain, d.rule, d.missing)


def test_t52c_unknown_lifecycle_is_not_entity():
    d = decide(grant_records(lifecycle=None)).decisions[A]
    assert d.grain == "UNKNOWN", (d.grain, d.rule)


# ------------------------------------------------------------------ T46b: reference_example

def test_t46b_reference_example_is_premise_not_a_claim():
    ex = rec(F, "identity", {"aspect": "reference_example", "attribute": "box", "example_type": P,
                             "rule": "R-REF-EXAMPLE"})
    ad = C25Adapter(guard_records(typed=False) + [ex], candidates={P, F})
    ev = ad.evidence(F)
    assert not any("reference_example" in str((c.get("source") or {}).get("note")) for c in ev.claims["identity"])
    assert "box" not in ev.references                       # sozinho não tipa
    assert any("T46b" in w for w in ad.reasons.get(F, []))


# ------------------------------------------------------------------ calibração: SE real do pin

@pytest.fixture(scope="module")
def real():
    p = data_root() / "SERVICE-EVIDENCE" / "service_evidence.jsonl"
    if not p.is_file():
        pytest.skip(f"dado real ausente: {p}")
    from bo.grain import realdata as RD
    recs = RD.load_evidence(p)
    return {pv: RD.run(slice_types={pv: RD.STO_SLICE[pv]}, records=recs)["providers"][pv]["_res"]
            for pv in ("aws", "google")}


def test_calibration_aws_public_access_block_facet_scope_parent(real):
    d = real["aws"].decisions["aws_s3_bucket_public_access_block"]
    assert d.grain == "FACET" and d.parent == "aws_s3_bucket" and d.scope["kind"] == "parent", (
        d.grain, d.rule, d.missing, d.scope)


def test_calibration_google_bucket_access_control_entity_g4_ns(real):
    d = real["google"].decisions["google_storage_bucket_access_control"]
    assert d.grain == "ENTITY" and d.rule == "GRAIN-G4-NS", (d.grain, d.rule, d.missing)
