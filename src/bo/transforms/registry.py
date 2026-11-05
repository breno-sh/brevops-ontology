"""Registro FECHADO de transformações do C10: escalares, combinadores de tupla e comparadores da leitura de volta.

TRANSFORMAÇÃO ESCALAR: um valor -> um valor, e a grandeza de saída É a de entrada (C10-KIND). Quem muda de
grandeza ou de forma (um texto vira dois inteiros, cinco componentes viram uma expressão) é COMBINADOR DE
TUPLA: n entradas nomeadas e tipadas -> m saídas nomeadas e tipadas.

Toda entrada do registro declara: domínio, codomínio, pré-condição, erro (código do C00 e quando), perda
(tipos do loss_contract: rounding, saturation, absence, sentinel, context_dependence, not_expressible, semantic)
e inversa parcial ({name, partial}: partial=false quando inv(f(x)) = x em TODO o domínio; true quando só num
subconjunto declarado; name=null quando não há inversa). Cada entrada traz exemplos executáveis (positivos, de
erro e de ida e volta) que o bo.transforms.audit roda.

Operações numéricas que preservam a grandeza (converter, arredondar, saturar, sentinela, janela de taxa) são
declaradas POR GRANDEZA (unit_convert_time, round_information...): o tipo do domínio é concreto, não uma
variável. identity é a única polimórfica: o valor e o tipo inteiro passam intactos (o C10 declara a grandeza dela
como NOT_APPLICABLE porque ela não impõe nem muda grandeza; ver o LEIA do módulo).

Nomes do núcleo do SEMANTICS (bo.semantics.transforms): identity, enum_map, duration_to_number,
number_to_duration, split/join_port_range, split/join_cidr, split/join_alarm_query, json_get e map_get têm o
mesmo nome aqui. unit_convert vira unit_convert_<grandeza> (resolve_kernel), rate_window_convert vira
rate_window_convert_<grandeza>; scale (fator sem unidade) NÃO entra: não tem garantia de grandeza.
"""

from __future__ import annotations

import ipaddress
import json
import math
import re
import unicodedata
from dataclasses import dataclass, field
from fractions import Fraction
from typing import Callable

from . import comparators as CMP
from . import units as U
from .errors import DeclarationError, NoUnit, OutOfDomain, SymbolicInput, TransformError, UnknownInput
from .markers import ABSENT, is_absent, is_not_read, is_symbolic

REGISTRY_VERSION = "1.6.0"
GENERATED_AT = "2026-11-04T21:40:00-03:00"     # data da versão do registro (fixa: a regeneração é idêntica)
LOSS_KINDS = ("rounding", "saturation", "absence", "sentinel", "context_dependence", "not_expressible", "semantic")
DATATYPES = ("integer", "decimal", "boolean", "string", "enum", "duration", "tuple", "number", "any", "list", "set",
             "map")
_NO = object()


@dataclass(frozen=True)
class Ex:
    """Exemplo executável. value: entrada (escalar) ou {porta: valor} (combinador)."""
    value: object
    params: dict = field(default_factory=dict)
    ctx: dict | None = None
    out: object = _NO
    err: str | None = None
    roundtrip: bool = False     # inv(f(x)) confere com x (comparador exact)
    note: str = ""


@dataclass(frozen=True)
class Scalar:
    name: str
    domain: dict
    codomain: dict
    precondition: str
    errors: tuple                 # ((código, quando), ...)
    loss: tuple                   # tipos de perda (vazio = nenhuma)
    loss_text: str
    inverse: str | None
    partial: bool
    fn: Callable
    type_out: Callable            # (tin: dict, params) -> tout: dict
    params: dict = field(default_factory=dict)
    inv_params: Callable | None = None     # params -> params da inversa | None (esta instância não tem inversa)
    context_required: tuple = ()
    duration_calendar: str | None = None
    examples: tuple = ()
    passes_symbolic: bool = False
    accepts_absent: bool = False
    kind: str = "scalar"


@dataclass(frozen=True)
class Combinator:
    name: str
    inputs: tuple                 # ((nome, datatype, restrição), ...)
    outputs: tuple
    precondition: str
    errors: tuple
    loss: tuple
    loss_text: str
    inverse: str | None
    partial: bool
    fn: Callable                  # (entradas: dict, ctx) -> saídas: dict
    examples: tuple = ()
    accepts_absent: bool = False
    c11_name: str | None = None   # comparador: nome no C11
    kind: str = "tuple"
    collection: tuple = ()        # ((porta, list|set|map), ...): coleção do C09 3.2.0 levada numa porta tuple do C10
    inv_inputs: Callable | None = None   # (entradas, saídas) -> entradas da inversa | None (sem inversa)
    port_types: tuple = ()        # ((porta, value_type do C09 3.2.0), ...): porta publicada como list/set/map (C10 3.1.0)
    positional: tuple = ()        # (forma da entrada, forma da saída), ex. ("T", "list[T]"): entrada posicional única


# ============================================================================================== parâmetros
def _req(p, k, what):
    if k not in p:
        raise DeclarationError(f"{what}: parâmetro obrigatório '{k}' ausente")
    return p[k]


def _check_params(spec: dict, p: dict, what: str):
    if not isinstance(p, dict):
        raise DeclarationError(f"{what}: params não é objeto")
    extra = set(p) - set(spec)
    if extra:
        raise DeclarationError(f"{what}: parâmetros desconhecidos {sorted(extra)}")
    for k, s in spec.items():
        if s.get("required") and k not in p:
            raise DeclarationError(f"{what}: parâmetro obrigatório '{k}' ausente")


def _unit_of_kind(iri, kind, what) -> U.Unit:
    try:
        u = U.unit(iri)
    except NoUnit as e:
        raise DeclarationError(f"{what}: {e.args[0]}") from None
    if u.kind != kind:
        raise DeclarationError(f"{what}: {iri} é de {u.kind}, não de {kind} (escalar não muda grandeza)")
    return u


def _num(v):
    if is_absent(v):
        raise OutOfDomain("valor ausente não é número")
    if isinstance(v, bool) or not isinstance(v, (int, float, Fraction, str)):
        raise OutOfDomain(f"não é número: {v!r}")
    return U.frac(v)


def _type(tin: dict, **upd) -> dict:
    t = dict(tin)
    t.update({k: v for k, v in upd.items() if v is not _NO})
    return {k: v for k, v in t.items() if v is not None}


def _need_kind(tin: dict, kind: str, what: str):
    if tin.get("quantity_kind") != kind:
        raise DeclarationError(f"{what}: entrada de grandeza {tin.get('quantity_kind')}, a função é de {kind}")


def _need_numeric(tin: dict, what: str):
    if tin.get("datatype") not in ("integer", "decimal", "number"):
        raise DeclarationError(f"{what}: entrada {tin.get('datatype')} não é numérica")


# ================================================================================================ escalares
def _identity(v, p, ctx):
    return v


def _identity_type(tin, p):
    return dict(tin)


# ------------------------------------------------------------------------------------ conversão de unidade
def _mk_unit_convert(key: str, kind: str):
    name = f"unit_convert_{key}"

    def fn(v, p, ctx):
        _unit_of_kind(p["from"], kind, name)
        _unit_of_kind(p["to"], kind, name)
        return U.convert(_num(v), p["from"], p["to"], ctx)

    def type_out(tin, p):
        _need_kind(tin, kind, name)
        _need_numeric(tin, name)
        if tin.get("unit") != p["from"]:
            raise DeclarationError(f"{name}: entrada em {tin.get('unit')}, from = {p['from']}")
        u = _unit_of_kind(p["to"], kind, name)
        return _type(tin, datatype="number", unit=u.iri, byte_convention=u.byte_convention)

    cal = kind == U.TIME
    units = U.units_of(kind)
    errs = [("TRANSFORM_OUT_OF_DOMAIN", "valor não numérico ou ausente"),
            ("DECLARATION_ERROR", "from/to fora do registro ou de outra grandeza")]
    if cal:
        errs.insert(1, ("TRANSFORM_OUT_OF_DOMAIN", "unit:MO/unit:YR sem contexto de calendário (mês/ano não tem "
                                                   "fator fixo de segundos), ou fração de mês com âncora"))
    ex = {
        U.TIME: (Ex(2, {"from": "unit:HR", "to": "unit:MIN"}, out=120, roundtrip=True),
                 Ex(90, {"from": "unit:SEC", "to": "unit:MIN"}, out=Fraction(3, 2), roundtrip=True),
                 Ex(1500, {"from": "unit:MilliSEC", "to": "unit:SEC"}, out=Fraction(3, 2), roundtrip=True),
                 Ex(1, {"from": "unit:MO", "to": "unit:SEC"}, err="TRANSFORM_OUT_OF_DOMAIN",
                    note="mês -> segundos sem contexto"),
                 Ex(1, {"from": "unit:YR", "to": "unit:DAY"}, err="TRANSFORM_OUT_OF_DOMAIN"),
                 Ex(18, {"from": "unit:MO", "to": "unit:YR"}, out=Fraction(3, 2), roundtrip=True,
                    note="mês <-> ano é exato, sem calendário"),
                 Ex(1, {"from": "unit:MO", "to": "unit:DAY"}, {"calendar": {"anchor": "2026-02-10T00:00:00-03:00"}},
                    out=28, roundtrip=True),
                 Ex(1, {"from": "unit:YR", "to": "unit:DAY"}, {"calendar": {"anchor": "2028-01-01T00:00:00-03:00"}},
                    out=366, roundtrip=True, note="2028 é bissexto"),
                 Ex(1, {"from": "unit:MO", "to": "unit:SEC"},
                    {"calendar": {"seconds_per_month": 2629746, "source": "mês gregoriano médio (365,2425 d / 12)"}},
                    out=2629746, roundtrip=True),
                 Ex(5, {"from": "unit:SEC", "to": "unit:BYTE"}, err="DECLARATION_ERROR"),
                 Ex(True, {"from": "unit:SEC", "to": "unit:MIN"}, err="TRANSFORM_OUT_OF_DOMAIN")),
        U.INFO: (Ex(1, {"from": "unit:GibiBYTE", "to": "unit:MebiBYTE"}, out=1024, roundtrip=True),
                 Ex(1, {"from": "unit:GibiBYTE", "to": "unit:GigaBYTE"}, out=Fraction(2**30, 10**9), roundtrip=True,
                    note="GiB ≠ GB: convenção de byte faz parte do tipo"),
                 Ex(8, {"from": "unit:BIT", "to": "unit:BYTE"}, out=1, roundtrip=True),
                 Ex(1, {"from": "unit:GigaBYTE", "to": "unit:SEC"}, err="DECLARATION_ERROR"),
                 Ex("abc", {"from": "unit:BYTE", "to": "unit:KiloBYTE"}, err="TRANSFORM_OUT_OF_DOMAIN")),
        U.RATIO: (Ex(50, {"from": "unit:PERCENT", "to": "unit:FRACTION"}, out=Fraction(1, 2), roundtrip=True),
                  Ex(0.25, {"from": "unit:FRACTION", "to": "unit:PERCENT"}, out=25, roundtrip=True),
                  Ex(1, {"from": "unit:PERCENT", "to": "unit:NUM"}, err="DECLARATION_ERROR"),
                  Ex(ABSENT, {"from": "unit:PERCENT", "to": "unit:FRACTION"}, err="TRANSFORM_OUT_OF_DOMAIN")),
    }[kind]
    return Scalar(
        name=name, domain={"datatype": "number", "quantity_kind": kind},
        codomain={"datatype": "number", "quantity_kind": kind},
        precondition=(f"mesma grandeza ({kind}); from e to ∈ {{{', '.join(units)}}}; valor na unidade from; a janela de "
                      "taxa, se houver, não muda; resultado exato (racional)" + (
                          "; mês/ano só com contexto de calendário" if cal else "")),
        errors=tuple(errs), loss=(), loss_text="exata (racional); arredondar é round_" + key,
        inverse=name, partial=False, fn=fn, type_out=type_out,
        params={"from": {"type": "unit", "quantity_kind": kind, "required": True},
                "to": {"type": "unit", "quantity_kind": kind, "required": True}},
        inv_params=lambda p: {"from": p["to"], "to": p["from"]},
        context_required=("calendar",) if cal else (), duration_calendar="with_context" if cal else None,
        examples=ex)


# --------------------------------------------------------------------------------------------- durações
_FIXED_TIME = [u for u in U.units_of(U.TIME) if U.UNITS[u].factor is not None]
_MONTHLY = ("unit:MO", "unit:YR")


def _duration_to_number(v, p, ctx):
    to = _unit_of_kind(p["to"], U.TIME, "duration_to_number")
    if is_absent(v):
        raise OutOfDomain("duração ausente")
    d = U.parse_duration(v)
    if to.iri in _MONTHLY:
        if d.seconds != 0:
            if U.calendar_of(ctx) is None:
                raise OutOfDomain(f"{v}: dias/horas não viram meses sem contexto de calendário")
            months = U.seconds_to_months(U.months_seconds(d.months, ctx, v) + d.seconds, ctx, f"duração {v}")
        else:
            months = Fraction(d.months)
        return U.num_out(months / 12 if to.iri == "unit:YR" else months)
    secs = U.months_seconds(d.months, ctx, f"duração {v}") + d.seconds
    return U.num_out(secs / to.factor)


