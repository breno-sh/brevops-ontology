"""Transporte de UM valor por uma alegação, numa direção (o que se transporta), com o traço do C23.

Implementa a tabela da §1.5 do plano com a direção SKOS correta:
  exact   A->B e B->A com a normalização declarada (B->A pela inversa parcial)
  close   A->B se a função parcial está definida no valor, perda registrada; B->A só com inversa parcial
  broad   (a ⊂ b) A->B por inclusão; B->A só onde o predicado de pertença a 'a' é verdadeiro
  narrow  (b ⊂ a) A->B só onde o predicado de pertença a 'b' é verdadeiro; B->A por inclusão
  related nunca transporta (RELATED_ONLY)
  guarda  verdadeira: segue; falsa: CONDITION_FALSE; indeterminada: CONDITION_INDETERMINATE (vai para o
          intervalo entre os limites inferior e superior)
  fixed/default (lado objeto sem atributo): só com valor, contexto e evidência datados, e se o valor coincide
  UNPROVEN / REFUTED_BY_RULE: não transporta
Resultado: carried (com fidelidade e perdas), omitted (origem sabidamente sem valor, destino opcional) ou
blocked (com código C23). Nenhum valor padrão é inventado (UNKNOWN_INPUT).
"""

from __future__ import annotations

import math
from fractions import Fraction

from . import guards as G
from . import predicates as P
from . import transforms as T
from .claims import Claim, invert
from .obligations import assess
from .valuetypes import NumDomain, OutOfDomain, TypeError_, frac, _is_num
from .vocab import ABSENT, NOT_READ, SYMBOLIC, is_marker

CODE_RULE = {"RELATED_ONLY": "T-RELATED", "UNPROVEN": "T-UNPROVEN", "REFUTED_BY_RULE": "T-UNPROVEN",
             "CONDITION_FALSE": "T-GUARD", "CONDITION_INDETERMINATE": "T-GUARD", "UNKNOWN_INPUT": "T-ABSENCE",
             "UNKNOWN_SYMBOLIC_INPUT": "T-SYMBOLIC", "OUT_OF_SUBSET": "T-SUBSET",
             "TRANSFORM_OUT_OF_DOMAIN": "T-DOMAIN"}


def _out(claim, direction, result, **kw):
    o = {"claim_id": claim.id, "direction": direction, "result": result}
    o.update(kw)
    return o


