"""Modelo do C24 1.0.0: constantes, construtores de registro e validação estrutural e semântica.

Os construtores (fx, cm, cq, req) são usados pelo conteúdo em content/; eles expandem uma notação
compacta em registros JSON estruturados. A validação (validate_*) é a do REQUIREMENTS: confere o
JSON Schema proposto (schemas.py) e as regras que um schema não exprime (polaridade x checagem,
fixture incompleta => UNKNOWN, termos declarados, referências cruzadas). Quando o CONTRACTS publicar
bo.contracts.validate, ele prevalece; este validador continua como checagem semântica do módulo.
"""

from __future__ import annotations

import re

from . import CONTRACT, CONTRACT_VERSION, terms

SCHEMAS = {
    "requirements": "bo.requirement/1",
    "commitments": "bo.commitment/1",
    "cq_spec": "bo.cq_spec/1",
}

# Os 6 casos adversariais obrigatórios da revisão GPT-6 (F1), mais GENERAL para o resto.
CASES = {
    "BUCKET": "armazenamento de objetos: contêiner x dono da configuração x alcance efetivo; conta x contêiner",
    "NIC": "instância com 1 e com 2 interfaces de rede: identidade, anexação e invariância",
    "FIREWALL": "filtragem de tráfego inline e standalone: regra, conjunto, alvo, anexação, estado de conexão, precedência e efeito",
    "IAM": "autorização: principal, permissão, atribuição, escopo e avaliação; a mesma concessão não conta 3 vezes",
    "LB": "balanceador como grafo: frontend, listener, roteamento, backend, sonda e TLS; camada 4 x camada 7",
    "DB": "banco gerenciado: serviço, servidor lógico, instância, banco lógico, réplica, parâmetros e backup; servidor lógico != instância",
}
ADVERSARIAL_CASES = tuple(CASES)
ALL_CASES = ADVERSARIAL_CASES + ("GENERAL",)

# Famílias de CQ (C24). "cis" vem do CQSRC; as outras 7 são as famílias além do CIS (S4).
FAMILIES_BEYOND_CIS = {
    "identity_lifecycle": "identidade e ciclo de vida",
    "composition": "composição",
    "authorization_effect": "efeito de autorização",
    "network_path": "caminho de rede",
    "config_vs_observation": "configuração x observação",
    "loss": "perda",
    "new_provider": "provedor novo",
}
FAMILIES = ("cis",) + tuple(FAMILIES_BEYOND_CIS)

