"""Regras de conjunto (A1, A2, A5 e o par direto da A4): conflito genuíno × estrutura válida.

Conflito genuíno (CONTESTED, todas as alegações envolvidas, sem voto):
  SKOS-DISJ       exact × broad/narrow/related no mesmo par sob guardas compatíveis (bo.semantics.check_set)
  ARB-ATOM-TYPE   o mesmo átomo (ou parte) com dois tipos sob guardas compatíveis daquele lado
  ARB-PAIR-REL    broad × narrow estritos no mesmo par e sentido
  ARB-PAIR-VALUE  mesmo par, mesmo valor de entrada, saídas diferentes, as duas sem perda
Estrutura válida que NÃO é conflito: 1:N, N:1, N:M (grupo é uma alegação só), um campo para vários conceitos
(projeções de partes distintas, ou da mesma parte com a sobreposição declarada), várias ocorrências (chave de
ocorrência), grupos que cruzam facetas (junção declarada), alternativas com guardas exclusivas.
Defeito de declaração (REFUTED_BY_RULE): projeção sobreposta sem declaração entre alegações (P-OVERLAP),
campo para vários conceitos sem projeção (ARB-PROJ-DECL), alternative_to não mútuo (ARB-ALT-MUTUAL),
exclusividade declarada sem prova (A-EXCL).
Realizações múltiplas sem prova de exclusividade: AMBIGUOUS (ARB-REAL-MULTI).
Guarda com satisfatibilidade indecidida não vira conflito: vai para 'undecided' no relatório.
"""

from __future__ import annotations

import itertools

from bo.semantics import guards as G
from bo.semantics import projections as PJ
from bo.semantics.claims import Claim
from bo.semantics.obligations import check_set
from bo.semantics.transport import transport
from bo.semantics.valuetypes import EnumDomain, NumDomain, OutOfDomain, TypeError_, ValueType

from .claimcheck import UNGLOSSED, Checked, _same, guard_of
from .common import canon, provider_of

TRANSPORTING = ("exact", "close", "broad", "narrow")
SET_OF = {"exact": "equal", "broad": "subset", "narrow": "superset"}
FLIP_REL = {"broad": "narrow", "narrow": "broad"}
SAMPLE = 24


def conflict(rule, outcome, claims, detail, **kw):
    return {"rule": rule, "outcome": outcome, "claims": sorted(set(claims)), "detail": str(detail)[:400], **kw}


def side_guard(g: dict, side: str) -> dict:
    """Restrição da guarda ao lado do átomo, renomeada para o papel 'subject' (para comparar alegações)."""
    g = g if side == "subject" else G.flip(g)
    return G.project(g, {"subject"})


def sat_of(*gs) -> tuple[str, dict]:
    try:
        return G.satisfiable(G.conj(*gs))
    except G.GuardTypeError as e:
        return G.UNKNOWN, {"type_error": str(e)}


def type_key(vt: ValueType):
    return (vt.signature(), None if vt.enum is None else frozenset(map(str, vt.enum)), vt.range, vt.step,
            vt.sentinels, tuple((n, type_key(t)) for n, t in vt.components))


def sample_points(tdict, n=SAMPLE) -> list:
    try:
        vt = ValueType.from_dict(tdict)
        d = vt.domain()
    except (TypeError_, OutOfDomain, ValueError, TypeError):
        return []
    if isinstance(d, EnumDomain):
        return sorted(d.values, key=lambda v: (str(type(v)), str(v)))[:n]
    if isinstance(d, NumDomain):
        cnt = d.count()
        if cnt is None or cnt > 4000:
            return []
        pts = list(d.points())
        if len(pts) <= n:
            return pts
        idx = sorted({round(i * (len(pts) - 1) / (n - 1)) for i in range(n)})
        return [pts[i] for i in idx]
    return []


def compare_values(xa, xb, points, ctx, dir_b="forward") -> list[dict]:
    """Pontos em que as duas alegações transportam sem perda para valores diferentes."""
    bad = []
    for v in points:
        try:
            ra = transport(xa, v, ctx, "forward")
            rb = transport(xb, v, ctx, dir_b)
        except Exception:     # noqa: BLE001 - valor de amostra que a biblioteca não aceita não decide nada
            continue
        if ra.get("result") == rb.get("result") == "carried" and not ra.get("losses") and not rb.get("losses") \
                and not _same(ra.get("value"), rb.get("value")):
            bad.append({"input": v, "a": ra.get("value"), "b": rb.get("value")})
    return bad


