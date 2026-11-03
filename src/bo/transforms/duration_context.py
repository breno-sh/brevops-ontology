"""Gate: P1M -> segundos reprova sem contexto (python -I -m bo.transforms.duration_context).

  1. recusa: toda duração com meses ≠ 0 (P1M, P1Y, -P1M, P1MT1S, P2Y3M, P0Y1M) -> segundos é
     TRANSFORM_OUT_OF_DOMAIN sem contexto de calendário, por TODOS os caminhos do registro que levam a segundos
     (duration_to_number para cada unidade fixa, duration_to_seconds_text, unit_convert_time de unit:MO/unit:YR,
     compare_quantity_tolerance com unidade de mês, units.duration_seconds);
  2. controle: o que não tem mês converte sem contexto (PT1M é minuto, P0M1D tem 0 meses, P1DT1H, -PT30S);
  3. com contexto: âncora de data dá o número exato do calendário (31/01 + P1M = 28 dias, 31/03 + P1M = 30, ano
     bissexto), convenção declarada dá meses × seconds_per_month; contexto mal formado é DECLARATION_ERROR;
  4. varredura: nenhuma escalar do registro, com os parâmetros dos seus exemplos, transforma 'P1M' sem contexto num
     número de unidade de fator fixo (meses só saem como meses: duration_to_number to unit:MO dá 1);
  5. declaração: toda escalar com duração declara duration_calendar; with_context só com context_required ∋ calendar.
"""

from __future__ import annotations

import sys
from fractions import Fraction

from . import common as C
from . import comparators as CMP
from . import registry as R
from . import units as U
from .errors import TransformError

CALENDAR = ["P1M", "P1Y", "-P1M", "P1MT1S", "P2Y3M", "P0Y1M", "P1Y0M", "P12M"]
CONTROL = [("PT1M", 60), ("P0M1D", 86400), ("P1DT1H", 90000), ("-PT30S", -30), ("PT0.5S", Fraction(1, 2)),
           ("P0Y", 0)]
ANCHORED = [  # (âncora, duração, segundos esperados)
    ("2026-01-31T00:00:00-03:00", "P1M", 28 * 86400),
    ("2026-03-31T12:00:00-03:00", "P1M", 30 * 86400),
    ("2026-01-15T00:00:00-03:00", "P1M", 31 * 86400),
    ("2024-02-29T00:00:00-03:00", "P1Y", 365 * 86400),
    ("2028-01-01T00:00:00-03:00", "P1Y", 366 * 86400),
    ("2026-01-31T00:00:00-03:00", "P1MT1S", 28 * 86400 + 1),
    ("2026-03-01T00:00:00-03:00", "-P1M", -28 * 86400),
]
BAD_CONTEXT = [{"calendar": {"anchor": "2026-01-31"}}, {"calendar": {"anchor": "ontem"}},
               {"calendar": {"seconds_per_month": 0, "source": "zero"}},
               {"calendar": {"seconds_per_month": 2592000}},
               {"calendar": {"anchor": "2026-01-31T00:00:00-03:00", "seconds_per_month": 1, "source": "x"}},
               {"calendar": "gregoriano"}]


def _code(fn):
    try:
        fn()
        return None
    except TransformError as e:
        return e.code


def refusal_paths(d: str):
    fixed = [u for u in U.units_of(U.TIME) if U.UNITS[u].factor is not None]
    paths = [(f"duration_to_number to {u}", lambda u=u: R.apply_scalar("duration_to_number", d, {"to": u}))
             for u in fixed]
    paths.append(("duration_to_seconds_text", lambda: R.apply_scalar("duration_to_seconds_text", d)))
    paths.append(("units.duration_seconds", lambda: U.duration_seconds(d)))
    return paths


