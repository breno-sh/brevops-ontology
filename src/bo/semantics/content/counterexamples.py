"""Contraexemplos por regra (semantics/counterexamples.jsonl). Cada linha é um PAR MÍNIMO:
  input    o caso que a regra tem de rejeitar (a v2, ou um erro plausível de mapeador)
  control  o mesmo caso com a única mudança que o torna válido (tem de ser aceito: a rejeição não é vacuidade)
  mutation 'strict': com a regra desligada, o input passa inteiro (é a regra, e só ela, que rejeita);
           'rule_only': com a regra desligada, a falha dessa regra some (outra regra pega o caso, dito em 'why').
kind: claim | set | trace | compose | hub | projections | alternatives | group.
"""

from __future__ import annotations

import copy

from . import examples as E
from ..vocab import ABSENT, NOT_READ, SYMBOLIC


def mut(base, *edits):
    """edits: (caminho com '/', valor) ou (caminho, '$del')."""
    r = copy.deepcopy(base)
    for path, val in edits:
        keys = path.split("/")
        cur = r
        for k in keys[:-1]:
            cur = cur[int(k)] if isinstance(cur, list) else cur[k]
        last = keys[-1]
        if val == "$del":
            del cur[last]
        elif isinstance(cur, list):
            cur[int(last)] = val
        else:
            cur[last] = val
    return r


CE: list[dict] = []


def ce(ce_id, rule, kind, why, inp, control, mutation="strict", **extra):
    CE.append({"ce_id": ce_id, "rule_id": rule, "kind": kind, "why": why, "input": inp, "control": control,
               "mutation": mutation, **extra})


X = E.EXACT_DAYS_SECS
# ------------------------------------------------------------------------------------------------- alegação
ce("CE-SKOS-PRED-1", "SKOS-PRED", "claim", "predicado narrowMatch com semantic_relation broad: os dois campos discordam",
   mut(E.BROAD_ARCHIVE, ("predicate_id", "skos:narrowMatch")), E.BROAD_ARCHIVE)
ce("CE-SKOS-ORIENT-1", "SKOS-ORIENT", "claim",
   "leitura da v2: 'a broadMatch b' com 'a' como o mais amplo (o predicado diz que o subconjunto é o objeto)",
   mut(E.BROAD_ARCHIVE, ("membership_predicate/subset", "object")), E.BROAD_ARCHIVE)
ce("CE-TYPE-WF-1", "TYPE-WF", "claim", "faixa vazia (min > max) no tipo do sujeito",
   mut(X, ("subject_value_type/range", {"min": 40, "max": 35})), X, "rule_only",
   note="tipo inválido some; sem tipo, KIND-UNKNOWN pega (unknown não é prova)")
ce("CE-KIND-UNKNOWN-1", "KIND-UNKNOWN", "claim", "grandeza e unidade UNKNOWN no destino: unknown==unknown não prova",
   mut(X, ("object_value_type/quantity_kind", "UNKNOWN"), ("object_value_type/unit", "UNKNOWN")), X)
ce("CE-KIND-EQ-1", "KIND-EQ", "claim",
   "dias de retenção ligados a contagem de cópias: números iguais, grandezas diferentes (7 dias != 7 cópias)",
   mut(X, ("object_value_type", {"datatype": "integer", "quantity_kind": "quantitykind:Count", "unit": "unit:NUM",
                                 "range": {"min": 0, "max": 31536000}}),
       ("translation_fn", {"name": "scale", "params": {"factor": "86400"}})),
   mut(X, ("translation_fn", {"name": "scale", "params": {"factor": "86400"}})))
ce("CE-KIND-TUPLE-1", "KIND-TUPLE", "claim", "combinador de tupla cuja saída viola o tipo de um componente (operador 'ge' fora do enum)",
   mut(E.TUPLE_ALARM, ("object_value_type/components/3/type/enum", ["gt", "lt"]),
       ("proof/tests", [{"input": "CpuUtilization[1m].mean() >= 80",
                         "expected": {"metric": "CpuUtilization", "window": "PT1M", "statistic": "mean",
                                      "operator": "ge", "threshold": 80}}])),
   E.TUPLE_ALARM)
