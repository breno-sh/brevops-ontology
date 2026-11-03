"""Gate G3: python -I -m bo.semantics.composition_check

close∘close não vira exact; guardas incompatíveis dão composição vazia; domínio incompatível dá UNPROVEN. Mais:
a tabela publicada (semantics/composition_table.json) é a calculada agora; a parte de domínios bate com o RCC5
da literatura; cadeias exact executam ida e volta; broad∘broad leva A->C inteiro e C->A só no subconjunto;
o composto nunca é melhor que a pior perna; o fecho só passa pela tabela; o caminho pelo conceito do glossário
herda as obrigações das âncoras. Relatório em $BO_DATA/SEMANTICS/composition_check_report.json.
"""

from __future__ import annotations

import copy
import json
import sys

from . import common
from .composition import closure, compose, hub_claim, rcc5_table, semantic_table, table_document, transport_composite
from .content import examples as E

# RCC5 (Randell, Cui e Cohn 1992; tabela de composição em Bennett 1994), com EQ=equal, PP=subset, PPi=superset,
# PO=overlap, DR=disjoint. Conferência independente de algumas linhas da enumeração.
LIT = {("subset", "subset"): ["subset"],
       ("subset", "superset"): ["equal", "subset", "superset", "overlap", "disjoint"],
       ("superset", "subset"): ["equal", "subset", "superset", "overlap"],
       ("disjoint", "subset"): ["subset", "overlap", "disjoint"],
       ("subset", "disjoint"): ["disjoint"],
       ("overlap", "subset"): ["subset", "overlap"],
       ("superset", "overlap"): ["superset", "overlap"],
       ("superset", "disjoint"): ["superset", "overlap", "disjoint"],
       ("disjoint", "superset"): ["disjoint"]}

TIER = E.claim("CLM-BR-02", "pb:storage_class", "broad", "pc:object_tier",
               E.ENUM("standard", "nearline", "coldline", "archive"), E.ENUM("hot", "cool", "cold", "archive", "deep"),
               E.EM({"standard": "hot", "nearline": "cool", "coldline": "cold", "archive": "archive"}), "subset", "lossless",
               tests=[{"input": "coldline", "expected": "cold"}],
               membership_predicate={"subset": "subject", "expr": {"op": "in", "values": ["hot", "cool", "cold", "archive"]},
                                     "tests": {"members": ["hot"], "non_members": ["deep"]}})