def main(argv=None) -> int:
    errs, n = [], 0
    # 1. recusa
    for d in CALENDAR:
        for what, fn in refusal_paths(d):
            n += 1
            c = _code(fn)
            if c != "TRANSFORM_OUT_OF_DOMAIN":
                errs.append(f"{d} por {what} sem contexto: {c or 'converteu'} (esperado TRANSFORM_OUT_OF_DOMAIN)")
    for u in ("unit:MO", "unit:YR"):
        for to in ("unit:SEC", "unit:DAY", "unit:WK"):
            n += 1
            c = _code(lambda: R.apply_scalar("unit_convert_time", 1, {"from": u, "to": to}))
            if c != "TRANSFORM_OUT_OF_DOMAIN":
                errs.append(f"1 {u} -> {to} sem contexto: {c or 'converteu'}")
        n += 1
        c = _code(lambda: CMP.compare({"name": "numeric_tolerance", "tolerance": 0}, 2592000, 1,
                                      expected_type={"unit": "unit:SEC"}, observed_type={"unit": u}))
        if c != "TRANSFORM_OUT_OF_DOMAIN":
            errs.append(f"compare_quantity_tolerance com {u} sem contexto: {c or 'comparou'}")
    # 2. controle
    for d, secs in CONTROL:
        n += 1
        try:
            got = R.apply_scalar("duration_to_number", d, {"to": "unit:SEC"})
            if U.frac(got) != U.frac(secs):
                errs.append(f"controle {d}: {got} s, esperado {secs}")
        except TransformError as e:
            errs.append(f"controle {d} recusado: {e}")
    # 3. com contexto
    for anchor, d, secs in ANCHORED:
        n += 1
        ctx = {"calendar": {"anchor": anchor}}
        try:
            got = R.apply_scalar("duration_to_number", d, {"to": "unit:SEC"}, ctx)
            if U.frac(got) != secs:
                errs.append(f"{anchor} + {d}: {got} s, esperado {secs}")
        except TransformError as e:
            errs.append(f"{anchor} + {d} recusado: {e}")
    n += 1
    conv = {"calendar": {"seconds_per_month": 2592000, "source": "convenção declarada de 30 dias"}}
    if R.apply_scalar("duration_to_number", "P2M", {"to": "unit:DAY"}, conv) != 60:
        errs.append("convenção de 30 dias: P2M ≠ 60 dias")
    for bad in BAD_CONTEXT:
        n += 1
        c = _code(lambda: R.apply_scalar("duration_to_number", "P1M", {"to": "unit:SEC"}, bad))
        if c != "DECLARATION_ERROR":
            errs.append(f"contexto mal formado {bad}: {c or 'aceito'}")
    # 4. varredura
    swept = 0
    for t in R.SCALARS:
        seen = []
        for ex in t.examples:
            if ex.err or ex.params in seen:
                continue
            seen.append(ex.params)
            tin = {"datatype": "duration", "quantity_kind": U.TIME}
            try:
                tout = R.type_out(t.name, ex.params, tin)
            except TransformError:
                continue
            swept += 1
            try:
                out = R.apply_scalar(t.name, "P1M", ex.params)
            except TransformError:
                continue
            unit = tout.get("unit")
            if tout.get("datatype") in ("number", "integer", "decimal") and unit in U.UNITS and U.UNITS[unit].factor:
                errs.append(f"{t.name} {ex.params}: P1M virou {out} {unit} sem contexto")
            if tout.get("datatype") == "string" and isinstance(out, str) and out.endswith("s"):
                errs.append(f"{t.name} {ex.params}: P1M virou {out!r} sem contexto")
            if tout.get("datatype") == "duration" and U.parse_duration(out).months != 1:
                errs.append(f"{t.name} {ex.params}: P1M virou {out!r} (meses não preservados)")
    if R.apply_scalar("duration_to_number", "P1M", {"to": "unit:MO"}) != 1:
        errs.append("P1M -> unit:MO deveria dar 1 sem contexto")
    if CMP.compare({"name": "duration_equal"}, "P1M", "P30D") is not False:
        errs.append("duration_equal: P1M = P30D sem contexto")
    # 5. declaração
    doc = C.load_yaml(C.transforms_yaml())
    for s in doc["scalar"]:
        dur = "duration" in (s["domain"]["datatype"], s["codomain"]["datatype"])
        if dur and s.get("duration_calendar") not in ("forbidden", "with_context"):
            errs.append(f"{s['name']}: duração sem duration_calendar")
        if s.get("duration_calendar") == "with_context" and "calendar" not in (s.get("context_required") or []):
            errs.append(f"{s['name']}: with_context sem context_required ∋ calendar")
    rep = C.report("duration_context", {"ok": not errs, "checks": n, "calendar_durations": CALENDAR,
                                        "swept_instances": swept, "errors": errs})
    if errs:
        for e in errs:
            print(f"REPROVADO: {e}", file=sys.stderr)
        return 1
    C.say(f"duration_context: {n} casos ({len(CALENDAR)} durações com mês/ano recusadas sem contexto por todos os "
          f"caminhos, {len(CONTROL)} controles, {len(ANCHORED)} âncoras exatas, {len(BAD_CONTEXT)} contextos mal "
          f"formados), {swept} instâncias varridas -> OK ({rep})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
