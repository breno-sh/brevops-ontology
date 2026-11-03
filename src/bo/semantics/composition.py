"""Tabela formal de composição (C10 composition_table.json) e composição executável de alegações.

Encadear m1: A->B e m2: B->C não é fecho transitivo indiscriminado:
  1. junção pelo mesmo nó (K-JOIN); 2. as duas pernas OK (K-LEGS, nunca promove);
  3. o tipo do nó do meio é o mesmo e conhecido nas duas pernas, e a imagem da ida encontra o domínio da volta
     (K-DOMAIN; senão UNPROVEN); 4. a relação semântica sai da tabela (K-TABLE; ⊥ = UNPROVEN);
  5. guardas intersectadas: UNSAT = composição vazia (K-GUARD-EMPTY), indecidida = UNPROVEN (K-GUARD-UNKNOWN);
  6. relação de domínios pela composição do RCC5 (K-VDR); 7. fidelidade = a pior das pernas (K-FIDELITY);
  8. evidência = a menor das pernas. O transporte do composto roda perna a perna (predicados de pertença,
     perdas e guardas de cada perna valem), com o nó do meio escolhido pela testemunha da guarda.

A parte de domínios da tabela NÃO é transcrita: é calculada por enumeração exaustiva de conjuntos finitos
(rcc5_table), e o gate confere que a tabela publicada é a calculada.
"""

from __future__ import annotations

import itertools

from . import guards as G
from . import transforms as T
from .claims import Claim, invert
from .obligations import assess, computed_vdr
from .transport import transport
from .valuetypes import AnyDomain, EnumDomain, relation, _set_rel
from .vocab import (EVIDENCE_RANK, EVIDENCE_STATES, FIDELITIES, FIDELITY_RANK, SKOS_PREDICATE, VDR_JEPD)

SET_OF = {"exact": "equal", "broad": "subset", "narrow": "superset"}   # semântica de conjuntos da extensão
REL_OF = {v: k for k, v in SET_OF.items()}
SEM = ("exact", "close", "broad", "narrow", "related")

POLICY = {
    ("exact", "close"): ("close", "exact preserva o significado; a perda da perna close continua declarada"),
    ("close", "exact"): ("close", "idem, na outra ordem"),
    ("close", "close"): (None, "closeMatch não é transitiva (SKOS: 'compound errors'): perdas acumulam; não vira exact nem close"),
    ("close", "broad"): (None, "inclusão aproximada não é relação do vocabulário: sem prova direta, UNPROVEN"),
    ("broad", "close"): (None, "idem"),
    ("close", "narrow"): (None, "idem"),
    ("narrow", "close"): (None, "idem"),
    ("exact", "related"): ("related", "exact substitui o termo sem mudar o significado; related continua sem transporte"),
    ("related", "exact"): ("related", "idem, na outra ordem"),
}


def rcc5_table(n: int = 4) -> dict[tuple[str, str], list[str]]:
    """Composição das 5 relações entre conjuntos não vazios, por enumeração exaustiva num universo de n pontos."""
    U = range(n)
    sets = [frozenset(s) for k in range(1, n + 1) for s in itertools.combinations(U, k)]
    rel = {(a, b): _set_rel(a, b) for a in sets for b in sets}
    out: dict[tuple[str, str], set] = {(r1, r2): set() for r1 in VDR_JEPD for r2 in VDR_JEPD}
    for a in sets:
        for b in sets:
            r1 = rel[(a, b)]
            for c in sets:
                out[(r1, rel[(b, c)])].add(rel[(a, c)])
    return {k: sorted(v, key=VDR_JEPD.index) for k, v in out.items()}


