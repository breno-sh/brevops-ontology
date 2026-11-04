"""Bateria plantada do árbitro: um mundo K4 sintético (provedores pa, pb, pc, pd) com estrutura válida e
conflitos plantados, e um conjunto isolado de alegações sem prova (gate unproven).

São fixtures da TEORIA, não fatos sobre provedores: evidência sintética (fonte 'fixture:'), nomes neutros.
Cada caso declara o veredito esperado e a regra que tem de aparecer. Estrutura válida (1:N, N:1, N:M, campo
para vários conceitos, várias ocorrências, grupo cruzando facetas, alternativas exclusivas, close∘close sem
fecho, guardas exclusivas no mesmo par, duplicata) NÃO pode sair CONTESTED.
"""

from __future__ import annotations

import copy

from bo.semantics.content import examples as E

T, UC, EM = E.T, E.UC, E.EM
DOC = E.DOC
IDN = {"name": "identity", "params": {}}
STR = T("string", quantity_kind="NOT_APPLICABLE", unit="NOT_APPLICABLE")


def NA(t):
    t = dict(t)
    t.setdefault("quantity_kind", "NOT_APPLICABLE")
    t.setdefault("unit", "NOT_APPLICABLE")
    return t


def ENUM(*v):
    return NA(T("enum", enum=list(v)))


BOOL = NA(T("boolean"))
DAYS = lambda lo, hi: T("integer", quantity_kind="quantitykind:Time", unit="unit:DAY", range={"min": lo, "max": hi})
HOURS = lambda lo, hi: T("integer", quantity_kind="quantitykind:Time", unit="unit:HR", range={"min": lo, "max": hi})
MINS = lambda lo, hi: T("integer", quantity_kind="quantitykind:Time", unit="unit:MIN", range={"min": lo, "max": hi})
SECS = lambda lo, hi: T("integer", quantity_kind="quantitykind:Time", unit="unit:SEC", range={"min": lo, "max": hi})
INT = lambda lo, hi: NA(T("integer", range={"min": lo, "max": hi}))
STD = [{"term": "object.edition", "op": "edition_in", "value": ["standard"]}]
PREM = [{"term": "object.edition", "op": "edition_in", "value": ["premium"]}]
BOTH = [{"term": "object.edition", "op": "edition_in", "value": ["standard", "premium"]}]


def C(cid, s, rel, o, st, ot, fn, vdr, fid, **kw):
    r = E.claim(cid, s, rel, o, st, ot, fn, vdr, fid, **kw)
    r["proof"]["evidence"] = copy.deepcopy(DOC)
    return r


def comp(name, ty):
    return {"name": name, "type": ty}


def TUP(*comps):
    return {"datatype": "tuple", "quantity_kind": "NOT_APPLICABLE", "unit": "NOT_APPLICABLE", "components": list(comps)}


def G(cid, s, o, group, st, ot, tests, rel="exact", fid="partial", **kw):
    r = C(cid, s, rel, o, st, ot, None, "unknown", fid, **kw)
    r.pop("translation_fn", None)
    r["bo_group_id"] = group["bo_group_id"]
    r["group"] = group
    r["proof"] = {"type": "group_execution", "evidence": copy.deepcopy(DOC), "tests": tests}
    return r


def P(pid, field, extractor, concept, ty, tests, scope="resource", keys=None, overlaps=None):
    p = {"projection_id": pid, "field": field, "occurrence": {"scope": scope}, "extractor": extractor,
         "concept": concept, "type": ty, "tests": tests}
    if keys:
        p["occurrence"]["key_fields"] = keys
    if overlaps:
        p["overlaps"] = overlaps
    return p


ALARM = "load_avg[5m].max() >= 3"
REDRIVE = '{"deadLetterTargetRef": "queue_dlq", "maxReceiveCount": 5}'


