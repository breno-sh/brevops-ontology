"""Projeções por ocorrência, realizações alternativas e grupos como regras sobre subgrafos (F3).

A injetividade da v2 ('um caminho serve a uma propriedade só') sai. Entra:
  projeção    {projection_id, field, occurrence{scope, key_fields}, extractor{name, component}, concept, type,
               overlaps[], tests[]}: cada uso de um campo declara a sua parte; um campo pode alimentar vários
               conceitos (a consulta de um alarme -> métrica, operador, limiar...).
  P-OCC       campo dentro de bloco repetido exige chave de ocorrência (campos de identidade, nunca a posição).
  P-EXEC      o extrator roda nos testes e a saída respeita o tipo declarado.
  P-OVERLAP   duas projeções do mesmo campo e ocorrência que leem a mesma parte têm de declarar a sobreposição.
  A-EXCL      várias realizações do mesmo alvo: exclusividade só com interseção das guardas UNSAT; senão AMBIGUOUS.
  grupo       {bo_group_id, cardinality, variables[{name, side, field, occurrence}], occurrence_vars[], joins[],
               steps[{name, params?, inputs{arg: ?var}, outputs{comp: ?var}}]}
  G-VARS      variáveis nomeadas, únicas, ligadas; argumentos nomeados; nenhuma variável solta.
  G-ARITY     argumentos do combinador = assinatura dele; cardinalidade declarada = contagem de variáveis.
  G-OCC       as entradas de um passo vêm da mesma ocorrência, ou de ocorrências ligadas por junção declarada.
"""

from __future__ import annotations

import re

from . import guards as G
from . import transforms as T
from .valuetypes import OutOfDomain, TypeError_, ValueType

SIGNATURES = {
    "split_alarm_query": (("query",), ("metric", "window", "statistic", "operator", "threshold")),
    "join_alarm_query": (("metric", "window", "statistic", "operator", "threshold"), ("query",)),
    "split_port_range": (("ports",), ("from_port", "to_port")),
    "join_port_range": (("from_port", "to_port"), ("ports",)),
    "split_cidr": (("cidr",), ("address", "prefix_length")),
    "join_cidr": (("address", "prefix_length"), ("cidr",)),
    "identity": (("value",), ("value",)),
    "unit_convert": (("value",), ("value",)),
    "enum_map": (("value",), ("value",)),
    "scale": (("value",), ("value",)),
}
_VAR = re.compile(r"^\?[a-z][a-z0-9_]*$")


def _f(rule, outcome, detail):
    return {"rule": rule, "outcome": outcome, "detail": detail}


# ------------------------------------------------------------------------------------------------ projeções
def _parts(p) -> set:
    ex = p.get("extractor") or {}
    comp = ex.get("component")
    if comp is None:
        sig = SIGNATURES.get(ex.get("name"), ((), ("*",)))
        return set(sig[1]) if ex.get("name") in SIGNATURES and ex.get("name") != "identity" else {"*"}
    return {comp}


def check_projections(projs: list[dict], fields: dict | None = None, disabled=frozenset()) -> dict:
    """fields: {campo: {"repeated": bool}} (do C01: bloco aninhado repetido). Veredito por projeção."""
    dis = frozenset(disabled)
    fields = fields or {}
    fails = []
    for p in projs:
        pid = p.get("projection_id")
        occ = p.get("occurrence") or {}
        if fields.get(p.get("field"), {}).get("repeated") and "P-OCC" not in dis:
            if occ.get("scope") != "block" or not occ.get("key_fields"):
                fails.append({**_f("P-OCC", "REFUTED_BY_RULE",
                                   f"{pid}: campo em bloco repetido sem chave de ocorrência"), "projection_id": pid})
            elif any(k in ("index", "position", "ordinal") for k in occ["key_fields"]):
                fails.append({**_f("P-OCC", "REFUTED_BY_RULE",
                                   f"{pid}: chave de ocorrência pela posição textual"), "projection_id": pid})
        ex = p.get("extractor") or {}
        tests = p.get("tests") or []
        if "P-EXEC" not in dis:
            if not tests:
                fails.append({**_f("P-EXEC", "UNPROVEN", f"{pid}: projeção sem testes"), "projection_id": pid})
            try:
                ty = ValueType.from_dict(p["type"])
            except (KeyError, TypeError_, ValueError) as e:
                fails.append({**_f("P-EXEC", "REFUTED_BY_RULE", f"{pid}: tipo inválido: {e}"), "projection_id": pid})
                ty = None
            for t in tests:
                try:
                    out = T.apply({"name": ex["name"], "params": ex.get("params")}, t["input"])
                    if ex.get("component"):
                        out = out[ex["component"]]
                except (OutOfDomain, TypeError_, KeyError) as e:
                    fails.append({**_f("P-EXEC", "REFUTED_BY_RULE", f"{pid}: extrator falha em {t['input']!r}: {e}"),
                                  "projection_id": pid})
                    continue
                if out != t["expected"] or (ty is not None and not ty.admits(out)):
                    fails.append({**_f("P-EXEC", "REFUTED_BY_RULE",
                                       f"{pid}: {t['input']!r} -> {out!r} (esperado {t['expected']!r}, tipo {p.get('type')})"),
                                  "projection_id": pid})
    if "P-OVERLAP" not in dis:
        for i, a in enumerate(projs):
            for b in projs[i + 1:]:
                if a.get("field") != b.get("field") or _occ_key(a) != _occ_key(b):
                    continue
                inter = _parts(a) & _parts(b)
                if "*" in _parts(a) or "*" in _parts(b):
                    inter = inter or {"*"}
                if inter:
                    declared = b.get("projection_id") in (a.get("overlaps") or []) or \
                        a.get("projection_id") in (b.get("overlaps") or [])
                    if not declared:
                        fails.append({**_f("P-OVERLAP", "REFUTED_BY_RULE",
                                           f"{a.get('projection_id')} e {b.get('projection_id')} leem {sorted(inter)} "
                                           f"de {a.get('field')} sem sobreposição declarada"),
                                      "projection_id": a.get("projection_id")})
    verdict = ("REFUTED_BY_RULE" if any(x["outcome"] == "REFUTED_BY_RULE" for x in fails)
               else "UNPROVEN" if fails else "OK")
    return {"verdict": verdict, "failures": fails, "n": len(projs)}


