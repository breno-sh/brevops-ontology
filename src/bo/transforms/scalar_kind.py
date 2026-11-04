"""Gate: transformação escalar não muda grandeza; combinador de tupla declara tipos estruturados
(python -I -m bo.transforms.scalar_kind).

  1. estático (transforms.yaml publicado): toda escalar tem grandeza de entrada = de saída e nenhuma porta tupla;
     todo combinador tem portas nomeadas (únicas), tipadas, e é estrutural de fato: n ≠ 1 ou m ≠ 1, ou uma
     porta do tipo tuple;
  2. por instância: cada exemplo positivo de escalar é tipado (bo.transforms.registry.type_out) e a grandeza de
     saída é a de entrada; cada exemplo positivo de combinador produz, em cada porta, um valor do datatype declarado;
  3. adversarial: tentativas de mudar grandeza por escalar são recusadas (DECLARATION_ERROR), e um transforms.yaml
     mutado (escalar que muda grandeza; escalar com tupla) é reprovado pelo validador do C10.
"""

from __future__ import annotations

import subprocess
import sys
from fractions import Fraction

import yaml

from . import common as C
from . import registry as R
from . import units as U
from .errors import DeclarationError, TransformError


def static_checks(doc: dict) -> list[str]:
    errs = []
    for s in doc.get("scalar") or []:
        if s["domain"]["quantity_kind"] != s["codomain"]["quantity_kind"]:
            errs.append(f"escalar {s['name']}: {s['domain']['quantity_kind']} -> {s['codomain']['quantity_kind']}")
        if "tuple" in (s["domain"]["datatype"], s["codomain"]["datatype"]):
            errs.append(f"escalar {s['name']}: porta tupla (é combinador)")
    for c in doc.get("combinators") or []:
        for side in ("inputs", "outputs"):
            names = [p["name"] for p in c[side]]
            if len(set(names)) != len(names):
                errs.append(f"combinador {c['name']}: {side} com nome repetido")
            if any(p["datatype"] not in R.DATATYPES for p in c[side]):
                errs.append(f"combinador {c['name']}: {side} com datatype inválido")
        structural = (len(c["inputs"]), len(c["outputs"])) != (1, 1) or any(
            p["datatype"] == "tuple" for p in c["inputs"] + c["outputs"])
        if not structural:
            errs.append(f"combinador {c['name']}: 1 -> 1 sem porta tupla (seria escalar)")
    return errs


def _tin(t: R.Scalar, ex: R.Ex) -> dict:
    tin = {"datatype": t.domain["datatype"], "quantity_kind": t.domain["quantity_kind"]}
    p = ex.params or {}
    if "from" in p:
        tin["unit"] = p["from"]
    elif t.domain["datatype"] in ("number", "integer", "decimal") and t.domain["quantity_kind"] in U.KINDS.values():
        tin["unit"] = {U.TIME: "unit:SEC", U.INFO: "unit:BYTE", U.COUNT: "unit:NUM", U.RATIO: "unit:FRACTION"}[
            t.domain["quantity_kind"]]
    if "from_window" in p:
        tin["rate_window"] = p["from_window"]
    return tin


def _runtime_ok(dt: str, v) -> bool:
    if dt == "any":
        return True
    if dt == "integer":
        return isinstance(v, int) and not isinstance(v, bool)
    if dt in ("number", "decimal"):
        return isinstance(v, (int, Fraction)) and not isinstance(v, bool)
    if dt == "boolean":
        return isinstance(v, bool)
    if dt in ("string", "enum"):
        return isinstance(v, str)
    if dt == "duration":
        try:
            U.parse_duration(v)
            return True
        except TransformError:
            return False
    if dt == "tuple":
        return isinstance(v, (dict, list))
    return False


def instance_checks() -> tuple[list[str], int, int]:
    errs, n_s, n_c = [], 0, 0
    for t in R.SCALARS:
        for i, ex in enumerate(t.examples):
            if ex.err is not None:
                continue
            tin = _tin(t, ex)
            try:
                tout = R.type_out(t.name, ex.params, tin)
            except TransformError as e:
                errs.append(f"{t.name}[{i}]: exemplo positivo não tipa: {e}")
                continue
            n_s += 1
            if tout.get("quantity_kind") != tin["quantity_kind"]:
                errs.append(f"{t.name}[{i}]: grandeza {tin['quantity_kind']} -> {tout.get('quantity_kind')}")
            if tout.get("datatype") not in (t.codomain["datatype"], "number") and t.codomain["datatype"] != "any":
                errs.append(f"{t.name}[{i}]: datatype de saída {tout.get('datatype')} ≠ codomínio {t.codomain['datatype']}")
    for c in R.COMBINATORS:
        for i, ex in enumerate(c.examples):
            if ex.err is not None:
                continue
            out = R.apply_combinator(c.name, ex.value, ex.ctx)
            n_c += 1
            for name, dt, _ in c.outputs:
                if not _runtime_ok(dt, out[name]):
                    errs.append(f"{c.name}[{i}]: porta {name} = {out[name]!r} não é {dt}")
            for name, dt, _ in c.inputs:
                if name in ex.value and not _runtime_ok(dt, ex.value[name]) and not isinstance(ex.value[name], dict):
                    if not (dt in ("number",) and isinstance(ex.value[name], str)):
                        errs.append(f"{c.name}[{i}]: entrada {name} = {ex.value[name]!r} não é {dt}")
    return errs, n_s, n_c


