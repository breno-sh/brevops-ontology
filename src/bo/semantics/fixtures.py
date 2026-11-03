"""Compromissos e CQs do REQUIREMENTS que listam o SEMANTICS como consumidor (família perda), como casos de teste.

Lê $BO_REPO/requirements/commitments.jsonl e cq_spec.jsonl (entrada congelada; vocabulário independente) e
traduz cada fixture numa alegação + transporte desta teoria. O adaptador é explícito e fixo (regras abaixo);
a resposta esperada vem do REQUIREMENTS, escrita antes deste módulo. Nada aqui ajusta a resposta.

Adaptador (fixture -> alegação):
  s1 translates_to t1, leitura completa, sem atributo semantic_relation/evidence_state: alegação exact provada
    (DOC_SUPPORTED, citação 'fixture:<id>'), porque a fixture dá a correspondência; com os atributos, valem eles.
  retention '<n>_<unidade>' -> número na unidade (day, second) ou xsd:duration para mês ('1_month' -> 'P1M').
  t1 retention '<unidade>' -> unidade do destino; t1 domain_max '<n>_<unidade>' -> faixa do destino, com saturação
    declarada no contrato de perda (o mapeador declara o limite do destino que conhece).
  t1 required -> atributo obrigatório; s1 value_symbolic -> valor simbólico; s1 value sem unidade com 'unit' não
    lido -> tipo sem unidade (UNKNOWN).
  não lido 'correspondence' -> evidência UNRESOLVED (código UNPROVEN); 'calendar_context' -> sem contexto de
    calendário; 'target_semantics' -> tipo do destino não determinado (código MISSING_EVIDENCE).
  efeito permitir/negar: destino com supports_deny=false só exprime 'allow' (negar = não exprimível, bloqueio com
    perda declarada); supports_deny='unknown' -> tipo do destino não determinado.
Código C24 a partir do traço: bloqueio por KIND-UNKNOWN -> MISSING_EVIDENCE; por falta de prova -> UNPROVEN;
os demais códigos do C23 passam iguais.
"""

from __future__ import annotations

import re

from . import common
from .transport import check_trace, transport
from .vocab import ABSENT, SYMBOLIC

UNIT = {"day": "unit:DAY", "second": "unit:SEC", "hour": "unit:HR"}
TIME = "quantitykind:Time"


def _attrs(fx: dict, of: str) -> dict:
    return {a["attr"]: a["value"] for a in fx.get("attributes", []) if a["of"] == of}


def _qty(s: str):
    m = re.match(r"^(\d+)_(day|second|hour|month)$", str(s))
    if not m:
        return None
    return int(m[1]), m[2]