def _occ_key(p):
    o = p.get("occurrence") or {}
    return (o.get("scope", "resource"), tuple(o.get("key_fields") or ()))


def project_value(projs: list[dict], field: str, value) -> dict:
    """Aplica todas as projeções de um campo a um valor: {conceito: parte}. Um campo, vários conceitos."""
    out = {}
    for p in projs:
        if p.get("field") != field:
            continue
        ex = p["extractor"]
        v = T.apply({"name": ex["name"], "params": ex.get("params")}, value)
        out[p["concept"]] = v[ex["component"]] if ex.get("component") else v
    return out


# --------------------------------------------------------------------------------------- alternativas (A-EXCL)
def check_alternatives(reals: list[dict], disabled=frozenset()) -> dict:
    """reals: realizações do mesmo alvo e provedor, cada uma com guard e (opcional) exclusivity declarada."""
    pairs, ambiguous = [], False
    for i, a in enumerate(reals):
        for b in reals[i + 1:]:
            try:
                sat, info = G.satisfiable(G.conj(a.get("guard") or G.empty(), b.get("guard") or G.empty()))
            except G.GuardTypeError as e:
                sat, info = G.UNKNOWN, {"type_error": str(e)}
            pairs.append({"a": a.get("realization_id"), "b": b.get("realization_id"), "intersection": sat})
            if sat != G.UNSAT:
                ambiguous = True
    computed = "Ambiguous" if ambiguous else "ProvenExclusive"
    fails = []
    if "A-EXCL" not in disabled:
        for r in reals:
            d = r.get("exclusivity")
            if d == "ProvenExclusive" and computed != "ProvenExclusive":
                fails.append(_f("A-EXCL", "REFUTED_BY_RULE",
                                f"{r.get('realization_id')}: exclusividade declarada, mas as guardas se cruzam"))
    verdict = "REFUTED_BY_RULE" if fails else ("AMBIGUOUS" if ambiguous else "OK")
    return {"verdict": verdict, "exclusivity": computed, "pairs": pairs, "failures": fails}