ADVERSARIAL = [
    ("tempo -> informação", "unit_convert_time", {"from": "unit:SEC", "to": "unit:BYTE"},
     {"datatype": "number", "quantity_kind": U.TIME, "unit": "unit:SEC"}),
    ("informação -> tempo", "unit_convert_information", {"from": "unit:GibiBYTE", "to": "unit:SEC"},
     {"datatype": "number", "quantity_kind": U.INFO, "unit": "unit:GibiBYTE"}),
    ("razão -> contagem", "unit_convert_ratio", {"from": "unit:PERCENT", "to": "unit:NUM"},
     {"datatype": "number", "quantity_kind": U.RATIO, "unit": "unit:PERCENT"}),
    ("arredondar informação com a função de tempo", "round_time", {"mode": "floor"},
     {"datatype": "number", "quantity_kind": U.INFO, "unit": "unit:BYTE"}),
    ("saturar contagem com a função de razão", "clamp_ratio", {"max": 1},
     {"datatype": "number", "quantity_kind": U.COUNT, "unit": "unit:NUM"}),
    ("janela de taxa sobre quantidade sem janela", "rate_window_convert_count",
     {"from_window": "PT1M", "to_window": "PT1S", "statistic": "sum"},
     {"datatype": "number", "quantity_kind": U.COUNT, "unit": "unit:NUM"}),
    ("janela declarada diferente da do valor", "rate_window_convert_count",
     {"from_window": "PT5M", "to_window": "PT1S", "statistic": "sum"},
     {"datatype": "number", "quantity_kind": U.COUNT, "unit": "unit:NUM", "rate_window": "PT1M"}),
    ("duração -> bytes", "duration_to_number", {"to": "unit:BYTE"},
     {"datatype": "duration", "quantity_kind": U.TIME}),
    ("unidade de entrada ≠ from", "unit_convert_time", {"from": "unit:HR", "to": "unit:SEC"},
     {"datatype": "number", "quantity_kind": U.TIME, "unit": "unit:MIN"}),
    ("combinador usado como escalar", "split_cidr", {}, {"datatype": "string", "quantity_kind": U.NOT_APPLICABLE}),
]

CHAIN_ADVERSARIAL = [
    ("cadeia termina em outra grandeza", [{"name": "unit_convert_time", "params": {"from": "unit:HR", "to": "unit:MIN"}}],
     {"datatype": "number", "quantity_kind": U.TIME, "unit": "unit:HR"},
     {"datatype": "number", "quantity_kind": U.INFO, "unit": "unit:BYTE"}),
    ("GB declarado onde o valor é GiB", [{"name": "unit_convert_information",
                                          "params": {"from": "unit:GibiBYTE", "to": "unit:MebiBYTE"}}],
     {"datatype": "number", "quantity_kind": U.INFO, "unit": "unit:GibiBYTE"},
     {"datatype": "number", "quantity_kind": U.INFO, "unit": "unit:MegaBYTE"}),
    ("janela PT1M declarada onde a cadeia dá PT1S", [{"name": "rate_window_convert_count",
                                                      "params": {"from_window": "PT5M", "to_window": "PT1S",
                                                                 "statistic": "sum"}}],
     {"datatype": "number", "quantity_kind": U.COUNT, "unit": "unit:NUM", "rate_window": "PT5M"},
     {"datatype": "number", "quantity_kind": U.COUNT, "unit": "unit:NUM", "rate_window": "PT1M"}),
]

