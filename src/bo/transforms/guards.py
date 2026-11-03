"""Gramática de guarda tipada e decidível do C10 (implementação do TRANSFORMS).

Guarda = conjunção de átomos ⟨termo, operador, valor⟩, sem negação nem disjunção:
  {"all": [{"term": "<papel>.<caminho>", "op": OP, "value": V}, ...],
   "term_types"?: {termo: {"datatype": string|enum|boolean|integer, "enum"?: [...]}},
   "kind_disjoint"?: [[tipo1, tipo2], ...]}
papel ∈ {subject, object} (na composição, n0/n1/n2). Operadores:
  eq V              termo tipado em term_types; V do tipo
  in [V...]         termo tipado; lista não vazia de valores do tipo
  present bool      true: o termo tem valor; false: sabidamente ausente
  refers_to_kind K  o termo é referência para unidade do tipo K
  region_in [..]    só sobre <papel>.region
  edition_in [..]   só sobre <papel>.edition
  version_range {min?, max_exclusive?}   só sobre <papel>.provider_version; versões 'n(.n){0,3}'

Decisão (os átomos restringem só o próprio termo, então decide-se termo a termo):
  typecheck(g)       bem tipada ou GuardTypeError
  satisfiable(g)     SAT (com testemunha que avalia TRUE) | UNSAT (com o termo e o porquê) | UNKNOWN
                     UNKNOWN só quando um termo exige dois tipos de referência sem disjunção declarada (mundo aberto)
  evaluate(g, ctx)   TRUE | FALSE | INDETERMINATE (termo fora do contexto, NOT_READ ou simbólico)
  intersect(g1, g2)  conjunção; tipos de termo conflitantes são erro de tipo
  compose(g12, g23)  papéis renomeados (n0, n1, n2), conjunção, eliminação existencial de n1

Esta implementação é independente da de bo.semantics.guards (mesma gramática, outro algoritmo): domínio por
termo como conjunto finito (quando o tipo é fechado ou há restrição de valor) ou intervalo de versões, e a
testemunha é sempre conferida pelo evaluate. O guard_sat compara as duas e um oráculo de força bruta.
"""

from __future__ import annotations

import re

from .markers import ABSENT, is_absent, is_not_read, is_symbolic

OPS = ("eq", "in", "present", "refers_to_kind", "region_in", "edition_in", "version_range")
ROLES = ("subject", "object")
CONTEXT_TERM = {"region_in": "region", "edition_in": "edition", "version_range": "provider_version"}
TERM_DATATYPES = ("string", "enum", "boolean", "integer")
SAT, UNSAT, UNKNOWN = "SAT", "UNSAT", "UNKNOWN"
TRUE, FALSE, INDETERMINATE = "TRUE", "FALSE", "INDETERMINATE"
_VER = re.compile(r"^\d+(\.\d+){0,3}$")
_ZERO = (0, 0, 0, 0)


class GuardTypeError(ValueError):
    pass


def ver(s) -> tuple:
    if not isinstance(s, str) or not _VER.match(s):
        raise GuardTypeError(f"versão inválida (n(.n){{0,3}}): {s!r}")
    t = tuple(int(x) for x in s.split("."))
    return t + (0,) * (4 - len(t))


def _ver_str(t: tuple) -> str:
    return ".".join(str(x) for x in t)


# ---------------------------------------------------------------------------------------------- tipagem
def _role(term) -> str:
    return term.split(".", 1)[0]


def _ok_value(dt, v) -> bool:
    if dt == "boolean":
        return isinstance(v, bool)
    if dt == "integer":
        return isinstance(v, int) and not isinstance(v, bool)
    return isinstance(v, str)


def _declared(g, term) -> dict:
    tt = (g.get("term_types") or {}).get(term)
    if tt is None:
        raise GuardTypeError(f"termo sem tipo em term_types: {term}")
    if not isinstance(tt, dict) or tt.get("datatype") not in TERM_DATATYPES:
        raise GuardTypeError(f"tipo de termo fora de {TERM_DATATYPES}: {term}: {tt!r}")
    return tt


def _check_val(tt, v, term):
    if not _ok_value(tt["datatype"], v):
        raise GuardTypeError(f"{term}: {v!r} não é {tt['datatype']}")
    if tt.get("enum") is not None and v not in tt["enum"]:
        raise GuardTypeError(f"{term}: {v!r} fora do enum declarado")


