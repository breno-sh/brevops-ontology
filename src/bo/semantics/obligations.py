"""Obrigações de prova por tipo de relação: veredito OK | REFUTED_BY_RULE | UNPROVEN (C21) por alegação.

REFUTED_BY_RULE: o que a alegação declara se contradiz ou é desmentido por execução (teste, domínio, tipo).
UNPROVEN: falta a prova que o tipo exige. Sem prova, nada transporta (CMT-LOSS-U02).
Cada falha cita a regra (rules.RULES). 'disabled' desliga regras só para o teste de mutação (cada contraexemplo
tem de passar quando a regra que ele isola é desligada: prova que é a regra, e não outra coisa, que o rejeita).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from . import guards as G
from . import predicates as P
from . import transforms as T
from .claims import Claim, check_predicate
from .valuetypes import (AnyDomain, EnumDomain, NumDomain, OutOfDomain, TypeError_, ValueType, canonical,
                         relation, domain_contains)
from .vocab import (EVIDENCE_RANK, MEANING_SUPPORT, SUBSET_SIDE, TRANSPORTING, FIDELITY_RANK, VDR_ORIENTATION,
                    VALUE_DOMAIN_RELATIONS, FIDELITIES)

_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}")
LOSSY_KINDS = ("rounding", "saturation", "not_expressible", "semantic", "sentinel")


@dataclass
class Assessment:
    claim_id: str
    verdict: str = "OK"
    failures: list = field(default_factory=list)   # [{rule, outcome, detail}]
    computed: dict = field(default_factory=dict)   # vdr calculada, fidelidade efetiva, satisfatibilidade

    def fail(self, rule: str, outcome: str, detail: str, disabled: frozenset):
        if rule in disabled:
            return
        self.failures.append({"rule": rule, "outcome": outcome, "detail": detail})

    def finish(self):
        outs = {f["outcome"] for f in self.failures}
        self.verdict = "REFUTED_BY_RULE" if "REFUTED_BY_RULE" in outs else "UNPROVEN" if "UNPROVEN" in outs else "OK"
        return self

    @property
    def rules(self) -> list[str]:
        return sorted({f["rule"] for f in self.failures})

    def to_dict(self) -> dict:
        return {"claim_id": self.claim_id, "verdict": self.verdict, "failures": self.failures,
                "computed": self.computed}


def _types(c: Claim, a: Assessment, dis):
    ts = []
    for side in ("subject_value_type", "object_value_type"):
        d = c[side]
        if d is None:
            ts.append(None)
            continue
        try:
            ts.append(ValueType.from_dict(d))
        except (TypeError_, OutOfDomain, ValueError) as e:
            a.fail("TYPE-WF", "REFUTED_BY_RULE", f"{side}: {e}", dis)
            ts.append(None)
    return ts


PARTIAL_ADJUST = {"equal": "superset", "subset": "overlap", "superset": "superset", "overlap": "overlap",
                  "disjoint": "disjoint", "unknown": "unknown"}


def computed_vdr(c: Claim, ts: ValueType, to: ValueType) -> str:
    """Relação entre ν(dom sujeito) e dom objeto. Se a função parcial não está definida em parte do domínio
    finito do sujeito, esses valores ficam sem contraparte (contam como elementos fora do objeto)."""
    if T.kind(c["translation_fn"]) == "tuple":
        return "unknown"
    if ts.is_collection or to.is_collection:
        if ts.datatype != to.datatype and not (ts.datatype == "set" and to.datatype == "list"):
            return "unknown"
        # coleção do mesmo tipo: a relação é a dos elementos (sem restrição de tamanho declarada)
        return computed_vdr(c, ts.item, to.item)
    try:
        dom = ts.domain()
        img = T.image(c["translation_fn"], dom)
    except (TypeError_, OutOfDomain):
        return "unknown"
    od = to.domain()
    fd = c["fixed_default"]
    if isinstance(fd, dict) and "value" in fd:
        od = EnumDomain(frozenset({fd["value"]}))      # destino sem atributo: só o valor fixo/padrão existe
    if c.loss("rounding") and isinstance(od, NumDomain):
        od = NumDomain(od.lo, od.hi, None)             # arredondamento declarado: conta o envoltório contínuo
    r = relation(img, od)
    if isinstance(dom, EnumDomain):
        undefined = 0
        for v in dom.values:
            try:
                T.apply_chain(T.chain_of(c["translation_fn"]), v)
            except (OutOfDomain, TypeError_):
                undefined += 1
        if undefined == len(dom.values):
            return "disjoint"
        if undefined:
            r = PARTIAL_ADJUST[r]
    return r


def derive_fidelity(rel: str, vdr: str, losses: list, has_pred: bool, fn_missing: bool) -> str:
    """Fidelidade que as regras admitem a partir do resto (usada na inversa, que não herda a da ida)."""
    if rel == "related" or fn_missing or vdr == "disjoint":
        return "none"
    lossy = [x for x in losses if x.get("kind") in LOSSY_KINDS and x.get("kind") != "sentinel"]
    if rel == "close":
        return "declared_loss" if lossy else "partial"
    if vdr in ("equal", "subset") and not lossy:
        if rel == "narrow":
            return "partial"
        return "lossless"
    if lossy and vdr in ("equal", "subset"):
        return "declared_loss"
    return "partial"


def assess(c: Claim | dict, disabled=frozenset()) -> Assessment:
    c = c if isinstance(c, Claim) else Claim(c)
    dis = frozenset(disabled)
    a = Assessment(c.id)
    rel = c.relation

    for e in check_predicate(c):
        a.fail("SKOS-PRED", "REFUTED_BY_RULE", e, dis)
    if rel not in ("exact", "close", "broad", "narrow", "related"):
        return a.finish()

    fid = c["transport_fidelity"]
    if fid is not None and fid not in FIDELITIES:
        a.fail("FID-COHERENT", "REFUTED_BY_RULE", f"transport_fidelity inválida: {fid!r}", dis)

    # guarda: bem tipada e satisfazível
    try:
        G.typecheck(c.guard)
        sat, info = G.satisfiable(c.guard)
        a.computed["guard_sat"] = sat
        if sat == G.UNSAT:
            a.fail("GUARD-SAT", "REFUTED_BY_RULE", f"guarda insatisfazível (alegação vazia): {info}", dis)
        elif sat == G.UNKNOWN:
            a.fail("GUARD-SAT", "UNPROVEN", f"satisfatibilidade indecidida: {info}", dis)
        else:
            ok, _ = G.evaluate(c.guard, info)
            if ok != G.TRUE:
                a.fail("GUARD-SAT", "REFUTED_BY_RULE", "testemunha não satisfaz a guarda (erro interno)", dis)
    except G.GuardTypeError as e:
        a.fail("GUARD-TYPE", "REFUTED_BY_RULE", str(e), dis)

    if rel == "related":
        if fid not in (None, "none"):
            a.fail("RELATED-NT", "REFUTED_BY_RULE", f"related não habilita transporte; fidelidade={fid}", dis)
        if c["translation_fn"] not in (None, []):
            a.fail("RELATED-NT", "REFUTED_BY_RULE", "related com função de tradução", dis)
        a.computed["fidelity"] = "none"
        return a.finish()

    ts, to = _types(c, a, dis)
    fd = c["fixed_default"]
    if fd is not None:
        _fixed_default(c, fd, to, a, dis)

    if ts is None or to is None:
        if fd is None:
            a.fail("KIND-UNKNOWN", "UNPROVEN", "tipo de valor de um lado não declarado (unknown==unknown não é prova)", dis)
        return a.finish()
    if ts.kind_unknown() or to.kind_unknown():
        a.fail("KIND-UNKNOWN", "UNPROVEN",
               f"grandeza/unidade UNKNOWN ({ts.quantity_kind}/{ts.unit} -> {to.quantity_kind}/{to.unit})", dis)

    chain = c["translation_fn"]
    tkind = None
    if chain is None and fd is None:
        a.fail("EXACT-NORM", "UNPROVEN", "sem função de tradução declarada (normalização explícita)", dis)
    elif chain is not None:
        try:
            tkind = T.kind(chain)
        except TypeError_ as e:
            a.fail("EXACT-NORM", "UNPROVEN", f"função fora do núcleo: {e}", dis)
    if tkind == "scalar" and (ts.is_collection or to.is_collection):
        if ts.is_collection != to.is_collection:
            a.fail("KIND-COLL", "REFUTED_BY_RULE",
                   f"transformação escalar entre coleção e não coleção ({ts.datatype} -> {to.datatype}); "
                   "exige combinador de coleção (wrap_list/unwrap_single)", dis)
        elif ts.datatype != to.datatype and not (ts.datatype == "set" and to.datatype == "list") and \
                not [x for x in c.losses if x.get("kind") in ("not_expressible", "semantic")]:
            a.fail("KIND-COLL", "REFUTED_BY_RULE",
                   f"{ts.datatype} -> {to.datatype} sem perda declarada (ordem, repetição ou chave)", dis)
    if tkind == "scalar" and not ts.kind_unknown() and not to.kind_unknown():
        ok, why = T.preserves_kind(chain, ts.element(), to.element())
        if not ok:
            a.fail("KIND-EQ", "REFUTED_BY_RULE", f"transformação escalar muda a grandeza: {why}", dis)
        if ts.datatype == "tuple" or to.datatype == "tuple":
            a.fail("KIND-TUPLE", "REFUTED_BY_RULE", "valor estruturado com transformação escalar", dis)
    if tkind == "tuple" and not (ts.datatype == "tuple" or to.datatype == "tuple"):
        a.fail("KIND-TUPLE", "REFUTED_BY_RULE", "combinador de tupla sem lado com tipo estruturado declarado", dis)

    # testes da normalização (executados)
    proof = c["proof"] or {}
    tests = proof.get("tests") or []
    if chain is not None and tkind is not None:
        if not tests:
            a.fail("EXACT-TESTS", "UNPROVEN", "normalização sem testes executáveis", dis)
        for t in tests:
            _run_test(c, chain, t, ts, to, a, dis, tkind)

    # domínios de valores (orientação sujeito -> objeto)
    vdr_decl = c.vdr
    orient = c.vdr_orientation
    if vdr_decl not in VALUE_DOMAIN_RELATIONS:
        a.fail("VDR-COMPUTED", "REFUTED_BY_RULE", f"value_domain_relation inválida: {vdr_decl!r}", dis)
    elif orient != VDR_ORIENTATION:
        a.fail("VDR-COMPUTED", "REFUTED_BY_RULE", f"orientação ausente ou errada: {orient!r} (é {VDR_ORIENTATION})", dis)
    vdr_comp = computed_vdr(c, ts, to) if tkind != "tuple" and chain is not None else "unknown"
    a.computed["vdr"] = vdr_comp
    if vdr_comp != "unknown" and vdr_decl in VALUE_DOMAIN_RELATIONS and vdr_decl not in ("unknown", vdr_comp):
        a.fail("VDR-COMPUTED", "REFUTED_BY_RULE",
               f"declarada {vdr_decl}, calculada {vdr_comp} (domínio do sujeito pela tradução vs domínio do objeto)", dis)
    eff_vdr = vdr_comp if vdr_comp != "unknown" else "unknown"

    losses = c.losses
    lossy = [x for x in losses if x.get("kind") in LOSSY_KINDS and x.get("kind") != "sentinel"]
    if fid == "lossless" and eff_vdr == "unknown":
        a.fail("VDR-UNKNOWN", "UNPROVEN", "sem perda alegado sem domínios que o provem", dis)
    if fid is None and not c["inverse_of"]:
        a.fail("FID-COHERENT", "REFUTED_BY_RULE", "transport_fidelity ausente", dis)
    if fid is not None:
        if fid == "lossless" and lossy:
            a.fail("FID-COHERENT", "REFUTED_BY_RULE", f"sem perda com perdas declaradas: {[x['kind'] for x in lossy]}", dis)
        if fid == "lossless" and eff_vdr in ("superset", "overlap", "disjoint"):
            a.fail("FID-COHERENT", "REFUTED_BY_RULE", f"sem perda com domínio {eff_vdr}: há valor que não cabe", dis)
        if eff_vdr == "disjoint" and fid != "none" and not c.loss("saturation"):
            a.fail("FID-COHERENT", "REFUTED_BY_RULE", "domínios disjuntos: nenhum valor atravessa", dis)
        if fid == "declared_loss" and not lossy:
            a.fail("FID-COHERENT", "REFUTED_BY_RULE", "perda declarada sem item de perda no contrato", dis)
    a.computed["fidelity"] = fid if fid is not None else derive_fidelity(
        rel, eff_vdr, losses, bool(c["membership_predicate"]), bool(c["inverse_missing"]))

    if rel == "close":
        if not lossy:
            a.fail("CLOSE-LOSS", "REFUTED_BY_RULE", "close tem de declarar o que se perde (loss_contract)", dis)
        if fid == "lossless":
            a.fail("CLOSE-LOSS", "REFUTED_BY_RULE", "close não é sem perda (conversão exata é exact)", dis)

    if rel in ("broad", "narrow"):
        _membership(c, rel, ts, to, a, dis)
        if rel == "narrow" and fid == "lossless" and not _pred_total(c, ts):
            a.fail("FID-COHERENT", "REFUTED_BY_RULE", "narrow na ida só transporta o subconjunto: não é sem perda", dis)

    # contexto, sentinelas
    gterms = G.terms(c.guard) if isinstance(c.guard, dict) else set()
    for x in c.loss("context_dependence"):
        miss = [t for t in x.get("terms", []) if t not in gterms]
        if miss:
            a.fail("CTX-DEP", "REFUTED_BY_RULE", f"a tradução depende de {miss}, fora da guarda", dis)
    smap = {}
    for x in c.loss("sentinel"):
        smap.update({str(k): v for k, v in (x.get("map") or {}).items()})
    for k, meaning in ts.sentinels:
        if k not in smap:
            a.fail("SENTINEL", "REFUTED_BY_RULE", f"sentinela {k}={meaning!r} da origem sem mapeamento declarado", dis)

    # evidência
    _evidence(c, a, dis)
    return a.finish()


def _pred_total(c: Claim, ts: ValueType) -> bool:
    mp = c["membership_predicate"] or {}
    d = ts.domain()
    try:
        P.check(mp.get("expr"))
    except P.PredicateError:
        return False
    if isinstance(d, EnumDomain):
        return all(P.evaluate(mp["expr"], v) for v in d.values)
    if isinstance(d, NumDomain) and d.count() is not None and d.count() <= 100000:
        return all(P.evaluate(mp["expr"], v) for v in d.points())
    return False


def _run_test(c, chain, t, ts, to, a, dis, tkind):
    if "input" not in t or "expected" not in t:
        a.fail("EXACT-TESTS", "UNPROVEN", f"teste sem input/expected: {t}", dis)
        return
    x, exp = t["input"], t["expected"]
    if not ts.admits(x):
        a.fail("EXACT-TESTS", "REFUTED_BY_RULE", f"entrada de teste fora do tipo do sujeito: {x!r}", dis)
        return
    try:
        y = T.apply_lifted(T.chain_of(chain), x, ts, to, t.get("context"))
    except (OutOfDomain, TypeError_) as e:
        a.fail("EXACT-TESTS", "REFUTED_BY_RULE", f"normalização falha no teste {x!r}: {e}", dis)
        return
    if not _same(y, exp):
        a.fail("EXACT-TESTS", "REFUTED_BY_RULE", f"normalização({x!r}) = {y!r}, teste diz {exp!r}", dis)
        return
    if tkind == "tuple":
        if to.datatype == "tuple" and not to.admits(y):
            a.fail("KIND-TUPLE", "REFUTED_BY_RULE", f"saída {y!r} não respeita os tipos dos componentes", dis)
        return
    if ts.is_collection and to.is_collection and ts.datatype == to.datatype and not t.get("lossy"):
        xs = list(x.values()) if isinstance(x, dict) else list(x)
        ys = list(y.values()) if isinstance(y, dict) else list(y)
        for xe, ye in zip(xs, ys):
            _run_test(c, chain, {"input": xe, "expected": ye}, ts.item, to.item, a, dis, tkind)
        return
    if c.relation in TRANSPORTING and ts.quantity_kind not in ("NOT_APPLICABLE", "UNKNOWN") and not ts.kind_unknown() \
            and not to.kind_unknown() and not t.get("lossy"):
        try:
            cs, co = canonical(ts, x, t.get("context", {}).get("calendar_context") if t.get("context") else None), \
                canonical(to, y)
        except OutOfDomain as e:
            a.fail("EXACT-TESTS", "REFUTED_BY_RULE", f"teste fora do domínio: {e}", dis)
            return
        if cs != co:
            rule = ("UNIT-BYTES" if ts.byte_convention != to.byte_convention and ts.byte_convention and to.byte_convention
                    else "UNIT-WINDOW" if ts.rate_window != to.rate_window else "NORM-PRESERVE")
            a.fail(rule, "REFUTED_BY_RULE",
                   f"valor canônico muda: {x!r}{ts.unit} -> {y!r}{to.unit} ({cs} != {co})", dis)


def _same(a, b) -> bool:
    if isinstance(a, dict) and isinstance(b, dict):
        return set(a) == set(b) and all(_same(a[k], b[k]) for k in a)
    return P._eq(a, b)


def _membership(c, rel, ts, to, a, dis):
    mp = c["membership_predicate"]
    if not isinstance(mp, dict) or "expr" not in mp:
        a.fail("BN-PRED", "UNPROVEN", "broad/narrow sem predicado de pertença executável", dis)
        return
    try:
        P.check(mp["expr"])
    except P.PredicateError as e:
        a.fail("BN-PRED", "UNPROVEN", f"predicado não executável: {e}", dis)
        return
    tests = mp.get("tests") or {}
    if not tests.get("members") or not tests.get("non_members"):
        a.fail("BN-PRED", "UNPROVEN", "predicado sem testes de membro e de não membro", dis)
    want = SUBSET_SIDE[rel]
    if mp.get("subset") != want:
        a.fail("SKOS-ORIENT", "REFUTED_BY_RULE",
               f"{c['predicate_id']}: o subconjunto é o {want} (direção SKOS); predicado declara {mp.get('subset')!r}", dis)
        return
    broad_t = to if want == "subject" else ts     # o predicado roda sobre valores do lado mais amplo
    narrow_t = ts if want == "subject" else to
    for v in tests.get("members") or []:
        if not broad_t.admits(v) or not P.evaluate(mp["expr"], v):
            a.fail("BN-PRED-TESTS", "REFUTED_BY_RULE", f"membro {v!r} rejeitado pelo predicado ou fora do tipo", dis)
    for v in tests.get("non_members") or []:
        if not broad_t.admits(v):
            a.fail("BN-PRED-TESTS", "REFUTED_BY_RULE",
                   f"não membro {v!r} fora do tipo do lado mais amplo: teste vazio, não prova nada", dis)
        elif P.evaluate(mp["expr"], v):
            a.fail("BN-PRED-TESTS", "REFUTED_BY_RULE", f"não membro {v!r} aceito pelo predicado", dis)
    # conferência exaustiva quando os domínios são finitos: predicado == pertença à imagem do lado estreito
    img = None
    if want == "subject":
        try:
            img = T.image(c["translation_fn"], narrow_t.domain())
        except (TypeError_, OutOfDomain):
            img = None
    if want == "subject" and img is not None and not isinstance(img, AnyDomain):
        bd = broad_t.domain()
        pts = sorted(bd.values, key=str) if isinstance(bd, EnumDomain) else (
            bd.points() if isinstance(bd, NumDomain) and bd.count() is not None and bd.count() <= 100000 else None)
        if pts is not None:
            for v in pts:
                if P.evaluate(mp["expr"], v) != domain_contains(img, v):
                    a.fail("BN-PRED-TESTS", "REFUTED_BY_RULE",
                           f"predicado em {v!r} != pertença à imagem do lado mais estreito", dis)
                    break
    if want == "object":
        nd, bd = narrow_t.domain(), broad_t.domain()
        pts = sorted(bd.values, key=str) if isinstance(bd, EnumDomain) else (
            bd.points() if isinstance(bd, NumDomain) and bd.count() is not None and bd.count() <= 100000 else None)
        try:
            ich = T.inverse_chain(c["translation_fn"])
        except TypeError_:
            ich = None
        if pts is not None and not isinstance(nd, AnyDomain) and ich is not None:
            img = T.image(ich, nd)
            if not isinstance(img, AnyDomain):
                for v in pts:
                    if P.evaluate(mp["expr"], v) != domain_contains(img, v):
                        a.fail("BN-PRED-TESTS", "REFUTED_BY_RULE",
                               f"predicado em {v!r} != pertença à imagem do lado mais estreito", dis)
                        break


def _fixed_default(c, fd, to, a, dis):
    miss = [k for k in ("kind", "value", "context", "evidence") if k not in fd]
    ev = fd.get("evidence") or {}
    if fd.get("kind") not in ("fixed", "default"):
        miss.append("kind ∈ {fixed, default}")
    if not isinstance(ev, dict) or not _DATE.match(str(ev.get("date", ""))) or not ev.get("source"):
        miss.append("evidence {date ISO, source}")
    ctx = fd.get("context")
    if ctx is not None:
        try:
            G.typecheck(ctx)
            if not ctx.get("all"):
                miss.append("context com ao menos uma condição (região, edição ou versão)")
        except G.GuardTypeError as e:
            miss.append(f"context mal tipado: {e}")
    if miss:
        a.fail("FIXED-DATED", "UNPROVEN", f"{fd.get('kind')}: falta {miss}", dis)
    if to is not None and "value" in fd and not to.admits(fd["value"]):
        a.fail("FIXED-DATED", "REFUTED_BY_RULE", f"valor fixo {fd['value']!r} fora do tipo do destino", dis)


def _evidence(c, a, dis):
    st = c["evidence_state"]
    proof = c["proof"] or {}
    evs = proof.get("evidence") or []
    cited = [e for e in evs if isinstance(e, dict) and e.get("source") and (e.get("sentence") or e.get("observation"))]
    if st not in MEANING_SUPPORT:
        a.fail("EVIDENCE", "UNPROVEN", f"estado de evidência {st!r} não sustenta transporte na leitura primária", dis)
    elif not cited:
        a.fail("EVIDENCE", "UNPROVEN",
               f"{st} sem citação (sentença ou observação); leitura de volta não promove significado", dis)
    if c["basis"] == "shared_concept":
        anchors = c["anchors"] or []
        bad = [x for x in anchors if (x or {}).get("evidence_state") not in ("DOC_SUPPORTED", "OBSERVATION_TESTED")]
        if len(anchors) != 2 or bad:
            a.fail("ANCHOR-NOT-PROOF", "UNPROVEN",
                   "mesmo conceito do glossário não prova: as duas âncoras precisam de DOC_SUPPORTED", dis)


def check_set(claims: list[Claim | dict], disabled=frozenset()) -> list[dict]:
    """Regra de conjunto SKOS-DISJ: exactMatch é disjunta de broadMatch e relatedMatch (SKOS Reference S46),
    para o mesmo par, sob guardas que podem valer juntas. Saída: [{claim_ids, rule, verdict: CONTESTED}]."""
    if "SKOS-DISJ" in disabled:
        return []
    cs = [c if isinstance(c, Claim) else Claim(c) for c in claims]
    out = []
    for i, x in enumerate(cs):
        for y in cs[i + 1:]:
            pair_x = (x["subject_id"], x["object_id"])
            same = pair_x == (y["subject_id"], y["object_id"])
            rev = pair_x == (y["object_id"], y["subject_id"])
            if not (same or rev):
                continue
            rels = {x.relation, y.relation if same else {"broad": "narrow", "narrow": "broad"}.get(y.relation, y.relation)}
            if "exact" in rels and rels & {"broad", "narrow", "related"}:
                gy = y.guard if same else G.flip(y.guard)
                try:
                    sat, _ = G.satisfiable(G.conj(x.guard, gy))
                except G.GuardTypeError:
                    sat = G.UNKNOWN
                if sat != G.UNSAT:
                    out.append({"claim_ids": [x.id, y.id], "rule": "SKOS-DISJ", "verdict": "CONTESTED",
                                "detail": f"{sorted(rels)} no mesmo par com guardas compatíveis ({sat})"})
    return out