def semantic_table() -> dict[tuple[str, str], dict]:
    rc = rcc5_table()
    out = {}
    for r1 in SEM:
        for r2 in SEM:
            if r1 in SET_OF and r2 in SET_OF:
                poss = rc[(SET_OF[r1], SET_OF[r2])]
                res = REL_OF[poss[0]] if len(poss) == 1 and poss[0] in REL_OF else None
                why = (f"semântica de conjuntos: {SET_OF[r1]} ∘ {SET_OF[r2]} = {{{', '.join(poss)}}}"
                       + ("" if res else " (não é uma relação só: nenhuma relação derivável)"))
                out[(r1, r2)] = {"result": res, "derivation": "rcc5", "rcc5": poss, "why": why}
            elif (r1, r2) in POLICY:
                res, why = POLICY[(r1, r2)]
                out[(r1, r2)] = {"result": res, "derivation": "policy", "why": why}
            else:
                why = ("relatedMatch não é transitiva e não compõe com inclusão" if "related" in (r1, r2)
                       else "sem regra: UNPROVEN")
                out[(r1, r2)] = {"result": None, "derivation": "policy", "why": why}
    return out


def fidelity_compose(f1: str, f2: str) -> str:
    return FIDELITIES[max(FIDELITY_RANK[f1], FIDELITY_RANK[f2])]


def table_document() -> dict:
    """Conteúdo de semantics/composition_table.json (determinístico)."""
    st = semantic_table()
    rc4, rc5 = rcc5_table(4), rcc5_table(5)
    return {
        "schema": "bo.composition_table/1", "contract": "C10", "contract_version": "3.0.0",
        "module": "SEMANTICS",
        "reading": "linha (r1, r2) = resultado de m1∘m2 com m1: A->B por r1 e m2: B->C por r2 (aplica m1, depois m2)",
        "semantic_relation": [
            {"r1": r1, "r2": r2, "result": v["result"], "predicate": SKOS_PREDICATE.get(v["result"]) if v["result"] else None,
             "derivation": v["derivation"], **({"rcc5": v["rcc5"]} if "rcc5" in v else {}), "why": v["why"]}
            for (r1, r2), v in sorted(st.items(), key=lambda kv: (SEM.index(kv[0][0]), SEM.index(kv[0][1])))],
        "value_domain_relation": {
            "orientation": "subject_to_object (A R B, B R C => A ? C)",
            "method": "enumeração exaustiva de todos os conjuntos não vazios num universo de 4 pontos; conferida igual com 5",
            "stable_n4_n5": rc4 == rc5,
            "rows": [{"r1": r1, "r2": r2, "possible": rc4[(r1, r2)],
                      "result": rc4[(r1, r2)][0] if len(rc4[(r1, r2)]) == 1 else "unknown"}
                     for r1 in VDR_JEPD for r2 in VDR_JEPD],
            "unknown_rule": "unknown ∘ R = R ∘ unknown = unknown",
        },
        "transport_fidelity": {
            "rule": "a pior das pernas (lossless < declared_loss < partial < none); recalculada no composto",
            "rows": [{"f1": f1, "f2": f2, "result": fidelity_compose(f1, f2)} for f1 in FIDELITIES for f2 in FIDELITIES],
        },
        "guard": {"rule": "conjunção das guardas com os papéis renomeados (sujeito de m1, nó do meio, objeto de m2); "
                          "UNSAT = composição vazia; UNKNOWN = UNPROVEN; os termos do nó do meio são eliminados "
                          "existencialmente (exato: os átomos são por termo)"},
        "domain": {"rule": "tipo do nó do meio igual (datatype, grandeza, unidade, janela, convenção de byte) e conhecido "
                           "nas duas pernas, e imagem da ida ∩ domínio da volta ≠ ∅; senão UNPROVEN"},
        "evidence": {"rule": "a menor das pernas na escada (" + " < ".join(EVIDENCE_STATES) + ")"},
        "verdict": {"rule": "pernas OK; composição nunca promove: perna UNPROVEN ou REFUTED dá UNPROVEN"},
        "closure": {"rule": "só pela tabela; exactMatch é transitiva (com guardas satisfazíveis e domínios compatíveis); "
                            "closeMatch e relatedMatch não; o fecho OWL do SKOS é relatado à parte e não habilita transporte"},
    }