def _duration_to_number_type(tin, p):
    if tin.get("datatype") != "duration":
        raise DeclarationError("duration_to_number: entrada não é duração")
    _need_kind(tin, U.TIME, "duration_to_number")
    u = _unit_of_kind(p["to"], U.TIME, "duration_to_number")
    return _type(tin, datatype="number", unit=u.iri)


def _number_to_duration(v, p, ctx):
    fr = _unit_of_kind(p["from"], U.TIME, "number_to_duration")
    x = _num(v)
    if fr.iri in _MONTHLY:
        n = x * (12 if fr.iri == "unit:YR" else 1)
        if n.denominator != 1:
            raise OutOfDomain(f"{v} {fr.iri}: fração de mês não é xsd:duration")
        return U.canonical_duration(U.Duration(int(n), Fraction(0)))
    return U.canonical_duration(U.Duration(0, x * fr.factor))


def _number_to_duration_type(tin, p):
    _need_numeric(tin, "number_to_duration")
    _need_kind(tin, U.TIME, "number_to_duration")
    if tin.get("unit") != p["from"]:
        raise DeclarationError(f"number_to_duration: entrada em {tin.get('unit')}, from = {p['from']}")
    return _type(tin, datatype="duration", unit=None)


_PB = re.compile(r"^(-)?(\d+)(?:\.(\d{1,9}))?s$")
_PB_MAX = 315_576_000_000      # limite do google.protobuf.Duration (±10 000 anos)


def _seconds_text_to_duration(v, p, ctx):
    m = _PB.match(v) if isinstance(v, str) else None
    if not m:
        raise OutOfDomain(f"não é duração em segundos do protobuf ('<decimal>s'): {v!r}")
    secs = Fraction(int(m[2])) + (Fraction(int(m[3]), 10 ** len(m[3])) if m[3] else 0)
    if secs > _PB_MAX:
        raise OutOfDomain(f"{v}: fora da faixa do google.protobuf.Duration")
    return U.canonical_duration(U.Duration(0, -secs if m[1] else secs))


def _duration_to_seconds_text(v, p, ctx):
    if is_absent(v):
        raise OutOfDomain("duração ausente")
    secs = U.duration_seconds(v, ctx)
    if abs(secs) > _PB_MAX:
        raise OutOfDomain(f"{v}: fora da faixa do google.protobuf.Duration")
    sign = "-" if secs < 0 else ""
    a = abs(secs)
    if (a * 10**9).denominator != 1:
        raise OutOfDomain(f"{v}: mais de 9 casas de fração de segundo")
    whole, rest = int(a), a - int(a)
    if rest == 0:
        return f"{sign}{whole}s"
    digits = str(int(rest * 10**9)).rjust(9, "0").rstrip("0")
    return f"{sign}{whole}.{digits}s"


def _dur_text_type(tin, p):
    _need_kind(tin, U.TIME, "duração")
    return _type(tin, datatype="duration", unit=None)


def _dur_to_text_type(tin, p):
    if tin.get("datatype") != "duration":
        raise DeclarationError("duration_to_seconds_text: entrada não é duração")
    return _type(tin, datatype="string")


# --------------------------------------------------------------------------------------------- janela de taxa
_ADDITIVE = ("sum", "average")


def _mk_rate_window(key: str, kind: str):
    name = f"rate_window_convert_{key}"

    def chk(p):
        a, b = U.fixed_window_seconds(p["from_window"]), U.fixed_window_seconds(p["to_window"])
        if p["statistic"] not in _ADDITIVE:
            raise DeclarationError(f"{name}: estatística {p['statistic']!r} não se converte de janela "
                                   f"(só {_ADDITIVE}; máximo, mínimo e percentil dependem da distribuição na janela)")
        return a, b

    def fn(v, p, ctx):
        a, b = chk(p)
        return U.num_out(_num(v) * b / a)

    def type_out(tin, p):
        _need_kind(tin, kind, name)
        _need_numeric(tin, name)
        chk(p)
        w = tin.get("rate_window")
        if w is None:
            raise DeclarationError(f"{name}: entrada sem janela de taxa (é quantidade, não taxa)")
        if U.canonical_duration(U.parse_duration(w)) != U.canonical_duration(U.parse_duration(p["from_window"])):
            raise DeclarationError(f"{name}: janela da entrada {w} ≠ from_window {p['from_window']}")
        return _type(tin, datatype="number", rate_window=p["to_window"])

    return Scalar(
        name=name, domain={"datatype": "number", "quantity_kind": kind},
        codomain={"datatype": "number", "quantity_kind": kind},
        precondition=(f"valor de {kind} por janela from_window (tipo de unidade inclui a janela); janelas xsd:duration "
                      f"fixas (sem mês/ano) e positivas; statistic ∈ {list(_ADDITIVE)} (total ou média por janela)"),
        errors=(("TRANSFORM_OUT_OF_DOMAIN", "valor não numérico ou ausente"),
                ("DECLARATION_ERROR", "janela com mês/ano ou não positiva; estatística não aditiva (max, min, pNN)")),
        loss=("context_dependence",),
        loss_text="supõe taxa uniforme dentro da janela: a distribuição dentro da janela não se recupera",
        inverse=name, partial=False, fn=fn, type_out=type_out,
        params={"from_window": {"type": "duration_fixed", "required": True},
                "to_window": {"type": "duration_fixed", "required": True},
                "statistic": {"type": "enum", "values": list(_ADDITIVE) + ["maximum", "minimum", "percentile"],
                              "required": True}},
        inv_params=lambda p: {"from_window": p["to_window"], "to_window": p["from_window"], "statistic": p["statistic"]},
        examples=(Ex(300, {"from_window": "PT5M", "to_window": "PT1M", "statistic": "sum"}, out=60, roundtrip=True),
                  Ex(2, {"from_window": "PT1S", "to_window": "PT1H", "statistic": "average"}, out=7200, roundtrip=True),
                  Ex(10, {"from_window": "PT5M", "to_window": "PT1M", "statistic": "maximum"}, err="DECLARATION_ERROR"),
                  Ex(10, {"from_window": "P1M", "to_window": "PT1M", "statistic": "sum"}, err="DECLARATION_ERROR"),
                  Ex("x", {"from_window": "PT1M", "to_window": "PT1S", "statistic": "sum"},
                     err="TRANSFORM_OUT_OF_DOMAIN")))


# ------------------------------------------------------------------------------------------- arredondamento
_MODES = ("floor", "ceiling", "half_even", "half_up", "exact")


def _round(x: Fraction, mode: str) -> int:
    if mode == "floor":
        return math.floor(x)
    if mode == "ceiling":
        return math.ceil(x)
    if mode == "half_even":
        return round(x)
    if mode == "half_up":      # metade para longe do zero
        n = math.floor(abs(x) + Fraction(1, 2))
        return n if x >= 0 else -n
    if mode == "exact":
        if x.denominator != 1:
            raise OutOfDomain(f"{x} não é inteiro (modo exact)")
        return int(x)
    raise DeclarationError(f"modo de arredondamento {mode!r} (só {_MODES})")


def _mk_round(key: str, kind: str):
    name = f"round_{key}"

    def type_out(tin, p):
        _need_kind(tin, kind, name)
        _need_numeric(tin, name)
        if p["mode"] not in _MODES:
            raise DeclarationError(f"{name}: modo {p['mode']!r}")
        return _type(tin, datatype="integer")

    return Scalar(
        name=name, domain={"datatype": "number", "quantity_kind": kind},
        codomain={"datatype": "integer", "quantity_kind": kind},
        precondition=f"número de {kind}; unidade e janela não mudam; mode ∈ {list(_MODES)}",
        errors=(("TRANSFORM_OUT_OF_DOMAIN", "valor não numérico ou ausente; não inteiro no modo exact"),
                ("DECLARATION_ERROR", "modo fora da lista")),
        loss=("rounding",), loss_text="a fração descartada não se recupera (no modo exact não há perda)",
        inverse="identity", partial=True, fn=lambda v, p, ctx: _round(_num(v), p["mode"]), type_out=type_out,
        params={"mode": {"type": "enum", "values": list(_MODES), "required": True}},
        inv_params=lambda p: {},
        examples=(Ex(Fraction(5, 2), {"mode": "half_even"}, out=2), Ex("2.5", {"mode": "half_up"}, out=3),
                  Ex("-2.5", {"mode": "half_up"}, out=-3), Ex("2.7", {"mode": "floor"}, out=2),
                  Ex("2.1", {"mode": "ceiling"}, out=3), Ex(4, {"mode": "exact"}, out=4, roundtrip=True),
                  Ex("2.5", {"mode": "exact"}, err="TRANSFORM_OUT_OF_DOMAIN"),
                  Ex(3, {"mode": "truncate"}, err="DECLARATION_ERROR")))


# --------------------------------------------------------------------------------------------------- saturação
def _clamp_bounds(p):
    lo = None if p.get("min") is None else U.frac(p["min"])
    hi = None if p.get("max") is None else U.frac(p["max"])
    if lo is None and hi is None:
        raise DeclarationError("clamp sem min nem max")
    if lo is not None and hi is not None and lo > hi:
        raise DeclarationError(f"clamp com min {lo} > max {hi}")
    return lo, hi


def _clamp(v, p, ctx):
    lo, hi = _clamp_bounds(p)
    x = _num(v)
    if lo is not None and x < lo:
        x = lo
    if hi is not None and x > hi:
        x = hi
    return U.num_out(x)


def _mk_clamp(key: str, kind: str):
    name = f"clamp_{key}"

    def type_out(tin, p):
        _need_kind(tin, kind, name)
        _need_numeric(tin, name)
        _clamp_bounds(p)
        return _type(tin)

    return Scalar(
        name=name, domain={"datatype": "number", "quantity_kind": kind},
        codomain={"datatype": "number", "quantity_kind": kind},
        precondition=f"número de {kind}; min e/ou max na MESMA unidade do valor; min ≤ max",
        errors=(("TRANSFORM_OUT_OF_DOMAIN", "valor não numérico ou ausente"),
                ("DECLARATION_ERROR", "sem limite, ou min > max")),
        loss=("saturation",), loss_text="valor fora de [min, max] vira o limite; o original não se recupera",
        inverse="identity", partial=True, fn=_clamp, type_out=type_out,
        params={"min": {"type": "number"}, "max": {"type": "number"}}, inv_params=lambda p: {},
        examples=(Ex(5000, {"max": 3653}, out=3653), Ex(10, {"min": 30}, out=30),
                  Ex(100, {"min": 1, "max": 3653}, out=100, roundtrip=True),
                  Ex(5, {"min": 9, "max": 1}, err="DECLARATION_ERROR"),
                  Ex(ABSENT, {"max": 1}, err="TRANSFORM_OUT_OF_DOMAIN")))


# --------------------------------------------------------------------------------------------------- sentinelas
def _sent_table(p, what):
    t = p.get("table")
    if not isinstance(t, list) or not t:
        raise DeclarationError(f"{what}: table é lista não vazia de {{from, to}}")
    for r in t:
        if not isinstance(r, dict) or set(r) != {"from", "to"}:
            raise DeclarationError(f"{what}: linha da table é {{from, to}}: {r!r}")
        for v in (r["from"], r["to"]):
            if not (is_absent(v) or isinstance(v, (str, int, bool)) and not isinstance(v, float)):
                raise DeclarationError(f"{what}: sentinela é texto, inteiro, booleano ou ABSENT: {v!r}")
    froms = [CMP._canon(r["from"]) if not is_absent(r["from"]) else "$absent" for r in t]
    if len(set(froms)) != len(froms):
        raise DeclarationError(f"{what}: sentinela de origem repetida")
    return t


def _same(a, b) -> bool:
    return CMP.value_equal(a, b)


def _sentinel_map(v, p, ctx):
    t = _sent_table(p, "sentinel_map")
    for r in t:
        if _same(v, r["from"]):
            return dict(ABSENT) if is_absent(r["to"]) else r["to"]
    for r in t:
        if _same(v, r["to"]):
            raise OutOfDomain(f"valor regular {v!r} colide com a sentinela de destino (ficaria ambíguo)")
    if is_absent(v):
        raise OutOfDomain("ausência sem sentinela declarada")
    return v


def _sentinel_inv(p):
    t = _sent_table(p, "sentinel_map")
    tos = ["$absent" if is_absent(r["to"]) else CMP._canon(r["to"]) for r in t]
    if len(set(tos)) != len(tos):
        return None    # não injetiva: duas sentinelas viram a mesma; sem inversa
    return {"table": [{"from": r["to"], "to": r["from"]} for r in t]}