def transport(claim: Claim | dict, value, ctx: dict | None = None, direction: str = "forward",
              disabled=frozenset()) -> dict:
    c = claim if isinstance(claim, Claim) else Claim(claim)
    dis = frozenset(disabled)
    ctx = ctx or {}
    if c["basis"] == "composition" and isinstance(c["derivation"], list):
        from .composition import run_leg        # alegação composta: refeita das pernas e transportada perna a perna
        return run_leg(c, value, ctx, direction)
    if direction == "inverse":
        c = invert(c)
        if c["inverse_missing"] and "T-INVERSE" not in dis:
            return _out(c, direction, "blocked", code="UNPROVEN", rule="T-INVERSE",
                        detail="sem inversa parcial: a direção contrária não transporta")
    elif direction != "forward":
        raise ValueError(direction)

    if c.relation == "related" and "T-RELATED" not in dis:
        return _out(c, direction, "blocked", code="RELATED_ONLY", rule="T-RELATED",
                    detail="related não habilita transporte")
    a = assess(c)
    if a.verdict != "OK" and "T-UNPROVEN" not in dis:
        code = "REFUTED_BY_RULE" if a.verdict == "REFUTED_BY_RULE" else "UNPROVEN"
        return _out(c, direction, "blocked", code=code, rule="T-UNPROVEN", verdict=a.verdict, failed=a.rules,
                    detail="alegação sem prova não transporta" if code == "UNPROVEN" else "alegação refutada")

    # a guarda decide se a alegação vale neste contexto: vem antes de olhar o valor
    gv, gt = G.evaluate(c.guard, ctx)
    if gv != G.TRUE and "T-GUARD" not in dis:
        code = "CONDITION_FALSE" if gv == G.FALSE else "CONDITION_INDETERMINATE"
        return _out(c, direction, "blocked", code=code, rule="T-GUARD", guard=gv, terms=gt,
                    detail="guarda falsa" if gv == G.FALSE else "guarda indeterminada: termo não lido; vai ao intervalo")

    ts, to = c.subject_value_type, c.object_value_type
    required = bool((c["object_value_type"] or {}).get("required"))
    if is_marker(value, SYMBOLIC) and "T-SYMBOLIC" not in dis:
        return _out(c, direction, "blocked", code="UNKNOWN_SYMBOLIC_INPUT", rule="T-SYMBOLIC",
                    detail="valor simbólico (conhecido só depois da criação ou referência não resolvida)")
    if is_marker(value, NOT_READ) and "T-ABSENCE" not in dis:
        return _out(c, direction, "blocked", code="UNKNOWN_INPUT", rule="T-ABSENCE",
                    detail="valor de origem não lido")
    if (value is None or is_marker(value, ABSENT)) and "T-ABSENCE" not in dis:
        if required:
            return _out(c, direction, "blocked", code="UNKNOWN_INPUT", rule="T-ABSENCE",
                        detail="obrigatório no destino sem valor na origem; nenhum padrão é inventado")
        return _out(c, direction, "omitted", detail="origem sem valor e destino opcional: nada a emitir")

    if ts is not None and not ts.admits(value) and "T-DOMAIN" not in dis:
        return _out(c, direction, "blocked", code="TRANSFORM_OUT_OF_DOMAIN", rule="T-DOMAIN",
                    detail=f"valor {value!r} fora do tipo de origem")

    losses = []
    # sentinelas: mapeadas pela tabela declarada, nunca pela aritmética
    if ts is not None and ts.is_sentinel(value) and "T-SENTINEL" not in dis:
        smap = {}
        for x in c.loss("sentinel"):
            smap.update({str(k): v for k, v in (x.get("map") or {}).items()})
        k = next(k for k, _ in ts.sentinels if P._eq(value, k))
        if smap.get(k) is None:
            return _out(c, direction, "blocked", code="TRANSFORM_OUT_OF_DOMAIN", rule="T-SENTINEL",
                        losses=[{"kind": "sentinel", "value": value, "meaning": ts.sentinel_meaning(value)}],
                        detail="sentinela sem equivalente no destino: perda declarada, nada emitido")
        return _out(c, direction, "carried", value=smap[k], fidelity="lossless", losses=[],
                    detail=f"sentinela {value!r} ({ts.sentinel_meaning(value)}) -> {smap[k]!r}")

    # broad/narrow em direção ao subconjunto: só valores com pertença verdadeira
    mp = c["membership_predicate"]
    if c.relation == "narrow" and mp and "T-SUBSET" not in dis:
        if not P.evaluate(mp["expr"], value):
            return _out(c, direction, "blocked", code="OUT_OF_SUBSET", rule="T-SUBSET",
                        detail="valor fora do subconjunto (predicado de pertença falso)")

    ne = [x for x in c.loss("not_expressible") if any(P._eq(value, v) for v in x.get("values", []))]
    if ne:
        return _out(c, direction, "blocked", code="OUT_OF_SUBSET", rule="T-SUBSET",
                    losses=[{"kind": "not_expressible", "value": value, "why": ne[0].get("why", "")}],
                    detail="valor não exprimível no destino: bloqueio com perda declarada")

    try:
        y = T.apply_chain(c.fn, value, ctx) if c.fn else value
    except OutOfDomain as e:
        if "T-DOMAIN" not in dis:
            return _out(c, direction, "blocked", code="TRANSFORM_OUT_OF_DOMAIN", rule="T-DOMAIN", detail=str(e))
        y = value
    except TypeError_ as e:
        return _out(c, direction, "blocked", code="TRANSFORM_OUT_OF_DOMAIN", rule="T-DOMAIN", detail=str(e))

    if to is not None and _is_num(y) and to.datatype in ("integer", "decimal"):
        dom = to.domain()
        step = frac(to.step) if to.step else None
        if step is not None and (frac(y) - (dom.base if isinstance(dom, NumDomain) else 0)) % step != 0 \
                and "T-ROUNDING" not in dis:
            rnd = c.loss("rounding")
            if not rnd:
                return _out(c, direction, "blocked", code="TRANSFORM_OUT_OF_DOMAIN", rule="T-ROUNDING",
                            detail=f"{y} não é representável no destino (passo {step}) e não há arredondamento declarado")
            y2 = _round(frac(y), frac(rnd[0].get("granularity", to.step)), rnd[0].get("mode", "half_even"))
            losses.append({"kind": "rounding", "from": _j(y), "to": _j(y2)})
            y = y2
        lo, hi = (to.range or (None, None))
        if ((lo is not None and frac(y) < lo) or (hi is not None and frac(y) > hi)) and "T-SATURATION" not in dis:
            sat = c.loss("saturation")
            if not sat:
                return _out(c, direction, "blocked", code="TRANSFORM_OUT_OF_DOMAIN", rule="T-SATURATION",
                            detail=f"{_j(y)} fora da faixa do destino e sem saturação declarada")
            y2 = max(lo, frac(y)) if lo is not None and frac(y) < lo else min(hi, frac(y))
            losses.append({"kind": "saturation", "from": _j(y), "to": _j(y2)})
            y = y2
        y = _j(y)
    elif to is not None and not c["fixed_default"] and not to.admits(y) and "T-DOMAIN" not in dis:
        return _out(c, direction, "blocked", code="TRANSFORM_OUT_OF_DOMAIN", rule="T-DOMAIN",
                    detail=f"{y!r} fora do tipo do destino")

    fd = c["fixed_default"]
    if fd and "T-FIXED" not in dis:
        if not P._eq(y, fd["value"]):
            return _out(c, direction, "blocked", code="OUT_OF_SUBSET", rule="T-FIXED",
                        detail=f"destino só tem o valor {fd['kind']} {fd['value']!r}; origem dá {y!r}")
        return _out(c, direction, "carried", value=y, fidelity="lossless", losses=[], emitted=False,
                    origin="ProviderDefault" if fd["kind"] == "default" else "Fixed",
                    detail=f"satisfeito pelo comportamento {fd['kind']} do destino (evidência {fd['evidence']['date']})")

    for x in c.loss("semantic"):
        vals = x.get("values")
        if vals is None or any(P._eq(value, v) for v in vals):
            losses.append({"kind": "semantic", "what": x.get("what", "")})
    return _out(c, direction, "carried", value=y, fidelity="declared_loss" if losses else "lossless", losses=losses)