# ------------------------------------------------------------------------------------------- composição
def _type_sig(d):
    from .valuetypes import ValueType
    if not d:
        return None, None
    t = ValueType.from_dict(d)
    return t, t.signature()


def compose(m1: Claim | dict, m2: Claim | dict, disabled=frozenset()) -> dict:
    m1 = m1 if isinstance(m1, Claim) else Claim(m1)
    m2 = m2 if isinstance(m2, Claim) else Claim(m2)
    dis = frozenset(disabled)
    res = {"legs": [m1.id, m2.id], "reasons": []}

    def stop(outcome, rule, detail):
        res.update(outcome=outcome, rule=rule, detail=detail)
        res["reasons"].append(rule)
        return res

    if m1["object_id"] != m2["subject_id"] and "K-JOIN" not in dis:
        return stop("NOT_COMPOSABLE", "K-JOIN", f"{m1['object_id']} != {m2['subject_id']}")
    a1, a2 = leg_assess(m1), leg_assess(m2)
    if (a1.verdict != "OK" or a2.verdict != "OK") and "K-LEGS" not in dis:
        return stop("UNPROVEN", "K-LEGS", f"pernas {a1.verdict}/{a2.verdict}: composição não promove")
    tB1, sB1 = _type_sig(m1["object_value_type"])
    tB2, sB2 = _type_sig(m2["subject_value_type"])
    tA, _ = _type_sig(m1["subject_value_type"])
    tC, _ = _type_sig(m2["object_value_type"])
    if "K-DOMAIN" not in dis:
        if tB1 is None or tB2 is None or tB1.kind_unknown() or tB2.kind_unknown():
            return stop("UNPROVEN", "K-DOMAIN", "tipo do nó do meio ausente ou UNKNOWN")
        if sB1 != sB2:
            return stop("UNPROVEN", "K-DOMAIN", f"domínio incompatível no nó do meio: {sB1} != {sB2}")
        if T.kind(m1["translation_fn"]) == "scalar" and tA is not None:
            img = T.image(m1["translation_fn"], tA.domain())
            if not isinstance(img, AnyDomain) and not isinstance(tB2.domain(), AnyDomain):
                if relation(img, tB2.domain()) == "disjoint":
                    return stop("UNPROVEN", "K-DOMAIN", "a imagem da primeira perna não encontra o domínio da segunda")
                if T.kind(m2["translation_fn"]) == "scalar":
                    img2 = T.image(m2["translation_fn"], img)
                    if isinstance(img2, EnumDomain) and not img2.values:
                        return stop("UNPROVEN", "K-DOMAIN", "a segunda perna não está definida em nenhum valor da imagem")
    st = semantic_table()[(m1.relation, m2.relation)]
    rel = st["result"]
    if rel is None and "K-TABLE" not in dis:
        return stop("UNPROVEN", "K-TABLE", f"{m1.relation}∘{m2.relation}: {st['why']}")
    rel = rel or m1.relation
    g1 = G.rename(m1.guard, {"subject": "n0", "object": "n1"})
    g2 = G.rename(m2.guard, {"subject": "n1", "object": "n2"})
    roles = ("n0", "n1", "n2")
    gc = G.conj(g1, g2, roles=roles)
    sat, info = G.satisfiable(gc, roles=roles)
    res["guard_sat"] = sat
    if sat == G.UNSAT and "K-GUARD-EMPTY" not in dis:
        return stop("EMPTY", "K-GUARD-EMPTY", f"guardas incompatíveis: {info}")
    if sat == G.UNKNOWN and "K-GUARD-UNKNOWN" not in dis:
        return stop("UNPROVEN", "K-GUARD-UNKNOWN", f"satisfatibilidade indecidida: {info}")
    pivot = {k.split(".", 1)[1]: v for k, v in (info.items() if sat == G.SAT else []) if k.startswith("n1.")}
    guard = G.rename(G.project(gc, {"n0", "n2"}), {"n0": "subject", "n2": "object"})

    v1, v2 = m1.vdr or "unknown", m2.vdr or "unknown"
    poss = rcc5_table()[(v1, v2)] if v1 in VDR_JEPD and v2 in VDR_JEPD else list(VDR_JEPD)
    vdr = poss[0] if len(poss) == 1 else "unknown"
    fid1 = a1.computed.get("fidelity") or m1["transport_fidelity"]
    fid2 = a2.computed.get("fidelity") or m2["transport_fidelity"]
    fid = fidelity_compose(fid1, fid2) if "K-FIDELITY" not in dis else min(fid1, fid2, key=FIDELITY_RANK.get)
    ev = EVIDENCE_STATES[min(EVIDENCE_RANK.get(m1["evidence_state"], 0), EVIDENCE_RANK.get(m2["evidence_state"], 0))]
    chain = T.chain_of(m1["translation_fn"]) + T.chain_of(m2["translation_fn"])
    comp = {
        "claim_id": f"{m1.id}∘{m2.id}", "subject_id": m1["subject_id"], "object_id": m2["object_id"],
        "predicate_id": SKOS_PREDICATE[rel], "semantic_relation": rel,
        "value_domain_relation": {"relation": vdr, "orientation": "subject_to_object", "possible": poss},
        "transport_fidelity": fid, "guard": guard, "translation_fn": chain,
        "evidence_state": ev, "basis": "composition", "subject_value_type": m1["subject_value_type"],
        "object_value_type": m2["object_value_type"], "mapping_justification": "semapv:MappingChaining",
        "proof": {"type": "composition", "legs": [m1.id, m2.id], "table_row": f"{m1.relation}∘{m2.relation}",
                  "derivation": st["derivation"]},
        "pivot": {"node": m1["object_id"], "witness": pivot},
        "derivation": [m1.rec, m2.rec],
        "leg_losses": [m1.losses, m2.losses],
    }
    if tA is not None and tC is not None and T.kind(chain) == "scalar":
        try:
            probe = Claim({"translation_fn": chain, "loss_contract": m2.losses, "fixed_default": m2["fixed_default"]})
            real = computed_vdr(probe, tA, tC)
        except Exception:
            real = "unknown"
        if real != "unknown":
            if real not in poss and "K-VDR" not in dis:
                return stop("UNPROVEN", "K-VDR", f"relação de domínio calculada {real} fora da tabela {poss}")
            comp["value_domain_relation"]["relation"] = real
            if real in ("superset", "overlap") and fid == "lossless":
                comp["transport_fidelity"] = "partial"
    res.update(outcome="COMPOSED", rule=None, claim=comp, legs_records=[m1.rec, m2.rec], detail=st["why"])
    return res


