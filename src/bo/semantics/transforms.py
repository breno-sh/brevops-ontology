"""Núcleo de funções parciais de tradução (referência semântica; o registro fechado é do TRANSFORMS).

Separação do N4: TRANSFORMAÇÃO ESCALAR (um valor -> um valor) exige grandeza de entrada = grandeza de saída;
COMBINADOR DE TUPLA (um valor <-> vários, ou o contrário) declara tipos estruturados por componente e não
compara a grandeza do todo com a de cada parte.

Cada item declara: kind (scalar | tuple), domínio, codomínio, pré-condição, erro (OutOfDomain =
TRANSFORM_OUT_OF_DOMAIN), perda (nenhuma: a perda é declarada à parte, no loss_contract) e inversa parcial.
"""

from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass
from fractions import Fraction
from typing import Callable

from .valuetypes import (EnumDomain, NumDomain, AnyDomain, OutOfDomain, TypeError_, UNITS, ValueType,
                         duration_seconds, frac, jnum)


@dataclass(frozen=True)
class Spec:
    name: str
    kind: str                      # scalar | tuple
    domain: str
    codomain: str
    precondition: str
    error: str
    inverse: str                   # nome da inversa parcial ou "nenhuma"
    apply: Callable
    inv: Callable | None = None    # params -> (nome, params) da inversa
    image: Callable | None = None  # (domínio, params) -> domínio da imagem (para a relação de domínios)


# ------------------------------------------------------------------------------------------ escalares
def _identity(v, p, ctx):
    return v


def _factor(p) -> Fraction:
    fu, tu = p.get("from"), p.get("to")
    if fu not in UNITS or tu not in UNITS:
        raise TypeError_(f"unit_convert: unidade fora do núcleo {fu}->{tu}")
    if UNITS[fu][0] != UNITS[tu][0]:
        raise TypeError_(f"unit_convert: grandezas diferentes ({UNITS[fu][0]} -> {UNITS[tu][0]}); escalar não muda grandeza")
    f1, f2 = UNITS[fu][1], UNITS[tu][1]
    if f1 is None or f2 is None:
        raise OutOfDomain(f"{fu}->{tu}: unidade sem fator fixo (mês/ano) exige contexto de calendário")
    return f1 / f2


def _unit_convert(v, p, ctx):
    return _num_out(frac(v) * _factor(p))


def _num_out(x: Fraction):
    return int(x) if x.denominator == 1 else x


def _scale(v, p, ctx):
    return _num_out(frac(v) * frac(p["factor"]))


def _scale_image(d, p):
    f = frac(p["factor"]) if "factor" in p else _factor(p)
    return _scale_dom(d, f)


def _scale_dom(d, f):
    if isinstance(d, NumDomain):
        if f > 0:
            return NumDomain(None if d.lo is None else d.lo * f, None if d.hi is None else d.hi * f,
                             None if d.step is None else d.step * f, d.base * f)
        return AnyDomain()
    if isinstance(d, EnumDomain):
        return EnumDomain(frozenset(frac(x) * f for x in d.values))
    return d


def _duration_to_number(v, p, ctx):
    secs = duration_seconds(v, (ctx or {}).get("calendar_context"))
    u = p["to"]
    if u not in UNITS or UNITS[u][1] is None:
        raise OutOfDomain(f"duração -> {u}: unidade sem fator fixo")
    return _num_out(secs / UNITS[u][1])


def _number_to_duration(v, p, ctx):
    u = p["from"]
    if u not in UNITS or UNITS[u][1] is None:
        raise OutOfDomain(f"{u} -> duração: unidade sem fator fixo")
    secs = frac(v) * UNITS[u][1]
    if secs.denominator != 1 or secs < 0:
        raise OutOfDomain("duração exige segundos inteiros não negativos")
    secs = int(secs)
    if secs % 86400 == 0:
        return f"P{secs // 86400}D"
    return f"PT{secs}S"


def _enum_map(v, p, ctx):
    table = p["table"]
    key = _key(v)
    if key not in table:
        raise OutOfDomain(f"enum_map: {v!r} fora do domínio da tabela")
    return table[key]