def test_inputs(rec: dict) -> list:
    return [t["input"] for t in ((rec.get("proof") or {}).get("tests")) or [] if isinstance(t, dict) and "input" in t]


def _uniq(vals) -> list:
    out, seen = [], set()
    for v in vals:
        k = canon(v)
        if k not in seen:
            seen.add(k)
            out.append(v)
    return out


# ----------------------------------------------------------------------------------------------- SKOS-DISJ
def skos_disjoint(cs: list[Checked], disabled) -> list[dict]:
    recs = [c.eff if c.eff is not None else c.rec for c in cs]
    out = []
    for x in check_set(recs, disabled=disabled):
        out.append(conflict("SKOS-DISJ", "CONTESTED", x["claim_ids"], x["detail"]))
    return out


# -------------------------------------------------------------------------------------------- ARB-ATOM-TYPE
def atom_types(cs: list[Checked], disabled, undecided: list) -> list[dict]:
    if "ARB-ATOM-TYPE" in disabled:
        return []
    decl: dict[str, list] = {}
    for c in cs:
        sides = list(c.group_sides) if c.form == "group" else [("subject", c.subject), ("object", c.object)]
        for side, s in sides:
            if s is None or not s.type:
                continue
            try:
                vt = ValueType.from_dict(s.type)
            except (TypeError_, OutOfDomain, ValueError, TypeError):
                continue
            decl.setdefault(s.id, []).append((c, side, vt))
    out = []
    for atom in sorted(decl):
        ds = decl[atom]
        for (ca, sa, ta), (cb, sb, tb) in itertools.combinations(ds, 2):
            if ca.cid == cb.cid or type_key(ta) == type_key(tb):
                continue
            sat, info = sat_of(side_guard(guard_of(ca), sa), side_guard(guard_of(cb), sb))
            if sat == G.UNSAT:
                continue
            what = "assinatura" if ta.signature() != tb.signature() else "domínio"
            if sat == G.UNKNOWN:
                undecided.append({"rule": "ARB-ATOM-TYPE", "claims": sorted([ca.cid, cb.cid]), "atom": atom, "why": info})
                continue
            out.append(conflict("ARB-ATOM-TYPE", "CONTESTED", [ca.cid, cb.cid],
                                f"{atom}: {what} diferente em {ca.cid} e {cb.cid}", atom=atom))
    return out


# --------------------------------------------------------------------------------------------- mesmo par
def same_pair(cs: list[Checked], disabled, undecided: list, duplicates: list) -> list[dict]:
    ok = [c for c in cs if c.verdict == "OK" and c.eff is not None and c.relation in TRANSPORTING]
    buckets: dict[tuple, list] = {}
    for c in ok:
        buckets.setdefault(tuple(sorted([c.subject.key, c.object.key], key=str)), []).append(c)
    out = []
    for key in sorted(buckets, key=str):
        for x, y in itertools.combinations(sorted(buckets[key], key=lambda c: c.cid), 2):
            same = x.subject.key == y.subject.key
            gy = guard_of(y) if same else G.flip(guard_of(y))
            sat, info = sat_of(guard_of(x), gy)
            if sat == G.UNSAT:
                continue
            if sat == G.UNKNOWN:
                undecided.append({"rule": "ARB-PAIR-VALUE", "claims": [x.cid, y.cid], "why": info})
                continue
            core = lambda r: {k: v for k, v in r.items() if k not in ("claim_id", "claim_version_id", "event_id",
                                                                       "supersedes", "proof", "alternative_to",
                                                                       "exclusivity", "confidence")}
            if same and canon(core(x.eff)) == canon(core(y.eff)):
                duplicates.append({"claims": [x.cid, y.cid], "pair": [x.subject.id, x.object.id]})
                continue
            rx, ry = x.relation, (y.relation if same else FLIP_REL.get(y.relation, y.relation))
            if {rx, ry} == {"broad", "narrow"} and "ARB-PAIR-REL" not in disabled:
                out.append(conflict("ARB-PAIR-REL", "CONTESTED", [x.cid, y.cid],
                                    f"{x.cid} {rx} e {y.cid} {ry} no mesmo par e sentido (inclusões estritas opostas)"))
            if "ARB-PAIR-VALUE" in disabled:
                continue
            pts = _uniq(test_inputs(x.eff) + (test_inputs(y.eff) if same else []) +
                        sample_points(x.eff.get("subject_value_type")))
            bad = compare_values(Claim(x.eff), Claim(y.eff), pts, info, "forward" if same else "inverse")
            if bad:
                b = bad[0]
                out.append(conflict("ARB-PAIR-VALUE", "CONTESTED", [x.cid, y.cid],
                                    f"entrada {b['input']!r}: {x.cid} dá {b['a']!r}, {y.cid} dá {b['b']!r} "
                                    f"({len(bad)} ponto(s))"))
    return out