ce("CE-KIND-COLL-1", "KIND-COLL", "claim",
   "lista de dias ligada a um número de segundos com conversão escalar (sem combinador de coleção)",
   mut(E.DAYS_LIST, ("object_value_type", E.SECS(0, 31536000)), ("proof/tests", [{"input": [1], "expected": [86400]}]),
       ("value_domain_relation/relation", "unknown"), ("transport_fidelity", "partial")),
   mut(E.DAYS_LIST, ("value_domain_relation/relation", "unknown"), ("transport_fidelity", "partial")), "rule_only",
   note="sem a regra, o teste de lista não é admitido pelo tipo escalar do destino (EXACT-TESTS segura)")
ce("CE-KIND-COLL-2", "KIND-COLL", "claim", "lista -> conjunto sem declarar a perda de ordem e de repetição",
   mut(E.PREFIX_LIST, ("object_value_type", E.T("set", item_type=E.T("string")))), E.PREFIX_LIST)
ce("CE-KIND-COLL-3", "KIND-COLL", "claim", "wrap_list usado entre duas listas (a forma do combinador é escalar -> lista)",
   mut(E.WRAP_PREFIX, ("subject_value_type", E.T("list", item_type=E.T("string"))),
       ("proof/tests", [{"input": ["a/"], "expected": [["a/"]]}]), ("value_domain_relation/relation", "unknown")),
   E.WRAP_PREFIX, "rule_only", note="sem a regra, a lista de listas não é admitida pelo destino (KIND-TUPLE segura)")
ce("CE-VDR-COMPUTED-3", "VDR-COMPUTED", "claim",
   "wrap_list declarado com domínios iguais: a imagem são listas de um item, subconjunto próprio do destino",
   mut(E.WRAP_PREFIX, ("value_domain_relation/relation", "equal")), E.WRAP_PREFIX)
ce("CE-FID-COHERENT-3", "FID-COHERENT", "claim",
   "unwrap_single declarado sem perda: só lista de tamanho 1 tem contraparte (parcial)",
   mut(E.UNWRAP_PREFIX, ("transport_fidelity", "lossless")), E.UNWRAP_PREFIX)
ce("CE-UNIT-WINDOW-1", "UNIT-WINDOW", "claim", "taxa por minuto copiada como taxa por segundo (identidade)",
   mut(E.RATE, ("translation_fn", {"name": "identity", "params": {}}), ("proof/tests", [{"input": 60, "expected": 60}]),
       ("value_domain_relation/relation", "superset"), ("transport_fidelity", "partial")),
   E.RATE)
ce("CE-UNIT-BYTES-1", "UNIT-BYTES", "claim", "GiB copiado como GB (identidade): 1 GiB != 1 GB",
   mut(E.EXACT_GIB_GB, ("translation_fn", {"name": "identity", "params": {}}), ("proof/tests", [{"input": 1, "expected": 1}])),
   E.EXACT_GIB_GB)
ce("CE-NORM-PRESERVE-1", "NORM-PRESERVE", "claim", "dias -> horas com fator 12 (testes coerentes com a função, valor canônico não)",
   mut(E.EXACT_DAYS_HOURS, ("translation_fn", {"name": "scale", "params": {"factor": "12"}}),
       ("proof/tests", [{"input": 2, "expected": 24}])),
   E.EXACT_DAYS_HOURS)
ce("CE-EXACT-NORM-1", "EXACT-NORM", "claim", "exact sem função de tradução (dias e segundos sem normalização explícita)",
   mut(X, ("translation_fn", None), ("transport_fidelity", "partial")), mut(X, ("transport_fidelity", "partial")))
ce("CE-EXACT-TESTS-1", "EXACT-TESTS", "claim", "teste da normalização falha (7 dias != 600000 s)",
   mut(X, ("proof/tests", [{"input": 7, "expected": 600000}])), X)