def _mk_sentinel(key: str, kind: str):
    name = f"sentinel_map_{key}"

    def type_out(tin, p):
        if kind != U.NOT_APPLICABLE:
            _need_kind(tin, kind, name)
        _sent_table(p, name)
        return _type(tin)

    num = kind != U.NOT_APPLICABLE
    if num:
        exs = (Ex(0, {"table": [{"from": 0, "to": ABSENT}]}, out=ABSENT, roundtrip=True,
                  note="retenção 0 = nunca expira (lado com ausência)"),
               Ex(7, {"table": [{"from": 0, "to": ABSENT}]}, out=7, roundtrip=True),
               Ex(-1, {"table": [{"from": -1, "to": 0}]}, out=0, roundtrip=True),
               Ex(0, {"table": [{"from": -1, "to": 0}]}, err="TRANSFORM_OUT_OF_DOMAIN",
                  note="0 regular colidiria com a sentinela de destino"),
               Ex(ABSENT, {"table": [{"from": 0, "to": 1}]}, err="TRANSFORM_OUT_OF_DOMAIN"),
               Ex(-1, {"table": [{"from": 0, "to": ABSENT}, {"from": -1, "to": ABSENT}]}, out=ABSENT,
                  note="duas sentinelas para a mesma ausência: sem inversa"),
               Ex(1, {"table": []}, err="DECLARATION_ERROR"))
    else:
        exs = (Ex("", {"table": [{"from": "", "to": ABSENT}]}, out=ABSENT, roundtrip=True),
               Ex("abc", {"table": [{"from": "", "to": ABSENT}]}, out="abc", roundtrip=True),
               Ex(ABSENT, {"table": [{"from": ABSENT, "to": "none"}]}, out="none", roundtrip=True),
               Ex("none", {"table": [{"from": ABSENT, "to": "none"}]}, err="TRANSFORM_OUT_OF_DOMAIN"),
               Ex(ABSENT, {"table": [{"from": "", "to": "-"}, {"from": ABSENT, "to": "-"}]}, out="-",
                  note="duas origens para o mesmo destino: sem inversa"),
               Ex("x", {"table": [{"from": "a"}]}, err="DECLARATION_ERROR"))
    return Scalar(
        name=name,
        domain={"datatype": "number" if num else "any", "quantity_kind": kind},
        codomain={"datatype": "number" if num else "any", "quantity_kind": kind},
        precondition=("table = [{from, to}] com sentinelas (texto, inteiro, booleano ou ABSENT); valor que não é "
                      "sentinela passa intacto; valor regular igual a uma sentinela de destino é recusado"
                      + (f"; grandeza {kind} e unidade não mudam" if num else "")),
        errors=(("TRANSFORM_OUT_OF_DOMAIN", "valor regular colide com sentinela de destino; ausência sem sentinela"),
                ("DECLARATION_ERROR", "table vazia, mal formada ou com origem repetida")),
        loss=("sentinel",), loss_text="o significado da sentinela é declarado na table; nada além dela muda",
        inverse=name, partial=True, fn=_sentinel_map, type_out=type_out,
        params={"table": {"type": "sentinel_table", "required": True}}, inv_params=_sentinel_inv,
        examples=exs, accepts_absent=True)


# ---------------------------------------------------------------------------------------------- enumerações
def _enum_table(p, what):
    t = p.get("table")
    if not isinstance(t, dict) or not t or not all(isinstance(k, str) and isinstance(v, str) for k, v in t.items()):
        raise DeclarationError(f"{what}: table é objeto não vazio texto -> texto")
    return t


def _enum_map(v, p, ctx):
    t = _enum_table(p, "enum_map")
    if not isinstance(v, str) or v not in t:
        raise OutOfDomain(f"enum_map: {v!r} fora do domínio da tabela")
    return t[v]


def _enum_inv(p):
    t = _enum_table(p, "enum_map")
    if len(set(t.values())) != len(t):
        return None
    return {"table": {b: a for a, b in t.items()}}


def _enum_type(tin, p):
    _enum_table(p, "enum_map")
    if tin.get("datatype") not in ("enum", "string"):
        raise DeclarationError("enum_map: entrada não é enumeração")
    return _type(tin, datatype="enum")


def _b2e_params(p, what):
    a, b = _req(p, "true", what), _req(p, "false", what)
    if not isinstance(a, str) or not isinstance(b, str) or a == b:
        raise DeclarationError(f"{what}: true e false são textos distintos")
    return a, b


def _bool_to_enum(v, p, ctx):
    a, b = _b2e_params(p, "bool_to_enum")
    if not isinstance(v, bool):
        raise OutOfDomain(f"bool_to_enum: {v!r} não é booleano")
    return a if v else b


def _e2b_params(p, what):
    a, b = _req(p, "true", what), _req(p, "false", what)
    if not (isinstance(a, list) and isinstance(b, list) and a and b and all(isinstance(x, str) for x in a + b)):
        raise DeclarationError(f"{what}: true e false são listas não vazias de textos")
    if set(a) & set(b):
        raise DeclarationError(f"{what}: valor em true e em false")
    return a, b


def _enum_to_bool(v, p, ctx):
    a, b = _e2b_params(p, "enum_to_bool")
    if v in a:
        return True
    if v in b:
        return False
    raise OutOfDomain(f"enum_to_bool: {v!r} fora de true ∪ false")


def _norm_text(v, p, ctx):
    case = p.get("case", "preserve")
    if case not in ("preserve", "lower", "upper"):
        raise DeclarationError(f"normalize_text: case {case!r}")
    s = CMP.normalize_string(v)
    return s.lower() if case == "lower" else s.upper() if case == "upper" else s


def _text_type(tin, p):
    if tin.get("datatype") not in ("string", "enum"):
        raise DeclarationError("normalize_text: entrada não é texto")
    return _type(tin)


NA = U.NOT_APPLICABLE

