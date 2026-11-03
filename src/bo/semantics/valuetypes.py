"""Tipos de valor (parte semântica do C05), normalização e relação entre domínios de valores.

Um tipo declara datatype, grandeza (IRI | NOT_APPLICABLE | UNKNOWN), unidade, janela de taxa e convenção de
byte (N4: os dois fazem parte do tipo), domínio (enum, faixa com passo) e sentinelas. A relação entre domínios
é calculada, não declarada: equal, subset, superset, overlap, disjoint (as cinco do RCC5) ou unknown.

O núcleo de unidades abaixo é o mínimo para executar a teoria (fatores exatos em Fraction). Os IRIs QUDT são
comparados por igualdade de texto; o registro fechado de unidades e a conferência dos IRIs é do UNITS.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from fractions import Fraction

from .vocab import NOT_APPLICABLE, UNKNOWN

TIME = "quantitykind:Time"
INFO = "quantitykind:InformationEntropy"
COUNT = "quantitykind:Count"
RATIO = "quantitykind:DimensionlessRatio"

# unidade -> (grandeza, fator para a unidade base da grandeza ou None se não é fixo, convenção de byte)
UNITS: dict[str, tuple[str, Fraction | None, str | None]] = {
    "unit:SEC": (TIME, Fraction(1), None),
    "unit:MIN": (TIME, Fraction(60), None),
    "unit:HR": (TIME, Fraction(3600), None),
    "unit:DAY": (TIME, Fraction(86400), None),
    "unit:WK": (TIME, Fraction(604800), None),
    "unit:MO": (TIME, None, None),      # mês não é número fixo de segundos (CMT-LOSS-U01)
    "unit:YR": (TIME, None, None),      # ano idem
    "unit:BYTE": (INFO, Fraction(1), None),
    "unit:KiloBYTE": (INFO, Fraction(10**3), "SI"),
    "unit:MegaBYTE": (INFO, Fraction(10**6), "SI"),
    "unit:GigaBYTE": (INFO, Fraction(10**9), "SI"),
    "unit:KibiBYTE": (INFO, Fraction(2**10), "IEC"),
    "unit:MebiBYTE": (INFO, Fraction(2**20), "IEC"),
    "unit:GibiBYTE": (INFO, Fraction(2**30), "IEC"),
    "unit:NUM": (COUNT, Fraction(1), None),
    "unit:PERCENT": (RATIO, Fraction(1, 100), None),
}
DATATYPES = ("integer", "decimal", "boolean", "string", "enum", "duration", "tuple")
NUMERIC = ("integer", "decimal")


class TypeError_(ValueError):
    """Tipo mal declarado (regra KIND-*/UNIT-*)."""


class OutOfDomain(ValueError):
    """Valor fora do domínio de uma função parcial (TRANSFORM_OUT_OF_DOMAIN)."""


def frac(x) -> Fraction:
    if isinstance(x, bool):
        raise TypeError_("booleano não é número")
    if isinstance(x, Fraction):
        return x
    if isinstance(x, int):
        return Fraction(x)
    if isinstance(x, float):
        return Fraction(str(x))
    if isinstance(x, str):
        return Fraction(x)
    raise TypeError_(f"não numérico: {x!r}")


def jnum(x: Fraction):
    """Fraction -> número JSON (int quando inteiro; senão texto exato 'p/q')."""
    x = Fraction(x)
    return int(x) if x.denominator == 1 else f"{x.numerator}/{x.denominator}"


_DUR = re.compile(r"^P(?:(\d+)Y)?(?:(\d+)M)?(?:(\d+)W)?(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?)?$")


def duration_seconds(s: str, calendar_context: dict | None = None) -> Fraction:
    """xsd:duration -> segundos. Y e M (mês) só com contexto de calendário explícito; sem ele, fora do domínio."""
    m = _DUR.match(s or "")
    if not m or s in ("P", "PT"):
        raise OutOfDomain(f"duração inválida: {s!r}")
    y, mo, w, d, h, mi, sec = m.groups()
    if (y and int(y)) or (mo and int(mo)):
        if not calendar_context or "seconds_per_month" not in calendar_context:
            raise OutOfDomain(f"{s}: mês/ano não é número fixo de segundos sem contexto de calendário")
        spm = frac(calendar_context["seconds_per_month"])
        months = int(y or 0) * 12 + int(mo or 0)
        base = months * spm
    else:
        base = Fraction(0)
    return (base + int(w or 0) * 604800 + int(d or 0) * 86400 + int(h or 0) * 3600 + int(mi or 0) * 60
            + Fraction(sec or "0"))


# ----------------------------------------------------------------------------------------------- domínios
@dataclass(frozen=True)
class AnyDomain:
    """Domínio não declarado (aberto). A relação com ele é sempre 'unknown'."""
    datatype: str = "any"


@dataclass(frozen=True)
class EnumDomain:
    values: frozenset


@dataclass(frozen=True)
class NumDomain:
    """{x : lo <= x <= hi, (x - base) múltiplo de step}; lo/hi None = sem limite; step None = contínuo."""
    lo: Fraction | None
    hi: Fraction | None
    step: Fraction | None = None
    base: Fraction = Fraction(0)

    def contains(self, x) -> bool:
        x = frac(x)
        if self.lo is not None and x < self.lo:
            return False
        if self.hi is not None and x > self.hi:
            return False
        if self.step is not None and (x - self.base) % self.step != 0:
            return False
        return True

    def first(self):
        if self.step is None:
            return self.lo
        if self.lo is None:
            return None
        k = math.ceil((self.lo - self.base) / self.step)
        return self.base + k * self.step

    def last(self):
        if self.step is None:
            return self.hi
        if self.hi is None:
            return None
        k = math.floor((self.hi - self.base) / self.step)
        return self.base + k * self.step

    def empty(self) -> bool:
        f, l = self.first(), self.last()
        return f is not None and l is not None and f > l

    def count(self):
        """Número de pontos (None se infinito ou contínuo com mais de um ponto)."""
        if self.empty():
            return 0
        f, l = self.first(), self.last()
        if f is None or l is None:
            return None
        if self.step is None:
            return 1 if f == l else None
        return int((l - f) / self.step) + 1

    def points(self):
        f = self.first()
        n = self.count()
        if n is None:
            raise ValueError("domínio infinito")
        return [f + i * (self.step or 0) for i in range(n)]


def domain_contains(d, v) -> bool:
    if isinstance(d, AnyDomain):
        return True
    if isinstance(d, EnumDomain):
        return v in d.values or (_is_num(v) and any(_is_num(x) and frac(x) == frac(v) for x in d.values))
    if isinstance(d, NumDomain):
        return _is_num(v) and d.contains(v)
    raise TypeError_(f"domínio desconhecido {d!r}")


def _is_num(v) -> bool:
    if isinstance(v, bool):
        return False
    if isinstance(v, (int, float, Fraction)):
        return True
    if isinstance(v, str):
        try:
            Fraction(v)
            return True
        except ValueError:
            return False
    return False


def _crt(a1: Fraction, m1: Fraction, a2: Fraction, m2: Fraction):
    """x ≡ a1 (mod m1), x ≡ a2 (mod m2) com módulos racionais: (resíduo, módulo) ou None."""
    den = math.lcm(a1.denominator, m1.denominator, a2.denominator, m2.denominator)
    A1, M1, A2, M2 = (int(v * den) for v in (a1, m1, a2, m2))
    g = math.gcd(M1, M2)
    if (A2 - A1) % g:
        return None
    l = M1 // g * M2
    # A1 + M1*t ≡ A2 (mod M2)
    t = ((A2 - A1) // g * pow(M1 // g, -1, M2 // g)) % (M2 // g) if M2 // g > 1 else 0
    r = (A1 + M1 * t) % l
    return Fraction(r, den), Fraction(l, den)


def _intersect_num(a: NumDomain, b: NumDomain):
    lo = a.lo if b.lo is None else (b.lo if a.lo is None else max(a.lo, b.lo))
    hi = a.hi if b.hi is None else (b.hi if a.hi is None else min(a.hi, b.hi))
    if a.step is None and b.step is None:
        return NumDomain(lo, hi, None)
    if a.step is None or b.step is None:
        d = a if a.step is not None else b
        return NumDomain(lo, hi, d.step, d.base)
    c = _crt(a.base, a.step, b.base, b.step)
    if c is None:
        return None
    return NumDomain(lo, hi, c[1], c[0])


def _subset_num(a: NumDomain, b: NumDomain) -> bool:
    if a.empty():
        return True
    fa, la = a.first(), a.last()
    if b.lo is not None and (fa is None or fa < b.lo):
        return False
    if b.hi is not None and (la is None or la > b.hi):
        return False
    if b.step is None:
        return True
    if a.count() == 1:
        return b.contains(fa)
    if a.step is None:
        return False   # contínuo com mais de um ponto não cabe num reticulado
    return a.step % b.step == 0 and (a.base - b.base) % b.step == 0


def relation(da, db) -> str:
    """Relação entre dois domínios (JEPD ou 'unknown'), orientada: da R db."""
    if isinstance(da, AnyDomain) or isinstance(db, AnyDomain):
        return "unknown"
    if isinstance(da, EnumDomain) and isinstance(db, EnumDomain):
        A, B = _norm_set(da.values), _norm_set(db.values)
        return _set_rel(A, B)
    if isinstance(da, NumDomain) and isinstance(db, NumDomain):
        inter = _intersect_num(da, db)
        nonempty = inter is not None and not inter.empty()
        if not nonempty:
            return "disjoint"
        ab, ba = _subset_num(da, db), _subset_num(db, da)
        return "equal" if ab and ba else "subset" if ab else "superset" if ba else "overlap"
    # enum x numérico
    if isinstance(da, NumDomain):
        r = relation(db, da)
        from .vocab import INVERSE_VDR
        return INVERSE_VDR[r]
    vals = _norm_set(da.values)
    if not all(_is_num(v) for v in vals):
        return "disjoint" if not any(_is_num(v) and db.contains(v) for v in vals) else "unknown"
    inA = {v for v in vals if db.contains(v)}
    n = db.count()
    if not inA:
        return "disjoint"
    if n is not None and n <= 100000:
        B = {frac(p) for p in db.points()}
        return _set_rel({frac(v) for v in vals}, B)
    return "subset" if len(inA) == len(vals) else "overlap"


def _norm_set(vals) -> frozenset:
    out = set()
    for v in vals:
        out.add(frac(v) if _is_num(v) and not isinstance(v, str) else v)
    return frozenset(out)


def _set_rel(A, B) -> str:
    if not A & B:
        return "disjoint"
    if A == B:
        return "equal"
    if A < B:
        return "subset"
    if A > B:
        return "superset"
    return "overlap"


# --------------------------------------------------------------------------------------------------- tipo
@dataclass(frozen=True)
class ValueType:
    datatype: str
    quantity_kind: str = NOT_APPLICABLE
    unit: str = NOT_APPLICABLE
    rate_window: str | None = None
    byte_convention: str | None = None
    enum: tuple | None = None
    range: tuple | None = None          # (min|None, max|None) na unidade do tipo
    step: str | None = None             # passo (inteiros: 1)
    sentinels: tuple = ()               # ((valor, significado), ...)
    components: tuple = ()              # tupla: ((nome, ValueType), ...)
    raw: dict = field(default_factory=dict, compare=False, hash=False)

    @staticmethod
    def from_dict(d: dict) -> "ValueType":
        if not isinstance(d, dict):
            raise TypeError_(f"tipo não é objeto: {d!r}")
        dt = d.get("datatype")
        if dt not in DATATYPES:
            raise TypeError_(f"datatype inválido: {dt!r}")
        qk = d.get("quantity_kind", NOT_APPLICABLE)
        unit = d.get("unit", NOT_APPLICABLE)
        if dt in NUMERIC and qk != NOT_APPLICABLE and qk != UNKNOWN:
            if unit == NOT_APPLICABLE:
                raise TypeError_("valor numérico com grandeza exige unidade (ou UNKNOWN)")
            if unit != UNKNOWN:
                if unit not in UNITS:
                    raise TypeError_(f"unidade fora do núcleo: {unit}")
                if UNITS[unit][0] != qk:
                    raise TypeError_(f"unidade {unit} não é da grandeza {qk}")
        bc = d.get("byte_convention")
        if unit in UNITS and UNITS[unit][2] and bc and bc != UNITS[unit][2]:
            raise TypeError_(f"convenção de byte {bc} contradiz a unidade {unit}")
        if unit in UNITS and UNITS[unit][2] and not bc:
            bc = UNITS[unit][2]
        rw = d.get("rate_window")
        if rw is not None:
            duration_seconds(rw)   # janela tem de ser duração fixa
        rng = d.get("range")
        if rng is not None:
            lo, hi = rng.get("min"), rng.get("max")
            rng = (None if lo is None else frac(lo), None if hi is None else frac(hi))
            if rng[0] is not None and rng[1] is not None and rng[0] > rng[1]:
                raise TypeError_("faixa vazia")
        enum = d.get("enum")
        comps = tuple((c["name"], ValueType.from_dict(c["type"])) for c in d.get("components", []))
        if dt == "tuple" and not comps:
            raise TypeError_("tupla exige componentes tipados (KIND-TUPLE)")
        sent = tuple(sorted(((str(k), v) for k, v in (d.get("sentinels") or {}).items())))
        step = d.get("step")
        if dt == "integer" and step is None:
            step = "1"
        return ValueType(dt, qk, unit, rw, bc, tuple(enum) if enum is not None else None, rng,
                         None if step is None else str(step), sent, comps, dict(d))

    # -- grandeza conhecida?
    def kind_unknown(self) -> bool:
        if self.datatype == "tuple":
            return any(t.kind_unknown() for _, t in self.components)
        return self.quantity_kind == UNKNOWN or (self.datatype in NUMERIC and self.unit == UNKNOWN)

    def signature(self) -> tuple:
        """O que tem de ser igual para dois lados falarem do mesmo valor (composição: K-DOMAIN)."""
        return (self.datatype, self.quantity_kind, self.unit, self.rate_window, self.byte_convention,
                tuple((n, t.signature()) for n, t in self.components))

    def is_sentinel(self, v) -> bool:
        return any(_eqv(v, k) for k, _ in self.sentinels)

    def sentinel_meaning(self, v):
        for k, m in self.sentinels:
            if _eqv(v, k):
                return m
        return None

    def domain(self):
        """Domínio no espaço de valores do próprio tipo (sem as sentinelas)."""
        if self.datatype == "boolean":
            return EnumDomain(frozenset({True, False}))
        if self.enum is not None:
            return EnumDomain(frozenset(self.enum))
        if self.datatype in NUMERIC:
            if self.range is None:
                return AnyDomain(self.datatype)
            st = None if self.step is None else frac(self.step)
            base = Fraction(0) if st is None or self.range[0] is None else self.range[0]
            return NumDomain(self.range[0], self.range[1], st, base)
        return AnyDomain(self.datatype)

    def admits(self, v) -> bool:
        """O valor é do tipo (domínio ou sentinela)?"""
        if self.is_sentinel(v):
            return True
        if self.datatype == "boolean":
            return isinstance(v, bool)
        if self.datatype in NUMERIC:
            return _is_num(v) and domain_contains(self.domain(), v)
        if self.datatype in ("string", "enum"):
            return isinstance(v, str) and domain_contains(self.domain(), v)
        if self.datatype == "duration":
            return isinstance(v, str) and bool(_DUR.match(v))
        if self.datatype == "tuple":
            return isinstance(v, dict) and set(v) == {n for n, _ in self.components} and all(
                t.admits(v[n]) for n, t in self.components)
        return False

    def unit_factor(self) -> Fraction | None:
        if self.unit in UNITS:
            return UNITS[self.unit][1]
        return None

    def to_dict(self) -> dict:
        return dict(self.raw)


def _eqv(a, b) -> bool:
    if _is_num(a) and _is_num(b):
        return frac(a) == frac(b)
    return str(a) == str(b) if not isinstance(a, bool) else a == b


def canonical(t: ValueType, v, calendar_context: dict | None = None):
    """ν: valor no tipo -> valor canônico da grandeza (segundos, bytes, contagem; taxa por segundo)."""
    if t.datatype == "duration":
        x = duration_seconds(v, calendar_context)
    elif t.datatype in NUMERIC and t.quantity_kind not in (NOT_APPLICABLE, UNKNOWN):
        f = t.unit_factor()
        if f is None:
            raise OutOfDomain(f"{t.unit} não tem fator fixo para a unidade base")
        x = frac(v) * f
    else:
        return v
    if t.rate_window:
        x = x / duration_seconds(t.rate_window)
    return x