POLARITIES = ("positive", "negative", "unknown")
CHECKS = {
    "positive": ("entails", "count", "invariant"),
    "negative": ("rejects", "not_entails"),
    "unknown": ("unknown",),
}
EXPECTED_BY_CHECK = {
    "entails": "ENTAILED",
    "invariant": "INVARIANT",
    "rejects": "REJECTED",
    "not_entails": "NOT_ENTAILED",
    "unknown": "UNKNOWN",
}
# Códigos que acompanham UNKNOWN ou bloqueio (alinhados ao C23 e ao C29 do plano).
CODES = (
    "OUT_OF_PIN", "UNKNOWN_INPUT", "UNKNOWN_SYMBOLIC_INPUT", "CONDITION_INDETERMINATE", "UNRESOLVED",
    "UNPROVEN", "UNSUPPORTED_BY_TRANSLATOR", "UNGLOSSED", "TRANSFORM_OUT_OF_DOMAIN", "NO_REALIZATION",
    "SHACL_VIOLATION", "INCONSISTENT", "RELATED_ONLY", "DECLARED_LOSS", "MISSING_EVIDENCE",
    "INCOMPLETE_READ", "WITHHELD",
)
UPPER_AXES = ("identity", "time", "role")
LAYERS = ("domain", "terraform", "api", "translation", "evaluation")
PROVIDERS = ("aws", "google", "azurerm", "oci")
EVIDENCE_STATES = ("UNRESOLVED", "DOC_SUPPORTED", "STRUCTURALLY_VALID", "PERSISTENCE_VERIFIED", "OBSERVATION_TESTED")
ANSWER_FORMS = ("boolean", "count", "decision", "enum", "identity")
AREAS = {
    "entity": "entidades e disjunção entre tipos rígidos",
    "taxonomy": "taxonomia e OntoClean",
    "desired_vs_observed": "configuração desejada x estado observado x observação",
    "absence": "ausência, leitura incompleta e retido",
    "identity": "identidade composta e de ocorrência",
    "lifecycle": "ciclo de vida e controlador",
    "relation": "dono x alcance; parte-todo tipada",
    "network": "filtragem e caminho de rede",
    "authorization": "autorização",
    "load_balancing": "balanceador como grafo",
    "database": "banco gerenciado",
    "storage": "armazenamento de objetos",
    "composition": "composição e unidade implantável completa",
    "loss": "perda e transporte",
    "new_provider": "provedor novo",
    "method": "método: congelamento, proteção e regressão",
}
OBJECTION_RE = re.compile(r"^(R[1-4]-M\d{1,2}|R[1-4]-W\d{1,2}|F[1-9]|S\d{1,2}|N\d{1,2}|A\d{1,2})$")
REQ_ID_RE = re.compile(r"^REQ-[A-Z]{2,5}-\d{2}$")
CMT_ID_RE = re.compile(r"^CMT-[A-Z]{2,8}-[PNU]\d{2}$")
CQ_ID_RE = re.compile(r"^CQ-[A-Z]{3,4}-\d{2}$")
FX_ID_RE = re.compile(r"^FX-[A-Z0-9-]{3,40}$")
LOCAL_ID_RE = re.compile(r"^[a-z][a-z0-9_]{0,23}$")
MODULE_RE = re.compile(r"^[A-Z][A-Z0-9-]{1,40}$")


class SpecError(ValueError):
    pass


# ----------------------------------------------------------------------------- construtores

def _value(v: str):
    if v in ("true", "false"):
        return v == "true"
    if re.fullmatch(r"-?\d+", v):
        return int(v)
    return v


def fx(fid: str, summary: str, ents: str, rels=(), attrs=(), complete: bool = True, not_read=(),
       withheld=()) -> dict:
    """Fixture abstrata. ents: 'a:kind b:kind' ('x:k1+k2' = indivíduo com dois tipos, só em contraexemplo); rels: 'a rel b'; attrs: 'a.attr=valor';
    not_read: 'a.o_que'; withheld: 'a.atributo' (existe, valor nunca gravado)."""
    entities = []
    for tok in ents.split():
        i, _, k = tok.partition(":")
        kinds = k.split("+")
        e = {"id": i, "kind": kinds[0]}
        if len(kinds) > 1:
            e["also_kinds"] = kinds[1:]
        entities.append(e)
    relations = []
    for r in rels:
        parts = r.split()
        if len(parts) != 3:
            raise SpecError(f"{fid}: relação mal formada: {r!r}")
        relations.append({"from": parts[0], "rel": parts[1], "to": parts[2]})
    attributes = []
    for a in attrs:
        m = re.fullmatch(r"([a-z][a-z0-9_]*)\.([a-z_]+)=(.+)", a)
        if not m:
            raise SpecError(f"{fid}: atributo mal formado: {a!r}")
        attributes.append({"of": m.group(1), "attr": m.group(2), "value": _value(m.group(3))})
    nr = []
    for n in not_read:
        o, _, w = n.partition(".")
        nr.append({"of": o, "what": w})
    wh = []
    for n in withheld:
        o, _, w = n.partition(".")
        wh.append({"of": o, "attr": w})
    return {
        "fixture_id": fid,
        "summary": summary,
        "entities": entities,
        "relations": relations,
        "attributes": attributes,
        "read": {"completeness": "complete" if complete else "partial", "not_read": nr, "withheld": wh},
    }


def ground(provider: str, note: str) -> dict:
    return {"provider": provider, "note": note, "evidence_state": "UNRESOLVED", "verify_in": "SERVICE-EVIDENCE"}


