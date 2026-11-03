"""Gate: C12 e C22 usam a mesma união discriminada de desfechos; nenhum valor de desfecho fora dela.

  python -I -m bo.contracts.enum_union

Confere, nos schemas PUBLICADOS e nos stubs:
  U1  o C00 define outcome = oneOf[persistence, behavior], cada ramo {axis: const, value: enum}, com os valores do
      plano (§4, C12 e C22) — nem a mais, nem a menos;
  U2  o campo outcome do C12 (outcomes.jsonl) e do C22 (pair_judgements.jsonl) referencia ESSA definição (mesmo $ref)
      e só fixa o eixo;
  U3  nenhum outro schema declara enum/const com valor exclusivo de desfecho (PERSISTED, ALTERED, …);
  U4  nos stubs, todo objeto {axis, value} de eixo de desfecho tem valor do seu eixo, e nenhum valor exclusivo de
      desfecho aparece solto (fora de um objeto da união);
  U5  autoteste: cada valor passa no seu eixo e reprova no outro; valor fora da união reprova; desfecho plano
      (string em vez de {axis, value}) reprova.
"""

from __future__ import annotations

import json
import sys

import jsonschema

from . import _base, catalog, fileio

# Valores copiados do plano (§4) de forma independente do spec_a: se um dos dois mudar, U1 reprova.
PLAN = {"persistence": ["PERSISTED", "ALTERED", "REJECTED_BY_API", "NOT_READABLE", "INFRA_ERROR", "UNKNOWN"],
        "behavior": ["OBSERVATIONS_MATCH_UNDER_PROTOCOL", "OBSERVATIONS_DIFFER_UNDER_PROTOCOL", "NOT_OBSERVED_IN_WINDOW",
                     "PROTOCOL_UNSUPPORTED", "INFRA_ERROR", "UNKNOWN"]}
SHARED = {"INFRA_ERROR", "UNKNOWN"}
EXCLUSIVE = (set(PLAN["persistence"]) | set(PLAN["behavior"])) - SHARED
UNION_REF = f"{_base.BASE_URI}{_base.C00}#/$defs/outcome"
USERS = {("C12", "outcome_record"): "persistence", ("C22", "pair_judgement"): "behavior"}


def _walk(x, path=""):
    if isinstance(x, dict):
        yield path, x
        for k, v in x.items():
            yield from _walk(v, f"{path}/{k}")
    elif isinstance(x, list):
        for i, v in enumerate(x):
            yield from _walk(v, f"{path}/{i}")


def check_schemas(sch: dict) -> tuple[list[str], dict]:
    errs, info = [], {}
    d = sch["C00"]["$defs"]
    u = d.get("outcome") or {}
    refs = [b.get("$ref") for b in u.get("oneOf") or []]
    if refs != ["#/$defs/outcome_persistence", "#/$defs/outcome_behavior"]:
        errs.append(f"U1 C00 outcome não é oneOf[persistence, behavior]: {refs}")
    for axis in ("persistence", "behavior"):
        b = d.get(f"outcome_{axis}") or {}
        p = b.get("properties") or {}
        if (p.get("axis") or {}).get("const") != axis:
            errs.append(f"U1 ramo {axis}: axis não é const {axis!r}")
        vals = (p.get("value") or {}).get("enum")
        if vals != PLAN[axis]:
            errs.append(f"U1 ramo {axis}: valores {vals} != plano {PLAN[axis]}")
        if set(b.get("required") or []) != {"axis", "value"} or b.get("additionalProperties") is not False:
            errs.append(f"U1 ramo {axis}: tem de exigir axis e value e ser fechado")
        info[axis] = vals
    for (cid, rec), axis in USERS.items():
        f = ((sch[cid]["$defs"].get(rec) or {}).get("properties") or {}).get("outcome")
        if not f:
            errs.append(f"U2 {cid}.{rec}: sem campo outcome")
            continue
        parts = f.get("allOf") or []
        ref = [p.get("$ref") for p in parts if "$ref" in p]
        pin = [p for p in parts if "$ref" not in p]
        if ref != [UNION_REF]:
            errs.append(f"U2 {cid}.{rec}.outcome não referencia a união do C00 ({ref})")
        if pin != [{"properties": {"axis": {"const": axis}}}]:
            errs.append(f"U2 {cid}.{rec}.outcome tem de só fixar axis = {axis} (veio {pin})")
    for cid, s in sorted(sch.items()):
        for path, node in _walk(s):
            if cid == "C00" and path.startswith("/$defs/outcome"):
                continue
            vals = list(node.get("enum") or []) + ([node["const"]] if "const" in node else [])
            bad = sorted(v for v in vals if isinstance(v, str) and v in EXCLUSIVE)
            if bad:
                errs.append(f"U3 {cid}{path}: valor de desfecho fora da união: {bad}")
    return errs, info