CHAIN_OK = [
    ("PT5M -> PT1M de contagem", [{"name": "rate_window_convert_count",
                                   "params": {"from_window": "PT5M", "to_window": "PT60S", "statistic": "sum"}}],
     {"datatype": "number", "quantity_kind": U.COUNT, "unit": "unit:NUM", "rate_window": "PT5M"},
     {"datatype": "number", "quantity_kind": U.COUNT, "unit": "unit:NUM", "rate_window": "PT1M"}),
    ("GiB -> GB -> inteiro", [{"name": "unit_convert_information", "params": {"from": "unit:GibiBYTE",
                                                                             "to": "unit:GigaBYTE"}},
                              {"name": "round_information", "params": {"mode": "ceiling"}}],
     {"datatype": "number", "quantity_kind": U.INFO, "unit": "unit:GibiBYTE"},
     {"datatype": "integer", "quantity_kind": U.INFO, "unit": "unit:GigaBYTE"}),
]


def adversarial_checks() -> list[str]:
    errs = []
    for why, name, p, tin in ADVERSARIAL:
        try:
            R.type_out(name, p, tin)
            errs.append(f"adversarial aceito: {why} ({name})")
        except DeclarationError:
            pass
    for why, chain, tin, tout in CHAIN_ADVERSARIAL:
        try:
            R.check_chain(chain, tin, tout)
            errs.append(f"cadeia adversarial aceita: {why}")
        except DeclarationError:
            pass
    # coleção (emenda 1.2.0): elemento a elemento herda a regra da escalar
    gib = {"datatype": "number", "quantity_kind": U.INFO, "unit": "unit:GibiBYTE"}
    for nm, src in (("map_list", "list"), ("map_set", "set")):
        try:
            R.collection_type_out(nm, {"datatype": src, "item_type": gib}, "unit_convert_time",
                                  {"from": "unit:SEC", "to": "unit:MIN"})
            errs.append(f"coleção adversarial aceita: {nm} com escalar de outra grandeza")
        except DeclarationError:
            pass
    for why, chain, tin, tout in CHAIN_OK:
        try:
            R.check_chain(chain, tin, tout)
        except DeclarationError as e:
            errs.append(f"cadeia correta recusada: {why}: {e}")
    return errs


def mutation_checks(doc: dict) -> list[str]:
    import copy
    errs = []
    muts = []
    m1 = copy.deepcopy(doc)
    tgt = next(s for s in m1["scalar"] if s["name"] == "unit_convert_time")
    tgt["codomain"]["quantity_kind"] = U.INFO
    muts.append(("escalar que muda grandeza", m1))
    m2 = copy.deepcopy(doc)
    tgt = next(s for s in m2["scalar"] if s["name"] == "identity")
    tgt["codomain"]["datatype"] = "tuple"
    muts.append(("escalar com tupla", m2))
    m3 = copy.deepcopy(doc)
    tgt = next(s for s in m3["scalar"] if s["name"] == "duration_to_number")
    tgt["context_required"] = []
    muts.append(("mês/ano com contexto sem context_required ∋ calendar", m3))
    for k, (why, m) in enumerate(muts):
        p = C.tmp() / f"mutacao_{k}.transforms.yaml"
        p.write_text(yaml.safe_dump(m, sort_keys=False, allow_unicode=True), encoding="utf-8")
        r = subprocess.run([sys.executable, "-I", "-m", "bo.contracts.validate", "transforms", str(p)],
                           capture_output=True, text=True)
        if r.returncode == 0:
            errs.append(f"validador do C10 aceitou a mutação: {why}")
        p.unlink()
    return errs


def main(argv=None) -> int:
    doc = C.load_yaml(C.transforms_yaml())
    s_errs = static_checks(doc)
    i_errs, n_s, n_c = instance_checks()
    a_errs = adversarial_checks()
    m_errs = mutation_checks(doc)
    errs = s_errs + i_errs + a_errs + m_errs
    rep = C.report("scalar_kind", {
        "ok": not errs, "scalar": len(doc["scalar"]), "combinators": len(doc["combinators"]),
        "typed_scalar_examples": n_s, "typed_combinator_examples": n_c,
        "adversarial_rejected": len(ADVERSARIAL) + len(CHAIN_ADVERSARIAL) - len(a_errs),
        "adversarial_total": len(ADVERSARIAL) + len(CHAIN_ADVERSARIAL), "chains_ok": len(CHAIN_OK),
        "mutations": 3, "errors": errs})
    if errs:
        for e in errs:
            print(f"REPROVADO: {e}", file=sys.stderr)
        return 1
    C.say(f"scalar_kind: {len(doc['scalar'])} escalares com grandeza preservada, {len(doc['combinators'])} combinadores "
          f"estruturais; {n_s} instâncias escalares tipadas, {n_c} saídas de combinador no tipo declarado; "
          f"{len(ADVERSARIAL) + len(CHAIN_ADVERSARIAL)} tentativas de mudar grandeza recusadas; 3 mutações reprovadas "
          f"pelo validador -> OK ({rep})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
