"""Renomear e permutar provedores, reordenar registros e trocar a embalagem: mesma saída, byte a byte."""
import pytest

from bo.metrics import core, invariance as IV, models as MD, resample as RS, units as U
from bo.metrics.spec import BINDINGS, directions
from conftest import synth
from test_units import POLICY, doc_record

OP = BINDINGS["M-OPCOV-DEC"].table


def _attrs(f, i, rng):
    return {"complex": bool(i % 3 == 0), "auth_edge": i % 2, "domain": ["CMP", "STO", "SEC"][i % 3]}


DATA = synth(n_fam=32, per_fam=4, dirs=directions(), seed=31, attrs=_attrs)


def pipeline(units):
    cell = lambda u: f"{u.source}->{u.target}"
    alt = [u.with_codes(["omitted"]) if u.unit_id.endswith("-01") else u for u in units]
    out = {
        "opcov": {k: v.as_dict() for k, v in core.reading("M-OPCOV-DEC", units).items()},
        "complex": {k: v.as_dict() for k, v in core.complex_fraction(units).items()},
        "intervals": RS.interval_cells(units, OP, cell, reps=200),
        "hub": MD.paired_contrast(units, alt, OP, OP, ratio=0.95, reps=200),
        "asym": MD.asymmetry(units, OP, reps=200),
        "logit": MD.fixed_effects_logit(units, OP, "auth_edge", ["pair", "direction", "domain"]),
    }
    out["logit"].pop("collinear_dropped")   # nomes das colunas de referência dependem do rótulo, o ajuste não
    return out


def test_rename_providers_to_opaque_names():
    IV.check_rename(pipeline, DATA)


def test_every_permutation_of_provider_identities():
    assert IV.check_permutations(pipeline, DATA) == 23


def test_reorder_records():
    IV.check_reorder(pipeline, DATA, seed=4, rounds=3)


def test_invariance_detects_a_label_dependent_defect():
    def leaky(units):  # defeito plantado: o resultado depende do nome do provedor
        return {"x": sum(1 for u in units if u.source == "aws")}
    with pytest.raises(IV.InvarianceError):
        IV.check_rename(leaky, DATA)

    def order_dependent(units):
        return {"first": units[0].unit_id}
    with pytest.raises(IV.InvarianceError):
        IV.check_reorder(order_dependent, DATA)


def test_repackaging_inline_vs_blocks_same_decision_output():
    def decisions_reading(records):
        ds = U.decision_units(U.field_units(U.fields_from_symbolic(records)))
        us = [U.Unit(d.decision_id, d.family_id, d.repo_id, "aws", "google",
                     codes=("carried" if i % 2 else "TRANSFORM_OUT_OF_DOMAIN",)) for i, d in enumerate(ds)]
        return {k: v.as_dict() for k, v in core.reading("M-OPCOV-DEC", us).items()}
    a = IV.canonical_bytes(decisions_reading([doc_record(POLICY)]))
    b = IV.canonical_bytes(decisions_reading(IV.policy_to_block_records(doc_record(POLICY))))
    assert a == b