ce("CE-EXACT-TESTS-2", "EXACT-TESTS", "claim", "normalização sem nenhum teste executável", mut(X, ("proof/tests", [])), X)
ce("CE-VDR-COMPUTED-1", "VDR-COMPUTED", "claim",
   "orientação invertida: domínio do sujeito (1..35 dias) declarado superconjunto do destino que o contém",
   mut(X, ("value_domain_relation/relation", "superset"), ("transport_fidelity", "partial")),
   mut(X, ("transport_fidelity", "partial")))
ce("CE-VDR-COMPUTED-2", "VDR-COMPUTED", "claim", "relação de domínio sem orientação declarada",
   mut(X, ("value_domain_relation", {"relation": "subset"})), X)
ce("CE-VDR-UNKNOWN-1", "VDR-UNKNOWN", "claim", "sem perda alegado sobre domínio indeterminado (duração sem faixa)",
   mut(E.DURATION_MONTHS, ("transport_fidelity", "lossless")), E.DURATION_MONTHS)
ce("CE-FID-COHERENT-1", "FID-COHERENT", "claim", "exact com saturação declarada vendido como sem perda (v2: exact = sem perda)",
   mut(E.EXACT_SATURATING, ("transport_fidelity", "lossless")), E.EXACT_SATURATING)
ce("CE-FID-COHERENT-2", "FID-COHERENT", "claim", "perda declarada sem item de perda no contrato",
   mut(X, ("transport_fidelity", "declared_loss")), X)
ce("CE-CLOSE-LOSS-1", "CLOSE-LOSS", "claim", "close sem declarar o que se perde",
   mut(E.CLOSE_VERSIONING, ("loss_contract", []), ("transport_fidelity", "partial")), E.CLOSE_VERSIONING)
ce("CE-BN-PRED-1", "BN-PRED", "claim", "broad com predicado em texto livre ('as classes de arquivo')",
   mut(E.BROAD_ARCHIVE, ("membership_predicate/expr", "as classes de arquivo")), E.BROAD_ARCHIVE)
ce("CE-BN-PRED-TESTS-1", "BN-PRED-TESTS", "claim",
   "predicado esquece 'coldline' (imagem de 'flexible_retrieval'): passa nos testes escolhidos, falha na conferência exaustiva",
   mut(E.BROAD_ARCHIVE, ("membership_predicate/expr", {"op": "in", "values": ["archive"]})), E.BROAD_ARCHIVE)
ce("CE-RELATED-NT-1", "RELATED-NT", "claim", "related com fidelidade 'perda declarada' (related usado para carregar valor)",
   mut(E.RELATED_KMS, ("transport_fidelity", "declared_loss")), E.RELATED_KMS)
ce("CE-FIXED-DATED-1", "FIXED-DATED", "claim", "comportamento fixo do destino sem data na evidência",
   mut(E.FIXED_ENCRYPTION, ("fixed_default/evidence", {"source": "fixture:doc-sintetica#criptografia"})), E.FIXED_ENCRYPTION)
ce("CE-EVIDENCE-1", "EVIDENCE", "claim", "leitura de volta (PERSISTENCE_VERIFIED) sem sentença: persistência não prova significado",
   mut(X, ("evidence_state", "PERSISTENCE_VERIFIED"), ("proof/evidence", [{"source": "fixture:readback", "readback": True}])), X)
ce("CE-EVIDENCE-2", "EVIDENCE", "claim", "alegação só bem formada (STRUCTURALLY_VALID) tentando transportar",
   mut(X, ("evidence_state", "STRUCTURALLY_VALID")), X)
ce("CE-ANCHOR-NOT-PROOF-1", "ANCHOR-NOT-PROOF", "claim",
   "exact porque os dois átomos estão no mesmo conceito do glossário, com as âncoras UNRESOLVED (F4)",
   mut(X, ("basis", "shared_concept"), ("anchors", [{"atom": "pa:backup_retention_days", "evidence_state": "UNRESOLVED"},
                                                   {"atom": "pb:backup_retention_seconds", "evidence_state": "UNRESOLVED"}])),
   mut(X, ("basis", "shared_concept"), ("anchors", [{"atom": "pa:backup_retention_days", "evidence_state": "DOC_SUPPORTED"},
                                                   {"atom": "pb:backup_retention_seconds", "evidence_state": "DOC_SUPPORTED"}])))