def req(rid: str, area: str, statement: str, rationale: str, answers, priority: str = "MUST",
        consumers=()) -> dict:
    return {
        "schema": SCHEMAS["requirements"], "contract": CONTRACT, "contract_version": CONTRACT_VERSION,
        "req_id": rid, "area": area, "priority": priority, "statement": statement, "rationale": rationale,
        "answers": list(answers), "consumers": list(consumers),
    }


def cm(cid: str, case: str, polarity: str, check: str, statement: str, assertion: str, fixtures, expected,
       why: str, reqs, answers, protects: str, layer: str = "domain", grounding=(), axes=(), consumers=(),
       code: str | None = None) -> dict:
    fixtures = list(fixtures) if isinstance(fixtures, (list, tuple)) else [fixtures]
    reqs = list(reqs)
    # Rastreio metodológico: todo negativo/desconhecido é protegido (REQ-METH-02); todo caso com eixo de
    # ontologia de topo alimenta a decisão (REQ-METH-03).
    if polarity in ("negative", "unknown") and "REQ-METH-02" not in reqs:
        reqs.append("REQ-METH-02")
    if axes and "REQ-METH-03" not in reqs:
        reqs.append("REQ-METH-03")
    exp = {"value": expected, "why": why}
    if code:
        exp["code"] = code
    return {
        "schema": SCHEMAS["commitments"], "contract": CONTRACT, "contract_version": CONTRACT_VERSION,
        "commitment_id": cid, "case": case, "polarity": polarity,
        "check": {"kind": check, "assertion": assertion},
        "statement": statement, "fixtures": fixtures, "expected_answer": exp,
        "protects": protects, "layer": layer, "upper_axes": list(axes),
        "requirement_ids": list(reqs), "answers": list(answers),
        "provider_grounding": list(grounding), "consumers": list(consumers),
    }


def cq(qid: str, family: str, question: str, criterion: str, answer_form: str, conforming, nonconforming,
       incomplete, reqs, cmts, cases, answers, reasoning: str, negation: bool = False) -> dict:
    """conforming/nonconforming = (fixture, valor, porquê); incomplete = (fixture, porquê, código|None)."""
    def side(t):
        f, v, w = t
        return {"fixture": f, "expected": {"value": v, "why": w}}
    reqs = list(reqs)
    if "REQ-METH-01" not in reqs:  # toda CQ é escrita antes da indução, com as 3 fixtures (REQ-METH-01)
        reqs.append("REQ-METH-01")
    f, w, code = incomplete
    inc = {"fixture": f, "expected": {"value": "UNKNOWN", "why": w}}
    if code:
        inc["expected"]["code"] = code
    return {
        "schema": SCHEMAS["cq_spec"], "contract": CONTRACT, "contract_version": CONTRACT_VERSION,
        "cq_id": qid, "family": family, "question": question, "criterion": criterion,
        "answer_form": answer_form,
        "fixtures": {"conforming": side(conforming), "nonconforming": side(nonconforming), "incomplete": inc},
        "closed_world": {"uses_negation": negation, "negation_requires_complete_read": True},
        "applicability": ("todo provedor fixado; NOT_APPLICABLE só com evidência (SERVICE-EVIDENCE) de que "
                          "o provedor não tem a estrutura; a decisão é do CQFIX e fica registrada"),
        "reasoning_needs": reasoning,
        "requirement_ids": list(reqs), "commitment_ids": list(cmts), "cases": list(cases),
        "answers": list(answers),
    }


# ----------------------------------------------------------------------------- validação

def _err(errs: list, where: str, msg: str):
    errs.append(f"{where}: {msg}")