def typecheck(g, roles=ROLES) -> None:
    if not isinstance(g, dict) or not isinstance(g.get("all"), list):
        raise GuardTypeError("guarda é {'all': [átomos], 'term_types'?, 'kind_disjoint'?}")
    if set(g) - {"all", "term_types", "kind_disjoint"}:
        raise GuardTypeError(f"campos desconhecidos: {sorted(set(g) - {'all', 'term_types', 'kind_disjoint'})}")
    for a in g["all"]:
        if not isinstance(a, dict) or set(a) != {"term", "op", "value"}:
            raise GuardTypeError(f"átomo é {{term, op, value}}: {a!r}")
        term, op, v = a["term"], a["op"], a["value"]
        if op not in OPS:
            raise GuardTypeError(f"operador fora da gramática: {op!r}")
        if not isinstance(term, str) or "." not in term or _role(term) not in roles:
            raise GuardTypeError(f"termo inválido (papel ∈ {tuple(roles)}): {term!r}")
        if op in CONTEXT_TERM:
            if term.split(".", 1)[1] != CONTEXT_TERM[op]:
                raise GuardTypeError(f"{op} só sobre <papel>.{CONTEXT_TERM[op]}: {term}")
            if op == "version_range":
                if not isinstance(v, dict) or not v or set(v) - {"min", "max_exclusive"}:
                    raise GuardTypeError(f"version_range é {{min?, max_exclusive?}}: {v!r}")
                lo = ver(v["min"]) if "min" in v else None
                hi = ver(v["max_exclusive"]) if "max_exclusive" in v else None
                if lo is not None and hi is not None and lo >= hi:
                    raise GuardTypeError(f"version_range vazio: {v}")
            elif not (isinstance(v, list) and v and all(isinstance(x, str) for x in v)):
                raise GuardTypeError(f"{op} exige lista não vazia de textos: {v!r}")
        elif op == "present":
            if not isinstance(v, bool):
                raise GuardTypeError(f"present exige booleano: {v!r}")
        elif op == "refers_to_kind":
            if not isinstance(v, str) or not v:
                raise GuardTypeError(f"refers_to_kind exige nome de tipo: {v!r}")
        else:
            tt = _declared(g, term)
            if op == "eq":
                _check_val(tt, v, term)
            else:
                if not isinstance(v, list) or not v:
                    raise GuardTypeError(f"in exige lista não vazia: {v!r}")
                for x in v:
                    _check_val(tt, x, term)
    for pair in g.get("kind_disjoint") or []:
        if not (isinstance(pair, list) and len(pair) == 2 and all(isinstance(x, str) for x in pair)):
            raise GuardTypeError(f"kind_disjoint é lista de pares de textos: {pair!r}")


# ------------------------------------------------------------------------------------------- decisão
def _universe(g, term):
    """Universo fechado do termo (boolean ou enum declarado) ou None (aberto)."""
    tt = (g.get("term_types") or {}).get(term)
    if not tt:
        return None
    if tt.get("datatype") == "boolean":
        return [True, False]
    if tt.get("enum") is not None:
        return list(tt["enum"])
    return None