SCALARS: list[Scalar] = [
    Scalar(
        name="identity", domain={"datatype": "any", "quantity_kind": NA, "unit": NA},
        codomain={"datatype": "any", "quantity_kind": NA, "unit": NA},
        precondition=("nenhuma; polimórfica: valor e tipo inteiro (datatype, grandeza, unidade, janela, convenção) "
                      "passam intactos, inclusive ABSENT e valor simbólico"),
        errors=(("UNKNOWN_INPUT", "valor não lido (NOT_READ)"),), loss=(), loss_text="nenhuma",
        inverse="identity", partial=False, fn=_identity, type_out=_identity_type, inv_params=lambda p: {},
        examples=(Ex("standard", out="standard", roundtrip=True), Ex(443, out=443, roundtrip=True),
                  Ex(ABSENT, out=ABSENT, roundtrip=True), Ex({"$not_read": True}, err="UNKNOWN_INPUT")),
        passes_symbolic=True, accepts_absent=True),
    Scalar(
        name="enum_map", domain={"datatype": "enum", "quantity_kind": NA}, codomain={"datatype": "enum", "quantity_kind": NA},
        precondition=("tabela finita texto -> texto, declarada em table; domínio finito = chaves da tabela e imagem = "
                      "valores, calculáveis por bo.transforms.registry.finite_domain/finite_image"),
        errors=(("TRANSFORM_OUT_OF_DOMAIN", "valor fora das chaves da tabela"),
                ("DECLARATION_ERROR", "table vazia ou não texto -> texto")),
        loss=("semantic",), loss_text="se a tabela não é injetiva, a origem não se recupera (sem inversa)",
        inverse="enum_map", partial=True, fn=_enum_map, type_out=_enum_type, inv_params=_enum_inv,
        params={"table": {"type": "enum_table", "required": True, "part_of": "domain_keys_image_values"}},
        examples=(Ex("gp3", {"table": {"gp3": "Premium_LRS", "standard": "Standard_LRS"}}, out="Premium_LRS",
                     roundtrip=True),
                  Ex("io2", {"table": {"gp3": "Premium_LRS"}}, err="TRANSFORM_OUT_OF_DOMAIN"),
                  Ex("a", {"table": {"a": "x", "b": "x"}}, out="x", note="tabela não injetiva: sem inversa"),
                  Ex("gp3", {"table": {}}, err="DECLARATION_ERROR"))),
    Scalar(
        name="bool_to_enum", domain={"datatype": "boolean", "quantity_kind": NA},
        codomain={"datatype": "enum", "quantity_kind": NA},
        precondition=("booleano; true e false são textos distintos; domínio finito = {true, false} e imagem = "
                      "{params.true, params.false}, calculáveis por finite_domain/finite_image"), errors=(
            ("TRANSFORM_OUT_OF_DOMAIN", "valor não booleano (inclusive 'true' em texto)"),
            ("DECLARATION_ERROR", "true = false, ou não texto")),
        loss=(), loss_text="nenhuma (bijeção sobre {true, false})", inverse="enum_to_bool", partial=False,
        fn=_bool_to_enum, type_out=lambda tin, p: (_b2e_params(p, "bool_to_enum"), _type(tin, datatype="enum"))[1],
        params={"true": {"type": "string", "required": True, "part_of": "image"},
                "false": {"type": "string", "required": True, "part_of": "image"}},
        inv_params=lambda p: {"true": [p["true"]], "false": [p["false"]]},
        examples=(Ex(True, {"true": "Enabled", "false": "Disabled"}, out="Enabled", roundtrip=True),
                  Ex(False, {"true": "Enabled", "false": "Disabled"}, out="Disabled", roundtrip=True),
                  Ex("true", {"true": "Enabled", "false": "Disabled"}, err="TRANSFORM_OUT_OF_DOMAIN"),
                  Ex(True, {"true": "X", "false": "X"}, err="DECLARATION_ERROR"))),
    Scalar(
        name="enum_to_bool", domain={"datatype": "enum", "quantity_kind": NA},
        codomain={"datatype": "boolean", "quantity_kind": NA},
        precondition=("true e false são listas disjuntas e não vazias de textos; domínio finito = true ∪ false "
                      "(calculável por bo.transforms.registry.finite_domain); imagem ⊆ {true, false}"),
        errors=(("TRANSFORM_OUT_OF_DOMAIN", "valor fora de true ∪ false"),
                ("DECLARATION_ERROR", "listas vazias ou com interseção")),
        loss=("semantic",), loss_text="com mais de um texto por lado, qual deles era não se recupera",
        inverse="bool_to_enum", partial=True, fn=_enum_to_bool,
        type_out=lambda tin, p: (_e2b_params(p, "enum_to_bool"), _type(tin, datatype="boolean"))[1],
        params={"true": {"type": "string_list", "required": True, "part_of": "domain"},
                "false": {"type": "string_list", "required": True, "part_of": "domain"}},
        inv_params=lambda p: {"true": p["true"][0], "false": p["false"][0]},
        examples=(Ex("Enabled", {"true": ["Enabled"], "false": ["Disabled"]}, out=True, roundtrip=True),
                  Ex("Suspended", {"true": ["Enabled"], "false": ["Disabled", "Suspended"]}, out=False),
                  Ex("Unknown", {"true": ["Enabled"], "false": ["Disabled"]}, err="TRANSFORM_OUT_OF_DOMAIN"),
                  Ex("A", {"true": ["A"], "false": ["A"]}, err="DECLARATION_ERROR"))),
    Scalar(
        name="normalize_text", domain={"datatype": "string", "quantity_kind": NA},
        codomain={"datatype": "string", "quantity_kind": NA},
        precondition="texto; Unicode NFC, espaço das pontas removido, espaço interno colapsado; case ∈ preserve|lower|upper",
        errors=(("TRANSFORM_OUT_OF_DOMAIN", "valor não é texto"), ("DECLARATION_ERROR", "case fora da lista")),
        loss=("not_expressible",), loss_text="espaço extra, forma Unicode e (com case ≠ preserve) a caixa original",
        inverse="identity", partial=True, fn=_norm_text, type_out=_text_type,
        params={"case": {"type": "enum", "values": ["preserve", "lower", "upper"]}}, inv_params=lambda p: {},
        examples=(Ex("  Standard   LRS ", out="Standard LRS"), Ex("GP3", {"case": "lower"}, out="gp3"),
                  Ex("ok", out="ok", roundtrip=True), Ex(3, err="TRANSFORM_OUT_OF_DOMAIN"),
                  Ex("a", {"case": "title"}, err="DECLARATION_ERROR"))),
    Scalar(
        name="duration_to_number", domain={"datatype": "duration", "quantity_kind": U.TIME},
        codomain={"datatype": "number", "quantity_kind": U.TIME},
        precondition=("xsd:duration (XSD 1.1, espaço (meses, segundos)); to = unidade de tempo do registro; meses ≠ 0 "
                      "para unidade fixa só com contexto de calendário (anchor | seconds_per_month); para unit:MO/unit:YR "
                      "a duração sem dias/horas vira meses exatos sem contexto"),
        errors=(("TRANSFORM_OUT_OF_DOMAIN", "não é xsd:duration, mês/ano -> segundos sem contexto de calendário "
                                            "(P1M, P1Y), ou dias -> meses sem contexto"),
                ("DECLARATION_ERROR", "to fora das unidades de tempo; contexto de calendário mal formado")),
        loss=("context_dependence",),
        loss_text="com meses, o número depende do calendário declarado (âncora ou convenção); sem meses, exata",
        inverse="number_to_duration", partial=True, fn=_duration_to_number, type_out=_duration_to_number_type,
        params={"to": {"type": "unit", "quantity_kind": U.TIME, "required": True}},
        inv_params=lambda p: {"from": p["to"]}, context_required=("calendar",), duration_calendar="with_context",
        examples=(Ex("PT1H", {"to": "unit:MIN"}, out=60, roundtrip=True),
                  Ex("PT1M", {"to": "unit:SEC"}, out=60, roundtrip=True, note="M depois de T é minuto"),
                  Ex("P1DT1S", {"to": "unit:SEC"}, out=86401, roundtrip=True),
                  Ex("-PT30S", {"to": "unit:SEC"}, out=-30, roundtrip=True),
                  Ex("P0M1D", {"to": "unit:SEC"}, out=86400, note="0 meses: espaço de valores sem calendário"),
                  Ex("P1M", {"to": "unit:SEC"}, err="TRANSFORM_OUT_OF_DOMAIN", note="mês -> segundos sem contexto"),
                  Ex("P1Y", {"to": "unit:SEC"}, err="TRANSFORM_OUT_OF_DOMAIN"),
                  Ex("P1Y2M", {"to": "unit:DAY"}, err="TRANSFORM_OUT_OF_DOMAIN"),
                  Ex("P1M", {"to": "unit:SEC"}, {"calendar": {"anchor": "2026-01-31T00:00:00-03:00"}}, out=2419200,
                     note="31/01 + 1 mês = 28/02 (dia fixado no fim do mês)"),
                  Ex("P1M", {"to": "unit:DAY"}, {"calendar": {"seconds_per_month": "2592000", "source": "convenção de 30 dias"}},
                     out=30),
                  Ex("P3M", {"to": "unit:MO"}, out=3, roundtrip=True),
                  Ex("P1Y6M", {"to": "unit:YR"}, out=Fraction(3, 2)),
                  Ex("P30D", {"to": "unit:MO"}, err="TRANSFORM_OUT_OF_DOMAIN"),
                  Ex("1h", {"to": "unit:SEC"}, err="TRANSFORM_OUT_OF_DOMAIN"),
                  Ex("PT1H", {"to": "unit:BYTE"}, err="DECLARATION_ERROR"),
                  Ex("P1M", {"to": "unit:SEC"}, {"calendar": {"anchor": "2026-01-31"}}, err="DECLARATION_ERROR"))),
    Scalar(
        name="number_to_duration", domain={"datatype": "number", "quantity_kind": U.TIME},
        codomain={"datatype": "duration", "quantity_kind": U.TIME},
        precondition=("número na unidade from; saída na forma canônica do XSD 1.1; nunca converte meses em segundos: "
                      "de unit:MO/unit:YR sai PnM/PnY (inteiro de meses), das demais sai dias/horas/minutos/segundos"),
        errors=(("TRANSFORM_OUT_OF_DOMAIN", "fração de mês; segundos sem representação decimal finita; não numérico"),
                ("DECLARATION_ERROR", "from fora das unidades de tempo")),
        loss=(), loss_text="nenhuma (no espaço de valores; a forma lexical sai canônica)",
        inverse="duration_to_number", partial=False, fn=_number_to_duration, type_out=_number_to_duration_type,
        params={"from": {"type": "unit", "quantity_kind": U.TIME, "required": True}},
        inv_params=lambda p: {"to": p["from"]}, duration_calendar="forbidden",
        examples=(Ex(3600, {"from": "unit:SEC"}, out="PT1H", roundtrip=True),
                  Ex(90061, {"from": "unit:SEC"}, out="P1DT1H1M1S", roundtrip=True),
                  Ex(0, {"from": "unit:SEC"}, out="PT0S", roundtrip=True),
                  Ex(1.5, {"from": "unit:SEC"}, out="PT1.5S", roundtrip=True),
                  Ex(3, {"from": "unit:MO"}, out="P3M", roundtrip=True),
                  Ex(18, {"from": "unit:MO"}, out="P1Y6M", roundtrip=True),
                  Ex("1.5", {"from": "unit:MO"}, err="TRANSFORM_OUT_OF_DOMAIN"),
                  Ex("1/3", {"from": "unit:SEC"}, err="TRANSFORM_OUT_OF_DOMAIN"),
                  Ex(1, {"from": "unit:NUM"}, err="DECLARATION_ERROR"))),
    Scalar(
        name="seconds_text_to_duration", domain={"datatype": "string", "quantity_kind": U.TIME},
        codomain={"datatype": "duration", "quantity_kind": U.TIME},
        precondition=("texto '<segundos>[.<até 9 casas>]s' (google.protobuf.Duration em JSON, ex. '3600s'), "
                      "|valor| ≤ 315 576 000 000 s; saída xsd:duration canônica, sem meses"),
        errors=(("TRANSFORM_OUT_OF_DOMAIN", "outro formato ('1h', '3600', mais de 9 casas) ou fora da faixa"),),
        loss=("not_expressible",), loss_text="zeros à direita e '-0s' saem na forma canônica ('3600.500s' volta '3600.5s')",
        inverse="duration_to_seconds_text", partial=True,
        fn=_seconds_text_to_duration, type_out=_dur_text_type, inv_params=lambda p: {},
        duration_calendar="forbidden",
        examples=(Ex("3600s", out="PT1H", roundtrip=True), Ex("1.5s", out="PT1.5S", roundtrip=True),
                  Ex("-5s", out="-PT5S", roundtrip=True), Ex("0s", out="PT0S", roundtrip=True),
                  Ex("3600.500s", out="PT1H0.5S", note="forma não canônica: a volta dá '3600.5s'"),
                  Ex("3600", err="TRANSFORM_OUT_OF_DOMAIN"), Ex("1h", err="TRANSFORM_OUT_OF_DOMAIN"),
                  Ex("1.0000000001s", err="TRANSFORM_OUT_OF_DOMAIN"))),
    Scalar(
        name="duration_to_seconds_text", domain={"datatype": "duration", "quantity_kind": U.TIME},
        codomain={"datatype": "string", "quantity_kind": U.TIME},
        precondition=("xsd:duration; meses ≠ 0 só com contexto de calendário; até 9 casas de fração de segundo; "
                      "saída '<segundos>s' do google.protobuf.Duration"),
        errors=(("TRANSFORM_OUT_OF_DOMAIN", "mês/ano sem contexto de calendário; mais de 9 casas; fora da faixa"),
                ("DECLARATION_ERROR", "contexto de calendário mal formado")),
        loss=("context_dependence",), loss_text="com meses, o número de segundos depende do calendário declarado",
        inverse="seconds_text_to_duration", partial=True, fn=_duration_to_seconds_text, type_out=_dur_to_text_type,
        inv_params=lambda p: {}, context_required=("calendar",), duration_calendar="with_context",
        examples=(Ex("PT1H", out="3600s", roundtrip=True), Ex("PT0.5S", out="0.5s", roundtrip=True),
                  Ex("P1M", err="TRANSFORM_OUT_OF_DOMAIN", note="mês -> segundos sem contexto"),
                  Ex("P1M", ctx={"calendar": {"anchor": "2026-01-01T00:00:00-03:00"}}, out="2678400s"),
                  Ex("P1M", ctx={"calendar": {"anchor": "2026-01-01T00:00:00-03:00", "seconds_per_month": 1}},
                     err="DECLARATION_ERROR"))),
]
for _k, _q in (("time", U.TIME), ("information", U.INFO), ("ratio", U.RATIO)):
    SCALARS.append(_mk_unit_convert(_k, _q))
for _k, _q in (("count", U.COUNT), ("information", U.INFO)):
    SCALARS.append(_mk_rate_window(_k, _q))
for _k, _q in (("time", U.TIME), ("information", U.INFO), ("count", U.COUNT), ("ratio", U.RATIO)):
    SCALARS.append(_mk_round(_k, _q))
for _k, _q in (("time", U.TIME), ("information", U.INFO), ("count", U.COUNT), ("ratio", U.RATIO)):
    SCALARS.append(_mk_clamp(_k, _q))
for _k, _q in (("time", U.TIME), ("information", U.INFO), ("count", U.COUNT), ("ratio", U.RATIO), ("value", NA)):
    SCALARS.append(_mk_sentinel(_k, _q))


# ======================================================================================== combinadores de tupla
def _ports(v, ctx):
    s = v["ports"]
    if not isinstance(s, str) or not re.fullmatch(r"\d{1,5}(-\d{1,5})?", s):
        raise OutOfDomain(f"faixa de portas não é 'p' ou 'p1-p2': {s!r}")
    a, _, b = s.partition("-")
    lo, hi = int(a), int(b or a)
    if not 0 <= lo <= hi <= 65535:
        raise OutOfDomain(f"faixa de portas inválida: {s}")
    return {"from_port": lo, "to_port": hi}


def _join_ports(v, ctx):
    lo, hi = v["from_port"], v["to_port"]
    if not (isinstance(lo, int) and isinstance(hi, int) and not isinstance(lo, bool) and not isinstance(hi, bool)
            and 0 <= lo <= hi <= 65535):
        raise OutOfDomain(f"faixa inválida {lo!r}-{hi!r}")
    return {"ports": str(lo) if lo == hi else f"{lo}-{hi}"}


def _split_cidr(v, ctx):
    n = CMP.network(v["cidr"])
    return {"address": str(n.network_address), "prefix_length": n.prefixlen}


def _join_cidr(v, ctx):
    a, p = v["address"], v["prefix_length"]
    if not isinstance(a, str) or not isinstance(p, int) or isinstance(p, bool):
        raise OutOfDomain(f"address texto e prefix_length inteiro: {a!r}, {p!r}")
    try:
        ipaddress.ip_address(a)
    except ValueError:
        raise OutOfDomain(f"endereço inválido: {a!r}")
    n = CMP.network(f"{a}/{p}")
    return {"cidr": str(n)}


_ALARM = re.compile(r"^\s*(?P<metric>[A-Za-z][A-Za-z0-9_]*)\[(?P<n>\d+)(?P<u>[smhd])\]\.(?P<stat>[a-z]+)\(\)\s*"
                    r"(?P<op>>=|<=|==|!=|>|<)\s*(?P<thr>-?\d+(?:\.\d+)?)\s*$")
_OPS = {">": "gt", ">=": "ge", "<": "lt", "<=": "le", "==": "eq", "!=": "ne"}
_STATS = ("mean", "sum", "min", "max", "count")
_USEC = {"s": 1, "m": 60, "h": 3600, "d": 86400}


def _split_alarm(v, ctx):
    q = v["query"]
    m = _ALARM.match(q) if isinstance(q, str) else None
    if not m:
        raise OutOfDomain(f"expressão de alarme fora do subconjunto 'Metrica[Nu].estat() op limiar': {q!r}")
    if m["stat"] not in _STATS:
        raise OutOfDomain(f"estatística {m['stat']!r} fora de {_STATS}")
    secs = int(m["n"]) * _USEC[m["u"]]
    if secs == 0:
        raise OutOfDomain("janela zero")
    return {"metric": m["metric"], "window": U.canonical_duration(U.Duration(0, Fraction(secs))),
            "statistic": m["stat"], "operator": _OPS[m["op"]], "threshold": U.num_out(Fraction(m["thr"]))}