ce("CE-GUARD-TYPE-1", "GUARD-TYPE", "claim", "operador fora da gramática (neq)",
   mut(X, ("guard", {"all": [{"term": "object.edition", "op": "neq", "value": "basic"}]})),
   mut(X, ("guard", {"all": E.EDITION_STD})))
ce("CE-GUARD-TYPE-2", "GUARD-TYPE", "claim", "termo vizinho sem tipo declarado",
   mut(X, ("guard", {"all": [{"term": "subject.engine", "op": "eq", "value": "engine_a"}]})),
   mut(X, ("guard", {"all": [{"term": "subject.engine", "op": "eq", "value": "engine_a"}],
                     "term_types": {"subject.engine": {"datatype": "enum", "enum": ["engine_a", "engine_b"]}}})))
ce("CE-GUARD-SAT-1", "GUARD-SAT", "claim", "guarda insatisfazível: edição standard e premium ao mesmo tempo (alegação vazia)",
   mut(X, ("guard", {"all": E.EDITION_STD + E.EDITION_PREM})), mut(X, ("guard", {"all": E.EDITION_STD + E.EDITION_ANY})))
ce("CE-GUARD-SAT-2", "GUARD-SAT", "claim", "referência a dois tipos sem disjunção declarada: satisfatibilidade indecidida",
   mut(X, ("guard", {"all": [{"term": "object.key_ref", "op": "refers_to_kind", "value": "kind_a"},
                             {"term": "object.key_ref", "op": "refers_to_kind", "value": "kind_b"}]})),
   mut(X, ("guard", {"all": [{"term": "object.key_ref", "op": "refers_to_kind", "value": "kind_a"}]})))
ce("CE-CTX-DEP-1", "CTX-DEP", "claim", "a tradução depende da edição do destino, que não está na guarda",
   mut(X, ("loss_contract", [{"kind": "context_dependence", "terms": ["object.edition"]}])),
   mut(X, ("loss_contract", [{"kind": "context_dependence", "terms": ["object.edition"]}]), ("guard", {"all": E.EDITION_ANY})))
ce("CE-SENTINEL-1", "SENTINEL", "claim", "sentinela 0 = 'nunca expira' sem mapeamento (vira 0 s = expira já)",
   mut(E.SENTINEL_RETENTION, ("loss_contract", [])), E.SENTINEL_RETENTION)
# ------------------------------------------------------------------------------------------------- conjunto
REL_SAME = E.claim("CLM-RE-02", X["subject_id"], "related", X["object_id"], X["subject_value_type"], X["object_value_type"],
                   None, "unknown", "none")
ce("CE-SKOS-DISJ-1", "SKOS-DISJ", "set", "exactMatch e relatedMatch no mesmo par sob guardas compatíveis",
   [X, REL_SAME], [E.with_guard(X, E.EDITION_STD), E.with_guard(REL_SAME, E.EDITION_PREM)])
# --------------------------------------------------------------------------------------------------- traço


def tr(claim, value, asserted, ctx=None, direction="forward"):
    r = {"claim": claim, "value": value, "asserted": asserted, "direction": direction}
    if ctx is not None:
        r["context"] = ctx
    return r


ce("CE-T-DOMAIN-2", "T-DOMAIN", "trace", "lista de dois prefixos achatada para o primeiro (unwrap_single fora do domínio)",
   tr(E.UNWRAP_PREFIX, ["a/", "b/"], {"result": "carried", "value": "a/"}),
   tr(E.UNWRAP_PREFIX, ["a/"], {"result": "carried", "value": "a/"}), "rule_only",
   note="sem a regra, a lista passa crua e não é o valor afirmado")
