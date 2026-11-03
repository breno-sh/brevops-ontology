"""Unidades, tipo de unidade e durações do registro fechado (C10).

Tipo de unidade = (unidade QUDT, janela de taxa, convenção de byte). A janela e a convenção fazem parte do TIPO
(N4): 5 contagens por PT5M não são 5 contagens por PT1M, e GigaBYTE (SI, 10^9) não é GibiBYTE (IEC, 2^30).
Dois valores só se comparam ou se convertem com o tipo inteiro declarado; a conversão é sempre explícita.

Grandezas (QUDT, por IRI): Time, InformationEntropy, Count, DimensionlessRatio. NOT_APPLICABLE (não há grandeza)
é diferente de UNKNOWN (há, mas não se sabe); UNKNOWN como unidade é NO_UNIT, nunca um palpite.
Os IRIs abaixo seguem o padrão do C00; a conferência de existência no QUDT é do módulo UNITS (iri_status).

Durações (xsd:duration, XSD 1.1 parte 2, §3.3.6): o espaço de valores é o par (meses, segundos). Mês e ano não são
número fixo de segundos: duração com meses ≠ 0 só vira segundos com CONTEXTO DE CALENDÁRIO explícito
(âncora de data, ou convenção declarada de segundos por mês); sem ele, TRANSFORM_OUT_OF_DOMAIN.
"""

from __future__ import annotations

import calendar as _cal
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from fractions import Fraction

from .errors import DeclarationError, NoUnit, OutOfDomain

NOT_APPLICABLE = "NOT_APPLICABLE"
UNKNOWN = "UNKNOWN"

TIME = "quantitykind:Time"
INFO = "quantitykind:InformationEntropy"
COUNT = "quantitykind:Count"
RATIO = "quantitykind:DimensionlessRatio"
KINDS = {"time": TIME, "information": INFO, "count": COUNT, "ratio": RATIO}
IRI_STATUS = "pattern_only"   # padrão C00 conferido aqui; existência no QUDT conferida pelo UNITS


@dataclass(frozen=True)
class Unit:
    iri: str
    kind: str
    factor: Fraction | None        # para a unidade base da grandeza (SEC, BYTE, NUM, FRACTION); None = sem fator fixo
    byte_convention: str | None    # SI (10^3n) | IEC (2^10n) | None (sem prefixo)
    label: str


def _u(iri, kind, factor, conv, label):
    return Unit(iri, kind, None if factor is None else Fraction(factor), conv, label)


UNITS: dict[str, Unit] = {u.iri: u for u in [
    _u("unit:NanoSEC", TIME, Fraction(1, 10**9), None, "nanossegundo"),
    _u("unit:MicroSEC", TIME, Fraction(1, 10**6), None, "microssegundo"),
    _u("unit:MilliSEC", TIME, Fraction(1, 1000), None, "milissegundo"),
    _u("unit:SEC", TIME, 1, None, "segundo"),
    _u("unit:MIN", TIME, 60, None, "minuto"),
    _u("unit:HR", TIME, 3600, None, "hora"),
    _u("unit:DAY", TIME, 86400, None, "dia (86400 s; sem segundo bissexto)"),
    _u("unit:WK", TIME, 604800, None, "semana"),
    _u("unit:MO", TIME, None, None, "mês (sem fator fixo)"),
    _u("unit:YR", TIME, None, None, "ano (sem fator fixo)"),
    _u("unit:BIT", INFO, Fraction(1, 8), None, "bit"),
    _u("unit:KiloBIT", INFO, Fraction(10**3, 8), "SI", "kilobit"),
    _u("unit:MegaBIT", INFO, Fraction(10**6, 8), "SI", "megabit"),
    _u("unit:GigaBIT", INFO, Fraction(10**9, 8), "SI", "gigabit"),
    _u("unit:BYTE", INFO, 1, None, "byte"),
    _u("unit:KiloBYTE", INFO, 10**3, "SI", "kilobyte (10^3)"),
    _u("unit:MegaBYTE", INFO, 10**6, "SI", "megabyte (10^6)"),
    _u("unit:GigaBYTE", INFO, 10**9, "SI", "gigabyte (10^9)"),
    _u("unit:TeraBYTE", INFO, 10**12, "SI", "terabyte (10^12)"),
    _u("unit:KibiBYTE", INFO, 2**10, "IEC", "kibibyte (2^10)"),
    _u("unit:MebiBYTE", INFO, 2**20, "IEC", "mebibyte (2^20)"),
    _u("unit:GibiBYTE", INFO, 2**30, "IEC", "gibibyte (2^30)"),
    _u("unit:TebiBYTE", INFO, 2**40, "IEC", "tebibyte (2^40)"),
    _u("unit:NUM", COUNT, 1, None, "contagem"),
    _u("unit:FRACTION", RATIO, 1, None, "fração (0..1)"),
    _u("unit:PERCENT", RATIO, Fraction(1, 100), None, "por cento"),
]}
BYTE_CONVENTIONS = ("SI", "IEC")