def check_fixture(f: dict, where: str, errs: list):
    if not isinstance(f, dict):
        _err(errs, where, "fixture não é objeto")
        return
    fid = f.get("fixture_id", "?")
    w = f"{where}/{fid}"
    if not FX_ID_RE.match(str(fid)):
        _err(errs, w, "fixture_id fora do formato FX-...")
    if not str(f.get("summary", "")).strip():
        _err(errs, w, "summary vazio")
    ids = set()
    ents = f.get("entities") or []
    if not ents:
        _err(errs, w, "fixture sem entidades")
    for e in ents:
        i, k = e.get("id"), e.get("kind")
        if not LOCAL_ID_RE.match(str(i)):
            _err(errs, w, f"id local inválido: {i!r}")
        if i in ids:
            _err(errs, w, f"id local repetido: {i}")
        ids.add(i)
        for kk in [k] + list(e.get("also_kinds") or []):
            if kk not in terms.KINDS:
                _err(errs, w, f"tipo não declarado em terms.KINDS: {kk!r}")
    for r in f.get("relations") or []:
        if r.get("rel") not in terms.RELATIONS:
            _err(errs, w, f"relação não declarada: {r.get('rel')!r}")
        for end in ("from", "to"):
            if r.get(end) not in ids:
                _err(errs, w, f"relação {r.get('rel')} aponta para id inexistente: {r.get(end)!r}")
    for a in f.get("attributes") or []:
        if a.get("attr") not in terms.ATTRIBUTES:
            _err(errs, w, f"atributo não declarado: {a.get('attr')!r}")
        if a.get("of") not in ids:
            _err(errs, w, f"atributo de id inexistente: {a.get('of')!r}")
    rd = f.get("read") or {}
    if rd.get("completeness") not in terms.COMPLETENESS:
        _err(errs, w, "read.completeness inválido")
    for n in rd.get("not_read") or []:
        if n.get("what") not in terms.NOT_READ_WHAT:
            _err(errs, w, f"not_read.what não declarado: {n.get('what')!r}")
        if n.get("of") not in ids:
            _err(errs, w, f"not_read de id inexistente: {n.get('of')!r}")
    for n in rd.get("withheld") or []:
        if n.get("of") not in ids:
            _err(errs, w, f"withheld de id inexistente: {n.get('of')!r}")
    if rd.get("completeness") == "partial" and not rd.get("not_read"):
        _err(errs, w, "leitura parcial sem not_read (o que falta tem de ser dito)")
    if rd.get("completeness") == "complete" and rd.get("not_read"):
        _err(errs, w, "leitura completa com not_read")


def _common(rec: dict, kind: str, where: str, errs: list):
    if rec.get("schema") != SCHEMAS[kind]:
        _err(errs, where, f"schema != {SCHEMAS[kind]}")
    if rec.get("contract") != CONTRACT or rec.get("contract_version") != CONTRACT_VERSION:
        _err(errs, where, f"contract/contract_version != {CONTRACT} {CONTRACT_VERSION}")
    ans = rec.get("answers") or []
    if not ans:
        _err(errs, where, "answers vazio (toda entrada responde a ao menos uma objeção)")
    for a in ans:
        if not OBJECTION_RE.match(str(a)):
            _err(errs, where, f"objeção fora do formato: {a!r}")
    for m in rec.get("consumers") or []:
        if not MODULE_RE.match(str(m)):
            _err(errs, where, f"consumidor fora do formato de stable_id: {m!r}")


def validate_requirements(recs: list) -> list:
    errs, seen = [], set()
    for n, r in enumerate(recs, 1):
        where = f"requirements[{n}] {r.get('req_id', '?')}"
        _common(r, "requirements", where, errs)
        rid = r.get("req_id")
        if not REQ_ID_RE.match(str(rid)):
            _err(errs, where, "req_id fora do formato REQ-XXX-NN")
        if rid in seen:
            _err(errs, where, "req_id repetido")
        seen.add(rid)
        if r.get("area") not in AREAS:
            _err(errs, where, f"area inválida: {r.get('area')!r}")
        if r.get("priority") not in ("MUST", "SHOULD"):
            _err(errs, where, "priority != MUST|SHOULD")
        for k in ("statement", "rationale"):
            if len(str(r.get(k, "")).strip()) < 20:
                _err(errs, where, f"{k} vazio ou curto demais")
    return errs