# ================================================================================== estrutura válida
def valid_cases() -> list[dict]:
    cases = []

    # K4 de retenção: dias, horas, minutos, segundos; as 6 arestas, todas exact sem perda e consistentes
    t = {"pa": DAYS(1, 30), "pb": HOURS(1, 720), "pc": MINS(1, 43200), "pd": SECS(1, 2592000)}
    u = {"pa": "unit:DAY", "pb": "unit:HR", "pc": "unit:MIN", "pd": "unit:SEC"}
    f = {"pa": 86400, "pb": 3600, "pc": 60, "pd": 1}
    ks = []
    for a, b in (("pa", "pb"), ("pa", "pc"), ("pa", "pd"), ("pb", "pc"), ("pb", "pd"), ("pc", "pd")):
        x = 2
        ks.append(C(f"K4-{a[1].upper()}{b[1].upper()}", f"{a}:k4.retention", "exact", f"{b}:k4.retention",
                    t[a], t[b], UC(u[a], u[b]), "subset", "lossless",
                    tests=[{"input": x, "expected": x * f[a] // f[b]}],
                    subject_concept="concept:retention_period", object_concept="concept:retention_period"))
    cases.append({"case": "k4_exact_consistente", "claims": ks, "expect": {c["claim_id"]: "OK" for c in ks},
                  "why": "6 arestas exact consistentes: todo composto confere com a direta"})

    # K4 com broad: arquivamento (2 valores) ⊂ classe (4 valores), classe = classe; broad∘exact = broad
    br = [C("K4B-AB", "pa:k4b.archive", "broad", "pb:k4b.class", ENUM("deep", "flex"), ENUM("std", "near", "cold", "arch"),
            EM({"deep": "arch", "flex": "cold"}), "subset", "lossless", tests=[{"input": "deep", "expected": "arch"}],
            membership_predicate={"subset": "subject", "expr": {"op": "in", "values": ["cold", "arch"]},
                                  "tests": {"members": ["arch"], "non_members": ["std"]}}),
          C("K4B-BC", "pb:k4b.class", "exact", "pc:k4b.class", ENUM("std", "near", "cold", "arch"), ENUM("S", "N", "C", "A"),
            EM({"std": "S", "near": "N", "cold": "C", "arch": "A"}), "equal", "lossless",
            tests=[{"input": "arch", "expected": "A"}]),
          C("K4B-AC", "pa:k4b.archive", "broad", "pc:k4b.class", ENUM("deep", "flex"), ENUM("S", "N", "C", "A"),
            EM({"deep": "A", "flex": "C"}), "subset", "lossless", tests=[{"input": "deep", "expected": "A"}],
            membership_predicate={"subset": "subject", "expr": {"op": "in", "values": ["C", "A"]},
                                  "tests": {"members": ["A"], "non_members": ["S"]}})]
    cases.append({"case": "k4_broad_consistente", "claims": br, "expect": {c["claim_id"]: "OK" for c in br},
                  "why": "broad∘exact = broad pela tabela; a direta broad confere"})

    # 1:N — uma consulta de alarme -> cinco atributos do destino (grupo, uma alegação)
    g1 = {"bo_group_id": "GRP-B1N", "cardinality": "1:N",
          "variables": [{"name": "?q", "side": "subject", "field": "pa:g1n.alarm.query", "occurrence": "?al"},
                        {"name": "?metric", "side": "object", "field": "pb:g1n.alarm.metric", "occurrence": "?bl"},
                        {"name": "?op", "side": "object", "field": "pb:g1n.alarm.comparison", "occurrence": "?bl"},
                        {"name": "?thr", "side": "object", "field": "pb:g1n.alarm.threshold", "occurrence": "?bl"},
                        {"name": "?win", "side": "object", "field": "pb:g1n.alarm.period", "occurrence": "?bl"},
                        {"name": "?stat", "side": "object", "field": "pb:g1n.alarm.statistic", "occurrence": "?bl"}],
          "occurrence_vars": ["?al", "?bl"], "joins": [],
          "steps": [{"name": "split_alarm_query", "inputs": {"query": "?q"},
                     "outputs": {"metric": "?metric", "operator": "?op", "threshold": "?thr", "window": "?win",
                                 "statistic": "?stat"}}]}
    win = T("duration", quantity_kind="quantitykind:Time", unit="NOT_APPLICABLE")
    gc = [G("G-1N", "pa:g1n.alarm.query", "pb:g1n.alarm.metric", g1, TUP(comp("q", STR)),
            TUP(comp("metric", STR), comp("op", ENUM("gt", "ge", "lt", "le", "eq", "ne")), comp("thr", NA(T("decimal"))),
                comp("win", win), comp("stat", ENUM("mean", "max", "min", "sum", "count"))),
            [{"input": {"?q": ALARM}, "expected": {"?metric": "load_avg", "?op": "ge", "?thr": 3, "?win": "PT5M",
                                                   "?stat": "max"}}])]
    # N:1 cruzando facetas — endereço (faceta de rede) + prefixo (faceta de sub-rede) -> CIDR
    gn1 = {"bo_group_id": "GRP-BN1", "cardinality": "N:1",
           "variables": [{"name": "?addr", "side": "subject", "field": "pa:gn1.network.base_address", "occurrence": "?n"},
                         {"name": "?plen", "side": "subject", "field": "pa:gn1.subnet_sizing.prefix_length", "occurrence": "?s"},
                         {"name": "?cidr", "side": "object", "field": "pb:gn1.subnet.cidr", "occurrence": "?b"}],
           "occurrence_vars": ["?n", "?s", "?b"], "joins": [{"left": "?s", "right": "?n", "via": "facet_of"}],
           "steps": [{"name": "join_cidr", "inputs": {"address": "?addr", "prefix_length": "?plen"},
                      "outputs": {"cidr": "?cidr"}}]}
    gc.append(G("G-N1", "pa:gn1.network.base_address", "pb:gn1.subnet.cidr", gn1,
                TUP(comp("addr", STR), comp("plen", INT(0, 32))), TUP(comp("cidr", STR)),
                [{"input": {"?addr": "10.0.0.0", "?plen": 16}, "expected": {"?cidr": "10.0.0.0/16"}}]))
    # N:M — (protocolo, porta inicial, porta final) de cada regra -> (protocolo, faixa) de cada permissão,
    # campos em bloco repetido com a ocorrência identificada por campos-chave (várias ocorrências)
    gnm = {"bo_group_id": "GRP-BNM", "cardinality": "N:M",
           "variables": [{"name": "?proto", "side": "subject", "field": "pa:gnm.rule.protocol", "occurrence": "?r"},
                         {"name": "?from", "side": "subject", "field": "pa:gnm.rule.from_port", "occurrence": "?r"},
                         {"name": "?to", "side": "subject", "field": "pa:gnm.rule.to_port", "occurrence": "?r"},
                         {"name": "?proto_b", "side": "object", "field": "pb:gnm.allow.protocol", "occurrence": "?a"},
                         {"name": "?ports", "side": "object", "field": "pb:gnm.allow.ports", "occurrence": "?a"}],
           "occurrence_vars": ["?r", "?a"], "joins": [],
           "steps": [{"name": "identity", "inputs": {"value": "?proto"}, "outputs": {"value": "?proto_b"}},
                     {"name": "join_port_range", "inputs": {"from_port": "?from", "to_port": "?to"},
                      "outputs": {"ports": "?ports"}}]}
    rk = ["protocol", "from_port", "to_port"]
    ak = ["protocol", "ports"]
    projs = [P("PRJ-NM-proto", "pa:gnm.rule.protocol", {"name": "identity"}, "concept:rule_protocol", STR,
               [{"input": "tcp", "expected": "tcp"}], "block", rk),
             P("PRJ-NM-from", "pa:gnm.rule.from_port", {"name": "identity"}, "concept:port_from", INT(0, 65535),
               [{"input": 80, "expected": 80}], "block", rk),
             P("PRJ-NM-to", "pa:gnm.rule.to_port", {"name": "identity"}, "concept:port_to", INT(0, 65535),
               [{"input": 443, "expected": 443}], "block", rk),
             P("PRJ-NM-bproto", "pb:gnm.allow.protocol", {"name": "identity"}, "concept:rule_protocol", STR,
               [{"input": "tcp", "expected": "tcp"}], "block", ak),
             P("PRJ-NM-ports", "pb:gnm.allow.ports", {"name": "identity"}, "concept:port_range", STR,
               [{"input": "80-443", "expected": "80-443"}], "block", ak)]
    gc.append(G("G-NM", "pa:gnm.rule.protocol", "pb:gnm.allow.protocol", gnm,
                TUP(comp("proto", STR), comp("from", INT(0, 65535)), comp("to", INT(0, 65535))),
                TUP(comp("proto_b", STR), comp("ports", STR)),
                [{"input": {"?proto": "tcp", "?from": 80, "?to": 443}, "expected": {"?proto_b": "tcp", "?ports": "80-443"}},
                 {"input": {"?proto": "udp", "?from": 53, "?to": 53}, "expected": {"?proto_b": "udp", "?ports": "53"}}],
                projection=projs))
    # outra ocorrência do mesmo bloco repetido, identificada pela mesma chave, em alegação escalar separada
    gc.append(C("OCC-DESC", "pa:gnm.rule.description", "exact", "pb:gnm.allow.description", STR, STR, IDN, "unknown",
                "partial", tests=[{"input": "web", "expected": "web"}],
                projection=[P("PRJ-NM-desc", "pa:gnm.rule.description", {"name": "identity"}, "bo:UNGLOSSED", STR,
                              [{"input": "web", "expected": "web"}], "block", rk),
                            P("PRJ-NM-bdesc", "pb:gnm.allow.description", {"name": "identity"}, "bo:UNGLOSSED", STR,
                              [{"input": "web", "expected": "web"}], "block", ak)]))
    cases.append({"case": "grupos_1N_N1_NM_ocorrencias", "claims": gc, "expect": {c["claim_id"]: "OK" for c in gc},
                  "why": "1:N, N:1 cruzando facetas, N:M em bloco repetido com chave de ocorrência"})

    # um campo, vários conceitos: a consulta alimenta três atributos de pc (partes distintas) e o mesmo
    # componente vai a dois conceitos de pd com a sobreposição declarada; o documento JSON dá dois conceitos
    q = "pa:mc.alarm.query"

    def part(pid, c_, ty, val, concept, ov=None):
        return P(pid, q, {"name": "split_alarm_query", "component": c_}, concept, ty, [{"input": ALARM, "expected": val}],
                 overlaps=ov)
    mc = []
    for cid, c_, ty, val, concept, tgt in (("MC-METRIC", "metric", STR, "load_avg", "concept:alarm_metric", "pc:mc.metric"),
                                           ("MC-THR", "threshold", NA(T("decimal")), 3, "concept:alarm_threshold", "pc:mc.threshold"),
                                           ("MC-OP", "operator", ENUM("gt", "ge", "lt", "le", "eq", "ne"), "ge",
                                            "concept:alarm_operator", "pc:mc.operator")):
        mc.append(C(cid, q, "exact", tgt, STR, ty, {"name": "split_alarm_query", "params": {}}, "unknown", "partial",
                    tests=[{"input": ALARM, "expected": val}], subject_concept=concept, object_concept=concept,
                    projection=[part(f"PRJ-{cid}", c_, ty, val, concept)]))
    mc.append(C("MC-PD-NAME", q, "exact", "pd:mc.metric_name", STR, STR, IDN, "unknown", "partial",
                tests=[{"input": ALARM, "expected": "load_avg"}], subject_concept="concept:alarm_metric",
                object_concept="concept:alarm_metric",
                projection=[part("PRJ-MC-M1", "metric", STR, "load_avg", "concept:alarm_metric", ["PRJ-MC-M2"])]))
    mc.append(C("MC-PD-LABEL", q, "exact", "pd:mc.metric_label", STR, STR, IDN, "unknown", "partial",
                tests=[{"input": ALARM, "expected": "load_avg"}], subject_concept="concept:metric_label",
                object_concept="concept:metric_label",
                projection=[part("PRJ-MC-M2", "metric", STR, "load_avg", "concept:metric_label", ["PRJ-MC-M1"])]))
    rd = "pa:mc.queue.redrive"
    for cid, key, ty, val, concept, tgt in (("MC-DLQ", "deadLetterTargetRef", STR, "queue_dlq", "concept:dead_letter_target",
                                             "pb:mc.dlq_target"),
                                            ("MC-MAXRC", "maxReceiveCount", T("integer", quantity_kind="quantitykind:Count",
                                                                            unit="unit:NUM", range={"min": 1, "max": 1000}),
                                             5, "concept:max_receive_count", "pb:mc.max_receive")):
        mc.append(C(cid, rd, "exact", tgt, STR, ty, IDN, "unknown", "partial", tests=[{"input": REDRIVE, "expected": val}],
                    subject_concept=concept, object_concept=concept,
                    projection=[P(f"PRJ-{cid}", rd, {"name": "json_get", "params": {"key": key}}, concept, ty,
                                  [{"input": REDRIVE, "expected": val}])]))
    cases.append({"case": "campo_varios_conceitos", "claims": mc, "expect": {c["claim_id"]: "OK" for c in mc},
                  "why": "projeções por ocorrência; mesma parte em dois conceitos com sobreposição declarada"})

    # alternativas com guardas exclusivas (edição): realizações múltiplas provadas exclusivas
    alt = [C("ALT-STD", "pa:alt.versioning", "exact", "pb:alt.versioning_mode", ENUM("enabled", "suspended"),
             ENUM("enabled", "suspended"), IDN, "equal", "lossless", tests=[{"input": "enabled", "expected": "enabled"}],
             guard={"all": STD}, alternative_to=["ALT-PREM"], exclusivity="ProvenExclusive",
             subject_concept="concept:object_versioning", object_concept="concept:object_versioning"),
           C("ALT-PREM", "pa:alt.versioning", "close", "pb:alt.retention_lock", ENUM("enabled", "suspended"), BOOL,
             EM({"enabled": True, "suspended": False}), "equal", "declared_loss",
             loss_contract=[{"kind": "semantic", "values": ["suspended"], "what": "suspenso e nunca ativado caem em false"}],
             tests=[{"input": "enabled", "expected": True}], guard={"all": PREM}, alternative_to=["ALT-STD"],
             exclusivity="ProvenExclusive", subject_concept="concept:object_versioning")]
    cases.append({"case": "alternativas_exclusivas", "claims": alt, "expect": {c["claim_id"]: "OK" for c in alt},
                  "why": "duas realizações do mesmo alvo com interseção de guardas UNSAT"})

    # close∘close não compõe por fecho: o composto close∘close (e close∘close pela inversa) é ⊥ na tabela, então
    # a direta close pa→pc, cujo valor difere do que um fecho de closeMatch daria, não é contestada
    cc = [C("CC-AB", "pa:cc.versioning", "close", "pb:cc.versioning", ENUM("Enabled", "Suspended"), BOOL,
            EM({"Enabled": True, "Suspended": False}), "equal", "declared_loss",
            loss_contract=[{"kind": "semantic", "values": ["Suspended"], "what": "suspenso preserva versões; falso não diz isso"}],
            tests=[{"input": "Enabled", "expected": True}]),
          C("CC-BC", "pb:cc.versioning", "close", "pc:cc.versioning", BOOL, ENUM("on", "paused"),
            EM({"true": "on", "false": "paused"}), "equal", "declared_loss",
            loss_contract=[{"kind": "semantic", "values": [False], "what": "pausado mantém regras de ciclo de vida"}],
            tests=[{"input": True, "expected": "on"}]),
          C("CC-AC", "pa:cc.versioning", "close", "pc:cc.versioning", ENUM("Enabled", "Suspended"), ENUM("on", "paused"),
            EM({"Enabled": "paused", "Suspended": "on"}), "equal", "declared_loss",
            loss_contract=[{"kind": "semantic", "values": ["Enabled", "Suspended"], "what": "modos com regras diferentes"}],
            tests=[{"input": "Enabled", "expected": "paused"}])]
    cases.append({"case": "close_nao_compoe", "claims": cc, "expect": {c["claim_id"]: "OK" for c in cc},
                  "why": "close∘close = ⊥ na tabela: nada a conferir contra a direta (sem fecho de closeMatch)"})

    # mesmo par com guardas exclusivas e funções diferentes: válido (uma por edição)
    gp = [C("PAIRG-STD", "pa:pg.mode", "exact", "pb:pg.mode", ENUM("a", "b"), ENUM("p", "q"), EM({"a": "p", "b": "q"}),
            "equal", "lossless", tests=[{"input": "a", "expected": "p"}], guard={"all": STD}),
          C("PAIRG-PREM", "pa:pg.mode", "exact", "pb:pg.mode", ENUM("a", "b"), ENUM("p", "q"), EM({"a": "q", "b": "p"}),
            "equal", "lossless", tests=[{"input": "a", "expected": "q"}], guard={"all": PREM})]
    cases.append({"case": "mesmo_par_guardas_exclusivas", "claims": gp, "expect": {c["claim_id"]: "OK" for c in gp},
                  "why": "funções diferentes sob edições disjuntas não se contradizem"})

    # comportamento fixo do destino, datado; e duplicata exata (relatada, não contestada)
    fx = copy.deepcopy(E.FIXED_ENCRYPTION)
    fx.update(claim_id="FIX-ENC", claim_version_id="FIX-ENC@1", event_id="EV-FIX-ENC", subject_id="pa:fx.encryption",
              object_id="pb:fx.encryption_fixed", subject_value_type=BOOL, object_value_type=BOOL)
    d1 = C("DUP-1", "pa:dup.size", "exact", "pb:dup.size", INT(1, 10), INT(1, 10), IDN, "equal", "lossless",
           tests=[{"input": 3, "expected": 3}])
    d2 = copy.deepcopy(d1)
    d2.update(claim_id="DUP-2", claim_version_id="DUP-2@1", event_id="EV-DUP-2")
    cases.append({"case": "fixo_e_duplicata", "claims": [fx, d1, d2],
                  "expect": {"FIX-ENC": "OK", "DUP-1": "OK", "DUP-2": "OK"},
                  "why": "fixo com valor, contexto e evidência datados; duplicata vai ao relatório"})
    return cases


# =================================================================================== conflitos plantados
def conflict_cases() -> list[dict]:
    cases = []
    x1 = [C("X1-EXACT", "pa:x1.cls", "exact", "pb:x1.cls", ENUM("a", "b"), ENUM("p", "q", "r"), EM({"a": "p", "b": "q"}),
            "subset", "lossless", tests=[{"input": "a", "expected": "p"}]),
          C("X1-BROAD", "pa:x1.cls", "broad", "pb:x1.cls", ENUM("a", "b"), ENUM("p", "q", "r"), EM({"a": "p", "b": "q"}),
            "subset", "lossless", tests=[{"input": "a", "expected": "p"}],
            membership_predicate={"subset": "subject", "expr": {"op": "in", "values": ["p", "q"]},
                                  "tests": {"members": ["p"], "non_members": ["r"]}})]
    cases.append({"case": "skos_disj", "claims": x1, "expect": {"X1-EXACT": "CONTESTED", "X1-BROAD": "CONTESTED"},
                  "rule": "SKOS-DISJ"})

    x2 = [C("X2-AB", "pa:x2.tier", "exact", "pb:x2.tier", ENUM("t1", "t2"), ENUM("u1", "u2"), EM({"t1": "u1", "t2": "u2"}),
            "equal", "lossless", tests=[{"input": "t1", "expected": "u1"}]),
          C("X2-BC", "pb:x2.tier", "exact", "pc:x2.tier", ENUM("u1", "u2"), ENUM("v1", "v2"), EM({"u1": "v1", "u2": "v2"}),
            "equal", "lossless", tests=[{"input": "u1", "expected": "v1"}]),
          C("X2-AC", "pa:x2.tier", "exact", "pc:x2.tier", ENUM("t1", "t2"), ENUM("v1", "v2"), EM({"t1": "v2", "t2": "v1"}),
            "equal", "lossless", tests=[{"input": "t1", "expected": "v2"}])]
    cases.append({"case": "k4_valor", "claims": x2, "expect": {c["claim_id"]: "CONTESTED" for c in x2},
                  "rule": "ARB-K4-VALUE"})

    x3 = [C("X3-AB", "pa:x3.cls", "exact", "pb:x3.cls", ENUM("x", "y"), ENUM("m", "n"), EM({"x": "m", "y": "n"}),
            "equal", "lossless", tests=[{"input": "x", "expected": "m"}]),
          C("X3-BC", "pb:x3.cls", "exact", "pc:x3.cls", ENUM("m", "n"), ENUM("p", "q", "r"), EM({"m": "p", "n": "q"}),
            "subset", "lossless", tests=[{"input": "m", "expected": "p"}]),
          C("X3-AC", "pa:x3.cls", "broad", "pc:x3.cls", ENUM("x", "y"), ENUM("p", "q", "r"), EM({"x": "p", "y": "q"}),
            "subset", "lossless", tests=[{"input": "x", "expected": "p"}],
            membership_predicate={"subset": "subject", "expr": {"op": "in", "values": ["p", "q"]},
                                  "tests": {"members": ["p"], "non_members": ["r"]}})]
    cases.append({"case": "k4_relacao", "claims": x3, "expect": {c["claim_id"]: "CONTESTED" for c in x3},
                  "rule": "ARB-K4-REL"})

    gib = T("integer", quantity_kind="quantitykind:InformationEntropy", unit="unit:GibiBYTE", range={"min": 1, "max": 64})
    gb = T("integer", quantity_kind="quantitykind:InformationEntropy", unit="unit:GigaBYTE", range={"min": 1, "max": 64})
    x4 = [C("X4-AB", "pa:x4.size", "exact", "pb:x4.size", gib, gib, IDN, "equal", "lossless", tests=[{"input": 8, "expected": 8}]),
          C("X4-CB", "pc:x4.size", "exact", "pb:x4.size", gb, gb, IDN, "equal", "lossless", tests=[{"input": 8, "expected": 8}])]
    cases.append({"case": "tipo_do_atomo", "claims": x4, "expect": {"X4-AB": "CONTESTED", "X4-CB": "CONTESTED"},
                  "rule": "ARB-ATOM-TYPE"})
    x4r = [C("X4R-1", "pa:x4r.n", "exact", "pb:x4r.n", INT(1, 50), INT(1, 100), IDN, "subset", "lossless",
             tests=[{"input": 5, "expected": 5}]),
           C("X4R-2", "pc:x4r.n", "exact", "pb:x4r.n", INT(1, 50), INT(1, 50), IDN, "equal", "lossless",
             tests=[{"input": 5, "expected": 5}])]
    cases.append({"case": "dominio_do_atomo", "claims": x4r, "expect": {"X4R-1": "CONTESTED", "X4R-2": "CONTESTED"},
                  "rule": "ARB-ATOM-TYPE"})

    x5 = [C("X5-1", "pa:x5.mode", "exact", "pb:x5.mode", ENUM("a", "b"), ENUM("p", "q"), EM({"a": "p", "b": "q"}),
            "equal", "lossless", tests=[{"input": "a", "expected": "p"}]),
          C("X5-2", "pa:x5.mode", "exact", "pb:x5.mode", ENUM("a", "b"), ENUM("p", "q"), EM({"a": "q", "b": "p"}),
            "equal", "lossless", tests=[{"input": "a", "expected": "q"}])]
    cases.append({"case": "mesmo_par_valor", "claims": x5, "expect": {"X5-1": "CONTESTED", "X5-2": "CONTESTED"},
                  "rule": "ARB-PAIR-VALUE"})

    s3 = ENUM("s1", "s2", "s3")
    x5r = [C("X5R-B", "pa:x5r.cls", "broad", "pb:x5r.cls", s3, ENUM("p", "q"), EM({"s1": "p", "s2": "p", "s3": "p"}),
             "subset", "lossless", tests=[{"input": "s1", "expected": "p"}],
             membership_predicate={"subset": "subject", "expr": {"op": "in", "values": ["p"]},
                                   "tests": {"members": ["p"], "non_members": ["q"]}}),
           C("X5R-N", "pa:x5r.cls", "narrow", "pb:x5r.cls", s3, ENUM("p", "q"), EM({"s1": "p", "s2": "q"}),
             "superset", "partial", tests=[{"input": "s1", "expected": "p"}],
             membership_predicate={"subset": "object", "expr": {"op": "in", "values": ["s1", "s2"]},
                                   "tests": {"members": ["s1"], "non_members": ["s3"]}})]
    cases.append({"case": "mesmo_par_inclusoes_opostas", "claims": x5r,
                  "expect": {"X5R-B": "CONTESTED", "X5R-N": "CONTESTED"}, "rule": "ARB-PAIR-REL"})

    q = "pa:x6.alarm.query"
    x6 = [C(cid, q, "exact", tgt, STR, STR, IDN, "unknown", "partial", tests=[{"input": ALARM, "expected": "load_avg"}],
            subject_concept=concept, object_concept=concept,
            projection=[P(f"PRJ-{cid}", q, {"name": "split_alarm_query", "component": "metric"}, concept, STR,
                          [{"input": ALARM, "expected": "load_avg"}])])
          for cid, tgt, concept in (("X6-NAME", "pc:x6.metric", "concept:alarm_metric"),
                                    ("X6-LABEL", "pc:x6.label", "concept:metric_label"))]
    cases.append({"case": "sobreposicao_nao_declarada", "claims": x6,
                  "expect": {"X6-NAME": "REFUTED_BY_RULE", "X6-LABEL": "REFUTED_BY_RULE"}, "rule": "P-OVERLAP"})
    x6b = [C(cid, "pa:x6b.field", "exact", tgt, STR, STR, IDN, "unknown", "partial", tests=[{"input": "v", "expected": "v"}],
             subject_concept=concept, object_concept=concept)
           for cid, tgt, concept in (("X6B-1", "pb:x6b.one", "concept:first_use"), ("X6B-2", "pb:x6b.two", "concept:second_use"))]
    cases.append({"case": "varios_conceitos_sem_projecao", "claims": x6b,
                  "expect": {"X6B-1": "REFUTED_BY_RULE", "X6B-2": "REFUTED_BY_RULE"}, "rule": "ARB-PROJ-DECL"})

    x7 = [C(cid, "pa:x7.encryption", "exact", tgt, BOOL, BOOL, IDN, "equal", "lossless",
            tests=[{"input": True, "expected": True}])
          for cid, tgt in (("X7-A", "pb:x7.encryption_a"), ("X7-B", "pb:x7.encryption_b"))]
    cases.append({"case": "realizacoes_ambiguas", "claims": x7, "expect": {"X7-A": "AMBIGUOUS", "X7-B": "AMBIGUOUS"},
                  "rule": "ARB-REAL-MULTI"})
    x7b = [C("X7B-STD", "pa:x7b.mode", "exact", "pb:x7b.mode_a", ENUM("on", "off"), ENUM("on", "off"), IDN, "equal",
             "lossless", tests=[{"input": "on", "expected": "on"}], guard={"all": STD}, alternative_to=["X7B-ANY"],
             exclusivity="ProvenExclusive"),
           C("X7B-ANY", "pa:x7b.mode", "exact", "pb:x7b.mode_b", ENUM("on", "off"), ENUM("on", "off"), IDN, "equal",
             "lossless", tests=[{"input": "on", "expected": "on"}], guard={"all": BOTH}, alternative_to=["X7B-STD"],
             exclusivity="ProvenExclusive")]
    cases.append({"case": "exclusividade_sem_prova", "claims": x7b,
                  "expect": {"X7B-STD": "REFUTED_BY_RULE", "X7B-ANY": "REFUTED_BY_RULE"}, "rule": "A-EXCL"})
    x7c = [C("X7C-1", "pa:x7c.mode", "exact", "pb:x7c.mode_a", ENUM("on", "off"), ENUM("on", "off"), IDN, "equal",
             "lossless", tests=[{"input": "on", "expected": "on"}], guard={"all": STD}, alternative_to=["X7C-2"],
             exclusivity="ProvenExclusive"),
           C("X7C-2", "pa:x7c.mode", "exact", "pb:x7c.mode_b", ENUM("on", "off"), ENUM("on", "off"), IDN, "equal",
             "lossless", tests=[{"input": "on", "expected": "on"}], guard={"all": PREM})]
    cases.append({"case": "alternativa_nao_mutua", "claims": x7c, "expect": {"X7C-1": "REFUTED_BY_RULE"},
                  "rule": "ARB-ALT-MUTUAL"})

    def grp(gid, variables, steps, occ, joins=()):
        return {"bo_group_id": gid, "cardinality": "N:1", "variables": variables, "occurrence_vars": occ,
                "joins": list(joins), "steps": steps}
    vs = [{"name": "?a", "side": "subject", "field": "pa:x8.from_port", "occurrence": "?r"},
          {"name": "?b", "side": "subject", "field": "pa:x8.to_port", "occurrence": "?r"},
          {"name": "?out", "side": "object", "field": "pb:x8.ports", "occurrence": "?o"}]
    st = TUP(comp("a", INT(0, 65535)), comp("b", INT(0, 65535)))
    ot = TUP(comp("out", STR))
    tst = [{"input": {"?a": 80, "?b": 443}, "expected": {"?out": "80-443"}}]
    x8 = [G("X8-UNBOUND", "pa:x8.from_port", "pb:x8.ports",
            grp("GRP-X8U", vs, [{"name": "join_port_range", "inputs": {"from_port": "?a", "to_port": "?zz"},
                                 "outputs": {"ports": "?out"}}], ["?r", "?o"]), st, ot, tst),
          G("X8-DUPOUT", "pa:x8.from_port", "pb:x8.ports",
            grp("GRP-X8D", vs, [{"name": "join_port_range", "inputs": {"from_port": "?a", "to_port": "?b"},
                                 "outputs": {"ports": "?out"}},
                                {"name": "identity", "inputs": {"value": "?a"}, "outputs": {"value": "?out"}}],
                ["?r", "?o"]), st, ot, tst),
          G("X8-ARITY", "pa:x8.from_port", "pb:x8.ports",
            grp("GRP-X8A", vs, [{"name": "join_port_range", "inputs": {"from_port": "?a"}, "outputs": {"ports": "?out"}},
                                {"name": "identity", "inputs": {"value": "?b"}, "outputs": {"value": "?out"}}],
                ["?r", "?o"]), st, ot, tst),
          G("X8-OCC", "pa:x8.from_port", "pb:x8.ports",
            grp("GRP-X8O", [dict(vs[0]), dict(vs[1], occurrence="?r2"), vs[2]],
                [{"name": "join_port_range", "inputs": {"from_port": "?a", "to_port": "?b"},
                  "outputs": {"ports": "?out"}}], ["?r", "?r2", "?o"]), st, ot, tst)]
    for c in x8:
        c["object_id"] = c["object_id"] + "." + c["claim_id"].lower()
        c["group"]["variables"][-1]["field"] = c["object_id"]
    cases.append({"case": "grupos_mal_formados", "claims": x8,
                  "expect": {"X8-UNBOUND": "REFUTED_BY_RULE", "X8-DUPOUT": "REFUTED_BY_RULE",
                             "X8-ARITY": "REFUTED_BY_RULE", "X8-OCC": "REFUTED_BY_RULE"},
                  "rules": {"X8-UNBOUND": "G-VARS", "X8-DUPOUT": "ARB-G-DUP", "X8-ARITY": "G-ARITY", "X8-OCC": "G-OCC"}})

    good = grp("GRP-X9", [dict(v) for v in vs[:2]] + [dict(vs[2], field="pb:x9.ports")],
               [{"name": "join_port_range", "inputs": {"from_port": "?a", "to_port": "?b"}, "outputs": {"ports": "?out"}}],
               ["?r", "?o"])
    for v in good["variables"][:2]:
        v["field"] = v["field"].replace("x8", "x9")
    other = copy.deepcopy(good)
    other["cardinality"] = "N:1"
    other["joins"] = [{"left": "?r", "right": "?o", "via": "reference"}]
    x9 = [G("X9-1", "pa:x9.from_port", "pb:x9.ports", good, st, ot, tst),
          G("X9-2", "pa:x9.from_port", "pb:x9.ports", other, st, ot, tst)]
    cases.append({"case": "grupo_inconsistente", "claims": x9,
                  "expect": {"X9-1": "REFUTED_BY_RULE", "X9-2": "REFUTED_BY_RULE"}, "rule": "ARB-G-CONSIST"})

    cidr = "pa:x10.rule.cidr"
    x10 = [C("X10-KEYED", cidr, "exact", "pb:x10.allow.cidr", STR, STR, IDN, "unknown", "partial",
             tests=[{"input": "10.0.0.0/8", "expected": "10.0.0.0/8"}],
             projection=[P("PRJ-X10", cidr, {"name": "identity"}, "bo:UNGLOSSED", STR,
                           [{"input": "10.0.0.0/8", "expected": "10.0.0.0/8"}], "block", ["direction", "priority"])]),
           C("X10-PLAIN", cidr, "exact", "pc:x10.allow.cidr", STR, STR, IDN, "unknown", "partial",
             tests=[{"input": "10.0.0.0/8", "expected": "10.0.0.0/8"}])]
    cases.append({"case": "ocorrencia_nao_identificada", "claims": x10,
                  "expect": {"X10-KEYED": "OK", "X10-PLAIN": "REFUTED_BY_RULE"}, "rule": "ARB-OCC-ID"})

    f1 = C("X11", "pa:x11.n", "exact", "pb:x11.n", INT(1, 9), INT(1, 9), IDN, "equal", "lossless",
           tests=[{"input": 1, "expected": 1}])
    f2 = copy.deepcopy(f1)
    f2.update(claim_version_id="X11@2", event_id="EV-X11-2")
    cases.append({"case": "versao_bifurcada", "claims": [f1, f2], "expect": {"X11": "REFUTED_BY_RULE"},
                  "rule": "ARB-VERSION"})
    return cases


def world() -> tuple[list[dict], dict, list[dict]]:
    """(alegações do mundo plantado, {claim_id: veredito esperado}, casos)."""
    cases = valid_cases() + conflict_cases()
    claims, expect = [], {}
    for c in cases:
        claims.extend(copy.deepcopy(c["claims"]))
        expect.update(c["expect"])
    return claims, expect, cases


def items_of(claims: list[dict], source: str = "battery:mundo") -> list[dict]:
    return [{"rec": r, "source": source, "domain": None, "line": i} for i, r in enumerate(claims, 1)]


# =================================================================================== alegações sem prova
def glossary_records(states: dict[str, str]) -> dict:
    """C20 sintético: âncoras dos átomos dados, com o estado de evidência dado (pela auditoria)."""
    claims, audits = [], []
    for i, (atom, st) in enumerate(sorted(states.items()), 1):
        cid = f"ANC-BAT-{i:02d}"
        claims.append({"claim_id": cid, "claim_version_id": f"{cid}@1", "event_id": f"EV-ANC-BAT-{i:02d}",
                       "concept_id": "concept:backup_retention", "atom_id": atom,
                       "sentence": "frase sintética de documentação da âncora", "context": "seção sintética",
                       "counterexample_search": {"query": "retenção outro sentido", "found": False,
                                                 "result": "nenhum uso com outro sentido"},
                       "extraction_method": "parser", "evidence_level": "published",
                       "evidence_state": "STRUCTURALLY_VALID", "recorded_at": "2026-11-03T08:00:00-03:00"})
        audits.append({"audit_id": f"GA-BAT-{i:02d}", "claim_id": cid, "claim_version_id": f"{cid}@1",
                       "event_id": f"EV-AUD-BAT-{i:02d}", "check": "evidence_support",
                       "result": "pass" if st in ("DOC_SUPPORTED", "OBSERVATION_TESTED") else "unresolved",
                       "evidence_state_before": "STRUCTURALLY_VALID", "evidence_state_after": st,
                       "auditor": "GLOSSARY-AUDIT", "at": "2026-11-03T09:00:00-03:00"})
    return {"claims": claims, "audits": audits}


def _base(cid, s="pa:u.retention", o="pb:u.retention"):
    return C(cid, s, "exact", o, DAYS(1, 30), DAYS(1, 30), IDN, "equal", "lossless",
             tests=[{"input": 7, "expected": 7}])


def unproven_cases() -> list[dict]:
    """Cada caso: alegação isolada (átomos próprios), veredito e regra esperados; controle = a mesma com a prova."""
    out = []

    def fix(r):
        if r is not None:
            r["claim_version_id"], r["event_id"] = f"{r['claim_id']}@1", f"EV-{r['claim_id']}"
        return r

    def add(name, rec, verdict, rule, control=None, glossary=None, same_concept=False):
        rec, control = fix(copy.deepcopy(rec)), fix(copy.deepcopy(control))
        out.append({"case": name, "claim": rec, "verdict": verdict, "rule": rule, "control": control,
                    "glossary": glossary, "same_concept": same_concept})

    n = 0

    def ids(r):
        """Átomos próprios por caso (sufixo), inclusive nas projeções e nos grupos; id, versão e evento coerentes."""
        nonlocal n
        n += 1
        r = copy.deepcopy(r)
        ren = {r[k]: r[k] + f".u{n:02d}" for k in ("subject_id", "object_id")}
        for k in ("subject_id", "object_id"):
            r[k] = ren[r[k]]
        for p in r.get("projection") or []:
            p["field"] = ren.get(p["field"], p["field"])
        cid = r["claim_id"]
        r["claim_version_id"], r["event_id"] = f"{cid}@1", f"EV-{cid}"
        return r

    b = _base("U-CTRL")
    nofn = copy.deepcopy(b); nofn["translation_fn"] = None; nofn["claim_id"] = "U-NOFN"
    add("exact sem normalização", ids(nofn), "UNPROVEN", "EXACT-NORM", ids(b))
    notest = copy.deepcopy(b); notest["proof"]["tests"] = []; notest["claim_id"] = "U-NOTEST"
    add("exact sem testes", ids(notest), "UNPROVEN", "EXACT-TESTS", ids(b))
    sv = copy.deepcopy(b); sv["evidence_state"] = "STRUCTURALLY_VALID"; sv["claim_id"] = "U-SV"
    add("só estruturalmente válida", ids(sv), "UNPROVEN", "EVIDENCE-DOC", ids(b))
    nocite = copy.deepcopy(b); nocite["proof"]["evidence"] = []; nocite["claim_id"] = "U-NOCITE"
    add("DOC_SUPPORTED sem citação", ids(nocite), "UNPROVEN", "EVIDENCE-DOC", ids(b))
    pv = copy.deepcopy(b); pv["evidence_state"] = "UNRESOLVED"; pv["claim_id"] = "U-UNRES"
    add("UNRESOLVED", ids(pv), "UNPROVEN", "EVIDENCE-DOC", ids(b))
    br = copy.deepcopy(E.BROAD_ARCHIVE)
    for k, v in (("subject_value_type", ENUM("flexible_retrieval", "deep_archive")),
                 ("object_value_type", ENUM("standard", "nearline", "coldline", "archive"))):
        br[k] = v
    nob = copy.deepcopy(br); nob.pop("membership_predicate"); nob["claim_id"] = "U-NOPRED"
    add("broad sem predicado de pertença", ids(nob), "UNPROVEN", "BN-PRED", ids(br))
    nonm = copy.deepcopy(br); nonm["membership_predicate"]["tests"]["non_members"] = []; nonm["claim_id"] = "U-NONM"
    add("broad sem teste de não membro", ids(nonm), "UNPROVEN", "BN-PRED", ids(br))
    nr = copy.deepcopy(E.NARROW_TLS)
    nr["subject_value_type"] = ENUM("1.0", "1.1", "1.2", "1.3")
    nr["object_value_type"] = ENUM("P12", "P13")
    nonr = copy.deepcopy(nr); nonr["membership_predicate"] = None; nonr["claim_id"] = "U-NARROW"
    nonr.pop("membership_predicate")
    add("narrow sem predicado", ids(nonr), "UNPROVEN", "BN-PRED", ids(nr))
    fx = copy.deepcopy(E.FIXED_ENCRYPTION)
    fx["subject_value_type"], fx["object_value_type"] = BOOL, BOOL
    nod = copy.deepcopy(fx); nod["fixed_default"]["evidence"] = {"source": "fixture:doc", "date": "sem data"}
    nod["claim_id"] = "U-FIXND"
    add("fixo sem data", ids(nod), "UNPROVEN", "FIXED-DATED", ids(fx))
    uk = copy.deepcopy(b); uk["claim_id"] = "U-UNK"
    unk = T("integer", quantity_kind="UNKNOWN", unit="UNKNOWN", range={"min": 1, "max": 30})
    uk["subject_value_type"], uk["object_value_type"] = unk, copy.deepcopy(unk)
    add("unknown == unknown", ids(uk), "UNPROVEN", "KIND-UNKNOWN", ids(b))
    nt = copy.deepcopy(b); nt.pop("subject_value_type"); nt.pop("object_value_type"); nt["claim_id"] = "U-NOTYPE"
    add("tipos não declarados", ids(nt), "UNPROVEN", "KIND-UNKNOWN", ids(b))
    st = C("U-STR", "pa:u.label", "exact", "pb:u.label", STR, STR, IDN, "equal", "lossless",
           tests=[{"input": "x", "expected": "x"}])
    stc = copy.deepcopy(st); stc["transport_fidelity"] = "partial"; stc["value_domain_relation"]["relation"] = "unknown"
    add("sem perda sem domínio que prove", ids(st), "UNPROVEN", "VDR-UNKNOWN", ids(stc))
    rel = copy.deepcopy(E.RELATED_KMS)
    rel["subject_value_type"], rel["object_value_type"] = STR, STR
    rel["evidence_state"] = "STRUCTURALLY_VALID"
    rel["claim_id"] = "U-RELATED"
    relc = copy.deepcopy(E.RELATED_KMS)
    relc["subject_value_type"], relc["object_value_type"] = STR, STR
    relc["proof"]["evidence"] = copy.deepcopy(DOC)
    add("related sem evidência", ids(rel), "UNPROVEN", "ARB-RELATED-EV", ids(relc))
    gk = copy.deepcopy(b); gk["claim_id"] = "U-GUARDUNK"
    gk["guard"] = {"all": [{"term": "subject.key_ref", "op": "refers_to_kind", "value": "kind_a"},
                           {"term": "subject.key_ref", "op": "refers_to_kind", "value": "kind_b"}]}
    gkc = copy.deepcopy(gk); gkc["guard"]["kind_disjoint"] = []
    gkc["guard"] = {"all": gk["guard"]["all"][:1]}
    add("guarda indecidida", ids(gk), "UNPROVEN", "GUARD-SAT", ids(gkc))
    pj = C("U-PROJ", "pa:u.doc", "exact", "pb:u.target", STR, STR, IDN, "unknown", "partial",
           tests=[{"input": '{"k": "v"}', "expected": "v"}],
           projection=[P("PRJ-U-k", "pa:u.doc", {"name": "json_get", "params": {"key": "k"}}, "bo:UNGLOSSED", STR, [])])
    pjc = copy.deepcopy(pj); pjc["projection"][0]["tests"] = [{"input": '{"k": "v"}', "expected": "v"}]
    add("projeção sem testes", ids(pj), "UNPROVEN", "P-EXEC", ids(pjc))
    rg = C("U-REG", "pa:u.flag", "exact", "pb:u.flag", BOOL, ENUM("on", "off"),
           {"name": "bool_to_enum", "params": {"true": "on", "false": "off"}}, "unknown", "partial", tests=[])
    rgc = copy.deepcopy(rg); rgc["proof"]["tests"] = [{"input": True, "expected": "on"}]
    add("função do registro sem testes", ids(rg), "UNPROVEN", "EXACT-TESTS", ids(rgc))
    vs = [{"name": "?a", "side": "subject", "field": "pa:u.from", "occurrence": "?r"},
          {"name": "?b", "side": "subject", "field": "pa:u.to", "occurrence": "?r"},
          {"name": "?o", "side": "object", "field": "pb:u.ports", "occurrence": "?x"}]
    grp = {"bo_group_id": "GRP-U", "cardinality": "N:1", "variables": vs, "occurrence_vars": ["?r", "?x"], "joins": [],
           "steps": [{"name": "join_port_range", "inputs": {"from_port": "?a", "to_port": "?b"}, "outputs": {"ports": "?o"}}]}
    gt = G("U-GROUP", "pa:u.from", "pb:u.ports", grp, TUP(comp("a", INT(0, 65535)), comp("b", INT(0, 65535))),
           TUP(comp("o", STR)), [])
    gtc = copy.deepcopy(gt); gtc["proof"]["tests"] = [{"input": {"?a": 1, "?b": 2}, "expected": {"?o": "1-2"}}]
    add("grupo sem teste", gt, "UNPROVEN", "ARB-G-EXEC", gtc)

    # mesmo conceito no glossário não prova exact
    s, o = "pa:u.backup_retention", "pb:u.backup_retention"
    sc = copy.deepcopy(b)
    sc.update(claim_id="U-SAME-NOGLOSS", subject_id=s, object_id=o, basis="shared_concept",
              subject_concept="concept:backup_retention", object_concept="concept:backup_retention",
              anchors=[{"claim_id": "ANC-BAT-01", "atom_id": s, "evidence_state": "DOC_SUPPORTED"},
                       {"claim_id": "ANC-BAT-02", "atom_id": o, "evidence_state": "DOC_SUPPORTED"}])
    ok_g = glossary_records({s: "DOC_SUPPORTED", o: "DOC_SUPPORTED"})
    bad_g = glossary_records({s: "DOC_SUPPORTED", o: "STRUCTURALLY_VALID"})
    pv_g = glossary_records({s: "PERSISTENCE_VERIFIED", o: "DOC_SUPPORTED"})
    add("mesmo conceito, âncoras sem glossário auditado", sc, "UNPROVEN", "ARB-ANCHOR", sc, ok_g, True)
    out[-1]["glossary_case"] = None
    sc2 = copy.deepcopy(sc); sc2["claim_id"] = "U-SAME-SV"
    add("mesmo conceito, âncora só estruturalmente válida", sc2, "UNPROVEN", "ARB-ANCHOR", sc2, ok_g, True)
    out[-1]["glossary_case"] = bad_g
    sc3 = copy.deepcopy(sc); sc3["claim_id"] = "U-SAME-PV"
    add("mesmo conceito, âncora só com leitura de volta", sc3, "UNPROVEN", "ARB-ANCHOR", sc3, ok_g, True)
    out[-1]["glossary_case"] = pv_g
    sc4 = copy.deepcopy(b)
    sc4.update(claim_id="U-SAME-GLOSSEV", subject_id=s + ".g", object_id=o + ".g",
               subject_concept="concept:backup_retention", object_concept="concept:backup_retention")
    sc4["proof"]["evidence"] = [{"source": "glossary:concept:backup_retention", "date": "2026-11-03",
                                 "sentence": "os dois átomos são âncoras do mesmo conceito"}]
    c4 = copy.deepcopy(sc4); c4["proof"]["evidence"] = copy.deepcopy(DOC)
    add("mesmo conceito como única evidência", sc4, "UNPROVEN", "ANCHOR-NOT-PROOF", c4, None, True)
    return out
