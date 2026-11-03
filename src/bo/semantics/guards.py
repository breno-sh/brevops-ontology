"""Gramática de guarda tipada e decidível (C10): conjunção de átomos <termo, operador, valor>.

Operadores (os 7 do plano): eq, in, present, refers_to_kind, region_in, edition_in, version_range.
Termo = '<papel>.<caminho>', papel ∈ {subject, object}. Termos de contexto reservados por papel:
  <papel>.region (region_in), <papel>.edition (edition_in), <papel>.provider_version (version_range).
Termo vizinho (valor de outro atributo) declara o tipo em term_types; refers_to_kind usa um termo de referência.

Três decisões, todas executáveis:
  typecheck(g)        guarda bem tipada ou GuardTypeError (regra GUARD-TYPE)
  satisfiable(g)      SAT (com testemunha) | UNSAT | UNKNOWN (regra GUARD-SAT, K-GUARD-*)
  evaluate(g, ctx)    TRUE | FALSE | INDETERMINATE (termo não lido) (regra T-GUARD)
Não há negação nem disjunção: a conjunção de restrições por termo é decidida termo a termo. Exclusividade de
realizações alternativas = interseção UNSAT (regra A-EXCL). Tipos de referência distintos só são incompatíveis
se a disjunção foi declarada (kind_disjoint); sem ela a satisfatibilidade é UNKNOWN (mundo aberto).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .vocab import is_marker, ABSENT, NOT_READ, SYMBOLIC

OPS = ("eq", "in", "present", "refers_to_kind", "region_in", "edition_in", "version_range")
ROLES = ("subject", "object")
CONTEXT_TERM = {"region_in": "region", "edition_in": "edition", "version_range": "provider_version"}
SCALAR_TYPES = ("string", "enum", "boolean", "integer")
_VER = re.compile(r"^\d+(\.\d+){0,3}$")

SAT, UNSAT, UNKNOWN = "SAT", "UNSAT", "UNKNOWN"
TRUE, FALSE, INDETERMINATE = "TRUE", "FALSE", "INDETERMINATE"


class GuardTypeError(ValueError):
    pass


def ver(s: str) -> tuple:
    if not isinstance(s, str) or not _VER.match(s):
        raise GuardTypeError(f"versão inválida: {s!r}")
    t = tuple(int(x) for x in s.split("."))
    return t + (0,) * (4 - len(t))


def empty() -> dict:
    return {"all": []}


def role_of(term: str) -> str:
    return term.split(".", 1)[0]


def _check_term(term, roles=ROLES) -> None:
    if not isinstance(term, str) or "." not in term or role_of(term) not in roles:
        raise GuardTypeError(f"termo inválido (papel.caminho, papel ∈ {tuple(roles)}): {term!r}")


def _type_of(g: dict, term: str) -> dict:
    tt = (g.get("term_types") or {}).get(term)
    if tt is None:
        raise GuardTypeError(f"termo vizinho sem tipo declarado em term_types: {term}")
    if tt.get("datatype") not in SCALAR_TYPES:
        raise GuardTypeError(f"tipo de termo não escalar: {term}: {tt}")
    return tt


def _check_value(tt: dict, v, term: str) -> None:
    dt = tt["datatype"]
    ok = (isinstance(v, bool) if dt == "boolean" else
          isinstance(v, int) and not isinstance(v, bool) if dt == "integer" else isinstance(v, str))
    if not ok:
        raise GuardTypeError(f"{term}: valor {v!r} não é {dt}")
    if tt.get("enum") is not None and v not in tt["enum"]:
        raise GuardTypeError(f"{term}: valor {v!r} fora do enum declarado")


def typecheck(g: dict, roles=ROLES) -> None:
    if not isinstance(g, dict) or not isinstance(g.get("all", None), list):
        raise GuardTypeError("guarda é {'all': [átomos], 'term_types'?: {...}, 'kind_disjoint'?: [[k1,k2],...]}")
    extra = set(g) - {"all", "term_types", "kind_disjoint"}
    if extra:
        raise GuardTypeError(f"campos desconhecidos na guarda: {sorted(extra)}")
    for a in g["all"]:
        if not isinstance(a, dict) or set(a) != {"term", "op", "value"}:
            raise GuardTypeError(f"átomo é {{term, op, value}}: {a!r}")
        op, term, v = a["op"], a["term"], a["value"]
        if op not in OPS:
            raise GuardTypeError(f"operador fora da gramática: {op!r} (só {OPS})")
        _check_term(term, roles)
        if op in CONTEXT_TERM:
            if term.split(".", 1)[1] != CONTEXT_TERM[op]:
                raise GuardTypeError(f"{op} só vale sobre <papel>.{CONTEXT_TERM[op]}: {term}")
            if op == "version_range":
                if not isinstance(v, dict) or not set(v) <= {"min", "max_exclusive"} or not v:
                    raise GuardTypeError(f"version_range é {{min?, max_exclusive?}}: {v!r}")
                lo = ver(v["min"]) if "min" in v else None
                hi = ver(v["max_exclusive"]) if "max_exclusive" in v else None
                if lo is not None and hi is not None and lo >= hi:
                    raise GuardTypeError(f"version_range vazio: {v}")
            elif not isinstance(v, list) or not v or not all(isinstance(x, str) for x in v):
                raise GuardTypeError(f"{op} exige lista não vazia de textos: {v!r}")
        elif op == "present":
            if not isinstance(v, bool):
                raise GuardTypeError(f"present exige booleano: {v!r}")
        elif op == "refers_to_kind":
            if not isinstance(v, str) or not v:
                raise GuardTypeError(f"refers_to_kind exige o nome do tipo: {v!r}")
        else:
            tt = _type_of(g, term)
            if op == "eq":
                _check_value(tt, v, term)
            else:
                if not isinstance(v, list) or not v:
                    raise GuardTypeError(f"in exige lista não vazia: {v!r}")
                for x in v:
                    _check_value(tt, x, term)
    for pair in g.get("kind_disjoint") or []:
        if not (isinstance(pair, list) and len(pair) == 2 and all(isinstance(x, str) for x in pair)):
            raise GuardTypeError(f"kind_disjoint é lista de pares: {pair!r}")


@dataclass
class _Cons:
    allowed: set | None = None     # None = sem restrição de valor
    lo: tuple | None = None
    hi: tuple | None = None        # exclusivo
    present: bool | None = None
    kinds: set | None = None
    universe: set | None = None    # enum declarado (fechado)
    dtype: str | None = None       # datatype declarado em term_types


def _constraints(g: dict) -> dict[str, _Cons]:
    cons: dict[str, _Cons] = {}
    tt = g.get("term_types") or {}
    for a in g["all"]:
        op, term, v = a["op"], a["term"], a["value"]
        c = cons.setdefault(term, _Cons())
        c.dtype = (tt.get(term) or {}).get("datatype")
        if term in tt and tt[term].get("datatype") == "boolean":
            c.universe = {True, False}
        elif term in tt and tt[term].get("enum") is not None:
            c.universe = set(tt[term]["enum"])
        if op in ("eq",):
            vals = {v}
        elif op in ("in", "region_in", "edition_in"):
            vals = set(v)
        else:
            vals = None
        if vals is not None:
            c.allowed = vals if c.allowed is None else c.allowed & vals
        if op == "version_range":
            if "min" in v:
                lo = ver(v["min"])
                c.lo = lo if c.lo is None else max(c.lo, lo)
            if "max_exclusive" in v:
                hi = ver(v["max_exclusive"])
                c.hi = hi if c.hi is None else min(c.hi, hi)
        if op == "present":
            if c.present is not None and c.present != v:
                c.present = "CONFLICT"
            else:
                c.present = v
        if op == "refers_to_kind":
            c.kinds = {v} if c.kinds is None else c.kinds | {v}
    return cons


def satisfiable(g: dict, roles=ROLES) -> tuple[str, dict]:
    """(SAT|UNSAT|UNKNOWN, testemunha ou motivo)."""
    typecheck(g, roles)
    disj = {frozenset(p) for p in (g.get("kind_disjoint") or [])}
    witness, unknown = {}, []
    for term, c in sorted(_constraints(g).items()):
        if c.present == "CONFLICT":
            return UNSAT, {"term": term, "why": "present true e false"}
        has_value_cons = c.allowed is not None or c.lo is not None or c.hi is not None or c.kinds is not None
        if c.present is False and has_value_cons:
            return UNSAT, {"term": term, "why": "present false com restrição de valor"}
        ranged = c.lo is not None or c.hi is not None
        if c.kinds and (c.allowed is not None or ranged or c.universe is not None):
            # um valor é referência OU escalar: refers_to_kind com eq/in/region_in/edition_in/version_range ou com
            # termo de universo fechado (enum, booleano) no mesmo termo não tem valor possível
            return UNSAT, {"term": term, "why": "referência e restrição de valor escalar no mesmo termo"}
        if c.allowed is not None or (ranged and c.universe is not None):
            vals = c.allowed if c.allowed is not None else set(c.universe)
            if c.universe is not None:
                vals = vals & c.universe
            if ranged:
                vals = {x for x in vals if _in_ver(x, c.lo, c.hi)}
            if not vals:
                return UNSAT, {"term": term, "why": "nenhum valor do domínio satisfaz as restrições"}
            witness[term] = sorted(vals, key=str)[0]
        elif ranged:
            if (c.lo is not None and c.hi is not None and c.lo >= c.hi) or (c.lo is None and c.hi == (0, 0, 0, 0)):
                return UNSAT, {"term": term, "why": "faixa de versão vazia"}
            if c.dtype not in (None, "string"):
                return UNSAT, {"term": term, "why": f"faixa de versão sobre termo {c.dtype}"}
            witness[term] = ".".join(str(x) for x in (c.lo or (0, 0, 0, 0)))
        if c.kinds is not None and len(c.kinds) > 1:
            ks = sorted(c.kinds)
            pairs = [(a, b) for i, a in enumerate(ks) for b in ks[i + 1:]]
            if any(frozenset(p) in disj for p in pairs):
                return UNSAT, {"term": term, "why": f"tipos de referência declarados disjuntos: {ks}"}
            unknown.append({"term": term, "why": f"tipos {ks} sem disjunção declarada (mundo aberto)"})
        elif c.kinds:
            witness[term] = {"$kind": next(iter(c.kinds))}
        if c.present is True and term not in witness:
            witness[term] = {"$present": True}
        if c.present is False:
            witness[term] = ABSENT
    if unknown:
        return UNKNOWN, {"undecided": unknown}
    return SAT, witness


def _in_ver(x, lo, hi) -> bool:
    try:
        v = ver(x)
    except GuardTypeError:
        return False
    return (lo is None or v >= lo) and (hi is None or v < hi)


def conj(*gs: dict, roles=ROLES) -> dict:
    """Interseção (conjunção) de guardas; tipos de termo conflitantes são erro de tipo."""
    out = {"all": [], "term_types": {}, "kind_disjoint": []}
    for g in gs:
        typecheck(g, roles)
        out["all"].extend(g["all"])
        for t, ty in (g.get("term_types") or {}).items():
            if t in out["term_types"] and out["term_types"][t] != ty:
                raise GuardTypeError(f"tipos conflitantes para {t}")
            out["term_types"][t] = ty
        for p in g.get("kind_disjoint") or []:
            if p not in out["kind_disjoint"]:
                out["kind_disjoint"].append(p)
    if not out["term_types"]:
        del out["term_types"]
    if not out["kind_disjoint"]:
        del out["kind_disjoint"]
    return out


def rename(g: dict, mapping: dict[str, str]) -> dict:
    """Troca os papéis dos termos (subject/object -> nomes de nó) para compor guardas de duas alegações."""
    def rt(t):
        r, rest = t.split(".", 1)
        return f"{mapping.get(r, r)}.{rest}"
    out = {"all": [{"term": rt(a["term"]), "op": a["op"], "value": a["value"]} for a in g.get("all", [])]}
    if g.get("term_types"):
        out["term_types"] = {rt(t): ty for t, ty in g["term_types"].items()}
    if g.get("kind_disjoint"):
        out["kind_disjoint"] = g["kind_disjoint"]
    return out


def project(g: dict, keep_roles: set[str]) -> dict:
    """Eliminação existencial dos termos de outros papéis (exata: os átomos são por termo)."""
    out = {"all": [a for a in g["all"] if role_of(a["term"]) in keep_roles]}
    tt = {t: ty for t, ty in (g.get("term_types") or {}).items() if role_of(t) in keep_roles}
    if tt:
        out["term_types"] = tt
    if g.get("kind_disjoint"):
        out["kind_disjoint"] = g["kind_disjoint"]
    return out


def flip(g: dict) -> dict:
    """Guarda da alegação inversa: subject <-> object."""
    return _relabel(g, {"subject": "object", "object": "subject"})


def _relabel(g, m):
    out = rename(g, {"subject": "__s", "object": "__o"})
    return rename(out, {"__s": m["subject"], "__o": m["object"]})


def evaluate(g: dict, ctx: dict) -> tuple[str, list]:
    """Avalia a guarda num contexto {termo: valor}. Termo ausente do contexto ou NOT_READ/SYMBOLIC = não lido."""
    typecheck(g)
    indet, false = [], []
    for a in g["all"]:
        term, op, v = a["term"], a["op"], a["value"]
        if term not in ctx or is_marker(ctx[term], NOT_READ) or is_marker(ctx[term], SYMBOLIC):
            indet.append(term)
            continue
        x = ctx[term]
        absent = is_marker(x, ABSENT)
        if op == "present":
            ok = (not absent) == v
        elif absent:
            ok = False
        elif op == "eq":
            ok = x == v
        elif op in ("in", "region_in", "edition_in"):
            ok = x in v
        elif op == "version_range":
            try:
                vv = ver(x)
                ok = ("min" not in v or vv >= ver(v["min"])) and ("max_exclusive" not in v or vv < ver(v["max_exclusive"]))
            except GuardTypeError:
                ok = False      # valor que não é versão não está na faixa
        elif op == "refers_to_kind":
            ok = isinstance(x, dict) and x.get("$kind") == v
        else:  # pragma: no cover - typecheck impede
            raise GuardTypeError(op)
        if not ok:
            false.append(term)
    if false:
        return FALSE, false
    if indet:
        return INDETERMINATE, indet
    return TRUE, []


def terms(g: dict) -> set[str]:
    return {a["term"] for a in g.get("all", [])}