def build_case(fx: dict) -> dict:
    """Fixture de perda -> {claim, value, context}."""
    nr = {(x["of"], x["what"]) for x in fx.get("read", {}).get("not_read", [])}
    ents = {e["id"]: e["kind"] for e in fx.get("entities", [])}
    src = next(i for i, k in ents.items() if k in ("source_setting", "rule_set"))
    tgt = next(i for i, k in ents.items() if k == "target_setting")
    s, t = _attrs(fx, src), _attrs(fx, tgt)
    rule_attrs = {}
    for e, k in ents.items():
        if k == "filter_rule":
            rule_attrs = _attrs(fx, e)
    rel = s.get("semantic_relation", "exact")
    ev = s.get("evidence_state", "DOC_SUPPORTED")
    if (src, "correspondence") in nr:
        ev = "UNRESOLVED"
    loss, fn, value, ctx = [], None, None, {}
    tests = []
    if "effect" in rule_attrs:                                      # negação de origem (CQ-LOSS-02)
        st = {"datatype": "enum", "enum": ["allow", "deny"]}
        sd = t.get("supports_deny")
        if sd is True:
            ot = {"datatype": "enum", "enum": ["allow", "deny"]}
            vdr, fid = "equal", "lossless"
        elif sd is False:
            ot = {"datatype": "enum", "enum": ["allow"]}
            loss = [{"kind": "not_expressible", "values": ["deny"], "why": "destino só exprime permissão"}]
            vdr, fid = "superset", "partial"
        else:
            ot = None
            vdr, fid = "unknown", "partial"
        fn = {"name": "identity", "params": {}}
        value = rule_attrs["effect"]
        tests = [{"input": "allow", "expected": "allow"}]
    else:
        sq = _qty(s.get("retention", "")) if "retention" in s else None
        tu = t.get("retention")
        dmax = _qty(t.get("domain_max", "")) if "domain_max" in t else None
        if sq and sq[1] == "month":
            st = {"datatype": "duration", "quantity_kind": TIME}
            value = f"P{sq[0]}M"
            fn = {"name": "duration_to_number", "params": {"to": UNIT.get(tu, "unit:SEC")}}
            tests = [{"input": "P1D", "expected": 86400 if tu == "second" else 1}]
        elif sq:
            st = {"datatype": "integer", "quantity_kind": TIME, "unit": UNIT[sq[1]], "range": {"min": 0, "max": 100000}}
            value = sq[0]
        elif "value" in s and isinstance(s["value"], (int, float)) and (src, "unit") in nr:
            st = {"datatype": "integer", "quantity_kind": TIME, "unit": "UNKNOWN"}
            value = s["value"]
        else:
            st = {"datatype": "string"}
            value = s.get("value")
        if s.get("value_symbolic"):
            value = SYMBOLIC
        if st.get("datatype") == "integer":
            ou = UNIT.get(tu) if tu else (UNIT[dmax[1]] if dmax else st["unit"])
            omax = None
            if dmax:
                omax = dmax[0]
                if UNIT[dmax[1]] != ou:
                    from .valuetypes import UNITS
                    omax = int(dmax[0] * UNITS[UNIT[dmax[1]]][1] / UNITS[ou][1])
            ot = {"datatype": "integer", "quantity_kind": TIME, "unit": ou if ou else "UNKNOWN",
                  "range": {"min": 0, "max": omax}}
            if st["unit"] != "UNKNOWN" and ou and ou != st["unit"]:
                fn = {"name": "unit_convert", "params": {"from": st["unit"], "to": ou}}
                from .valuetypes import UNITS
                tests = [{"input": 1, "expected": int(UNITS[st["unit"]][1] / UNITS[ou][1])}]
            else:
                fn = {"name": "identity", "params": {}}
                tests = [{"input": 1, "expected": 1}]
            if dmax:
                loss = [{"kind": "saturation", "min": 0, "max": omax, "why": "máximo do destino"}]
        elif st.get("datatype") == "duration":
            ot = {"datatype": "integer", "quantity_kind": TIME, "unit": UNIT.get(tu, "unit:SEC"), "range": {"min": 0}}
        else:
            ot = {"datatype": "string"}
            fn = {"name": "identity", "params": {}}
            tests = [{"input": "x", "expected": "x"}]
        vdr = "unknown"
        fid = "declared_loss" if loss else "partial"
        if t.get("required") is not None and ot is not None:
            ot["required"] = bool(t["required"])
        if s.get("value_origin") == "configured" and "value" not in s and "retention" not in s:
            value = ABSENT
    claim = {"claim_id": f"FX:{fx['fixture_id']}", "subject_id": f"pa:{src}", "object_id": f"pb:{tgt}",
             "predicate_id": {"exact": "skos:exactMatch", "related": "skos:relatedMatch", "close": "skos:closeMatch"}.get(rel),
             "mapping_justification": "semapv:ManualMappingCuration", "semantic_relation": rel,
             "value_domain_relation": {"relation": vdr, "orientation": "subject_to_object"},
             "transport_fidelity": "none" if rel == "related" else fid,
             "translation_fn": None if rel == "related" else fn, "loss_contract": loss,
             "subject_value_type": st, "object_value_type": ot, "evidence_state": ev, "basis": "direct",
             "guard": {"all": []},
             "proof": {"type": "fixture", "tests": tests,
                       "evidence": [{"source": f"fixture:{fx['fixture_id']}", "sentence": fx.get("summary", "")}]}}
    return {"claim": claim, "value": value, "context": ctx}


def c24_code(out: dict) -> str | None:
    if out["result"] != "blocked":
        return None
    if out["code"] == "UNPROVEN" and out.get("failed") and set(out["failed"]) <= {"KIND-UNKNOWN"}:
        return "MISSING_EVIDENCE"
    return out["code"]