ce("CE-T-RELATED-1", "T-RELATED", "trace", "related usado para carregar valor (CMT-LOSS-N02)",
   tr(E.RELATED_KMS, "key_x", {"result": "carried", "value": "key_x"}),
   tr(E.RELATED_KMS, "key_x", {"result": "blocked", "code": "RELATED_ONLY"}))
ce("CE-T-UNPROVEN-1", "T-UNPROVEN", "trace", "exact sem prova (UNRESOLVED) transportando valor (CMT-LOSS-U02)",
   tr(mut(X, ("evidence_state", "UNRESOLVED")), 7, {"result": "carried", "value": 604800}),
   tr(mut(X, ("evidence_state", "UNRESOLVED")), 7, {"result": "blocked", "code": "UNPROVEN"}))
XG = E.with_guard(X, E.EDITION_STD)
ce("CE-T-GUARD-1", "T-GUARD", "trace", "edição do destino não lida tratada como 'atravessou'",
   tr(XG, 7, {"result": "carried", "value": 604800}, {}),
   tr(XG, 7, {"result": "blocked", "code": "CONDITION_INDETERMINATE"}, {}))
ce("CE-T-GUARD-2", "T-GUARD", "trace", "guarda falsa (edição premium) ignorada",
   tr(XG, 7, {"result": "carried", "value": 604800}, {"object.edition": "premium"}),
   tr(XG, 7, {"result": "carried", "value": 604800}, {"object.edition": "standard"}))
XR = mut(X, ("object_value_type/required", True))
ce("CE-T-ABSENCE-1", "T-ABSENCE", "trace", "obrigatório no destino sem valor na origem: emite padrão inventado (CMT-LOSS-N01)",
   tr(XR, ABSENT, {"result": "carried", "value": 0}), tr(XR, ABSENT, {"result": "blocked", "code": "UNKNOWN_INPUT"}),
   "rule_only", note="sem a regra, o marcador de ausência cai fora do tipo (T-DOMAIN); nunca vira valor")
ce("CE-T-ABSENCE-2", "T-ABSENCE", "trace", "valor de origem não lido tratado como zero",
   tr(X, NOT_READ, {"result": "carried", "value": 0}), tr(X, NOT_READ, {"result": "blocked", "code": "UNKNOWN_INPUT"}),
   "rule_only", note="sem a regra, o marcador cai fora do tipo (T-DOMAIN)")
ce("CE-T-SYMBOLIC-1", "T-SYMBOLIC", "trace", "valor conhecido só depois da criação transportado como vazio",
   tr(X, SYMBOLIC, {"result": "omitted"}), tr(X, SYMBOLIC, {"result": "blocked", "code": "UNKNOWN_SYMBOLIC_INPUT"}),
   "rule_only", note="sem a regra, o marcador cai fora do tipo (T-DOMAIN)")
ce("CE-T-DOMAIN-1", "T-DOMAIN", "trace", "1 mês convertido em 2592000 s (mês de 30 dias inventado; CMT-LOSS-U01)",
   tr(E.DURATION_MONTHS, "P1M", {"result": "carried", "value": 2592000}),
   tr(E.DURATION_MONTHS, "P1M", {"result": "blocked", "code": "TRANSFORM_OUT_OF_DOMAIN"}),
   "rule_only", note="sem a regra, o literal passa cru e não é o número afirmado")
ce("CE-T-SATURATION-1", "T-SATURATION", "trace", "400 dias para destino de no máximo 365 sem perda (CMT-LOSS-P01)",
   tr(E.EXACT_SATURATING, 400, {"result": "carried", "value": 400, "fidelity": "lossless"}),
   tr(E.EXACT_SATURATING, 400, {"result": "carried", "value": 365, "fidelity": "declared_loss", "loss_kinds": ["saturation"]}))
ce("CE-T-ROUNDING-1", "T-ROUNDING", "trace", "1 GiB emitido como 1,073741824 GB sem perda (destino só tem GB inteiro)",
   tr(E.EXACT_GIB_GB, 1, {"result": "carried", "value": "134217728/125000000", "fidelity": "lossless"}),
   tr(E.EXACT_GIB_GB, 1, {"result": "carried", "value": 2, "fidelity": "declared_loss", "loss_kinds": ["rounding"]}))