def _join_alarm(v, ctx):
    if not isinstance(v["metric"], str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", v["metric"]):
        raise OutOfDomain(f"métrica {v['metric']!r}")
    d = U.parse_duration(v["window"])
    if d.months or d.seconds <= 0 or d.seconds.denominator != 1:
        raise OutOfDomain(f"janela {v['window']} não exprimível (sem mês, inteira, positiva)")
    secs = int(d.seconds)
    u = next(k for k in ("d", "h", "m", "s") if secs % _USEC[k] == 0)
    if v["statistic"] not in _STATS:
        raise OutOfDomain(f"estatística {v['statistic']!r}")
    rev = {b: a for a, b in _OPS.items()}
    if v["operator"] not in rev:
        raise OutOfDomain(f"operador {v['operator']!r}")
    thr = _num(v["threshold"])
    thr_s = U._fmt_secs(abs(thr))
    return {"query": f"{v['metric']}[{secs // _USEC[u]}{u}].{v['statistic']}() {rev[v['operator']]} "
                     f"{'-' if thr < 0 else ''}{thr_s}"}


def _json_get(v, ctx):
    doc, key = v["document"], v["key"]
    if not isinstance(doc, str) or not isinstance(key, str):
        raise OutOfDomain("document e key são textos")
    try:
        d = json.loads(doc)
    except ValueError:
        raise OutOfDomain("document não é JSON")
    if not isinstance(d, dict) or key not in d:
        raise OutOfDomain(f"documento sem a chave de topo {key!r}")
    return {"value": d[key]}


def _map_get(v, ctx):
    m, key = v["map"], v["key"]
    if not isinstance(m, dict) or not isinstance(key, str):
        raise OutOfDomain("map é objeto e key é texto")
    if key not in m:
        raise OutOfDomain(f"mapa sem a chave {key!r}")
    return {"value": m[key]}


def _tags_to_map(v, ctx):
    tags = v["tags"]
    if not isinstance(tags, list):
        raise OutOfDomain("tags é lista de {key, value}")
    out = {}
    for t in tags:
        if not isinstance(t, dict) or set(t) not in ({"key", "value"}, {"Key", "Value"}):
            raise OutOfDomain(f"etiqueta é {{key, value}} ou {{Key, Value}}: {t!r}")
        k, val = (t["key"], t["value"]) if "key" in t else (t["Key"], t["Value"])
        if not isinstance(k, str) or not isinstance(val, str):
            raise OutOfDomain(f"chave e valor de etiqueta são textos: {t!r}")
        if k in out:
            raise OutOfDomain(f"chave de etiqueta repetida: {k!r}")
        out[k] = val
    return {"map": out}


def _map_to_tags(v, ctx):
    m = v["map"]
    if not isinstance(m, dict) or not all(isinstance(k, str) and isinstance(x, str) for k, x in m.items()):
        raise OutOfDomain("map é objeto texto -> texto")
    return {"tags": [{"key": k, "value": m[k]} for k in sorted(m)]}


def _cmp_fn(c11):
    impl = CMP.IMPLEMENTATIONS[c11]

    def fn(v, ctx):
        return {"match": impl(v["expected"], v["observed"], v.get("tolerance"), ctx)}
    return fn


def _cmp_quantity(v, ctx):
    return {"match": CMP.compare_numeric_tolerance(v["expected"], v["observed"], v["tolerance"], ctx,
                                                   v["expected_type"], v["observed_type"])}


_TAG_STR = {"datatype": "string", "quantity_kind": "NOT_APPLICABLE"}
_TAGS_LIST = {"datatype": "list", "item_type": {"datatype": "tuple", "components": [
    {"name": "key", "type": _TAG_STR}, {"name": "value", "type": _TAG_STR}]}}
_TAGS_MAP = {"datatype": "map", "key_type": "string", "item_type": _TAG_STR}
_PORTS_IN = (("ports", "string", "'p' ou 'p1-p2', 0 ≤ p1 ≤ p2 ≤ 65535"),)
_PORTS_OUT = (("from_port", "integer", "0..65535"), ("to_port", "integer", "from_port..65535"))
_CIDR_IN = (("cidr", "string", "rede IPv4/IPv6 sem bits de host"),)
_CIDR_OUT = (("address", "string", "endereço de rede"), ("prefix_length", "integer", "0..32 (IPv4) | 0..128 (IPv6)"))
_ALARM_IN = (("query", "string", "'Metrica[Nu].estat() op limiar', u ∈ s|m|h|d"),)
_ALARM_OUT = (("metric", "string", "identificador"), ("window", "duration", "xsd:duration fixa, canônica"),
              ("statistic", "enum", "|".join(_STATS)), ("operator", "enum", "gt|ge|lt|le|eq|ne"),
              ("threshold", "number", "decimal finito"))
_CMP_LOSS = ("not_expressible",)

COMBINATORS: list[Combinator] = [
    Combinator("split_port_range", _PORTS_IN, _PORTS_OUT, "texto 'p' ou 'p1-p2' com 0 ≤ p1 ≤ p2 ≤ 65535",
               (("TRANSFORM_OUT_OF_DOMAIN", "outro formato, porta > 65535 ou p1 > p2"),
                ("UNKNOWN_INPUT", "entrada ausente ou não lida")),
               ("not_expressible",), "'p-p' volta 'p' e zeros à esquerda somem ('080' volta '80')",
               "join_port_range", True, _ports,
               (Ex({"ports": "80-443"}, out={"from_port": 80, "to_port": 443}, roundtrip=True),
                Ex({"ports": "22"}, out={"from_port": 22, "to_port": 22}, roundtrip=True),
                Ex({"ports": "22-22"}, out={"from_port": 22, "to_port": 22}, note="a volta dá '22'"),
                Ex({"ports": "443-80"}, err="TRANSFORM_OUT_OF_DOMAIN"),
                Ex({"ports": "0-70000"}, err="TRANSFORM_OUT_OF_DOMAIN"),
                Ex({"ports": ABSENT}, err="UNKNOWN_INPUT"))),
    Combinator("join_port_range", _PORTS_OUT, _PORTS_IN, "from_port e to_port inteiros, 0 ≤ from_port ≤ to_port ≤ 65535",
               (("TRANSFORM_OUT_OF_DOMAIN", "fora da faixa ou from_port > to_port"),
                ("UNKNOWN_INPUT", "componente ausente ou não lido")),
               (), "nenhuma", "split_port_range", False, _join_ports,
               (Ex({"from_port": 80, "to_port": 443}, out={"ports": "80-443"}, roundtrip=True),
                Ex({"from_port": 22, "to_port": 22}, out={"ports": "22"}, roundtrip=True),
                Ex({"from_port": 443, "to_port": 80}, err="TRANSFORM_OUT_OF_DOMAIN"),
                Ex({"from_port": 80}, err="UNKNOWN_INPUT"))),
    Combinator("split_cidr", _CIDR_IN, _CIDR_OUT, "rede CIDR estrita (sem bits de host), IPv4 ou IPv6",
               (("TRANSFORM_OUT_OF_DOMAIN", "não é CIDR ou tem bits de host"),
                ("UNKNOWN_INPUT", "entrada ausente ou não lida")),
               ("not_expressible",), "a forma textual (maiúsculas e compressão IPv6) sai canônica (RFC 5952)",
               "join_cidr", True, _split_cidr,
               (Ex({"cidr": "10.0.0.0/16"}, out={"address": "10.0.0.0", "prefix_length": 16}, roundtrip=True),
                Ex({"cidr": "2001:db8::/32"}, out={"address": "2001:db8::", "prefix_length": 32}, roundtrip=True),
                Ex({"cidr": "2001:DB8:0::/32"}, out={"address": "2001:db8::", "prefix_length": 32}),
                Ex({"cidr": "10.0.0.5/16"}, err="TRANSFORM_OUT_OF_DOMAIN"),
                Ex({"cidr": "10.0.0.0/33"}, err="TRANSFORM_OUT_OF_DOMAIN"),
                Ex({"cidr": {"$symbolic": True}}, err="UNKNOWN_SYMBOLIC_INPUT"))),
    Combinator("join_cidr", _CIDR_OUT, _CIDR_IN, "endereço e prefixo formam rede estrita (monta o CIDR)",
               (("TRANSFORM_OUT_OF_DOMAIN", "endereço inválido, prefixo fora da família ou bits de host"),
                ("UNKNOWN_INPUT", "componente ausente ou não lido")),
               ("not_expressible",), "o endereço sai na forma canônica (RFC 5952): '2001:DB8::' volta '2001:db8::'",
               "split_cidr", True, _join_cidr,
               (Ex({"address": "10.0.0.0", "prefix_length": 16}, out={"cidr": "10.0.0.0/16"}, roundtrip=True),
                Ex({"address": "2001:DB8::", "prefix_length": 32}, out={"cidr": "2001:db8::/32"}),
                Ex({"address": "10.0.0.1", "prefix_length": 16}, err="TRANSFORM_OUT_OF_DOMAIN"),
                Ex({"address": "10.0.0.0", "prefix_length": "16"}, err="TRANSFORM_OUT_OF_DOMAIN"),
                Ex({"address": "10.0.0.0"}, err="UNKNOWN_INPUT"))),
    Combinator("split_alarm_query", _ALARM_IN, _ALARM_OUT,
               f"subconjunto 'Metrica[Nu].estat() op limiar' com estat ∈ {list(_STATS)}; dimensões, agrupamento e "
               "funções ficam fora", (("TRANSFORM_OUT_OF_DOMAIN", "fora do subconjunto suportado"),
                                      ("UNKNOWN_INPUT", "entrada ausente ou não lida")),
               ("not_expressible",), "espaços, forma do limiar (1.50 -> 1.5) e unidade da janela (60s -> 1m) saem canônicos",
               "join_alarm_query", True, _split_alarm,
               (Ex({"query": "CPUUtilization[5m].mean() > 80"},
                   out={"metric": "CPUUtilization", "window": "PT5M", "statistic": "mean", "operator": "gt",
                        "threshold": 80}, roundtrip=True),
                Ex({"query": "Latency[60s].max() >= 1.5"},
                   out={"metric": "Latency", "window": "PT1M", "statistic": "max", "operator": "ge",
                        "threshold": Fraction(3, 2)}),
                Ex({"query": "Errors[1d].sum() != -2"},
                   out={"metric": "Errors", "window": "P1D", "statistic": "sum", "operator": "ne", "threshold": -2},
                   roundtrip=True),
                Ex({"query": "CPU[5m].p99() > 80"}, err="TRANSFORM_OUT_OF_DOMAIN"),
                Ex({"query": "avg(CPU{host='a'}) > 80"}, err="TRANSFORM_OUT_OF_DOMAIN"))),
    Combinator("join_alarm_query", _ALARM_OUT, _ALARM_IN, "os 5 componentes presentes; janela fixa inteira positiva",
               (("TRANSFORM_OUT_OF_DOMAIN", "janela com mês, não inteira ou zero; operador ou estatística fora da lista"),
                ("UNKNOWN_INPUT", "componente ausente ou não lido")),
               (), "nenhuma", "split_alarm_query", False, _join_alarm,
               (Ex({"metric": "CPUUtilization", "window": "PT5M", "statistic": "mean", "operator": "gt", "threshold": 80},
                   out={"query": "CPUUtilization[5m].mean() > 80"}, roundtrip=True),
                Ex({"metric": "Latency", "window": "PT90S", "statistic": "max", "operator": "le", "threshold": Fraction(1, 4)},
                   out={"query": "Latency[90s].max() <= 0.25"}),
                Ex({"metric": "CPU", "window": "P1M", "statistic": "mean", "operator": "gt", "threshold": 80},
                   err="TRANSFORM_OUT_OF_DOMAIN"),
                Ex({"metric": "CPU", "window": "PT5M", "statistic": "mean", "operator": "gt"}, err="UNKNOWN_INPUT"))),
    Combinator("json_get", (("document", "string", "texto JSON cujo topo é objeto"), ("key", "string", "chave de topo")),
               (("value", "any", "valor JSON da chave"),), "documento JSON (objeto) com a chave de topo",
               (("TRANSFORM_OUT_OF_DOMAIN", "não é JSON, topo não é objeto ou chave ausente"),
                ("UNKNOWN_INPUT", "entrada ausente ou não lida")),
               ("not_expressible",), "o resto do documento não se reconstrói de uma chave", None, False, _json_get,
               (Ex({"document": '{"Version": "2012-10-17", "Statement": []}', "key": "Version"}, out={"value": "2012-10-17"}),
                Ex({"document": "[1, 2]", "key": "a"}, err="TRANSFORM_OUT_OF_DOMAIN"),
                Ex({"document": "{", "key": "a"}, err="TRANSFORM_OUT_OF_DOMAIN"))),
    Combinator("map_get", (("map", "tuple", "objeto (ex. rótulos)"), ("key", "string", "chave")),
               (("value", "any", "valor da chave"),), "chave presente no mapa",
               (("TRANSFORM_OUT_OF_DOMAIN", "map não é objeto ou chave ausente"),
                ("UNKNOWN_INPUT", "entrada ausente ou não lida")),
               ("not_expressible",), "as outras chaves do mapa", None, False, _map_get,
               (Ex({"map": {"env": "prod", "team": "a"}, "key": "env"}, out={"value": "prod"}),
                Ex({"map": {"env": "prod"}, "key": "team"}, err="TRANSFORM_OUT_OF_DOMAIN")),
               collection=(("map", "map"),)),
    Combinator("tags_list_to_map", (("tags", "tuple", "lista de {key, value} ou {Key, Value}, textos"),),
               (("map", "tuple", "objeto texto -> texto"),), "chaves únicas; chave e valor textos",
               (("TRANSFORM_OUT_OF_DOMAIN", "chave repetida, campo fora de {key, value} ou valor não texto"),
                ("UNKNOWN_INPUT", "entrada ausente ou não lida")),
               ("not_expressible",), "a ordem da lista e a caixa dos nomes de campo (Key/key)",
               "tags_map_to_list", True, _tags_to_map,
               (Ex({"tags": [{"key": "env", "value": "prod"}, {"key": "a", "value": "1"}]},
                   out={"map": {"env": "prod", "a": "1"}}),
                Ex({"tags": [{"key": "a", "value": "1"}, {"key": "env", "value": "prod"}]},
                   out={"map": {"a": "1", "env": "prod"}}, roundtrip=True),
                Ex({"tags": [{"Key": "env", "Value": "prod"}]}, out={"map": {"env": "prod"}}),
                Ex({"tags": [{"key": "a", "value": "1"}, {"key": "a", "value": "2"}]}, err="TRANSFORM_OUT_OF_DOMAIN"),
                Ex({"tags": [{"name": "a", "value": "1"}]}, err="TRANSFORM_OUT_OF_DOMAIN")),
               port_types=(("tags", _TAGS_LIST), ("map", _TAGS_MAP))),
    Combinator("tags_map_to_list", (("map", "tuple", "objeto texto -> texto"),),
               (("tags", "tuple", "lista de {key, value} ordenada pela chave"),), "objeto texto -> texto",
               (("TRANSFORM_OUT_OF_DOMAIN", "valor não texto"), ("UNKNOWN_INPUT", "entrada ausente ou não lida")),
               (), "nenhuma", "tags_list_to_map", False, _map_to_tags,
               (Ex({"map": {"env": "prod", "a": "1"}}, out={"tags": [{"key": "a", "value": "1"},
                                                                    {"key": "env", "value": "prod"}]}, roundtrip=True),
                Ex({"map": {"a": 1}}, err="TRANSFORM_OUT_OF_DOMAIN")),
               port_types=(("map", _TAGS_MAP), ("tags", _TAGS_LIST))),
]

_CMP_DOC = {
    "exact": ("any", "igualdade de valor JSON: número por valor exato, texto por texto ('1' ≠ 1), booleano só com "
                     "booleano, lista na ordem, objeto chave a chave; ABSENT só confere com ABSENT; tolerância 0",
              (), "nenhuma (decide igualdade)",
              (Ex({"expected": 80, "observed": 80.0}, out={"match": True}),
               Ex({"expected": "1", "observed": 1}, out={"match": False}),
               Ex({"expected": ABSENT, "observed": ABSENT}, out={"match": True}),
               Ex({"expected": 1, "observed": 1, "tolerance": 1}, err="DECLARATION_ERROR"),
               Ex({"expected": 1, "observed": {"$not_read": True}}, err="UNKNOWN_INPUT"))),
    "numeric_tolerance": ("number", "|observed − expected| ≤ tolerance (absoluta, na unidade do expected, aritmética "
                                    "exata); tolerância obrigatória ≥ 0; mesmo tipo de unidade dos dois lados (para "
                                    "tipos diferentes use compare_quantity_tolerance)",
                          (), "nenhuma (a folga é declarada na tolerância)",
                          (Ex({"expected": 100, "observed": "100.4", "tolerance": "0.5"}, out={"match": True}),
                           Ex({"expected": 100, "observed": 101, "tolerance": "0.5"}, out={"match": False}),
                           Ex({"expected": "0.1", "observed": "0.3", "tolerance": "0.2"}, out={"match": True},
                              note="aritmética exata: 0,3 − 0,1 = 0,2"),
                           Ex({"expected": 100, "observed": 100}, err="DECLARATION_ERROR",
                              note="tolerância não declarada"),
                           Ex({"expected": 100, "observed": 100, "tolerance": -1}, err="DECLARATION_ERROR"),
                           Ex({"expected": True, "observed": 1, "tolerance": 0}, err="TRANSFORM_OUT_OF_DOMAIN"))),
    "set_equal": ("tuple", "listas comparadas como conjuntos de valores JSON canônicos; tolerância 0",
                  ("not_expressible",), "ordem e repetição não contam",
                  (Ex({"expected": ["a", "b"], "observed": ["b", "a", "a"]}, out={"match": True}),
                   Ex({"expected": [1, 2], "observed": [1]}, out={"match": False}),
                   Ex({"expected": "a", "observed": ["a"]}, err="TRANSFORM_OUT_OF_DOMAIN"))),
    "normalized_string": ("string", "texto em NFC, sem espaço nas pontas, espaço interno colapsado; caixa preservada; "
                                    "tolerância 0", ("not_expressible",), "espaço extra e forma Unicode não contam",
                          (Ex({"expected": "Standard LRS", "observed": "  Standard  LRS"}, out={"match": True}),
                           Ex({"expected": "café", "observed": "café"}, out={"match": True}),
                           Ex({"expected": "gp3", "observed": "GP3"}, out={"match": False}),
                           Ex({"expected": "a", "observed": 1}, err="TRANSFORM_OUT_OF_DOMAIN"))),
    "duration_equal": ("duration", "xsd:duration pelo espaço de valores do XSD 1.1 (meses, segundos): P12M = P1Y, "
                                   "PT60M = PT1H, P1M ≠ P30D; com contexto de calendário, segundos na âncora; "
                                   "tolerância 0", (), "nenhuma",
                       (Ex({"expected": "PT1H", "observed": "PT60M"}, out={"match": True}),
                        Ex({"expected": "P1Y", "observed": "P12M"}, out={"match": True}),
                        Ex({"expected": "P1M", "observed": "P30D"}, out={"match": False}),
                        Ex({"expected": "P1M", "observed": "P31D"}, {}, {"calendar": {"anchor": "2026-01-01T00:00:00-03:00"}},
                           out={"match": True}),
                        Ex({"expected": "PT1H", "observed": "3600s"}, err="TRANSFORM_OUT_OF_DOMAIN"))),
    "cidr_equal": ("string", "mesma rede (endereço de rede e prefixo), forma textual livre; tolerância 0",
                   ("not_expressible",), "a forma textual não conta",
                   (Ex({"expected": "2001:db8::/32", "observed": "2001:DB8:0:0::/32"}, out={"match": True}),
                    Ex({"expected": "10.0.0.0/16", "observed": "10.0.0.0/24"}, out={"match": False}),
                    Ex({"expected": "10.0.0.0/16", "observed": "10.0.0.1/16"}, err="TRANSFORM_OUT_OF_DOMAIN"))),
}
for _c11, (_dt, _pre, _loss, _ltxt, _exs) in _CMP_DOC.items():
    _ins = [("expected", _dt, "valor planejado"), ("observed", _dt, "valor lido de volta")]
    if _c11 == "numeric_tolerance":
        _ins.append(("tolerance", "number", "tolerância absoluta declarada, ≥ 0"))
    COMBINATORS.append(Combinator(
        f"compare_{_c11}", tuple(_ins), (("match", "boolean", "confere sob o comparador"),), _pre,
        ((() if _c11 == "exact" else (("TRANSFORM_OUT_OF_DOMAIN", "valor fora do tipo do comparador"),)) + (
         ("UNKNOWN_INPUT", "valor não lido (NOT_READ)"),
         ("UNKNOWN_SYMBOLIC_INPUT", "valor simbólico ainda não resolvido"),
         ("DECLARATION_ERROR", "tolerância ausente, negativa ou fora de numeric_tolerance"))),
        _loss, _ltxt, None, False, _cmp_fn(_c11), _exs, accepts_absent=True, c11_name=_c11,
        collection=(("expected", "list"), ("observed", "list")) if _c11 == "set_equal" else ()))
COMBINATORS.append(Combinator(
    "compare_quantity_tolerance",
    (("expected", "number", "valor planejado"), ("expected_type", "tuple", "{unit, rate_window?, byte_convention?}"),
     ("observed", "number", "valor lido de volta"), ("observed_type", "tuple", "{unit, rate_window?, byte_convention?}"),
     ("tolerance", "number", "tolerância absoluta na unidade do expected, ≥ 0")),
    (("match", "boolean", "confere sob o comparador"),),
    ("numeric_tolerance com tipo de unidade inteiro dos dois lados (unidade, janela de taxa, convenção de byte): "
     "observed convertido para o tipo do expected, depois |observed − expected| ≤ tolerance"),
    (("TRANSFORM_OUT_OF_DOMAIN", "valor não numérico, ou unidade de mês/ano sem contexto de calendário"),
     ("NO_UNIT", "unidade ausente, UNKNOWN ou fora do registro"),
     ("UNKNOWN_INPUT", "valor não lido (NOT_READ)"),
     ("UNKNOWN_SYMBOLIC_INPUT", "valor simbólico ainda não resolvido"),
     ("DECLARATION_ERROR", "grandezas diferentes, taxa x quantidade, convenção de byte que contradiz a unidade, "
                           "tolerância ausente ou negativa")),
    (), "nenhuma (conversão exata; a folga é a tolerância)", None, False, _cmp_quantity,
    (Ex({"expected": 1, "expected_type": {"unit": "unit:GibiBYTE"}, "observed": 1024,
         "observed_type": {"unit": "unit:MebiBYTE"}, "tolerance": 0}, out={"match": True}),
     Ex({"expected": 1, "expected_type": {"unit": "unit:GibiBYTE"}, "observed": 1,
         "observed_type": {"unit": "unit:GigaBYTE"}, "tolerance": 0}, out={"match": False},
        note="1 GB ≠ 1 GiB"),
     Ex({"expected": 60, "expected_type": {"unit": "unit:NUM", "rate_window": "PT1M"}, "observed": 1,
         "observed_type": {"unit": "unit:NUM", "rate_window": "PT1S"}, "tolerance": 0}, out={"match": True}),
     Ex({"expected": 1, "expected_type": {"unit": "unit:GigaBYTE", "byte_convention": "IEC"}, "observed": 1,
         "observed_type": {"unit": "unit:GigaBYTE"}, "tolerance": 0}, err="DECLARATION_ERROR",
        note="GigaBYTE com convenção IEC é contradição de tipo"),
     Ex({"expected": 1, "expected_type": {"unit": "UNKNOWN"}, "observed": 1, "observed_type": {"unit": "unit:BYTE"},
         "tolerance": 0}, err="NO_UNIT"),
     Ex({"expected": 1, "expected_type": {"unit": "unit:SEC"}, "observed": 1, "observed_type": {"unit": "unit:BYTE"},
         "tolerance": 0}, err="DECLARATION_ERROR"),
     Ex({"expected": "x", "expected_type": {"unit": "unit:SEC"}, "observed": 1, "observed_type": {"unit": "unit:SEC"},
         "tolerance": 0}, err="TRANSFORM_OUT_OF_DOMAIN"),
     Ex({"expected": 1, "expected_type": {"unit": "unit:SEC"}, "observed": 1, "observed_type": {"unit": "unit:MO"},
         "tolerance": 0}, err="TRANSFORM_OUT_OF_DOMAIN", note="mês sem contexto de calendário")),
    accepts_absent=True, c11_name="numeric_tolerance"))

# ======================================================================== combinadores de coleção (emenda 1.2.0)
# Pedido STO-MAP CC-6: o C09 3.2.0 tem value_type list/set/map com item_type (e key_type). Representação: lista JSON
# (list), lista JSON sem repetição em ordem canônica (set) e objeto JSON (map). O C10 3.0.0 não tem list/set/map no
# datatype de porta: as portas são 'tuple' (valor estruturado) e o tipo de coleção vai em 'collection' e na restrição
# da porta (proposta em results/TRANSFORMS/CONTRACT_CHANGE.txt).
def _as_list(v, what):
    if not isinstance(v, list):
        raise OutOfDomain(f"{what}: não é lista: {v!r}")
    return v


def _canon_sorted(xs):
    keyed = {}
    for x in xs:
        keyed.setdefault(CMP._canon(x), x)
    return [keyed[k] for k in sorted(keyed)]


def _wrap_list(v, ctx):
    return {"list": [v["value"]]}


def _unwrap_single(v, ctx):
    xs = _as_list(v["list"], "unwrap_single")
    if len(xs) != 1:
        raise OutOfDomain(f"unwrap_single exige exatamente um elemento (tem {len(xs)})")
    return {"value": xs[0]}


def _list_to_set(v, ctx):
    return {"set": _canon_sorted(_as_list(v["list"], "list_to_set"))}


def _set_to_list(v, ctx):
    xs = _as_list(v["set"], "set_to_list")
    if len({CMP._canon(x) for x in xs}) != len(xs):
        raise OutOfDomain("set_to_list: conjunto com elemento repetido")
    return {"list": _canon_sorted(xs)}


def _elem_fn(v, what):
    name, p = v["fn"], v["params"]
    if not isinstance(name, str) or not isinstance(p, dict):
        raise DeclarationError(f"{what}: fn é nome e params é objeto")
    if not isinstance(get(name), Scalar):
        raise DeclarationError(f"{what}: {name} não é escalar; elemento a elemento só com escalar do registro")
    return name, p


def _map_elems(xs, name, p, ctx, what):
    out = []
    for i, x in enumerate(xs):
        try:
            out.append(apply_scalar(name, x, p, ctx))
        except TransformError as e:
            raise type(e)(f"{what}[{i}]: {e.args[0]}", e.code) from None
    return out


def _map_list(v, ctx):
    name, p = _elem_fn(v, "map_list")
    return {"list": _map_elems(_as_list(v["list"], "map_list"), name, p, ctx, "map_list")}


def _map_set(v, ctx):
    name, p = _elem_fn(v, "map_set")
    xs = _as_list(v["set"], "map_set")
    if len({CMP._canon(x) for x in xs}) != len(xs):
        raise OutOfDomain("map_set: conjunto com elemento repetido")
    return {"set": _canon_sorted(_map_elems(xs, name, p, ctx, "map_set"))}


def _map_values(v, ctx):
    name, p = _elem_fn(v, "map_values")
    m = v["map"]
    if not isinstance(m, dict):
        raise OutOfDomain(f"map_values: não é objeto: {m!r}")
    keys = list(m)
    return {"map": dict(zip(keys, _map_elems([m[k] for k in keys], name, p, ctx, "map_values")))}


def _elem_inverse(port):
    def inv(inputs, outputs):
        r = inverse_of(inputs["fn"], inputs["params"])
        return None if r is None else {port: outputs[port], "fn": r[0], "params": r[1]}
    return inv


_ELEM_ERRORS = (("TRANSFORM_OUT_OF_DOMAIN", "coleção mal formada ou elemento fora do domínio da escalar"),
                ("DECLARATION_ERROR", "fn fora do registro ou não escalar, ou params mal tipados para fn"))
_GIB = {"fn": "unit_convert_information", "params": {"from": "unit:GibiBYTE", "to": "unit:MebiBYTE"}}
_NONINJ = {"fn": "enum_map", "params": {"table": {"a": "x", "b": "x", "c": "y"}}}
_FN_PORTS = (("fn", "string", "nome de transformação ESCALAR do registro"),
             ("params", "tuple", "params da escalar (objeto)"))

COMBINATORS += [
    Combinator("wrap_list", (("value", "any", "qualquer valor"),), (("list", "tuple", "lista (C09 list) de um elemento"),),
               "qualquer valor; escalar -> lista de um elemento (ex. prefixo escalar -> lista de prefixos)", (), (),
               "nenhuma", "unwrap_single", False, _wrap_list,
               (Ex({"value": "logs/"}, out={"list": ["logs/"]}, roundtrip=True),
                Ex({"value": {"k": 1}}, out={"list": [{"k": 1}]}, roundtrip=True)),
               positional=('T', 'list[T]'), collection=(("list", "list"),)),
    Combinator("unwrap_single", (("list", "tuple", "lista (C09 list) de exatamente um elemento"),),
               (("value", "any", "o elemento"),), "lista com exatamente um elemento",
               (("TRANSFORM_OUT_OF_DOMAIN", "não é lista, ou lista vazia ou com mais de um elemento"),), (),
               "nenhuma", "wrap_list", False, _unwrap_single,
               (Ex({"list": ["logs/"]}, out={"value": "logs/"}, roundtrip=True),
                Ex({"list": []}, err="TRANSFORM_OUT_OF_DOMAIN"),
                Ex({"list": ["a", "b"]}, err="TRANSFORM_OUT_OF_DOMAIN", note="lista de dois não vira escalar"),
                Ex({"list": "a"}, err="TRANSFORM_OUT_OF_DOMAIN")),
               positional=('list[T]', 'T'), collection=(("list", "list"),)),
    Combinator("list_to_set", (("list", "tuple", "lista (C09 list) de valores JSON"),),
               (("set", "tuple", "conjunto (C09 set): lista sem repetição em ordem canônica"),),
               "lista de valores JSON", (("TRANSFORM_OUT_OF_DOMAIN", "não é lista"),),
               ("not_expressible",), "a ordem e a repetição da lista não se recuperam", "set_to_list", True,
               _list_to_set,
               (Ex({"list": ["b", "a", "b"]}, out={"set": ["a", "b"]}, note="ordem e repetição somem"),
                Ex({"list": ["a", "b"]}, out={"set": ["a", "b"]}, roundtrip=True),
                Ex({"list": {"a": 1}}, err="TRANSFORM_OUT_OF_DOMAIN")),
               positional=('list[T]', 'set[T]'), collection=(("list", "list"), ("set", "set"))),
    Combinator("set_to_list", (("set", "tuple", "conjunto (C09 set): lista sem repetição, qualquer ordem"),),
               (("list", "tuple", "lista (C09 list) na ordem canônica"),), "conjunto sem elemento repetido",
               (("TRANSFORM_OUT_OF_DOMAIN", "não é lista, ou tem elemento repetido"),), (),
               "nenhuma (a ordem da lista é a canônica: o conjunto não tem ordem para perder)", "list_to_set", False,
               _set_to_list,
               (Ex({"set": ["b", "a"]}, out={"list": ["a", "b"]}, roundtrip=True),
                Ex({"set": [3, 1, 2]}, out={"list": [1, 2, 3]}, roundtrip=True),
                Ex({"set": ["a", "a"]}, err="TRANSFORM_OUT_OF_DOMAIN")),
               positional=('set[T]', 'list[T]'), collection=(("set", "set"), ("list", "list"))),
    Combinator("map_list", (("list", "tuple", "lista (C09 list)"),) + _FN_PORTS,
               (("list", "tuple", "lista do mesmo tamanho e ordem, item_type = saída da escalar"),),
               "aplica a escalar fn (com params) a cada elemento, na ordem; a grandeza do elemento é a da escalar "
               "(não muda)", _ELEM_ERRORS, ("semantic",),
               "a perda de cada elemento é a da escalar fn; a inversa é map_list com a inversa de fn", "map_list", True,
               _map_list,
               (Ex({"list": [1, 2], **_GIB}, out={"list": [1024, 2048]}, roundtrip=True),
                Ex({"list": [], **_GIB}, out={"list": []}, roundtrip=True),
                Ex({"list": ["a", "b"], **_NONINJ}, out={"list": ["x", "x"]}, note="enum_map não injetiva: sem inversa"),
                Ex({"list": ["a", "z"], **_NONINJ}, err="TRANSFORM_OUT_OF_DOMAIN"),
                Ex({"list": ["10.0.0.0/8"], "fn": "split_cidr", "params": {}}, err="DECLARATION_ERROR"),
                Ex({"list": [1], "fn": "scale", "params": {"factor": 2}}, err="DECLARATION_ERROR"),
                Ex({"list": [1, {"$not_read": True}], **_GIB}, err="UNKNOWN_INPUT"),
                Ex({"list": [{"$symbolic": True}], **_GIB}, err="UNKNOWN_SYMBOLIC_INPUT")),
               collection=(("list", "list"),), inv_inputs=_elem_inverse("list")),
    Combinator("map_set", (("set", "tuple", "conjunto (C09 set)"),) + _FN_PORTS,
               (("set", "tuple", "conjunto das imagens, ordem canônica"),),
               "aplica a escalar fn a cada elemento do conjunto; imagens iguais se juntam", _ELEM_ERRORS,
               ("semantic",), "escalar não injetiva junta elementos (o conjunto encolhe); além disso, a perda de fn",
               "map_set", True, _map_set,
               (Ex({"set": [1, 2], **_GIB}, out={"set": [1024, 2048]}, roundtrip=True),
                Ex({"set": ["a", "b", "c"], **_NONINJ}, out={"set": ["x", "y"]}, note="a e b viram x"),
                Ex({"set": [1, 1], **_GIB}, err="TRANSFORM_OUT_OF_DOMAIN"),
                Ex({"set": [1], "fn": "nao_existe", "params": {}}, err="DECLARATION_ERROR")),
               collection=(("set", "set"),), inv_inputs=_elem_inverse("set")),
    Combinator("map_values", (("map", "tuple", "mapa (C09 map) chave -> valor"),) + _FN_PORTS,
               (("map", "tuple", "mesmas chaves, valores = saída da escalar"),),
               "aplica a escalar fn a cada valor do mapa; as chaves não mudam", _ELEM_ERRORS, ("semantic",),
               "a perda de cada valor é a da escalar fn; a inversa é map_values com a inversa de fn", "map_values",
               True, _map_values,
               (Ex({"map": {"a": 1, "b": 2}, **_GIB}, out={"map": {"a": 1024, "b": 2048}}, roundtrip=True),
                Ex({"map": {"k": "a"}, **_NONINJ}, out={"map": {"k": "x"}}, note="enum_map não injetiva: sem inversa"),
                Ex({"map": [1], **_GIB}, err="TRANSFORM_OUT_OF_DOMAIN"),
                Ex({"map": {"k": 1}, "fn": "unit_convert_information", "params": {"from": "unit:SEC", "to": "unit:BYTE"}},
                   err="DECLARATION_ERROR")),
               collection=(("map", "map"),), inv_inputs=_elem_inverse("map")),
]

_MARKER_ERRORS = (("UNKNOWN_INPUT", "valor não lido (NOT_READ)"),
                  ("UNKNOWN_SYMBOLIC_INPUT", "valor simbólico ainda não resolvido"))


def _key(v) -> str:
    return json.dumps(v, sort_keys=True, default=str)


def _with_marker_examples(t):
    """Os marcadores valem para todo item (apply_scalar/apply_combinator): NOT_READ -> UNKNOWN_INPUT, simbólico ->
    UNKNOWN_SYMBOLIC_INPUT (identity deixa o simbólico passar). Aqui eles entram no campo error de cada item e
    ganham exemplos; nos comparadores, também a tolerância indevida ou ausente."""
    from dataclasses import replace
    have_codes = {c for c, _ in t.errors}
    errs = tuple(t.errors)
    marks = [("UNKNOWN_INPUT", {"$not_read": True})]
    if not getattr(t, "passes_symbolic", False):
        marks.append(("UNKNOWN_SYMBOLIC_INPUT", {"$symbolic": True}))
    for code, _ in marks:
        if code not in have_codes:
            errs += tuple(e for e in _MARKER_ERRORS if e[0] == code)
    pos = next(e for e in t.examples if e.err is None)
    extra = []
    if isinstance(t, Scalar):
        extra += [Ex(m, pos.params, err=code) for code, m in marks]
    else:
        first = t.inputs[0][0]
        extra += [Ex({**pos.value, first: m}, err=code) for code, m in marks]
        if t.c11_name:
            if "tolerance" not in [i[0] for i in t.inputs]:
                extra.append(Ex({**pos.value, "tolerance": 1}, err="DECLARATION_ERROR",
                                note="tolerância fora de numeric_tolerance"))
            else:
                extra.append(Ex({k: v for k, v in pos.value.items() if k != "tolerance"}, err="DECLARATION_ERROR",
                                note="tolerância não declarada"))
    have = {(e.err, _key(e.value), _key(e.params)) for e in t.examples}
    new = tuple(e for e in extra if (e.err, _key(e.value), _key(e.params)) not in have)
    return replace(t, errors=errs, examples=tuple(t.examples) + new)


SCALARS = [_with_marker_examples(s) for s in SCALARS]
COMBINATORS = [_with_marker_examples(c) for c in COMBINATORS]

for _c in COMBINATORS:
    if _c.positional and (len(_c.inputs), len(_c.outputs)) != (1, 1):
        raise RuntimeError(f"{_c.name}: posicional exige uma entrada e uma saída")

REGISTRY: dict[str, Scalar | Combinator] = {}
for _t in SCALARS + COMBINATORS:
    if _t.name in REGISTRY:
        raise RuntimeError(f"nome repetido no registro: {_t.name}")
    REGISTRY[_t.name] = _t


# =============================================================================================== aplicação
def get(name: str):
    if name not in REGISTRY:
        raise DeclarationError(f"transformação fora do registro fechado: {name!r}")
    return REGISTRY[name]


def apply_scalar(name: str, v, params: dict | None = None, ctx: dict | None = None):
    s = get(name)
    if not isinstance(s, Scalar):
        raise DeclarationError(f"{name} é combinador de tupla: use apply_combinator")
    p = params or {}
    _check_params(s.params, p, name)
    if is_not_read(v):
        raise UnknownInput(f"{name}: valor não lido")
    if is_symbolic(v):
        if s.passes_symbolic:
            return v
        raise SymbolicInput(f"{name}: valor simbólico ainda não resolvido")
    if is_absent(v) and not s.accepts_absent:
        raise OutOfDomain(f"{name}: valor ausente fora do domínio")
    try:
        return s.fn(v, p, ctx)
    except TransformError:
        raise
    except (KeyError, TypeError, ValueError, ArithmeticError) as e:
        raise OutOfDomain(f"{name}: {type(e).__name__}: {e}") from None


def apply_combinator(name: str, inputs: dict, ctx: dict | None = None) -> dict:
    c = get(name)
    if not isinstance(c, Combinator):
        raise DeclarationError(f"{name} é escalar: use apply_scalar")
    if not isinstance(inputs, dict):
        raise DeclarationError(f"{name}: entradas são {{porta: valor}}")
    names = [i[0] for i in c.inputs]
    extra = set(inputs) - set(names)
    if extra:
        raise DeclarationError(f"{name}: portas desconhecidas {sorted(extra)}")
    for n in names:
        if n not in inputs:
            if c.c11_name and n == "tolerance":
                raise DeclarationError(f"{name}: tolerância não declarada")
            raise UnknownInput(f"{name}: componente {n!r} ausente")
        v = inputs[n]
        if is_not_read(v):
            raise UnknownInput(f"{name}: componente {n!r} não lido")
        if is_symbolic(v):
            raise SymbolicInput(f"{name}: componente {n!r} simbólico")
        if is_absent(v) and not c.accepts_absent:
            raise UnknownInput(f"{name}: componente {n!r} ausente")
    try:
        out = c.fn(inputs, ctx)
    except TransformError:
        raise
    except (KeyError, TypeError, ValueError, ArithmeticError) as e:
        raise OutOfDomain(f"{name}: {type(e).__name__}: {e}") from None
    if set(out) != {o[0] for o in c.outputs}:
        raise RuntimeError(f"{name}: saídas {sorted(out)} ≠ declaradas")
    return out


def inverse_of(name: str, params: dict | None = None):
    """(nome, params) da inversa parcial desta instância, ou None quando não há."""
    t = get(name)
    if t.inverse is None:
        return None
    if isinstance(t, Scalar):
        p = t.inv_params(params or {}) if t.inv_params else {}
        return None if p is None else (t.inverse, p)
    return t.inverse, {}


# ------------------------------------------------------------------- domínio e imagem finitos (emenda 1.1.0)
_FINITE = {
    "enum_map": lambda p: frozenset(_enum_table(p, "enum_map")),
    "bool_to_enum": lambda p: (_b2e_params(p, "bool_to_enum"), frozenset({True, False}))[1],
    "enum_to_bool": lambda p: (lambda a, b: frozenset(a) | frozenset(b))(*_e2b_params(p, "enum_to_bool")),
}


def finite_domain(name: str, params: dict | None = None):
    """Domínio declarado de uma escalar de tabela finita (frozenset), ou None quando o domínio não é finito pela
    declaração (então o domínio é o do tipo de entrada). Pedido STO-MAP CC-9: o árbitro calcula o domínio e a
    imagem de enum_to_bool/bool_to_enum/enum_map para a relação de domínios de valores."""
    t = get(name)
    if not isinstance(t, Scalar):
        raise DeclarationError(f"{name} é combinador: o domínio é por porta")
    p = params or {}
    _check_params(t.params, p, name)
    f = _FINITE.get(name)
    return None if f is None else f(p)


def finite_image(name: str, params: dict | None = None, values=None):
    """Imagem de um conjunto finito de valores pela escalar (frozenset). values=None usa o domínio finito declarado
    (DECLARATION_ERROR se ele não existe). Valor fora do domínio da função levanta o erro dela (o chamador decide se
    a transformação é parcial sobre o domínio do tipo)."""
    p = params or {}
    if values is None:
        values = finite_domain(name, p)
        if values is None:
            raise DeclarationError(f"{name}: sem domínio finito declarado; passe os valores")
    out = set()
    for v in values:
        r = apply_scalar(name, v, p)
        out.add(CMP._canon(r) if isinstance(r, (dict, list)) else r)
    return frozenset(out)


# ------------------------------------------------------- entrada posicional única (emenda 1.6.0, ciclo v4)
def signature(name: str) -> dict:
    """Assinatura estrutural de um combinador para quem julga a alegação (SEMANTICS, ARBITERLIB): portas nomeadas e,
    quando a entrada é posicional única, a forma 'T -> list[T]' etc. (T = tipo do elemento; o tipo exato de um uso
    sai de collection_type_out)."""
    t = get(name)
    if not isinstance(t, Combinator):
        raise DeclarationError(f"{name} é escalar")
    out = {"name": name, "kind": "tuple", "inputs": [p[0] for p in t.inputs], "outputs": [p[0] for p in t.outputs],
           "positional": bool(t.positional)}
    if t.positional:
        out.update({"input": t.inputs[0][0], "output": t.outputs[0][0], "in": t.positional[0],
                    "out": t.positional[1]})
    return out


def apply_positional(name: str, value, ctx: dict | None = None):
    """Aplica um combinador de entrada posicional única ao valor (sem embrulhar em {porta: valor}); devolve o valor da
    única saída. Valor que é objeto JSON vai como valor, nunca como entradas nomeadas."""
    t = get(name)
    if not isinstance(t, Combinator) or not t.positional:
        raise DeclarationError(f"{name} não tem entrada posicional única")
    return apply_combinator(name, {t.inputs[0][0]: value}, ctx)[t.outputs[0][0]]


def invert(name: str, params: dict | None, inputs, outputs):
    """(nome, params|entradas) para aplicar a inversa parcial a esta instância, ou None quando não há.
    Escalar: (nome, params). Combinador: (nome, entradas da inversa) = saídas, ou o que inv_inputs der."""
    t = get(name)
    if isinstance(t, Scalar):
        return inverse_of(name, params)
    if t.inverse is None:
        return None
    if t.inv_inputs is not None:
        ins = t.inv_inputs(inputs, outputs)
        return None if ins is None else (t.inverse, ins)
    return t.inverse, outputs


_COLL_SHAPE = {"wrap_list": (None, "list"), "unwrap_single": ("list", None), "list_to_set": ("list", "set"),
               "set_to_list": ("set", "list"), "map_list": ("list", "list"), "map_set": ("set", "set"),
               "map_values": ("map", "map")}


def collection_type_out(name: str, tin: dict, fn: str | None = None, params: dict | None = None) -> dict:
    """Tipo de saída (value_type do C09 3.2.0: {datatype: list|set|map, item_type, key_type?}) de um combinador de
    coleção. map_* tipam o elemento por type_out da escalar, que reprova se a grandeza do elemento mudaria."""
    if name not in _COLL_SHAPE:
        raise DeclarationError(f"{name} não é combinador de coleção")
    src, dst = _COLL_SHAPE[name]
    if src is not None and tin.get("datatype") != src:
        raise DeclarationError(f"{name}: entrada {tin.get('datatype')}, esperado {src}")
    if src is not None and "item_type" not in tin:
        raise DeclarationError(f"{name}: coleção sem item_type (C09-COLL)")
    if name == "wrap_list":
        return {"datatype": "list", "item_type": dict(tin)}
    if name == "unwrap_single":
        return dict(tin["item_type"])
    item = dict(tin["item_type"])
    if name.startswith("map_"):
        if fn is None:
            raise DeclarationError(f"{name}: tipar exige fn")
        item = type_out(fn, params or {}, item)
    out = {"datatype": dst, "item_type": item}
    if dst == "map":
        out["key_type"] = tin.get("key_type")
    return out


def apply_chain(chain, v, ctx: dict | None = None):
    """Cadeia de escalares [{name, params}], da esquerda para a direita."""
    for item in chain_of(chain):
        v = apply_scalar(item["name"], v, item.get("params") or {}, ctx)
    return v


def chain_of(fn) -> list[dict]:
    if fn is None:
        return []
    return list(fn) if isinstance(fn, list) else [fn]


def type_out(name: str, params: dict | None, tin: dict) -> dict:
    """Tipo de saída de uma escalar dada a entrada; reprova (DECLARATION_ERROR) se a grandeza mudaria."""
    s = get(name)
    if not isinstance(s, Scalar):
        raise DeclarationError(f"{name} é combinador: os tipos são por porta")
    p = params or {}
    _check_params(s.params, p, name)
    try:
        tout = s.type_out(dict(tin), p)
    except TransformError:
        raise
    except (KeyError, TypeError, ValueError) as e:
        raise DeclarationError(f"{name}: {type(e).__name__}: {e}") from None
    if tout.get("quantity_kind") != tin.get("quantity_kind"):
        raise DeclarationError(f"{name}: grandeza {tin.get('quantity_kind')} -> {tout.get('quantity_kind')}")
    return tout


def check_chain(chain, tin: dict, tout: dict | None = None) -> dict:
    """Tipa a cadeia passo a passo; com tout, o tipo final tem de bater (datatype, grandeza, unidade, janela)."""
    t = dict(tin)
    for item in chain_of(chain):
        t = type_out(item["name"], item.get("params") or {}, t)
    if tout is not None:
        keys = ("quantity_kind", "unit", "rate_window", "byte_convention")
        a = {k: t.get(k) for k in keys}
        b = {k: tout.get(k) for k in keys}
        for d in (a, b):
            if d["rate_window"] is not None:
                d["rate_window"] = U.canonical_duration(U.parse_duration(d["rate_window"]))
            if d["unit"] in U.UNITS:
                d["byte_convention"] = U.UnitType.of({"unit": d["unit"],
                                                      "byte_convention": d["byte_convention"]}).byte_convention
        if a != b:
            raise DeclarationError(f"cadeia termina em {a}, declarado {b}")
    return t


def resolve_kernel(name: str, params: dict | None = None) -> tuple[str, dict]:
    """Nome do núcleo do SEMANTICS -> entrada tipada do registro (unit_convert -> unit_convert_<grandeza>)."""
    p = dict(params or {})
    if name == "unit_convert":
        k = U.unit(p.get("from")).kind
        key = {v: k_ for k_, v in U.KINDS.items()}[k]
        n = f"unit_convert_{key}"
        get(n)
        return n, p
    if name in ("scale", "rate_window_convert"):
        raise DeclarationError(f"{name} do núcleo não tem grandeza concreta; declare a entrada por grandeza")
    get(name)
    return name, p


# ================================================================================================ documento
def _err_text(errs) -> str:
    for c, w in errs:
        if " | " in w:
            raise RuntimeError(f"texto de erro com ' | ' (separador do campo error): {w!r}")
    return " | ".join(f"{c}: {w}" for c, w in errs) if errs else "nunca"


def _loss_text(t) -> str:
    if t.loss:
        return f"{', '.join(t.loss)}: {t.loss_text}"
    return t.loss_text if t.loss_text.startswith("nenhuma") else f"nenhuma ({t.loss_text})"


def _port(t, name, dt) -> dict:
    """Porta publicada: list/set/map com item_type (C10 3.1.0) quando o tipo do elemento é concreto; porta polimórfica
    (elemento de qualquer tipo) sai list/set/map com item_type {datatype: any} (C10 3.2.0)."""
    vt = dict(t.port_types).get(name) if isinstance(t, Combinator) else None
    if vt is None and isinstance(t, Combinator) and name in dict(t.collection):
        # porta polimórfica: elemento de qualquer tipo (C10 3.2.0, item_type {datatype: any})
        kind = dict(t.collection)[name]
        vt = {"datatype": kind, "item_type": {"datatype": "any"}, **({"key_type": "string"} if kind == "map" else {})}
    if vt is None:
        return {"name": name, "datatype": dt}
    return {"name": name, **json.loads(json.dumps({k: vt[k] for k in ("datatype", "key_type", "item_type") if k in vt}))}


def to_item(t) -> dict:
    if isinstance(t, Scalar):
        d = {"name": t.name, "kind": "scalar", "domain": dict(t.domain), "codomain": dict(t.codomain),
             "precondition": t.precondition, "error": _err_text(t.errors), "loss": _loss_text(t),
             "inverse": {"name": t.inverse, "partial": t.partial}}
        if t.params:
            d["params"] = {k: dict(v) for k, v in t.params.items()}
        if t.context_required:
            d["context_required"] = list(t.context_required)
        if t.duration_calendar:
            d["duration_calendar"] = t.duration_calendar
        return d
    return {"name": t.name, "kind": "tuple",
            "inputs": [_port(t, n, dt) for n, dt, _ in t.inputs],
            "outputs": [_port(t, n, dt) for n, dt, _ in t.outputs],
            "precondition": t.precondition + (
                f"; entrada posicional única {t.inputs[0][0]}: {t.positional[0]} -> saída {t.outputs[0][0]}: "
                f"{t.positional[1]}" if t.positional else "") + "; portas: " + "; ".join(
                f"{n} ({r})" for n, _, r in t.inputs + t.outputs) + (
                "; coleção (C09 3.2.0) por porta: " + ", ".join(f"{p} = {k}" for p, k in t.collection)
                if t.collection else ""),
            "error": _err_text(t.errors), "loss": _loss_text(t),
            "inverse": {"name": t.inverse, "partial": t.partial}}


def document() -> dict:
    return {"schema": "bo.transforms/1", "contract": "C10", "contract_version": "3.2.0", "module": "TRANSFORMS",
            "generated_at": GENERATED_AT, "scalar": [to_item(s) for s in SCALARS],
            "combinators": [to_item(c) for c in COMBINATORS]}


def parse_error_field(text: str) -> list[tuple[str, str]]:
    """'CÓDIGO: quando | CÓDIGO: quando' ou 'nunca' -> [(código, quando)]."""
    if text == "nunca":
        return []
    out = []
    for part in text.split(" | "):
        code, sep, when = part.partition(": ")
        out.append((code, when if sep else ""))
    return out


def parse_loss_field(text: str) -> list[str]:
    """'nenhuma[ (...)]' | 'k1, k2: texto' -> [tipos]."""
    if text == "nenhuma" or text.startswith("nenhuma ("):
        return []
    kinds, sep, _ = text.partition(": ")
    return [k.strip() for k in kinds.split(",")] if sep else ["<sem tipo>"]


__all__ = ["signature", "apply_positional", "invert", "collection_type_out", "finite_domain", "finite_image", "REGISTRY", "SCALARS", "COMBINATORS", "Scalar", "Combinator", "Ex", "apply_scalar", "apply_combinator",
           "apply_chain", "inverse_of", "type_out", "check_chain", "resolve_kernel", "document", "to_item", "get",
           "LOSS_KINDS", "DATATYPES", "parse_error_field", "parse_loss_field", "REGISTRY_VERSION", "GENERATED_AT"]