def validate_commitments(recs: list, req_ids: set | None = None) -> list:
    errs, seen, fx_seen = [], set(), set()
    for n, c in enumerate(recs, 1):
        where = f"commitments[{n}] {c.get('commitment_id', '?')}"
        _common(c, "commitments", where, errs)
        cid = c.get("commitment_id")
        if not CMT_ID_RE.match(str(cid)):
            _err(errs, where, "commitment_id fora do formato CMT-XXX-[PNU]NN")
        if cid in seen:
            _err(errs, where, "commitment_id repetido")
        seen.add(cid)
        pol = c.get("polarity")
        if pol not in POLARITIES:
            _err(errs, where, f"polarity inválida: {pol!r}")
            continue
        if cid and CMT_ID_RE.match(str(cid)) and cid.rsplit("-", 1)[1][0] != pol[0].upper():
            _err(errs, where, "letra do id não bate com a polaridade (P/N/U)")
        if c.get("case") not in ALL_CASES:
            _err(errs, where, f"case inválido: {c.get('case')!r}")
        chk = (c.get("check") or {}).get("kind")
        if chk not in CHECKS[pol]:
            _err(errs, where, f"check {chk!r} incompatível com polaridade {pol} (aceitos: {CHECKS[pol]})")
        if len(str((c.get("check") or {}).get("assertion", "")).strip()) < 10:
            _err(errs, where, "check.assertion vazio")
        if len(str(c.get("statement", "")).strip()) < 20:
            _err(errs, where, "statement vazio ou curto")
        if len(str(c.get("protects", "")).strip()) < 10:
            _err(errs, where, "protects vazio (o que este compromisso protege?)")
        if c.get("layer") not in LAYERS:
            _err(errs, where, f"layer inválida: {c.get('layer')!r}")
        exp = c.get("expected_answer") or {}
        val = exp.get("value")
        if chk == "count":
            if not isinstance(val, int) or isinstance(val, bool) or val < 0:
                _err(errs, where, "check count exige valor inteiro >= 0")
        elif chk in EXPECTED_BY_CHECK and val != EXPECTED_BY_CHECK[chk]:
            _err(errs, where, f"resposta esperada {val!r} != {EXPECTED_BY_CHECK[chk]} para check {chk}")
        if len(str(exp.get("why", "")).strip()) < 10:
            _err(errs, where, "expected_answer.why vazio")
        if exp.get("code") is not None and exp.get("code") not in CODES:
            _err(errs, where, f"código desconhecido: {exp.get('code')!r}")
        fxs = c.get("fixtures") or []
        if not fxs:
            _err(errs, where, "sem fixture")
        if chk == "invariant" and len(fxs) < 2:
            _err(errs, where, "invariant exige ao menos 2 fixtures (base e variante)")
        for f in fxs:
            check_fixture(f, where, errs)
            if f.get("fixture_id") in fx_seen:
                _err(errs, where, f"fixture_id repetido entre compromissos: {f.get('fixture_id')}")
            fx_seen.add(f.get("fixture_id"))
        if pol == "unknown" and not any((f.get("read") or {}).get("completeness") == "partial" for f in fxs):
            _err(errs, where, "compromisso UNKNOWN sem fixture de leitura parcial (o que falta?)")
        if pol != "unknown":
            for f in fxs:
                if (f.get("read") or {}).get("completeness") != "complete":
                    _err(errs, where, f"compromisso {pol} com fixture parcial {f.get('fixture_id')}: "
                                      "resposta definida exige leitura completa declarada")
        for a in c.get("upper_axes") or []:
            if a not in UPPER_AXES:
                _err(errs, where, f"upper_axes inválido: {a!r}")
        for g in c.get("provider_grounding") or []:
            if g.get("provider") not in PROVIDERS:
                _err(errs, where, f"provider_grounding.provider inválido: {g.get('provider')!r}")
            if g.get("evidence_state") not in EVIDENCE_STATES:
                _err(errs, where, "provider_grounding.evidence_state inválido")
            if len(str(g.get("note", ""))) < 10:
                _err(errs, where, "provider_grounding.note vazio")
        rids = c.get("requirement_ids") or []
        if not rids:
            _err(errs, where, "requirement_ids vazio")
        if req_ids is not None:
            for r in rids:
                if r not in req_ids:
                    _err(errs, where, f"requisito inexistente: {r}")
    return errs