def _key(v):
    if isinstance(v, bool):
        return "true" if v else "false"
    return str(v)


def _enum_inv(p):
    t = p["table"]
    vals = [_key(x) for x in t.values()]
    if len(set(vals)) != len(vals):
        return None   # não injetiva: sem inversa total; a parcial não é única
    return "enum_map", {"table": {_key(b): _unkey(a) for a, b in t.items()}}


def _unkey(a: str):
    return True if a == "true" else False if a == "false" else a


def _enum_image(d, p):
    if isinstance(d, EnumDomain):
        t = p["table"]
        return EnumDomain(frozenset(t[_key(x)] for x in d.values if _key(x) in t))
    return AnyDomain()


def _rate_window(v, p, ctx):
    a, b = duration_seconds(p["from"]), duration_seconds(p["to"])
    return _num_out(frac(v) * b / a)


# --------------------------------------------------------------------------------- combinadores de tupla
_ALARM = re.compile(r"^(?P<metric>[A-Za-z][A-Za-z0-9_]*)\[(?P<n>\d+)(?P<u>[smhd])\]\.(?P<stat>[a-z]+)\(\)\s*"
                    r"(?P<op>>=|<=|==|!=|>|<)\s*(?P<thr>-?\d+(?:\.\d+)?)$")
_OPS = {">": "gt", ">=": "ge", "<": "lt", "<=": "le", "==": "eq", "!=": "ne"}
_UNIT_DUR = {"s": "S", "m": "M", "h": "H", "d": "D"}


def _split_alarm(v, p, ctx):
    """Expressão de alarme 'Metrica[1m].mean() > 80' -> métrica, janela, estatística, operador, limiar.
    Parcial: qualquer outra forma (dimensões, agrupamento, funções) é TRANSFORM_OUT_OF_DOMAIN."""
    m = _ALARM.match(v.strip()) if isinstance(v, str) else None
    if not m:
        raise OutOfDomain(f"expressão de alarme fora do subconjunto suportado: {v!r}")
    n, u = int(m["n"]), m["u"]
    win = f"P{n}D" if u == "d" else f"PT{n}{_UNIT_DUR[u]}"
    thr = Fraction(m["thr"])
    return {"metric": m["metric"], "window": win, "statistic": m["stat"], "operator": _OPS[m["op"]],
            "threshold": _num_out(thr)}


_DUR_BACK = re.compile(r"^(?:P(\d+)D|PT(\d+)([SMH]))$")


def _join_alarm(v, p, ctx):
    need = {"metric", "window", "statistic", "operator", "threshold"}
    if not isinstance(v, dict) or set(v) != need:
        raise OutOfDomain(f"join_alarm_query exige os 5 componentes: {sorted(need)}")
    m = _DUR_BACK.match(v["window"])
    if not m:
        raise OutOfDomain(f"janela não exprimível: {v['window']}")
    win = f"{m[1]}d" if m[1] else f"{m[2]}{m[3].lower()}"
    rev = {b: a for a, b in _OPS.items()}
    if v["operator"] not in rev:
        raise OutOfDomain(f"operador {v['operator']}")
    thr = frac(v["threshold"])
    thr_s = str(thr.numerator) if thr.denominator == 1 else str(float(thr))
    return f"{v['metric']}[{win}].{v['statistic']}() {rev[v['operator']]} {thr_s}"


def _split_ports(v, p, ctx):
    if not isinstance(v, str) or not re.match(r"^\d{1,5}(-\d{1,5})?$", v):
        raise OutOfDomain(f"faixa de portas: {v!r}")
    a, _, b = v.partition("-")
    lo, hi = int(a), int(b or a)
    if not (0 <= lo <= hi <= 65535):
        raise OutOfDomain(f"faixa de portas inválida: {v}")
    return {"from_port": lo, "to_port": hi}