def check_stubs(sch: dict) -> tuple[list[str], int]:
    from .validate import stub_index
    errs, n = [], 0
    for rel, kind in sorted(stub_index().items()):
        cid, k = kind.split(":")
        p = _base.stubs_dir() / rel
        fk = catalog.resolve(f"{cid}_{k}", p, sch)
        if fk.format not in ("json", "jsonl", "yaml", "sssom_tsv"):
            continue
        recs, _ = fileio.read(fk.format, p)
        for where, obj in recs:
            for path, node in _walk(obj):
                if node.get("axis") in PLAN and "value" in node:
                    n += 1
                    if node["value"] not in PLAN[node["axis"]]:
                        errs.append(f"U4 {rel} {where}{path}: {node['value']!r} fora do eixo {node['axis']}")
            for path, node in _walk({"_": obj}):
                for kk, v in node.items():
                    if isinstance(v, str) and v in EXCLUSIVE and not (kk == "value" and node.get("axis") in PLAN):
                        errs.append(f"U4 {rel} {where}{path}/{kk}: valor de desfecho solto {v!r}")
    return errs, n


def selftest(sch: dict) -> list[str]:
    errs = []
    reg = catalog.registry(sch)
    for (cid, rec), axis in USERS.items():
        sub = sch[cid]["$defs"][rec]["properties"]["outcome"]
        v = jsonschema.Draft202012Validator(sub, registry=reg)
        other = "behavior" if axis == "persistence" else "persistence"
        for val in PLAN[axis]:
            if not v.is_valid({"axis": axis, "value": val}):
                errs.append(f"U5 {cid}: {axis}/{val} devia passar")
        for val in set(PLAN[other]) - SHARED:
            if v.is_valid({"axis": axis, "value": val}) or v.is_valid({"axis": other, "value": val}):
                errs.append(f"U5 {cid}: {val} (do eixo {other}) devia reprovar no {cid}")
        for bad in ({"axis": axis, "value": "OK"}, PLAN[axis][0], {"value": PLAN[axis][0]},
                    {"axis": axis, "value": PLAN[axis][0], "extra": 1}):
            if v.is_valid(bad):
                errs.append(f"U5 {cid}: {bad!r} devia reprovar")
    return errs


def main(argv=None) -> int:
    sch = catalog.schemas()
    e1, info = check_schemas(sch)
    e2, n = check_stubs(sch)
    e3 = selftest(sch)
    errs = e1 + e2 + e3
    rep = {"at": _base.now(), "union_ref": UNION_REF, "axes": info, "shared_values": sorted(SHARED),
           "users": {f"{c}.{r}": a for (c, r), a in USERS.items()}, "stub_outcomes_checked": n, "errors": errs}
    d = _base.data_dir()
    d.mkdir(parents=True, exist_ok=True)
    (d / "enum_union.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    for e in errs:
        print(f"  FAIL {e}")
    print(f"[{_base.now()}] enum_union: união {UNION_REF.rsplit('/', 1)[-1]} com "
          f"{len(info.get('persistence') or [])}+{len(info.get('behavior') or [])} valores; C12 e C22 referenciam a mesma; "
          f"{n} desfecho(s) nos stubs; {len(errs)} erro(s)")
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
