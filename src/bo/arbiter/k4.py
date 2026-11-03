"""Composição no K4 (A4): fecho pela tabela formal do SEMANTICS e conflito de ciclo.

Pernas: alegações OK, escalares ou projetadas, com tradução do núcleo do SEMANTICS (grupo não compõe pela tabela:
tupla; etapa só do registro do TRANSFORMS não tem imagem nem inversa na referência), sem related. O fecho é o
bo.semantics.composition.closure (cadeias de até 3 pernas com as inversas): junção pelo mesmo nó, pernas OK,
domínio compatível no nó do meio, relação pela tabela (close∘close e related não compõem), interseção das
guardas (UNSAT = vazia, indecidida = UNPROVEN), relação de domínios pelo RCC5, fidelidade = a pior perna.

Para cada composto A→C, cada alegação DIRETA A→C (ou C→A invertida) que não é perna dele e cujas guardas podem
valer junto com as do composto é conferida:
  ARB-K4-REL    relação de conjunto incompatível (exact×broad/narrow/related, broad×narrow, ...)
  ARB-K4-VDR    relação de domínios da direta (calculada) fora das possíveis do composto
  ARB-K4-VALUE  o mesmo valor sai diferente pelo composto e pela direta, sem perda nas duas
Conflito marca CONTESTED a direta, as pernas (alegações afirmadas por trás) e o composto; composition_used =
a cadeia. Nenhum lado ganha: o árbitro não sabe quem errou.
"""

from __future__ import annotations

from bo.semantics import guards as G
from bo.semantics.claims import Claim
from bo.semantics.composition import closure, transport_composite
from bo.semantics.transport import transport

from .claimcheck import Checked, _same
from .common import base_claim_id
from .setcheck import SET_OF, _uniq, sample_points, sat_of, test_inputs

TRANSPORTING = ("exact", "close", "broad", "narrow")


def rel_conflict(rc: str, rd: str) -> bool:
    if rc in SET_OF and rd in SET_OF:
        return rc != rd
    return {rc, rd} == {"exact", "related"}


def run(cs: list[Checked], excluded: set[str], disabled=frozenset(), max_len: int = 3) -> dict:
    dis = frozenset(disabled)
    usable = [c for c in cs if c.verdict == "OK" and c.eff is not None and c.form in ("plain", "projection")
              and c.fn_path == "core" and c.cid not in excluded]
    legs = [c for c in usable if c.relation in TRANSPORTING]
    directs_src = usable
    legs.sort(key=lambda c: c.cid)
    directs: dict[tuple, list] = {}
    comp_vdr = {}
    for c in sorted(directs_src, key=lambda c: c.cid):
        d = Claim(c.eff)
        directs.setdefault((d["subject_id"], d["object_id"]), []).append((d, "forward", c))
        directs.setdefault((d["object_id"], d["subject_id"]), []).append((d, "inverse", c))
        comp_vdr[c.cid] = c.computed.get("vdr", "unknown")
    results = closure([Claim(c.eff) for c in legs], max_len=max_len) if legs else []
    composites, conflicts, cycles, undecided = [], [], [], []
    for r in results:
        chain = list(r.get("chain") or r.get("legs") or [])
        rec = {"chain": chain, "outcome": r["outcome"], "rule": r.get("rule"), "detail": str(r.get("detail", ""))[:300]}
        if r["outcome"] != "COMPOSED":
            cycles.append(rec)
            if r["outcome"] == "UNPROVEN" and r.get("rule") != "K-LEGS":
                composites.append({"claim_id": "∘".join(chain), "chain": chain, "verdict": "UNPROVEN",
                                   "rules": [r["rule"]], "detail": rec["detail"]})
            continue
        comp = r["claim"]
        A, C = comp["subject_id"], comp["object_id"]
        bases = {base_claim_id(x) for x in chain}
        found = []
        for d, direction, c in directs.get((A, C), []):
            if c.cid in bases:
                continue
            gd = d.guard if direction == "forward" else G.flip(d.guard)
            sat, info = sat_of(comp["guard"], gd)
            if sat == G.UNSAT:
                continue
            if sat == G.UNKNOWN:
                undecided.append({"rule": "ARB-K4", "chain": chain, "direct": c.cid, "why": info})
                continue
            rd = d.relation if direction == "forward" else {"broad": "narrow", "narrow": "broad"}.get(d.relation, d.relation)
            rc = comp["semantic_relation"]
            hits = []
            if rel_conflict(rc, rd) and "ARB-K4-REL" not in dis:
                hits.append(("ARB-K4-REL", f"composto {rc} ({'∘'.join(chain)}) × direta {rd} ({c.cid})"))
            vd = comp_vdr.get(c.cid, "unknown")
            if direction == "inverse":
                vd = {"subset": "superset", "superset": "subset"}.get(vd, vd)
            vc = comp["value_domain_relation"]
            poss = [vc["relation"]] if vc.get("relation") not in (None, "unknown") else list(vc.get("possible") or [])
            if vd != "unknown" and poss and vd not in poss and rd in TRANSPORTING and "ARB-K4-VDR" not in dis:
                hits.append(("ARB-K4-VDR", f"domínios: direta {vd}, composto {poss}"))
            if rd in TRANSPORTING and "ARB-K4-VALUE" not in dis:
                first = Claim(r["legs_records"][0]) if r.get("legs_records") else None
                pts = _uniq((test_inputs(first.rec) if first is not None else []) +
                            (test_inputs(d.rec) if direction == "forward" else []) +
                            sample_points(comp.get("subject_value_type")))
                bad = []
                for v in pts:
                    try:
                        rc_ = transport_composite(r, v, info)
                        rd_ = transport(d, v, info, direction)
                    except Exception:   # noqa: BLE001 - ponto que a biblioteca não aceita não decide nada
                        continue
                    if rc_.get("result") == rd_.get("result") == "carried" and not rc_.get("losses") \
                            and not rd_.get("losses") and not _same(rc_.get("value"), rd_.get("value")):
                        bad.append({"input": v, "a": rc_.get("value"), "b": rd_.get("value")})
                if bad:
                    b = bad[0]
                    hits.append(("ARB-K4-VALUE", f"entrada {b['input']!r}: composto dá {b['a']!r}, {c.cid} dá {b['b']!r} "
                                                 f"({len(bad)} ponto(s))"))
            for rule, detail in hits:
                conflicts.append({"rule": rule, "outcome": "CONTESTED", "claims": sorted(bases | {c.cid}),
                                  "composition_used": chain, "composite_id": comp["claim_id"], "detail": detail})
            found.append({"direct": c.cid, "direction": direction, "conflicts": [h[0] for h in hits]})
        rec["checked_against"] = found
        rec["composite_id"] = comp["claim_id"]
        rec["relation"] = comp["semantic_relation"]
        cycles.append(rec)
        crules = sorted({x["rule"] for x in conflicts if x["composite_id"] == comp["claim_id"]})
        composites.append({"claim_id": comp["claim_id"], "chain": chain,
                           "verdict": "CONTESTED" if crules else "OK", "rules": crules,
                           "detail": (f"composto pela tabela ({comp['semantic_relation']}, fidelidade "
                                      f"{comp['transport_fidelity']}); " +
                                      (f"conflito com direta: {', '.join(crules)}" if crules else
                                       f"{len(found)} direta(s) conferida(s) sem conflito"))})
    return {"composites": composites, "conflicts": conflicts, "cycles": cycles, "undecided": undecided,
            "n_legs": len(legs)}