# ---------------------------------------------------------------------------------- projeções entre alegações
def projection_sets(cs: list[Checked], disabled) -> list[dict]:
    """Projeções iguais (campo, ocorrência, extrator, conceito) em alegações diferentes são a MESMA projeção:
    fundidas, com a união dos ids e das sobreposições declaradas (independe da ordem). Entre as distintas, a
    P-OVERLAP do SEMANTICS: mesma ocorrência e partes que se cruzam exigem sobreposição declarada."""
    out = []
    uses: dict[str, list] = {}
    merged: dict[str, dict] = {}
    for c in cs:
        if c.form == "invalid":
            continue
        rp = c.rec.get("projection") or []
        for p in rp:
            k = canon({"f": p.get("field"), "o": p.get("occurrence"), "e": p.get("extractor"), "c": p.get("concept")})
            m = merged.setdefault(k, {"field": p.get("field"), "occ": PJ._occ_key(p), "parts": PJ._parts(p),
                                      "ids": set(), "overlaps": set(), "claims": set()})
            m["ids"].add(p.get("projection_id"))
            m["overlaps"] |= set(p.get("overlaps") or [])
            m["claims"].add(c.cid)
        if c.form == "group":
            continue
        for s_ in (c.subject, c.object):
            if s_ is None or s_.concept in (None, UNGLOSSED):
                continue
            has = any(p.get("field") == s_.field for p in rp)
            uses.setdefault(s_.field, []).append((c, s_.concept, has))
    if "ARB-PROJ-DECL" not in disabled:
        for f in sorted(uses):
            concepts = {u[1] for u in uses[f]}
            if len(concepts) < 2:
                continue
            naked = sorted({u[0].cid for u in uses[f] if not u[2]})
            if naked:
                out.append(conflict("ARB-PROJ-DECL", "REFUTED_BY_RULE", naked,
                                    f"{f} serve a {len(concepts)} conceitos e {len(naked)} uso(s) não declaram projeção"))
    if "P-OVERLAP" not in disabled:
        ents = sorted(merged.values(), key=lambda m: (str(m["field"]), sorted(map(str, m["ids"]))))
        for x, y in itertools.combinations(ents, 2):
            if x["field"] != y["field"] or x["occ"] != y["occ"] or x["claims"] == y["claims"] and len(x["claims"]) == 1:
                continue
            inter = x["parts"] & y["parts"]
            if "*" in x["parts"] or "*" in y["parts"]:
                inter = inter or {"*"}
            if not inter:
                continue
            if (x["ids"] & y["overlaps"]) or (y["ids"] & x["overlaps"]):
                continue
            out.append(conflict("P-OVERLAP", "REFUTED_BY_RULE", x["claims"] | y["claims"],
                                f"entre alegações: {sorted(map(str, x['ids']))} e {sorted(map(str, y['ids']))} leem "
                                f"{sorted(map(str, inter))} de {x['field']} sem sobreposição declarada"))
    return out


# ------------------------------------------------------------------------------------------------ realizações
def _target_concept(c: Checked, x_side: str) -> str:
    """A propriedade que a alegação realiza no outro provedor: o conceito do lado de lá; sem glossário dele, o do
    lado de cá; sem nenhum, UNGLOSSED (e todas as não glosadas competem)."""
    there = c.rec.get("object_concept") if x_side == "subject" else c.rec.get("subject_concept")
    here = c.rec.get("subject_concept") if x_side == "subject" else c.rec.get("object_concept")
    for k in (there, here):
        if k and k != UNGLOSSED:
            return k
    return UNGLOSSED


def _real_sides(c: Checked):
    """[(chave do átomo X, provedor do outro lado, conceito realizado, contraparte, guarda com X como sujeito)]."""
    g = guard_of(c)
    if c.form == "group":
        gid = "GRP:" + str(c.rec.get("bo_group_id"))
        out = []
        for side, s in c.group_sides:
            other = c.rec.get("object_id") if side == "subject" else c.rec.get("subject_id")
            out.append((s.key, provider_of(other), _target_concept(c, side), gid,
                        g if side == "subject" else G.flip(g)))
        return out
    return [(c.subject.key, provider_of(c.object.field), _target_concept(c, "subject"), c.object.key, g),
            (c.object.key, provider_of(c.subject.field), _target_concept(c, "object"), c.subject.key, G.flip(g))]


