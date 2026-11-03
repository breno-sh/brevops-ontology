"""Gate: interseção de guardas incompatíveis detectada como vazia (python -I -m bo.transforms.guard_sat).

  1. sat_tests do conditions.grammar.json publicado: o esperado = esta implementação = bo.semantics.guards =
     oráculo de força bruta; toda testemunha SAT avalia TRUE;
  2. pares incompatíveis: cada guarda SAT sozinha e a interseção UNSAT (nas duas implementações); pares
     compatíveis (controle): interseção SAT com testemunha;
  3. composição a->b->c: nó do meio com exigências incompatíveis dá composição vazia;
  4. diferencial: N guardas aleatórias (semente fixa) sobre os sete operadores; typecheck igual nas duas
     implementações; esta implementação = força bruta em TODAS; divergência com a do SEMANTICS só nas classes
     documentadas (e cada uma confirmada pela força bruta); classe não documentada reprova.
"""

from __future__ import annotations

import json
import random
import sys

from . import common as C
from . import grammar as GR
from . import guards as M

N_RANDOM = 4000
SEED = 20261103
REGIONS = ["r-a", "r-b", "r-c"]
EDITIONS = ["basic", "standard", "premium"]
VERSIONS = ["0", "1.0", "4.9", "5.0", "5.1", "5.10", "6", "7.2.1"]
KINDS = ["subnet", "network_interface", "vpc"]


def _sem():
    from bo.semantics import guards as S
    return S


def _rand_guard(rng: random.Random) -> dict:
    g = {"all": []}
    tt = {}
    for _ in range(rng.randint(0, 5)):
        term = rng.choice(["object.region", "subject.region", "object.edition", "object.provider_version",
                           "object.tier", "object.enabled", "object.port", "object.name", "object.target"])
        r = rng.random()
        if r < 0.12:
            g["all"].append(GR.A(term, "present", rng.random() < 0.6))
            continue
        if term.endswith(".region"):
            g["all"].append(GR.A(term, "region_in", rng.sample(REGIONS, rng.randint(1, 3))))
        elif term.endswith(".edition"):
            if r < 0.3:
                tt[term] = {"datatype": "enum", "enum": EDITIONS}
                g["all"].append(GR.A(term, "in", rng.sample(EDITIONS, rng.randint(1, 3))))
            else:
                g["all"].append(GR.A(term, "edition_in", rng.sample(EDITIONS, rng.randint(1, 2))))
        elif term.endswith(".provider_version"):
            if r < 0.35:
                if rng.random() < 0.5:
                    tt[term] = {"datatype": "enum", "enum": rng.sample(VERSIONS, 2)}
                    if rng.random() < 0.4:
                        g["all"].append(GR.A(term, "eq", rng.choice(tt[term]["enum"])))
                else:
                    tt[term] = {"datatype": "string"}
                    g["all"].append(GR.A(term, "in", rng.sample(VERSIONS, rng.randint(1, 3))))
            lo, hi = sorted(rng.sample(range(len(VERSIONS)), 2))
            v = {}
            if rng.random() < 0.7:
                v["min"] = VERSIONS[lo]
            if rng.random() < 0.7 or not v:
                v["max_exclusive"] = VERSIONS[hi]
            if "min" in v and "max_exclusive" in v and M.ver(v["min"]) >= M.ver(v["max_exclusive"]):
                del v["min"]
            g["all"].append(GR.A(term, "version_range", v))
        elif term == "object.tier":
            tt[term] = GR.TIER
            g["all"].append(GR.A(term, "eq", rng.choice(EDITIONS)) if r < 0.6 else
                            GR.A(term, "in", rng.sample(EDITIONS, rng.randint(1, 3))))
        elif term == "object.enabled":
            tt[term] = GR.BOOL
            g["all"].append(GR.A(term, "eq", rng.random() < 0.5))
        elif term == "object.port":
            tt[term] = GR.INT
            g["all"].append(GR.A(term, "in", rng.sample([22, 80, 443], rng.randint(1, 2))) if r < 0.5 else
                            GR.A(term, "eq", rng.choice([22, 80, 443])))
        elif term == "object.name":
            tt[term] = GR.STR
            g["all"].append(GR.A(term, "eq", rng.choice(["a", "b"])) if r < 0.6 else
                            GR.A(term, "in", rng.sample(["a", "b", "c"], 2)))
        else:
            if r < 0.2:
                tt[term] = GR.STR
                g["all"].append(GR.A(term, "eq", "ref-a"))
            else:
                g["all"].append(GR.A(term, "refers_to_kind", rng.choice(KINDS)))
    if tt:
        g["term_types"] = tt
    if rng.random() < 0.3:
        g["kind_disjoint"] = [rng.sample(KINDS, 2)]
    return g


def classify(g: dict) -> str:
    """Classe documentada de divergência com bo.semantics.guards (ou 'não documentada')."""
    by: dict[str, list] = {}
    for a in g["all"]:
        by.setdefault(a["term"], []).append(a)
    for term, atoms in by.items():
        ops = {a["op"] for a in atoms}
        if "refers_to_kind" in ops and ops & {"eq", "in", "region_in", "edition_in", "version_range"}:
            return "kind_with_scalar_value"
        uni = M._universe(g, term)
        if "version_range" in ops and uni is not None and not ops & {"eq", "in"}:
            return "version_range_over_closed_universe"
    return "não documentada"