class _Leg:
    def __init__(self, verdict, fidelity):
        self.verdict, self.computed = verdict, {"fidelity": fidelity}


def leg_assess(m: Claim):
    """Perna simples: obrigações de prova. Perna composta: refaz a composição a partir das pernas guardadas e
    exige o mesmo resultado (uma alegação 'composta' forjada não passa)."""
    if m["basis"] != "composition":
        return assess(m)
    der = m["derivation"]
    if not isinstance(der, list) or len(der) != 2:
        return _Leg("UNPROVEN", None)
    r = compose(Claim(der[0]), Claim(der[1]))
    if r.get("outcome") != "COMPOSED":
        return _Leg("UNPROVEN", None)
    from .common import canon
    if canon(r["claim"]) != canon(m.rec):
        return _Leg("REFUTED_BY_RULE", None)
    return _Leg("OK", m["transport_fidelity"])


def run_leg(m: Claim, value, ctx, direction):
    if m["basis"] == "composition":
        r = compose(Claim(m["derivation"][0]), Claim(m["derivation"][1]))
        return transport_composite(r, value, ctx, direction)
    return transport(m, value, ctx, direction)


def transport_composite(res: dict, value, ctx: dict | None = None, direction: str = "forward") -> dict:
    """Transporta perna a perna; o contexto do nó do meio é a testemunha da guarda (escolha existencial)."""
    if res.get("outcome") != "COMPOSED":
        return {"result": "blocked", "code": "UNPROVEN" if res.get("outcome") != "EMPTY" else "CONDITION_FALSE",
                "rule": res.get("rule"), "detail": res.get("detail")}
    m1, m2 = (Claim(r) for r in res["legs_records"])
    piv = {f"object.{k}": v for k, v in res["claim"]["pivot"]["witness"].items()}
    piv_s = {f"subject.{k}": v for k, v in res["claim"]["pivot"]["witness"].items()}
    ctx = ctx or {}
    if direction == "forward":
        c1 = {k: v for k, v in ctx.items() if k.startswith("subject.")} | piv
        c2 = piv_s | {k: v for k, v in ctx.items() if k.startswith("object.")}
        r1 = run_leg(m1, value, c1, "forward")
        if r1["result"] != "carried":
            return {**r1, "leg": 1}
        r2 = run_leg(m2, r1["value"], c2, "forward")
        if r2["result"] != "carried":
            return {**r2, "leg": 2}
        losses = r1.get("losses", []) + r2.get("losses", [])
        return {"result": "carried", "value": r2["value"], "losses": losses,
                "fidelity": "declared_loss" if losses else "lossless", "legs": [r1, r2]}
    c2 = {k.replace("object.", "subject.", 1): v for k, v in ctx.items() if k.startswith("object.")} | piv
    r2 = run_leg(m2, value, c2, "inverse")
    if r2["result"] != "carried":
        return {**r2, "leg": 2}
    c1 = piv_s | {k.replace("subject.", "object.", 1): v for k, v in ctx.items() if k.startswith("subject.")}
    r1 = run_leg(m1, r2["value"], c1, "inverse")
    if r1["result"] != "carried":
        return {**r1, "leg": 1}
    losses = r2.get("losses", []) + r1.get("losses", [])
    return {"result": "carried", "value": r1["value"], "losses": losses,
            "fidelity": "declared_loss" if losses else "lossless", "legs": [r2, r1]}