def validate_cq_spec(recs: list, req_ids: set | None = None, cmt_ids: set | None = None) -> list:
    errs, seen, fx_seen = [], set(), set()
    for n, q in enumerate(recs, 1):
        where = f"cq_spec[{n}] {q.get('cq_id', '?')}"
        _common(q, "cq_spec", where, errs)
        qid = q.get("cq_id")
        if not CQ_ID_RE.match(str(qid)):
            _err(errs, where, "cq_id fora do formato CQ-XXX-NN")
        if qid in seen:
            _err(errs, where, "cq_id repetido")
        seen.add(qid)
        if q.get("family") not in FAMILIES:
            _err(errs, where, f"family inválida: {q.get('family')!r}")
        if q.get("answer_form") not in ANSWER_FORMS:
            _err(errs, where, f"answer_form inválido: {q.get('answer_form')!r}")
        for k in ("question", "criterion", "reasoning_needs", "applicability"):
            if len(str(q.get(k, "")).strip()) < 15:
                _err(errs, where, f"{k} vazio ou curto")
        fxs = q.get("fixtures") or {}
        for role in ("conforming", "nonconforming", "incomplete"):
            s = fxs.get(role)
            if not isinstance(s, dict) or "fixture" not in s or "expected" not in s:
                _err(errs, where, f"falta fixture {role} com resposta esperada")
                continue
            check_fixture(s["fixture"], f"{where}/{role}", errs)
            fid = s["fixture"].get("fixture_id")
            if fid in fx_seen:
                _err(errs, where, f"fixture_id repetido entre CQs: {fid}")
            fx_seen.add(fid)
            e = s["expected"]
            if "value" not in e or len(str(e.get("why", "")).strip()) < 10:
                _err(errs, where, f"resposta esperada {role} sem valor ou sem porquê")
            if e.get("code") is not None and e.get("code") not in CODES:
                _err(errs, where, f"código desconhecido em {role}: {e.get('code')!r}")
            comp = (s["fixture"].get("read") or {}).get("completeness")
            if role == "incomplete":
                if e.get("value") != "UNKNOWN":
                    _err(errs, where, "fixture incompleta tem de esperar UNKNOWN")
                if comp != "partial":
                    _err(errs, where, "fixture incompleta precisa de leitura parcial declarada")
            else:
                if e.get("value") == "UNKNOWN":
                    _err(errs, where, f"fixture {role} não pode esperar UNKNOWN")
                if comp != "complete":
                    _err(errs, where, f"fixture {role} precisa de leitura completa declarada")
        try:
            if fxs["conforming"]["expected"]["value"] == fxs["nonconforming"]["expected"]["value"]:
                _err(errs, where, "conforme e não conforme têm a mesma resposta esperada")
        except (KeyError, TypeError):
            pass
        cw = q.get("closed_world") or {}
        if cw.get("negation_requires_complete_read") is not True:
            _err(errs, where, "negação tem de exigir leitura completa declarada")
        for c in q.get("cases") or []:
            if c not in ADVERSARIAL_CASES:
                _err(errs, where, f"case inválido: {c!r}")
        if not q.get("requirement_ids"):
            _err(errs, where, "requirement_ids vazio")
        if req_ids is not None:
            for r in q.get("requirement_ids") or []:
                if r not in req_ids:
                    _err(errs, where, f"requisito inexistente: {r}")
        if cmt_ids is not None:
            for c in q.get("commitment_ids") or []:
                if c not in cmt_ids:
                    _err(errs, where, f"compromisso inexistente: {c}")
    return errs