def _typecheck_agree(g, S) -> tuple[bool, bool]:
    a = b = True
    try:
        M.typecheck(g)
    except M.GuardTypeError:
        a = False
    try:
        S.typecheck(g)
    except S.GuardTypeError:
        b = False
    return a, b


def main(argv=None) -> int:
    S = _sem()
    errs = []
    # 1. sat_tests publicados
    gram = json.loads(C.grammar_json().read_text(encoding="utf-8"))
    for t in gram["sat_tests"]:
        g, exp = t["guard"], t["expected"]
        m, w = M.satisfiable(g)
        s, b = S.satisfiable(g)[0], M.brute_force(g)
        if not m == s == b == exp:
            errs.append(f"{t['test_id']}: esperado {exp}; TRANSFORMS {m}, SEMANTICS {s}, força bruta {b}")
        if m == "SAT" and not M.check_witness(g, w):
            errs.append(f"{t['test_id']}: testemunha não avalia TRUE: {w}")
    # 2. pares
    for pid, g1, g2 in GR.INCOMPATIBLE_PAIRS:
        a, b = M.satisfiable(g1)[0], M.satisfiable(g2)[0]
        c, d = M.intersection_satisfiable(g1, g2)[0], S.satisfiable(S.conj(g1, g2))[0]
        if (a, b, c, d) != ("SAT", "SAT", "UNSAT", "UNSAT"):
            errs.append(f"{pid}: sozinhas {a}/{b}, interseção TRANSFORMS {c}, SEMANTICS {d} (esperado SAT/SAT/UNSAT)")
    for pid, g1, g2 in GR.COMPATIBLE_PAIRS:
        st, w = M.intersection_satisfiable(g1, g2)
        if st != "SAT" or not M.check_witness(M.intersect(g1, g2), w) or S.satisfiable(S.conj(g1, g2))[0] != "SAT":
            errs.append(f"{pid}: controle compatível não deu SAT com testemunha")
    # 3. composição
    for kid, g1, g2, exp in GR.COMPOSITIONS:
        st = M.compose(g1, g2)[0]
        roles3 = ("n0", "n1", "n2")
        s = S.satisfiable(S.conj(S.rename(g1, {"subject": "n0", "object": "n1"}),
                                 S.rename(g2, {"subject": "n1", "object": "n2"}), roles=roles3), roles3)[0]
        if st != exp or s != exp:
            errs.append(f"{kid}: composição TRANSFORMS {st}, SEMANTICS {s}, esperado {exp}")
    # 4. diferencial
    rng = random.Random(SEED)
    stats = {"generated": N_RANDOM, "typed": 0, "type_errors": 0, "agree_all": 0, "SAT": 0, "UNSAT": 0, "UNKNOWN": 0,
             "witness_checked": 0, "divergences": {}}
    samples = {}
    for _ in range(N_RANDOM):
        g = _rand_guard(rng)
        ta, tb = _typecheck_agree(g, S)
        if ta != tb:
            errs.append(f"typecheck diverge (TRANSFORMS {ta}, SEMANTICS {tb}): {json.dumps(g)}")
            continue
        if not ta:
            stats["type_errors"] += 1
            continue
        stats["typed"] += 1
        m, w = M.satisfiable(g)
        b = M.brute_force(g)
        s = S.satisfiable(g)[0]
        stats[m] += 1
        if m != b:
            errs.append(f"TRANSFORMS {m} ≠ força bruta {b}: {json.dumps(g)}")
            continue
        if m == "SAT":
            stats["witness_checked"] += 1
            if not M.check_witness(g, w):
                errs.append(f"testemunha não avalia TRUE: {json.dumps(g)} -> {w}")
        if m == s:
            stats["agree_all"] += 1
            continue
        cls = classify(g)
        key = f"{cls}: TRANSFORMS={m} SEMANTICS={s}"
        stats["divergences"][key] = stats["divergences"].get(key, 0) + 1
        samples.setdefault(key, g)
        if cls == "não documentada" or m != "UNSAT" or s not in ("SAT", "UNKNOWN"):
            errs.append(f"divergência não documentada ({key}): {json.dumps(g)}")
    rep = C.report("guard_sat", {"ok": not errs, "seed": SEED, "sat_tests": len(gram["sat_tests"]),
                                 "incompatible_pairs": len(GR.INCOMPATIBLE_PAIRS),
                                 "compatible_pairs": len(GR.COMPATIBLE_PAIRS), "compositions": len(GR.COMPOSITIONS),
                                 "random": stats, "divergence_samples": samples, "errors": errs[:50]})
    if errs:
        for e in errs[:30]:
            print(f"REPROVADO: {e}", file=sys.stderr)
        return 1
    dv = sum(stats["divergences"].values())
    C.say(f"guard_sat: {len(gram['sat_tests'])} sat_tests iguais nas duas implementações e na força bruta; "
          f"{len(GR.INCOMPATIBLE_PAIRS)} interseções incompatíveis = UNSAT, {len(GR.COMPATIBLE_PAIRS)} controles SAT; "
          f"{len(GR.COMPOSITIONS)} composições; diferencial {stats['typed']} guardas tipadas: TRANSFORMS = força "
          f"bruta em todas, = SEMANTICS em {stats['agree_all']}, {dv} divergências documentadas "
          f"({'; '.join(f'{k} ×{v}' for k, v in sorted(stats['divergences'].items())) or 'nenhuma'}) -> OK ({rep})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