def _round(x: Fraction, g: Fraction, mode: str) -> Fraction:
    q = x / g
    if mode == "floor":
        n = math.floor(q)
    elif mode == "ceil":
        n = math.ceil(q)
    else:
        n = round(q)   # Fraction.__round__ é half-even
    return n * g


def _j(x):
    x = frac(x)
    return int(x) if x.denominator == 1 else x


def check_trace(row: dict, disabled=frozenset()) -> dict:
    """Confere uma linha de traço afirmada {claim, value, context, direction, asserted} contra a semântica.
    Rejeita (accepted=False) quando o resultado afirmado diverge do recalculado; cita a regra do recalculado."""
    got = transport(row["claim"], row.get("value"), row.get("context"), row.get("direction", "forward"), disabled)
    asserted = row["asserted"]
    keys = [k for k in ("result", "code", "value", "fidelity") if k in asserted]
    same = all(_eqv(got.get(k), asserted[k]) for k in keys)
    if "loss_kinds" in asserted:
        same = same and sorted(x["kind"] for x in got.get("losses", [])) == sorted(asserted["loss_kinds"])
    rule = got.get("rule") or ({"declared_loss": _loss_rule(got)}.get(got.get("fidelity")) if got["result"] == "carried" else None)
    return {"accepted": same, "recomputed": _jsonable(got), "asserted": asserted, "rule": rule}


def _loss_rule(got):
    kinds = {x["kind"] for x in got.get("losses", [])}
    return "T-SATURATION" if "saturation" in kinds else "T-ROUNDING" if "rounding" in kinds else "CLOSE-LOSS"


def _eqv(a, b):
    if isinstance(a, Fraction) or isinstance(b, Fraction):
        try:
            return frac(a) == frac(b)
        except Exception:
            return False
    return a == b or P._eq(a, b) if not isinstance(a, dict) else a == b


def _jsonable(o):
    if isinstance(o, dict):
        return {k: _jsonable(v) for k, v in o.items()}
    if isinstance(o, list):
        return [_jsonable(v) for v in o]
    if isinstance(o, Fraction):
        return T.jnum(o)
    return o