def _join_ports(v, p, ctx):
    if not isinstance(v, dict) or set(v) != {"from_port", "to_port"}:
        raise OutOfDomain("join_port_range exige from_port e to_port")
    lo, hi = v["from_port"], v["to_port"]
    if not (isinstance(lo, int) and isinstance(hi, int) and 0 <= lo <= hi <= 65535):
        raise OutOfDomain(f"faixa inválida {lo}-{hi}")
    return str(lo) if lo == hi else f"{lo}-{hi}"


def _split_cidr(v, p, ctx):
    try:
        n = ipaddress.ip_network(v, strict=True)
    except (ValueError, TypeError):
        raise OutOfDomain(f"CIDR inválido ou com bits de host: {v!r}")
    return {"address": str(n.network_address), "prefix_length": n.prefixlen}


def _join_cidr(v, p, ctx):
    if not isinstance(v, dict) or set(v) != {"address", "prefix_length"}:
        raise OutOfDomain("join_cidr exige address e prefix_length")
    return _split_cidr(f"{v['address']}/{v['prefix_length']}", p, ctx) and f"{v['address']}/{v['prefix_length']}"


def _json_get(v, p, ctx):
    """Documento JSON (texto) -> valor de uma chave de topo. Parcial: texto que não é objeto JSON, ou sem a chave."""
    import json as _json
    try:
        d = _json.loads(v) if isinstance(v, str) else v
    except ValueError:
        raise OutOfDomain("documento não é JSON")
    if not isinstance(d, dict) or p.get("key") not in d:
        raise OutOfDomain(f"documento sem a chave {p.get('key')!r}")
    return d[p["key"]]


def _map_get(v, p, ctx):
    """Mapa (ex. rótulos) -> valor de uma chave. Parcial: chave ausente."""
    if not isinstance(v, dict) or p.get("key") not in v:
        raise OutOfDomain(f"mapa sem a chave {p.get('key')!r}")
    return v[p["key"]]


REGISTRY: dict[str, Spec] = {s.name: s for s in [
    Spec("json_get", "tuple", "documento JSON (objeto) em texto", "valor da chave de topo 'key'", "objeto JSON com a chave",
         "OutOfDomain", "nenhuma (o documento inteiro não se reconstrói de uma chave)", _json_get),
    Spec("map_get", "tuple", "mapa de rótulos", "valor da chave 'key'", "chave presente", "OutOfDomain",
         "nenhuma", _map_get),
    Spec("identity", "scalar", "tipo de entrada", "o mesmo valor", "nenhuma", "nunca", "identity",
         _identity, lambda p: ("identity", {}), lambda d, p: d),
    Spec("unit_convert", "scalar", "número na unidade 'from' (fator fixo)", "número na unidade 'to'",
         "mesma grandeza; fatores fixos", "OutOfDomain se mês/ano; TypeError se grandezas diferem", "unit_convert",
         _unit_convert, lambda p: ("unit_convert", {"from": p["to"], "to": p["from"]}), _scale_image),
    Spec("scale", "scalar", "número", "número × factor", "factor racional > 0", "nunca", "scale(1/factor)",
         _scale, lambda p: ("scale", {"factor": str(1 / frac(p["factor"]))}), _scale_image),
    Spec("duration_to_number", "scalar", "xsd:duration sem Y/M (ou com contexto de calendário)",
         "número na unidade 'to'", "unidade 'to' com fator fixo", "OutOfDomain (TRANSFORM_OUT_OF_DOMAIN)",
         "number_to_duration", _duration_to_number, lambda p: ("number_to_duration", {"from": p["to"]})),
    Spec("number_to_duration", "scalar", "número na unidade 'from'", "xsd:duration em dias ou segundos",
         "segundos inteiros", "OutOfDomain", "duration_to_number", _number_to_duration,
         lambda p: ("duration_to_number", {"to": p["from"]})),
    Spec("enum_map", "scalar", "chaves da tabela", "valores da tabela", "tabela finita",
         "OutOfDomain fora da tabela", "enum_map invertida (só se injetiva)", _enum_map, _enum_inv, _enum_image),
    Spec("rate_window_convert", "scalar", "taxa por janela 'from'", "taxa por janela 'to'", "janelas fixas",
         "OutOfDomain", "rate_window_convert(to,from)", _rate_window,
         lambda p: ("rate_window_convert", {"from": p["to"], "to": p["from"]}),
         lambda d, p: _scale_dom(d, duration_seconds(p["to"]) / duration_seconds(p["from"]))),
    Spec("split_alarm_query", "tuple", "expressão 'Metrica[Nu].estat() op limiar'",
         "{metric, window, statistic, operator, threshold}", "subconjunto suportado da linguagem",
         "OutOfDomain fora do subconjunto", "join_alarm_query", _split_alarm, lambda p: ("join_alarm_query", {})),
    Spec("join_alarm_query", "tuple", "{metric, window, statistic, operator, threshold}", "expressão de alarme",
         "os 5 componentes presentes", "OutOfDomain (UNKNOWN_INPUT se faltar componente)", "split_alarm_query",
         _join_alarm, lambda p: ("split_alarm_query", {})),
    Spec("split_port_range", "tuple", "'p' ou 'p1-p2'", "{from_port, to_port}", "0<=p1<=p2<=65535", "OutOfDomain",
         "join_port_range", _split_ports, lambda p: ("join_port_range", {})),
    Spec("join_port_range", "tuple", "{from_port, to_port}", "'p' ou 'p1-p2'", "0<=p1<=p2<=65535", "OutOfDomain",
         "split_port_range", _join_ports, lambda p: ("split_port_range", {})),
    Spec("split_cidr", "tuple", "CIDR de rede (sem bits de host)", "{address, prefix_length}", "rede estrita",
         "OutOfDomain", "join_cidr", _split_cidr, lambda p: ("join_cidr", {})),
    Spec("join_cidr", "tuple", "{address, prefix_length}", "CIDR", "rede estrita", "OutOfDomain", "split_cidr",
         _join_cidr, lambda p: ("split_cidr", {})),
]}