def _decide_term(g, term, atoms, disjoint) -> tuple[str, object]:
    """(SAT, valor-testemunha) | (UNSAT, porquê) | (UNKNOWN, porquê) para um termo."""
    presence = {True, False}
    values = None          # None = sem restrição de valor; senão lista de candidatos
    lo = hi = None
    kinds = set()
    value_constrained = False
    for a in atoms:
        op, v = a["op"], a["value"]
        if op == "present":
            presence &= {v}
            continue
        value_constrained = True
        if op == "eq":
            vals = [v]
        elif op in ("in", "region_in", "edition_in"):
            vals = list(v)
        else:
            vals = None
        if vals is not None:
            values = [x for x in (vals if values is None else values) if any(x == y and type(x) is type(y) for y in vals)]
        if op == "version_range":
            if "min" in v:
                lo = ver(v["min"]) if lo is None else max(lo, ver(v["min"]))
            if "max_exclusive" in v:
                hi = ver(v["max_exclusive"]) if hi is None else min(hi, ver(v["max_exclusive"]))
        if op == "refers_to_kind":
            kinds.add(v)
    if not presence:
        return UNSAT, "present true e false"
    if value_constrained:
        if True not in presence:
            return UNSAT, "present false com restrição de valor"
    if presence == {False}:
        return SAT, dict(ABSENT)
    uni = _universe(g, term)
    dt = ((g.get("term_types") or {}).get(term) or {}).get("datatype")
    if kinds and (values is not None or lo is not None or hi is not None or uni is not None):
        return UNSAT, "referência (refers_to_kind) com restrição de valor escalar ou universo fechado no mesmo termo"
    if (lo is not None or hi is not None) and dt not in (None, "string", "enum"):
        return UNSAT, f"faixa de versão sobre termo {dt} (versão é texto)"
    if len(kinds) > 1:
        ks = sorted(kinds)
        dj = {frozenset(p) for p in disjoint}
        if any(frozenset((a, b)) in dj for i, a in enumerate(ks) for b in ks[i + 1:]):
            return UNSAT, f"tipos de referência declarados disjuntos: {ks}"
        return UNKNOWN, f"tipos {ks} sem disjunção declarada (mundo aberto)"
    if kinds:
        return SAT, {"$kind": next(iter(kinds))}
    ranged = lo is not None or hi is not None
    if ranged and lo is None and hi == _ZERO:
        return UNSAT, "faixa de versão vazia (abaixo de 0)"
    if ranged and lo is not None and hi is not None and lo >= hi:
        return UNSAT, "faixa de versão vazia"
    if values is None and uni is not None:
        values = list(uni)
    if values is not None:
        if uni is not None:
            values = [x for x in values if x in uni]
        if ranged:
            values = [x for x in values if _in_range(x, lo, hi)]
        if not values:
            return UNSAT, "interseção vazia dos valores permitidos" + (" com a faixa de versão" if ranged else "")
        return SAT, sorted(values, key=lambda x: (str(type(x)), str(x)))[0]
    if ranged:
        return SAT, _ver_str(lo or _ZERO)
    return SAT, {"$present": True}


def _in_range(x, lo, hi) -> bool:
    try:
        v = ver(x)
    except GuardTypeError:
        return False
    return (lo is None or v >= lo) and (hi is None or v < hi)


def satisfiable(g, roles=ROLES) -> tuple[str, dict]:
    typecheck(g, roles)
    by_term: dict[str, list] = {}
    for a in g["all"]:
        by_term.setdefault(a["term"], []).append(a)
    disjoint = g.get("kind_disjoint") or []
    witness, unknown = {}, []
    for term in sorted(by_term):
        st, w = _decide_term(g, term, by_term[term], disjoint)
        if st == UNSAT:
            return UNSAT, {"term": term, "why": w}
        if st == UNKNOWN:
            unknown.append({"term": term, "why": w})
        else:
            witness[term] = w
    if unknown:
        return UNKNOWN, {"undecided": unknown}
    return SAT, witness


def evaluate(g, ctx: dict, roles=ROLES) -> tuple[str, list]:
    """Avalia num contexto {termo: valor}; ausência do termo no contexto, NOT_READ ou simbólico = não lido."""
    typecheck(g, roles)
    indet, false = [], []
    for a in g["all"]:
        term, op, v = a["term"], a["op"], a["value"]
        if term not in ctx or is_not_read(ctx[term]) or is_symbolic(ctx[term]):
            indet.append(term)
            continue
        x = ctx[term]
        absent = is_absent(x)
        if op == "present":
            ok = (not absent) == v
        elif absent:
            ok = False
        elif op == "eq":
            ok = x == v and type(x) is type(v)
        elif op in ("in", "region_in", "edition_in"):
            ok = any(x == y and type(x) is type(y) for y in v)
        elif op == "version_range":
            ok = _in_range(x, ver(v["min"]) if "min" in v else None,
                           ver(v["max_exclusive"]) if "max_exclusive" in v else None)
        else:
            ok = isinstance(x, dict) and x.get("$kind") == v
        if not ok:
            false.append(term)
    if false:
        return FALSE, false
    if indet:
        return INDETERMINATE, indet
    return TRUE, []


def check_witness(g, witness: dict, roles=ROLES) -> bool:
    return evaluate(g, witness, roles)[0] == TRUE


# ------------------------------------------------------------------------------------ interseção e composição
def intersect(*gs, roles=ROLES) -> dict:
    out = {"all": [], "term_types": {}, "kind_disjoint": []}
    for g in gs:
        typecheck(g, roles)
        out["all"].extend(dict(a) for a in g["all"])
        for t, ty in (g.get("term_types") or {}).items():
            if t in out["term_types"] and out["term_types"][t] != ty:
                raise GuardTypeError(f"tipos conflitantes para {t}: {out['term_types'][t]} x {ty}")
            out["term_types"][t] = ty
        for p in g.get("kind_disjoint") or []:
            if p not in out["kind_disjoint"]:
                out["kind_disjoint"].append(p)
    for k in ("term_types", "kind_disjoint"):
        if not out[k]:
            del out[k]
    return out