ce("CE-T-SUBSET-1", "T-SUBSET", "trace", "volta de broad: 'standard' (fora de 'a') transportado",
   tr(E.BROAD_ARCHIVE, "standard", {"result": "carried", "value": "standard"}, direction="inverse"),
   tr(E.BROAD_ARCHIVE, "archive", {"result": "carried", "value": "deep_archive"}, direction="inverse"),
   "rule_only", note="sem a regra, a inversa parcial da tradução não está definida em 'standard' (T-DOMAIN)")
SN0 = mut(E.SENTINEL_RETENTION, ("object_value_type/range/min", 0))
ce("CE-T-SENTINEL-1", "T-SENTINEL", "trace", "0 = 'nunca expira' multiplicado por 86400 (vira 'expira já')",
   tr(SN0, 0, {"result": "carried", "value": 0}), tr(SN0, 0, {"result": "blocked", "code": "TRANSFORM_OUT_OF_DOMAIN"}))
ce("CE-T-FIXED-1", "T-FIXED", "trace", "destino sempre cifra; origem desligada transportada como se coincidisse",
   tr(E.FIXED_ENCRYPTION, False, {"result": "carried", "value": False}, {"object.provider_version": "5.2"}),
   tr(E.FIXED_ENCRYPTION, True, {"result": "carried", "value": True}, {"object.provider_version": "5.2"}))
ce("CE-T-INVERSE-1", "T-INVERSE", "trace", "volta por tabela não injetiva: 'slow' escolhido como 'warm'",
   tr(E.TIER_CLOSE, "slow", {"result": "carried", "value": "warm"}, direction="inverse"),
   tr(E.TIER_CLOSE, "hot", {"result": "carried", "value": "fast", "fidelity": "lossless"}),
   "rule_only", note="sem a regra, a inversa sem função cai em EXACT-NORM (UNPROVEN)")


# ----------------------------------------------------------------------------------------------- composição
def cp(m1, m2, asserted):
    return {"m1": m1, "m2": m2, "asserted": asserted}


GSTD = E.with_guard(E.EXACT_DAYS_HOURS, E.EDITION_STD)
SPREM = E.with_guard(E.EXACT_HOURS_SECS, [{"term": "subject.edition", "op": "edition_in", "value": ["premium"]}])
SANY = E.with_guard(E.EXACT_HOURS_SECS, [{"term": "subject.edition", "op": "edition_in", "value": ["standard", "premium"]}])
ce("CE-K-JOIN-1", "K-JOIN", "compose", "encadeia alegações que não compartilham o nó do meio",
   cp(E.EXACT_DAYS_HOURS, X, {"outcome": "COMPOSED"}), cp(E.EXACT_DAYS_HOURS, E.EXACT_HOURS_SECS, {"outcome": "COMPOSED"}),
   "rule_only", note="sem a regra, os tipos dos dois 'meios' diferem (K-DOMAIN)")
ce("CE-K-LEGS-1", "K-LEGS", "compose", "perna sem prova (UNRESOLVED) promovida a composto exact",
   cp(mut(E.EXACT_DAYS_HOURS, ("evidence_state", "UNRESOLVED")), E.EXACT_HOURS_SECS, {"outcome": "COMPOSED", "relation": "exact"}),
   cp(E.EXACT_DAYS_HOURS, E.EXACT_HOURS_SECS, {"outcome": "COMPOSED", "relation": "exact"}))
ce("CE-K-TABLE-1", "K-TABLE", "compose", "fecho transitivo indiscriminado: close∘close composto",
   cp(E.CLOSE_VERSIONING, E.CLOSE_VERSIONING_2, {"outcome": "COMPOSED"}),
   cp(E.EXACT_DAYS_HOURS, E.EXACT_HOURS_SECS, {"outcome": "COMPOSED"}))