def get(name: str) -> Spec:
    if name not in REGISTRY:
        raise TypeError_(f"função de tradução fora do núcleo: {name!r}")
    return REGISTRY[name]


def apply(fn: dict, v, ctx: dict | None = None):
    s = get(fn["name"])
    return s.apply(v, fn.get("params") or {}, ctx)


def apply_chain(chain: list[dict], v, ctx: dict | None = None):
    for fn in chain:
        v = apply(fn, v, ctx)
    return v


def chain_of(fn) -> list[dict]:
    """translation_fn é um item {name, params} ou uma lista (composição, aplicada da esquerda para a direita)."""
    if fn is None:
        return []
    return list(fn) if isinstance(fn, list) else [fn]


def inverse_chain(fn) -> list[dict] | None:
    out = []
    for item in reversed(chain_of(fn)):
        s = get(item["name"])
        if s.inv is None:
            return None
        r = s.inv(item.get("params") or {})
        if r is None:
            return None
        out.append({"name": r[0], "params": r[1]})
    return out


def image(fn, d):
    """Imagem de um domínio por uma cadeia escalar (AnyDomain quando não calculável)."""
    for item in chain_of(fn):
        s = get(item["name"])
        if s.image is None:
            return AnyDomain()
        d = s.image(d, item.get("params") or {})
    return d


def kind(fn) -> str:
    ch = chain_of(fn)
    return "tuple" if any(get(i["name"]).kind == "tuple" for i in ch) else "scalar"


def preserves_kind(fn, tin: ValueType, tout: ValueType) -> tuple[bool, str]:
    """Regra KIND-EQ (só para escalar): grandeza de entrada = grandeza de saída."""
    if kind(fn) == "tuple":
        return True, "combinador de tupla: tipos por componente"
    if tin.quantity_kind != tout.quantity_kind:
        return False, f"grandeza {tin.quantity_kind} -> {tout.quantity_kind}"
    return True, "mesma grandeza"


__all__ = ["REGISTRY", "Spec", "apply", "apply_chain", "chain_of", "inverse_chain", "image", "kind", "get",
           "preserves_kind", "jnum"]