def intersection_satisfiable(g1, g2, roles=ROLES) -> tuple[str, dict]:
    return satisfiable(intersect(g1, g2, roles=roles), roles)


def rename(g, mapping: dict) -> dict:
    def rt(t):
        r, rest = t.split(".", 1)
        return f"{mapping.get(r, r)}.{rest}"
    out = {"all": [{"term": rt(a["term"]), "op": a["op"], "value": a["value"]} for a in g.get("all", [])]}
    if g.get("term_types"):
        out["term_types"] = {rt(t): ty for t, ty in g["term_types"].items()}
    if g.get("kind_disjoint"):
        out["kind_disjoint"] = [list(p) for p in g["kind_disjoint"]]
    return out


def compose(g_ab, g_bc) -> tuple[str, dict, dict]:
    """Guarda de a->c a partir de a->b e b->c: (resultado da satisfatibilidade, guarda projetada, detalhe)."""
    roles3 = ("n0", "n1", "n2")
    whole = intersect(rename(g_ab, {"subject": "n0", "object": "n1"}),
                      rename(g_bc, {"subject": "n1", "object": "n2"}), roles=roles3)
    st, det = satisfiable(whole, roles3)
    keep = {"all": [a for a in whole["all"] if _role(a["term"]) in ("n0", "n2")]}
    tt = {t: ty for t, ty in (whole.get("term_types") or {}).items() if _role(t) in ("n0", "n2")}
    if tt:
        keep["term_types"] = tt
    if whole.get("kind_disjoint"):
        keep["kind_disjoint"] = whole["kind_disjoint"]
    return st, rename(keep, {"n0": "subject", "n2": "object"}), det


# ------------------------------------------------------------------------------------ oráculo de força bruta
def brute_force(g, roles=ROLES) -> str:
    """Oráculo independente: procura, termo a termo, um valor bem tipado que torne todos os átomos TRUE no
    evaluate, num conjunto finito de candidatos suficiente (constantes da guarda, valor novo, ABSENT, limites de
    versão, referências). UNKNOWN quando um termo pede dois tipos de referência sem disjunção declarada."""
    typecheck(g, roles)
    by_term: dict[str, list] = {}
    for a in g["all"]:
        by_term.setdefault(a["term"], []).append(a)
    dj = {frozenset(p) for p in g.get("kind_disjoint") or []}
    res = SAT
    for term, atoms in by_term.items():
        kinds = {a["value"] for a in atoms if a["op"] == "refers_to_kind"}
        if len(kinds) > 1:
            ks = sorted(kinds)
            if any(frozenset((a, b)) in dj for i, a in enumerate(ks) for b in ks[i + 1:]):
                return UNSAT
            # mundo aberto sobre tipos: decide-se só o subconjunto com UM tipo; se nem ele tem valor, é UNSAT
            atoms = [a for a in atoms if a["op"] != "refers_to_kind"] + [
                next(a for a in atoms if a["op"] == "refers_to_kind")]
            sub = {"all": atoms, **({"term_types": g["term_types"]} if g.get("term_types") else {})}
            if any(evaluate(sub, {term: c}, roles)[0] == TRUE for c in _candidates(g, term, atoms)):
                res = UNKNOWN
                continue
            return UNSAT
        sub = {"all": atoms, **({"term_types": g["term_types"]} if g.get("term_types") else {})}
        if not any(evaluate(sub, {term: c}, roles)[0] == TRUE for c in _candidates(g, term, atoms)):
            return UNSAT
    return res


def _candidates(g, term, atoms):
    tt = (g.get("term_types") or {}).get(term) or {}
    dt = tt.get("datatype")
    uni = _universe(g, term)
    cands = [dict(ABSENT)]
    if uni is not None:
        return cands + list(uni)
    consts = []
    for a in atoms:
        v = a["value"]
        if a["op"] == "eq":
            consts.append(v)
        elif a["op"] in ("in", "region_in", "edition_in"):
            consts.extend(v)
        elif a["op"] == "version_range":
            consts.extend(x for x in v.values())
            consts.append("0")
        elif a["op"] == "refers_to_kind":
            cands.append({"$kind": v})
    if dt == "integer":
        consts = [c for c in consts if isinstance(c, int) and not isinstance(c, bool)] + [987654]
    else:
        consts = [c for c in consts if isinstance(c, str)] + ["__valor_novo__"]
    return cands + consts