def closure(claims: list[Claim | dict], max_len: int = 3) -> list[dict]:
    """Fecho pela tabela: compõe cadeias de até max_len pernas (K4: 4 provedores = cadeias de até 3).
    Devolve os resultados de toda tentativa (COMPOSED, EMPTY, UNPROVEN), com a cadeia."""
    base = [c if isinstance(c, Claim) else Claim(c) for c in claims]
    pool = list(base)
    for c in base:
        if not c["inverse_of"]:
            pool.append(invert(c))
    out, frontier = [], [(c, [c.id]) for c in pool]
    for _ in range(max_len - 1):
        nxt = []
        for c, path in frontier:
            for d in pool:
                if d["subject_id"] != c["object_id"] or d["object_id"] == c["subject_id"]:
                    continue
                if d.id in path or (d["inverse_of"] and d["inverse_of"] in path) or \
                        any(p == f"{d.id}~inv" for p in path):
                    continue
                r = compose(c, d)
                r["chain"] = path + [d.id]
                out.append(r)
                if r["outcome"] == "COMPOSED":
                    nxt.append((Claim(r["claim"]), r["chain"]))
        frontier = nxt
    return out


def hub_claim(anchor_a: Claim | dict, anchor_b: Claim | dict) -> dict:
    """Atom a -> conceito <- atom b: a correspondência implícita é compose(âncora_a, inversa(âncora_b)) (K-HUB, F4).
    Herda as obrigações de prova das duas âncoras; mesmo conceito sem âncoras provadas é UNPROVEN."""
    a = anchor_a if isinstance(anchor_a, Claim) else Claim(anchor_a)
    b = anchor_b if isinstance(anchor_b, Claim) else Claim(anchor_b)
    return compose(a, invert(b))