ce("CE-K-GUARD-EMPTY-1", "K-GUARD-EMPTY", "compose", "guardas incompatíveis no nó do meio (standard x premium) compostas",
   cp(GSTD, SPREM, {"outcome": "COMPOSED"}), cp(GSTD, SANY, {"outcome": "COMPOSED"}))
KA = E.with_guard(E.EXACT_DAYS_HOURS, [{"term": "object.key_ref", "op": "refers_to_kind", "value": "kind_a"}])
KB = E.with_guard(E.EXACT_HOURS_SECS, [{"term": "subject.key_ref", "op": "refers_to_kind", "value": "kind_b"}])
KA2 = E.with_guard(E.EXACT_HOURS_SECS, [{"term": "subject.key_ref", "op": "refers_to_kind", "value": "kind_a"}])
ce("CE-K-GUARD-UNKNOWN-1", "K-GUARD-UNKNOWN", "compose", "interseção indecidida (dois tipos sem disjunção) tratada como satisfazível",
   cp(KA, KB, {"outcome": "COMPOSED"}), cp(KA, KA2, {"outcome": "COMPOSED"}))
MID_DAYS = mut(E.EXACT_HOURS_SECS, ("subject_value_type", E.DAYS(1, 30)), ("translation_fn", E.UC("unit:DAY", "unit:SEC")),
               ("proof/tests", [{"input": 2, "expected": 172800}]))
ce("CE-K-DOMAIN-1", "K-DOMAIN", "compose", "nó do meio em horas numa perna e em dias na outra (domínio incompatível)",
   cp(E.EXACT_DAYS_HOURS, MID_DAYS, {"outcome": "COMPOSED"}), cp(E.EXACT_DAYS_HOURS, E.EXACT_HOURS_SECS, {"outcome": "COMPOSED"}),
   "rule_only", note="sem a regra, a relação de domínio do composto sai fora da composição RCC5 (K-VDR segura)")
NB = E.T("integer", quantity_kind="quantitykind:Time", unit="unit:DAY")
VDR_L1 = E.claim("CLM-KV-01", "pa:keep_days", "exact", "pb:keep_days", E.DAYS(1, 100), NB, {"name": "identity", "params": {}},
                 "subset", "partial", tests=[{"input": 5, "expected": 5}])
VDR_L2 = E.claim("CLM-KV-02", "pb:keep_days", "exact", "pc:keep_days", NB, E.DAYS(1, 10), {"name": "identity", "params": {}},
                 "subset", "partial", tests=[{"input": 5, "expected": 5}])
ce("CE-K-VDR-1", "K-VDR", "compose",
   "pernas declaram 'subconjunto' sobre um meio sem faixa (não refutável perna a perna); o composto real é superconjunto",
   cp(VDR_L1, VDR_L2, {"outcome": "COMPOSED"}),
   cp(VDR_L1, mut(VDR_L2, ("value_domain_relation/relation", "superset")), {"outcome": "COMPOSED"}))
MIB_GIB = E.claim("CLM-KF-03", "pz:disk_size_mib", "exact", "pa:disk_size_gib",
                  E.T("integer", quantity_kind="quantitykind:AmountOfData", unit="unit:MebiBYTE",
                      range={"min": 1024, "max": 1048576}, step="1024"),
                  E.EXACT_GIB_GB["subject_value_type"], E.UC("unit:MebiBYTE", "unit:GibiBYTE"), "equal", "lossless",
                  tests=[{"input": 2048, "expected": 2}])
ce("CE-K-FIDELITY-1", "K-FIDELITY", "compose", "composto declarado sem perda com uma perna de perda declarada (arredondamento GiB->GB)",
   cp(MIB_GIB, E.EXACT_GIB_GB, {"outcome": "COMPOSED", "fidelity": "lossless"}),
   cp(MIB_GIB, E.EXACT_GIB_GB, {"outcome": "COMPOSED", "fidelity": "declared_loss"}))