def realizations(cs: list[Checked], disabled) -> list[dict]:
    out = []
    ok = [c for c in cs if c.verdict == "OK" and c.relation in TRANSPORTING and c.form != "invalid"]
    clusters: dict[tuple, list] = {}
    for c in ok:
        for xk, prov, concept, cp, g in _real_sides(c):
            clusters.setdefault((xk, prov, concept), []).append((c, cp, g))
    seen = set()
    for key in sorted(clusters, key=str):
        members = sorted(clusters[key], key=lambda m: m[0].cid)
        for (a, cpa, ga), (b, cpb, gb) in itertools.combinations(members, 2):
            if a.cid == b.cid or cpa == cpb:
                continue
            pair = (a.cid, b.cid, str(key))
            if pair in seen:
                continue
            seen.add(pair)
            r = PJ.check_alternatives([{"realization_id": a.cid, "guard": ga, "exclusivity": a.rec.get("exclusivity")},
                                       {"realization_id": b.cid, "guard": gb, "exclusivity": b.rec.get("exclusivity")}],
                                      disabled=disabled)
            if r["verdict"] == "OK":
                continue
            atom = key[0][0]
            if r["verdict"] == "REFUTED_BY_RULE":
                bad = [f["detail"].split(":")[0] for f in r["failures"]]
                out.append(conflict("A-EXCL", "REFUTED_BY_RULE", bad,
                                    f"{atom}: exclusividade declarada, mas as guardas de {a.cid} e {b.cid} se cruzam"))
            if "ARB-REAL-MULTI" not in disabled:
                out.append(conflict("ARB-REAL-MULTI", "AMBIGUOUS", [a.cid, b.cid],
                                    f"{atom} tem duas realizações em {key[1]} ({a.cid}, {b.cid}) sem prova de exclusividade "
                                    f"(interseção {r['pairs'][0]['intersection']})"))
    return out


def alternatives(cs: list[Checked], disabled) -> list[dict]:
    out = []
    byid = {c.cid: c for c in cs}
    for c in sorted(cs, key=lambda c: c.cid):
        alts = c.rec.get("alternative_to") or []
        if not alts:
            continue
        group = [c]
        for t in alts:
            o = byid.get(t)
            if o is None:
                if "ARB-ALT-MUTUAL" not in disabled:
                    out.append(conflict("ARB-ALT-MUTUAL", "REFUTED_BY_RULE", [c.cid], f"alternative_to {t}: alegação inexistente"))
                continue
            if o.rec.get("subject_id") != c.rec.get("subject_id") and "ARB-ALT-MUTUAL" not in disabled:
                out.append(conflict("ARB-ALT-MUTUAL", "REFUTED_BY_RULE", [c.cid, o.cid], f"{c.cid} e {t} de sujeitos diferentes"))
            if c.cid not in (o.rec.get("alternative_to") or []) and "ARB-ALT-MUTUAL" not in disabled:
                out.append(conflict("ARB-ALT-MUTUAL", "REFUTED_BY_RULE", [c.cid, o.cid], f"{t} não lista {c.cid} de volta"))
            group.append(o)
        if len(group) < 2:
            continue
        r = PJ.check_alternatives([{"realization_id": x.cid, "guard": guard_of(x), "exclusivity": x.rec.get("exclusivity")}
                                   for x in group], disabled=disabled)
        if r["verdict"] == "REFUTED_BY_RULE":
            bad = [f["detail"].split(":")[0] for f in r["failures"]]
            out.append(conflict("A-EXCL", "REFUTED_BY_RULE", bad, "exclusividade declarada sem prova (guardas se cruzam)"))
        elif r["verdict"] == "AMBIGUOUS" and "ARB-REAL-MULTI" not in disabled:
            out.append(conflict("ARB-REAL-MULTI", "AMBIGUOUS", [x.cid for x in group],
                                "alternativas declaradas sem guardas exclusivas"))
    return out


def run(cs: list[Checked], disabled=frozenset()) -> tuple[list[dict], dict]:
    dis = frozenset(disabled)
    undecided, duplicates = [], []
    alive = [c for c in cs if c.verdict != "REFUTED_BY_RULE" and c.form != "invalid"]
    out = []
    out += skos_disjoint(alive, dis)
    out += atom_types(alive, dis, undecided)
    out += same_pair(alive, dis, undecided, duplicates)
    out += projection_sets(alive, dis)
    out += alternatives(alive, dis)
    out += realizations(alive, dis)
    return out, {"undecided": undecided, "duplicates": duplicates}