# --------------------------------------------------------------------------------------------------- grupos
def check_group(g: dict, disabled=frozenset()) -> dict:
    dis = frozenset(disabled)
    fails = []
    vars_ = g.get("variables") or []
    names = [v.get("name") for v in vars_]
    byname = {v.get("name"): v for v in vars_}
    occs = set(g.get("occurrence_vars") or [])
    if "G-VARS" not in dis:
        dup = sorted({n for n in names if names.count(n) > 1})
        if dup:
            fails.append(_f("G-VARS", "REFUTED_BY_RULE", f"variável duplicada: {dup}"))
        for v in vars_:
            if not isinstance(v.get("name"), str) or not _VAR.match(v["name"]):
                fails.append(_f("G-VARS", "REFUTED_BY_RULE", f"variável sem nome válido (?nome): {v}"))
            if v.get("side") not in ("subject", "object") or not v.get("field"):
                fails.append(_f("G-VARS", "REFUTED_BY_RULE", f"{v.get('name')}: lado e campo obrigatórios"))
            if v.get("occurrence") not in occs:
                fails.append(_f("G-VARS", "REFUTED_BY_RULE", f"{v.get('name')}: ocorrência {v.get('occurrence')!r} não declarada"))
    used = set()
    for s in g.get("steps") or []:
        for kind in ("inputs", "outputs"):
            m = s.get(kind)
            if not isinstance(m, dict) or not m:
                if "G-VARS" not in dis:
                    fails.append(_f("G-VARS", "REFUTED_BY_RULE", f"passo {s.get('name')}: {kind} sem argumentos nomeados"))
                continue
            for arg, var in m.items():
                used.add(var)
                if var not in byname and "G-VARS" not in dis:
                    fails.append(_f("G-VARS", "REFUTED_BY_RULE", f"passo {s.get('name')}: {arg} -> {var} não ligada"))
                elif kind == "outputs" and byname[var].get("side") != "object" and "G-VARS" not in dis:
                    fails.append(_f("G-VARS", "REFUTED_BY_RULE",
                                    f"passo {s.get('name')}: saída {arg} escreve na variável de origem {var}"))
        sig = SIGNATURES.get(s.get("name"))
        if "G-ARITY" not in dis:
            if sig is None:
                fails.append(_f("G-ARITY", "REFUTED_BY_RULE", f"combinador sem assinatura: {s.get('name')}"))
            else:
                if set(s.get("inputs") or {}) != set(sig[0]) or set(s.get("outputs") or {}) != set(sig[1]):
                    fails.append(_f("G-ARITY", "REFUTED_BY_RULE",
                                    f"{s['name']}: argumentos {sorted(s.get('inputs') or {})}->{sorted(s.get('outputs') or {})}"
                                    f" != assinatura {list(sig[0])}->{list(sig[1])}"))
        if "G-OCC" not in dis:
            ins = [byname[v]["occurrence"] for v in (s.get("inputs") or {}).values() if v in byname]
            if len(set(ins)) > 1 and not _joined(set(ins), g.get("joins") or []):
                fails.append(_f("G-OCC", "REFUTED_BY_RULE",
                                f"passo {s.get('name')} mistura ocorrências {sorted(set(ins))} sem junção declarada"))
    if "G-VARS" not in dis:
        loose = sorted(set(names) - used)
        if loose:
            fails.append(_f("G-VARS", "REFUTED_BY_RULE", f"variáveis soltas: {loose}"))
    if "G-ARITY" not in dis:
        ns = sum(1 for v in vars_ if v.get("side") == "subject")
        no = sum(1 for v in vars_ if v.get("side") == "object")
        card = "1:1" if ns == no == 1 else "1:N" if ns == 1 else "N:1" if no == 1 else "N:M"
        if g.get("cardinality") != card:
            fails.append(_f("G-ARITY", "REFUTED_BY_RULE", f"cardinalidade declarada {g.get('cardinality')} != {card}"))
    verdict = "REFUTED_BY_RULE" if fails else "OK"
    return {"bo_group_id": g.get("bo_group_id"), "verdict": verdict, "failures": fails}


def _joined(occs: set, joins: list) -> bool:
    """As ocorrências estão todas ligadas por junções declaradas (grafo conexo)?"""
    occs = set(occs)
    seen = {next(iter(occs))}
    changed = True
    while changed:
        changed = False
        for j in joins:
            a, b = j.get("left"), j.get("right")
            if a in seen and b not in seen:
                seen.add(b)
                changed = True
            elif b in seen and a not in seen:
                seen.add(a)
                changed = True
    return occs <= seen


def apply_group(g: dict, instance: dict) -> dict:
    """Executa o grupo sobre um subgrafo concreto: instance = {?ocorrência: {campo: valor}} do lado sujeito.
    Devolve {?var_objeto: valor}. Passos em ordem; cada um lê variáveis já ligadas."""
    byname = {v["name"]: v for v in g["variables"]}
    env = {}
    for v in g["variables"]:
        if v["side"] == "subject":
            occ = instance.get(v["occurrence"], {})
            if v["field"] in occ:
                env[v["name"]] = occ[v["field"]]
    for s in g["steps"]:
        name = s["name"]
        sig = SIGNATURES[name]
        args = {a: env[var] for a, var in s["inputs"].items() if var in env}
        if len(args) != len(sig[0]):
            missing = sorted(set(sig[0]) - set(args))
            raise OutOfDomain(f"{name}: entrada faltando {missing} (UNKNOWN_INPUT)")
        if sig[0] == ("value",):
            out = {"value": T.apply({"name": name, "params": s.get("params")}, args["value"])}
        elif len(sig[0]) == 1:
            out = T.apply({"name": name, "params": s.get("params")}, args[sig[0][0]])
        else:
            out = T.apply({"name": name, "params": s.get("params")}, args)
        if len(sig[1]) == 1 and not isinstance(out, dict):
            out = {sig[1][0]: out}
        for comp, var in s["outputs"].items():
            env[var] = out[comp]
    return {k: v for k, v in env.items() if byname.get(k, {}).get("side") == "object"}