def units_of(kind: str) -> list[str]:
    return [u.iri for u in UNITS.values() if u.kind == kind]


def unit(iri) -> Unit:
    if iri in (None, UNKNOWN, NOT_APPLICABLE):
        raise NoUnit(f"unidade {iri!r}: sem unidade declarada não há conversão nem comparação numérica")
    if iri not in UNITS:
        raise NoUnit(f"unidade fora do registro: {iri!r}")
    return UNITS[iri]


# ------------------------------------------------------------------------------------------------ números
def frac(x) -> Fraction:
    """Número exato. Booleano não é número; float entra pela representação decimal mais curta."""
    if isinstance(x, bool):
        raise OutOfDomain("booleano não é número")
    if isinstance(x, Fraction):
        return x
    if isinstance(x, int):
        return Fraction(x)
    if isinstance(x, float):
        if x != x or x in (float("inf"), float("-inf")):
            raise OutOfDomain(f"número não finito: {x!r}")
        return Fraction(repr(x))
    if isinstance(x, str):
        if not re.fullmatch(r"\s*-?\d+(\.\d+)?(/\d+)?\s*", x):
            raise OutOfDomain(f"texto não é número exato: {x!r}")
        f = Fraction(x.strip())
        return f
    raise OutOfDomain(f"não numérico: {x!r}")


def num_out(x: Fraction):
    """Fraction -> int quando inteiro; senão Fraction (exata; quem grava em JSON usa jnum)."""
    return int(x) if x.denominator == 1 else x


def jnum(x):
    """Número exato -> valor JSON: int quando inteiro; senão texto 'p/q' (nunca float com erro de arredondamento)."""
    x = frac(x)
    return int(x) if x.denominator == 1 else f"{x.numerator}/{x.denominator}"


# ---------------------------------------------------------------------------------------------- durações
_DUR = re.compile(r"^(-)?P(?:(\d+)Y)?(?:(\d+)M)?(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?)?$")


@dataclass(frozen=True)
class Duration:
    """Valor de xsd:duration: (meses, segundos), mesmo sinal (XSD 1.1, §3.3.6.1)."""
    months: int
    seconds: Fraction

    @property
    def has_calendar(self) -> bool:
        return self.months != 0


def parse_duration(s) -> Duration:
    if not isinstance(s, str):
        raise OutOfDomain(f"duração não é texto xsd:duration: {s!r}")
    m = _DUR.match(s)
    if not m or s.rstrip("-").endswith(("P", "T")) or s in ("P", "-P"):
        raise OutOfDomain(f"não é xsd:duration: {s!r}")
    neg, y, mo, d, h, mi, sec = m.groups()
    if all(x is None for x in (y, mo, d, h, mi, sec)):
        raise OutOfDomain(f"xsd:duration sem campo: {s!r}")
    if "T" in s and all(x is None for x in (h, mi, sec)):
        raise OutOfDomain(f"xsd:duration com T e sem campo de hora: {s!r}")
    months = int(y or 0) * 12 + int(mo or 0)
    secs = int(d or 0) * 86400 + int(h or 0) * 3600 + int(mi or 0) * 60 + Fraction(sec or "0")
    sign = -1 if neg else 1
    return Duration(sign * months, sign * secs)


def _fmt_secs(x: Fraction) -> str:
    if x.denominator == 1:
        return str(x.numerator)
    # só decimais finitos são exprimíveis em xsd:duration
    d = x.denominator
    for p in (2, 5):
        while d % p == 0:
            d //= p
    if d != 1:
        raise OutOfDomain(f"segundos {x} não têm representação decimal finita")
    s, k = x, 0
    while s.denominator != 1:
        s *= 10
        k += 1
    digits = str(abs(s.numerator)).rjust(k + 1, "0")
    return f"{digits[:-k]}.{digits[-k:]}".rstrip("0").rstrip(".")


def canonical_duration(d: Duration) -> str:
    """Forma canônica do XSD 1.1 (§3.3.6.2): anos/meses e dias/horas/minutos/segundos; zero = PT0S."""
    if d.months and d.seconds and (d.months > 0) != (d.seconds > 0):
        raise OutOfDomain("meses e segundos com sinais opostos não são xsd:duration")
    if d.months == 0 and d.seconds == 0:
        return "PT0S"
    neg = d.months < 0 or d.seconds < 0
    mo, se = abs(d.months), abs(d.seconds)
    out = "-P" if neg else "P"
    y, m = divmod(mo, 12)
    if y:
        out += f"{y}Y"
    if m:
        out += f"{m}M"
    whole = int(se)
    frac_s = se - whole
    days, rem = divmod(whole, 86400)
    h, rem = divmod(rem, 3600)
    mi, s = divmod(rem, 60)
    sec = s + frac_s
    if days:
        out += f"{days}D"
    if h or mi or sec:
        out += "T"
        if h:
            out += f"{h}H"
        if mi:
            out += f"{mi}M"
        if sec:
            out += f"{_fmt_secs(Fraction(sec))}S"
    return out


