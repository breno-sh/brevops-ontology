"""Decomposição pelo lifting (evidência C25) = gabarito; invariância a ordem e embalagem; c3 recusa contraexemplos."""
from bo.pilot.sto import common as C
from bo.pilot.sto import evaluate as E
from bo.pilot.sto import lift as L
from bo.pilot.sto import pipeline as PL


def test_decomposition_matches_gabarito(expected, syn, ev):
    n = 0
    for fid, f in expected["fixtures"].items():
        fx = C.read_json(C.repo() / f["file"])
        dec = L.decomposition(L.lift(fx, syn, ev))
        for chk in f["checks"]:
            if chk["kind"] == "decomposition":
                n += 1
                u = dec.get(chk["unit"])
                assert u is not None and {k: u.get(k) for k in chk["expect"]} == chk["expect"], (fid, chk["unit"])
    assert n >= 20


def test_reorder_and_repackaging_invariance(expected, syn, ev):
    seen = 0
    for fid, f in sorted(expected["fixtures"].items()):
        fx = C.read_json(C.repo() / f["file"])
        base = E.neutral(L.decomposition(L.lift(fx, syn, ev)))
        assert E.neutral(L.decomposition(L.lift(E.shuffled(fx, 7), syn, ev))) == base, fid
        rp = E.repackaged(fx)
        if rp is not None:
            seen += 1
            assert E.neutral(L.decomposition(L.lift(rp, syn, ev))) == base, fid
    assert seen >= 3


def test_counterexamples_rejected_by_c3_not_by_c2(ctx_syn, expected):
    c2_accepts = 0
    for fid, f in expected["fixtures"].items():
        fx = C.read_json(C.repo() / f["file"])
        for chk in f["checks"]:
            if chk["kind"] == "claim" and chk["claim"]["about"] in ("decomposition", "disjoint_kinds"):
                assert PL.pipeline_answer(ctx_syn, fx, chk["claim"], "c3_full")["answer"] == "REJECT", fid
                if chk["claim"]["about"] == "disjoint_kinds":
                    c2_accepts += PL.pipeline_answer(ctx_syn, fx, chk["claim"], "c2_taxonomy")["answer"] == "ACCEPT"
    assert c2_accepts == 1          # sem axioma de disjunção, o c2 aceita o contraexemplo (consequência do c3)