ce("CE-K-HUB-1", "K-HUB", "hub", "v2: dois átomos no mesmo conceito = exact, com âncoras sem prova (F4)",
   {"a": mut(E.ANCHOR_A, ("evidence_state", "UNRESOLVED")), "b": mut(E.ANCHOR_B, ("evidence_state", "UNRESOLVED")),
    "asserted": {"outcome": "COMPOSED", "relation": "exact"}},
   {"a": E.ANCHOR_A, "b": E.ANCHOR_B, "asserted": {"outcome": "COMPOSED", "relation": "exact"}})
# ------------------------------------------------------------------------------------------ projeções/grupos
AP = E.ALARM_PROJECTIONS
REP = {"pa:rule[].port": {"repeated": True}}
PROJ_PORT = {"projection_id": "PRJ-PORT", "field": "pa:rule[].port", "occurrence": {"scope": "block", "key_fields": ["rule_name"]},
             "extractor": {"name": "identity"}, "concept": "concept:port", "type": E.T("integer", range={"min": 0, "max": 65535}),
             "tests": [{"input": 443, "expected": 443}]}
ce("CE-P-OCC-1", "P-OCC", "projections", "campo de bloco repetido sem chave de ocorrência",
   {"projections": [mut(PROJ_PORT, ("occurrence", {"scope": "resource"}))], "fields": REP},
   {"projections": [PROJ_PORT], "fields": REP})
ce("CE-P-OCC-2", "P-OCC", "projections", "ocorrência identificada pela posição textual",
   {"projections": [mut(PROJ_PORT, ("occurrence/key_fields", ["position"]))], "fields": REP},
   {"projections": [PROJ_PORT], "fields": REP})
ce("CE-P-EXEC-1", "P-EXEC", "projections", "extrator do limiar afirma 8 onde a consulta diz 80",
   {"projections": [mut(AP[2], ("tests/0/expected", 8))]}, {"projections": [AP[2]]})
ce("CE-P-OVERLAP-1", "P-OVERLAP", "projections", "duas projeções leem a métrica da mesma consulta sem declarar sobreposição",
   {"projections": [AP[0], mut(AP[0], ("projection_id", "PRJ-AL-metric-2"), ("concept", "concept:alarm_signal"))]},
   {"projections": AP})
ce("CE-A-EXCL-1", "A-EXCL", "alternatives", "exclusividade declarada com guardas que se cruzam (standard e standard|premium)",
   {"realizations": [E.REALIZATIONS_EXCLUSIVE[0], mut(E.REALIZATIONS_EXCLUSIVE[1], ("guard", {"all": E.EDITION_ANY}))]},
   {"realizations": E.REALIZATIONS_EXCLUSIVE})
ce("CE-G-VARS-1", "G-VARS", "group", "passo lê variável não ligada (?until)",
   {"group": mut(E.PORT_GROUP, ("steps/1/inputs/to_port", "?until"))}, {"group": E.PORT_GROUP}, "rule_only",
   note="sem a regra, a variável ?to fica solta e a contagem continua certa: só G-VARS pega")
ce("CE-G-ARITY-1", "G-ARITY", "group", "argumento do combinador com nome fora da assinatura (to em vez de to_port)",
   {"group": mut(E.PORT_GROUP, ("steps/1/inputs", {"from_port": "?from", "to": "?to"}))}, {"group": E.PORT_GROUP})
ce("CE-G-ARITY-2", "G-ARITY", "group", "cardinalidade 1:1 declarada para grupo 1:N",
   {"group": mut(E.ALARM_GROUP, ("cardinality", "1:1"))}, {"group": E.ALARM_GROUP})
TWO_OCC = mut(E.PORT_GROUP, ("variables/2/occurrence", "?r2"), ("occurrence_vars", ["?r", "?r2", "?a"]))
ce("CE-G-OCC-1", "G-OCC", "group", "porta inicial de uma regra com porta final de outra (ocorrências misturadas)",
   {"group": TWO_OCC}, {"group": mut(TWO_OCC, ("joins", [{"left": "?r", "right": "?r2", "via": "same_rule"}]))})


def records() -> list[dict]:
    return copy.deepcopy(CE)