# ------------------------------------------------------------------------------------- contexto de calendário
def calendar_of(ctx: dict | None) -> dict | None:
    """ctx['calendar'] = {'anchor': dateTime ISO com fuso} | {'seconds_per_month': racional > 0, 'source': texto}."""
    cal = (ctx or {}).get("calendar")
    if cal is None:
        return None
    if not isinstance(cal, dict):
        raise DeclarationError(f"contexto de calendário não é objeto: {cal!r}")
    keys = {"anchor", "seconds_per_month"} & set(cal)
    if len(keys) != 1:
        raise DeclarationError("contexto de calendário declara exatamente um: anchor | seconds_per_month")
    if "anchor" in cal:
        a = cal["anchor"]
        try:
            dt = datetime.fromisoformat(a) if isinstance(a, str) else None
        except ValueError:
            dt = None
        if dt is None or dt.tzinfo is None:
            raise DeclarationError(f"âncora de calendário precisa de dateTime ISO com fuso: {a!r}")
        return {"anchor": dt}
    spm = frac(cal["seconds_per_month"])
    if spm <= 0 or not isinstance(cal.get("source"), str) or len(cal["source"]) < 3:
        raise DeclarationError("seconds_per_month > 0 e com 'source' (de onde vem a convenção)")
    return {"seconds_per_month": spm}


def _add_months(dt: datetime, months: int) -> datetime:
    """Soma de meses do XSD (apêndice E): o dia é fixado no último dia do mês de chegada quando não existe."""
    total = dt.year * 12 + (dt.month - 1) + months
    y, m = divmod(total, 12)
    m += 1
    if not 1 <= y <= 9999:
        raise OutOfDomain("data fora do calendário gregoriano suportado")
    day = min(dt.day, _cal.monthrange(y, m)[1])
    return dt.replace(year=y, month=m, day=day)


def months_seconds(months: int, ctx: dict | None, what: str) -> Fraction:
    """Segundos de 'months' meses no contexto de calendário; sem contexto, TRANSFORM_OUT_OF_DOMAIN."""
    if months == 0:
        return Fraction(0)
    cal = calendar_of(ctx)
    if cal is None:
        raise OutOfDomain(f"{what}: mês/ano não é número fixo de segundos; exige contexto de calendário "
                          "(anchor ou seconds_per_month)")
    if "anchor" in cal:
        a = cal["anchor"]
        b = _add_months(a, months)
        delta: timedelta = b - a
        return Fraction(delta.days * 86400 + delta.seconds) + Fraction(delta.microseconds, 10**6)
    return months * cal["seconds_per_month"]


def months_to_seconds(n: Fraction, ctx: dict | None, what: str) -> Fraction:
    """n meses (racional) -> segundos. Com âncora só meses inteiros; com convenção, n × seconds_per_month."""
    n = frac(n)
    if n == 0:
        return Fraction(0)
    cal = calendar_of(ctx)
    if cal is None:
        return months_seconds(1, None, what)     # levanta TRANSFORM_OUT_OF_DOMAIN
    if "anchor" in cal:
        if n.denominator != 1:
            raise OutOfDomain(f"{what}: fração de mês ({n}) não tem data de chegada no calendário")
        return months_seconds(int(n), ctx, what)
    return n * cal["seconds_per_month"]


def seconds_to_months(x: Fraction, ctx: dict | None, what: str) -> Fraction:
    """Inversa de months_to_seconds: com âncora, só quando x é exatamente um número inteiro de meses."""
    x = frac(x)
    if x == 0:
        return Fraction(0)
    cal = calendar_of(ctx)
    if cal is None:
        return months_seconds(1, None, what)
    if "seconds_per_month" in cal:
        return x / cal["seconds_per_month"]
    guess = round(x / Fraction(2629746))          # mês gregoriano médio, só para achar o candidato
    for n in range(guess - 2, guess + 3):
        if n and months_seconds(n, ctx, what) == x:
            return Fraction(n)
    raise OutOfDomain(f"{what}: {x} s não é número inteiro de meses a partir da âncora")


def duration_seconds(s, ctx: dict | None = None) -> Fraction:
    d = parse_duration(s)
    return months_seconds(d.months, ctx, f"duração {s}") + d.seconds