def checks() -> list[dict]:
    out = []

    def check(name, ok, **d):
        out.append({"check": name, "ok": bool(ok), **d})

    # tabela publicada == calculada
    p = common.semantics_dir() / "composition_table.json"
    pub = json.loads(p.read_text(encoding="utf-8")) if p.is_file() else None
    check("published_table_equals_computed", pub == table_document(), file="semantics/composition_table.json")
    rc4, rc5 = rcc5_table(4), rcc5_table(5)
    check("rcc5_stable_n4_n5", rc4 == rc5)
    check("rcc5_matches_literature_rows", all(rc4[k] == v for k, v in LIT.items()),
          rows={f"{a}∘{b}": rc4[(a, b)] for a, b in LIT})
    st = semantic_table()
    check("table_close_close_not_exact", st[("close", "close")]["result"] not in ("exact", "close"))
    check("table_only_exact_exact_gives_exact",
          all((v["result"] == "exact") == (k == ("exact", "exact")) for k, v in st.items()))
    check("table_related_not_transitive", st[("related", "related")]["result"] is None)
    check("table_broad_narrow_none", st[("broad", "narrow")]["result"] is None and st[("narrow", "broad")]["result"] is None)

    # close∘close com alegações reais
    r = compose(E.CLOSE_VERSIONING, E.CLOSE_VERSIONING_2)
    check("close_close_not_exact", r["outcome"] != "COMPOSED" and r.get("rule") == "K-TABLE", outcome=r["outcome"])

    # guardas
    m1 = E.with_guard(E.EXACT_DAYS_HOURS, E.EDITION_STD)
    bad = E.with_guard(E.EXACT_HOURS_SECS, [{"term": "subject.edition", "op": "edition_in", "value": ["premium"]}])
    good = E.with_guard(E.EXACT_HOURS_SECS, [{"term": "subject.edition", "op": "edition_in", "value": ["standard", "premium"]}])
    r = compose(m1, bad)
    check("incompatible_guards_empty", r["outcome"] == "EMPTY" and r["rule"] == "K-GUARD-EMPTY", detail=r.get("detail"))
    r = compose(m1, good)
    check("compatible_guards_compose_with_pivot_witness",
          r["outcome"] == "COMPOSED" and r["claim"]["pivot"]["witness"] == {"edition": "standard"})
    ka = E.with_guard(E.EXACT_DAYS_HOURS, [{"term": "object.key_ref", "op": "refers_to_kind", "value": "kind_a"}])
    kb = E.with_guard(E.EXACT_HOURS_SECS, [{"term": "subject.key_ref", "op": "refers_to_kind", "value": "kind_b"}])
    r = compose(ka, kb)
    check("undecided_guards_unproven", r["outcome"] == "UNPROVEN" and r["rule"] == "K-GUARD-UNKNOWN")
    kb2 = copy.deepcopy(kb)
    kb2["guard"]["kind_disjoint"] = [["kind_a", "kind_b"]]
    r = compose(ka, kb2)
    check("declared_disjoint_kinds_empty", r["outcome"] == "EMPTY")

    # domínio incompatível
    mid_days = copy.deepcopy(E.EXACT_HOURS_SECS)
    mid_days["subject_value_type"] = E.DAYS(1, 30)
    mid_days["translation_fn"] = E.UC("unit:DAY", "unit:SEC")
    mid_days["proof"]["tests"] = [{"input": 2, "expected": 172800}]
    r = compose(E.EXACT_DAYS_HOURS, mid_days)
    check("incompatible_middle_type_unproven", r["outcome"] == "UNPROVEN" and r["rule"] == "K-DOMAIN", detail=r.get("detail"))
    unk = copy.deepcopy(E.EXACT_HOURS_SECS)
    unk["subject_value_type"]["unit"] = "UNKNOWN"
    r = compose(E.EXACT_DAYS_HOURS, unk)
    check("unknown_middle_type_unproven", r["outcome"] == "UNPROVEN", rule=r.get("rule"))
    far = copy.deepcopy(E.EXACT_HOURS_SECS)
    far["subject_value_type"]["range"] = {"min": 10000, "max": 20000}
    far["proof"]["tests"] = [{"input": 10000, "expected": 36000000}]
    far["object_value_type"]["range"] = {"min": 1, "max": 100000000}
    r = compose(E.EXACT_DAYS_HOURS, far)
    check("disjoint_image_unproven", r["outcome"] == "UNPROVEN" and r["rule"] == "K-DOMAIN", detail=r.get("detail"))

    # exact∘exact executa
    r = compose(E.EXACT_DAYS_HOURS, E.EXACT_HOURS_SECS)
    f = transport_composite(r, 2)
    b = transport_composite(r, 172800, direction="inverse")
    check("exact_exact_is_exact_and_executes", r["claim"]["semantic_relation"] == "exact" and f.get("value") == 172800
          and b.get("value") == 2)
    # broad∘broad
    r = compose(E.BROAD_ARCHIVE, TIER)
    fwd = {v: transport_composite(r, v).get("value") for v in ("flexible_retrieval", "deep_archive")}
    bwd = {v: transport_composite(r, v, direction="inverse") for v in ("hot", "cool", "cold", "archive", "deep")}
    check("broad_broad_is_broad", r["outcome"] == "COMPOSED" and r["claim"]["semantic_relation"] == "broad")
    check("broad_broad_A_to_C_integral", fwd == {"flexible_retrieval": "cold", "deep_archive": "archive"}, fwd=fwd)
    check("broad_broad_C_to_A_only_subset",
          {v for v, o in bwd.items() if o["result"] == "carried"} == {"cold", "archive"}
          and all(o.get("code") == "OUT_OF_SUBSET" for v, o in bwd.items() if o["result"] != "carried"))
    r = compose(E.BROAD_ARCHIVE, copy.deepcopy(E.claim("CLM-NR-02", "pb:storage_class", "narrow", "pc:cold_only",
                E.ENUM("standard", "nearline", "coldline", "archive"), E.ENUM("cold"), E.EM({"coldline": "cold"}),
                "superset", "partial", tests=[{"input": "coldline", "expected": "cold"}],
                membership_predicate={"subset": "object", "expr": {"op": "in", "values": ["coldline"]},
                                      "tests": {"members": ["coldline"], "non_members": ["standard"]}})))
    check("broad_narrow_unproven", r["outcome"] == "UNPROVEN" and r["rule"] == "K-TABLE", outcome=r["outcome"])

    # fidelidade e evidência do composto
    r = compose(E.RET_DAYS_HOURS, E.RET_HOURS_DAYS)
    t = transport_composite(r, 400)
    check("composite_fidelity_worst_leg", r["claim"]["transport_fidelity"] == "declared_loss" and t.get("value") == 365
          and [x["kind"] for x in t.get("losses", [])] == ["saturation"])
    weak = copy.deepcopy(E.EXACT_HOURS_SECS)
    weak["evidence_state"] = "STRUCTURALLY_VALID"
    r = compose(E.EXACT_DAYS_HOURS, weak)
    check("composition_never_promotes", r["outcome"] == "UNPROVEN" and r["rule"] == "K-LEGS")

    # fecho só pela tabela
    cl = closure([E.EXACT_DAYS_HOURS, E.EXACT_HOURS_SECS, E.CLOSE_VERSIONING, E.CLOSE_VERSIONING_2, E.RELATED_KMS])
    derived = [(x["chain"], x["claim"]["semantic_relation"]) for x in cl if x["outcome"] == "COMPOSED"]
    close_ids = {"CLM-CL-01", "CLM-CL-02", "CLM-CL-01~inv", "CLM-CL-02~inv", "CLM-RE-01", "CLM-RE-01~inv"}
    check("closure_close_and_related_derive_nothing",
          not any(set(ch) & close_ids for ch, _ in derived), derived=[" ∘ ".join(ch) for ch, _ in derived])
    check("closure_exact_chain_derived", any(rel == "exact" and ch == ["CLM-EX-02", "CLM-EX-03"] for ch, rel in derived))

    # caminho pelo conceito do glossário (F4)
    ua = copy.deepcopy(E.ANCHOR_A)
    ua["evidence_state"] = "UNRESOLVED"
    r = hub_claim(ua, E.ANCHOR_B)
    check("hub_unresolved_anchor_unproven", r["outcome"] == "UNPROVEN")
    r = hub_claim(E.ANCHOR_A, E.ANCHOR_B)
    v = transport_composite(r, 7)
    check("hub_supported_anchors_compose_exact", r["outcome"] == "COMPOSED" and r["claim"]["semantic_relation"] == "exact"
          and v.get("value") == 604800)
    return out


def main(argv=None) -> int:
    res = checks()
    for c in res:
        common.emit(f"  {'OK  ' if c['ok'] else 'FAIL'} {c['check']}")
    ok = all(c["ok"] for c in res)
    p = common.write_report("composition_check_report", {"module": "SEMANTICS", "gate": "composition_check",
                                                          "n": len(res), "n_ok": sum(c["ok"] for c in res), "checks": res})
    common.emit(f"[{common.now()}] composition_check: {sum(c['ok'] for c in res)}/{len(res)} -> {'PASS' if ok else 'FAIL'}  ({p})")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