def answer_commitment(c: dict) -> dict:
    fx = c["fixtures"][0]
    case = build_case(fx)
    out = transport(case["claim"], case["value"], case["context"])
    pol = c["polarity"]
    if pol == "positive":
        if out["result"] == "carried" and out["fidelity"] == "declared_loss":
            got = {"value": "ENTAILED", "code": "DECLARED_LOSS"}
        elif out["result"] == "carried":
            got = {"value": "ENTAILED", "code": "LOSSLESS"}
        else:
            got = {"value": "NOT_ENTAILED", "code": c24_code(out)}
    elif pol == "negative":
        emit = check_trace({"claim": case["claim"], "value": case["value"], "context": case["context"],
                            "asserted": {"result": "carried"}})
        got = {"value": "REJECTED" if (out["result"] == "blocked" and not emit["accepted"]) else "ACCEPTED",
               "code": c24_code(out)}
    else:
        got = {"value": "UNKNOWN" if out["result"] == "blocked" else "DEFINED", "code": c24_code(out)}
    exp = c["expected_answer"]
    ok = got["value"] == exp["value"] and (exp.get("code") is None or got.get("code") == exp["code"])
    return {"id": c["commitment_id"], "fixture": fx["fixture_id"], "expected": {k: exp.get(k) for k in ("value", "code")},
            "got": got, "reproduces": ok, "trace": out}


def answer_cq(q: dict) -> list[dict]:
    rows = []
    for which in ("conforming", "nonconforming", "incomplete"):
        f = q["fixtures"][which]
        case = build_case(f["fixture"])
        out = transport(case["claim"], case["value"], case["context"])
        form, cid = q["answer_form"], q["cq_id"]
        if out["result"] == "blocked" and f["fixture"]["read"]["completeness"] == "partial":
            got = {"value": "UNKNOWN", "code": c24_code(out)}
        elif cid == "CQ-LOSS-01":
            got = {"value": out["fidelity"] if out["result"] == "carried" else "blocked"}
        elif cid == "CQ-LOSS-02":
            nexp = any(x["kind"] == "not_expressible" for x in out.get("losses", []))
            got = {"value": "carried_as_deny" if out["result"] == "carried" and out.get("value") == "deny"
                   else "blocked_with_declared_loss" if out["result"] == "blocked" and nexp else out["result"]}
        elif form == "boolean":
            got = {"value": out["result"] == "carried"}
        else:
            got = {"value": out["result"]}
        exp = f["expected"]
        ok = got["value"] == exp["value"] and (exp.get("code") is None or got.get("code") == exp.get("code"))
        rows.append({"id": f"{cid}/{which}", "fixture": f["fixture"]["fixture_id"],
                     "expected": {k: exp.get(k) for k in ("value", "code")}, "got": got, "reproduces": ok, "trace": out})
    return rows


def suite() -> dict:
    req = common.repo() / "requirements"
    cmts = [c for c in common.load_jsonl(req / "commitments.jsonl") if "SEMANTICS" in c.get("consumers", [])]
    cqs = [q for q in common.load_jsonl(req / "cq_spec.jsonl") if q.get("family") == "loss"]
    rows = [answer_commitment(c) for c in cmts]
    for q in cqs:
        rows.extend(answer_cq(q))
    return {"inputs": {"commitments": "requirements/commitments.jsonl", "cq_spec": "requirements/cq_spec.jsonl",
                       "commitments_sha256": common.sha256_file(req / "commitments.jsonl"),
                       "cq_spec_sha256": common.sha256_file(req / "cq_spec.jsonl")},
            "selection": "compromissos com SEMANTICS em consumers; CQs da família loss",
            "n": len(rows), "n_reproduces": sum(r["reproduces"] for r in rows),
            "rows": [{k: v for k, v in r.items() if k != "trace"} | {"trace": _slim(r["trace"])} for r in rows]}


def _slim(t: dict) -> dict:
    from .transport import _jsonable
    return _jsonable({k: t.get(k) for k in ("result", "code", "rule", "value", "fidelity", "losses", "failed") if k in t})