def fixed_window_seconds(w) -> Fraction:
    """Janela de taxa: duração fixa (sem meses) e positiva."""
    d = parse_duration(w)
    if d.months:
        raise DeclarationError(f"janela de taxa {w} com mês/ano não é fixa")
    if d.seconds <= 0:
        raise DeclarationError(f"janela de taxa {w} tem de ser positiva")
    return d.seconds


# ------------------------------------------------------------------------------------------ tipo de unidade
@dataclass(frozen=True)
class UnitType:
    """(unidade, janela de taxa, convenção de byte): o tipo inteiro de um valor numérico com grandeza."""
    unit: str
    rate_window: str | None = None
    byte_convention: str | None = None

    @staticmethod
    def of(d) -> "UnitType":
        if isinstance(d, UnitType):
            return d.checked()
        if isinstance(d, str):
            return UnitType(d).checked()
        if not isinstance(d, dict) or set(d) - {"unit", "rate_window", "byte_convention", "quantity_kind"}:
            raise DeclarationError(f"tipo de unidade é {{unit, rate_window?, byte_convention?}}: {d!r}")
        t = UnitType(d.get("unit"), d.get("rate_window"), d.get("byte_convention")).checked()
        if d.get("quantity_kind") not in (None, t.kind):
            raise DeclarationError(f"unidade {t.unit} não é da grandeza {d['quantity_kind']}")
        return t

    def checked(self) -> "UnitType":
        u = unit(self.unit)
        bc = self.byte_convention
        if bc is not None:
            if bc not in BYTE_CONVENTIONS:
                raise DeclarationError(f"convenção de byte {bc!r} (só {BYTE_CONVENTIONS})")
            if u.byte_convention != bc:
                raise DeclarationError(f"convenção {bc} contradiz a unidade {u.iri} ({u.byte_convention or 'sem prefixo'})")
        if self.rate_window is not None:
            fixed_window_seconds(self.rate_window)
        return UnitType(u.iri, self.rate_window, u.byte_convention)

    @property
    def kind(self) -> str:
        return UNITS[self.unit].kind

    def signature(self) -> tuple:
        return (self.kind, self.unit, self.rate_window and canonical_duration(parse_duration(self.rate_window)),
                self.byte_convention)

    def to_base(self, v, ctx=None) -> Fraction:
        """Valor -> unidade base da grandeza (por segundo de janela, se é taxa). Mês/ano só com calendário."""
        u = UNITS[self.unit]
        x = frac(v)
        if u.factor is None:
            x = months_to_seconds(x * (12 if u.iri == "unit:YR" else 1), ctx, f"unidade {u.iri}")
        else:
            x = x * u.factor
        if self.rate_window is not None:
            x = x / fixed_window_seconds(self.rate_window)
        return x

    def from_base(self, x: Fraction, ctx=None) -> Fraction:
        u = UNITS[self.unit]
        if self.rate_window is not None:
            x = x * fixed_window_seconds(self.rate_window)
        if u.factor is None:
            n = seconds_to_months(x, ctx, f"unidade {u.iri}")
            return n / 12 if u.iri == "unit:YR" else n
        return x / u.factor


def convert(v, src, dst, ctx=None):
    """Converte v do tipo src para o tipo dst (mesma grandeza). Exata (Fraction)."""
    a, b = UnitType.of(src), UnitType.of(dst)
    if a.kind != b.kind:
        raise DeclarationError(f"grandezas diferentes {a.kind} -> {b.kind}: conversão escalar não muda grandeza")
    if (a.rate_window is None) != (b.rate_window is None):
        raise DeclarationError("taxa (com janela) e quantidade (sem janela) são tipos diferentes")
    monthly = ("unit:MO", "unit:YR")
    if a.unit in monthly and b.unit in monthly:
        # mês <-> ano é exato (12) e não passa por segundos: não precisa de calendário
        x = frac(v) * (12 if a.unit == "unit:YR" else 1) / (12 if b.unit == "unit:YR" else 1)
        if a.rate_window is not None:
            x = x * fixed_window_seconds(b.rate_window) / fixed_window_seconds(a.rate_window)
        return num_out(x)
    return num_out(b.from_base(a.to_base(v, ctx), ctx))


__all__ = ["UNITS", "Unit", "UnitType", "Duration", "KINDS", "TIME", "INFO", "COUNT", "RATIO", "NOT_APPLICABLE",
           "UNKNOWN", "IRI_STATUS", "convert", "canonical_duration", "parse_duration", "duration_seconds",
           "months_seconds", "months_to_seconds", "seconds_to_months", "calendar_of", "fixed_window_seconds", "frac", "num_out", "jnum", "units_of", "unit"]
