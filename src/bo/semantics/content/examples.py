"""Biblioteca de alegações-exemplo da teoria (provedores sintéticos pa, pb, pc, pd).

São fixtures da TEORIA, não fatos sobre provedores reais: a evidência citada é sintética (fonte 'fixture:') e
serve para exercitar as obrigações de prova. O único exemplo com nomes de schema público (alarme com consulta
em linguagem de métricas) vale só para as projeções e fica UNRESOLVED (a verificação é do SERVICE-EVIDENCE).
"""

from __future__ import annotations

import copy

DOC = [{"source": "fixture:doc-sintetica", "sentence": "frase sintética de documentação que sustenta a alegação",
        "date": "2026-11-02"}]


def T(datatype, **kw):
    d = {"datatype": datatype}
    d.update(kw)
    return d


DAYS = lambda lo, hi: T("integer", quantity_kind="quantitykind:Time", unit="unit:DAY", range={"min": lo, "max": hi})
SECS = lambda lo, hi: T("integer", quantity_kind="quantitykind:Time", unit="unit:SEC", range={"min": lo, "max": hi})
HOURS = lambda lo, hi: T("integer", quantity_kind="quantitykind:Time", unit="unit:HR", range={"min": lo, "max": hi})
ENUM = lambda *v: T("enum", enum=list(v))
BOOL = T("boolean")


def claim(cid, s, rel, o, st, ot, fn, vdr, fid, **kw):
    from ..vocab import SKOS_PREDICATE
    r = {"claim_id": cid, "claim_version_id": f"{cid}@1", "event_id": f"EV-{cid}",
         "subject_id": s, "predicate_id": SKOS_PREDICATE.get(rel, rel), "object_id": o,
         "mapping_justification": "semapv:ManualMappingCuration", "semantic_relation": rel,
         "value_domain_relation": {"relation": vdr, "orientation": "subject_to_object"},
         "transport_fidelity": fid, "guard": {"all": []}, "translation_fn": fn, "loss_contract": [],
         "subject_value_type": st, "object_value_type": ot, "evidence_state": "DOC_SUPPORTED", "basis": "direct",
         "proof": {"type": {"exact": "normalization", "close": "declared_loss", "broad": "membership",
                            "narrow": "membership", "related": "none"}.get(rel, "none"),
                   "evidence": copy.deepcopy(DOC), "tests": []},
         "subject_concept": "bo:UNGLOSSED", "object_concept": "bo:UNGLOSSED"}
    tests = kw.pop("tests", None)
    if tests is not None:
        r["proof"]["tests"] = tests
    r.update(kw)
    return r


def UC(a, b):
    return {"name": "unit_convert", "params": {"from": a, "to": b}}


def EM(table):
    return {"name": "enum_map", "params": {"table": table}}


# ------------------------------------------------------------------------------------------------- exact
EXACT_DAYS_SECS = claim(
    "CLM-EX-01", "pa:backup_retention_days", "exact", "pb:backup_retention_seconds",
    DAYS(1, 35), SECS(0, 31536000), UC("unit:DAY", "unit:SEC"), "subset", "lossless",
    tests=[{"input": 7, "expected": 604800}, {"input": 1, "expected": 86400}],
    preserved_observations=["objeto de backup mais velho que N dias é apagado"])

EXACT_DAYS_HOURS = claim(
    "CLM-EX-02", "pa:log_retention_days", "exact", "pb:log_retention_hours",
    DAYS(1, 30), HOURS(1, 720), UC("unit:DAY", "unit:HR"), "subset", "lossless",
    tests=[{"input": 2, "expected": 48}])
EXACT_HOURS_SECS = claim(
    "CLM-EX-03", "pb:log_retention_hours", "exact", "pc:log_retention_seconds",
    HOURS(1, 720), SECS(1, 2592000), UC("unit:HR", "unit:SEC"), "subset", "lossless",
    tests=[{"input": 48, "expected": 172800}])

# exact de significado com domínios que só se sobrepõem: transporte parcial + saturação declarada (F2: 3 campos)
EXACT_SATURATING = claim(
    "CLM-EX-04", "pa:retention_days", "exact", "pb:retention_days",
    DAYS(1, 3650), DAYS(1, 365), {"name": "identity", "params": {}}, "superset", "declared_loss",
    loss_contract=[{"kind": "saturation", "min": 1, "max": 365, "why": "destino aceita no máximo 365 dias"}],
    tests=[{"input": 30, "expected": 30}])

# bytes: GiB (IEC) -> GB (SI) é conversão exata seguida de arredondamento para cima declarado
EXACT_GIB_GB = claim(
    "CLM-EX-05", "pa:disk_size_gib", "exact", "pb:disk_size_gb",
    T("integer", quantity_kind="quantitykind:InformationEntropy", unit="unit:GibiBYTE", range={"min": 1, "max": 1024}),
    T("integer", quantity_kind="quantitykind:InformationEntropy", unit="unit:GigaBYTE", range={"min": 1, "max": 2000}),
    UC("unit:GibiBYTE", "unit:GigaBYTE"), "unknown", "declared_loss",
    loss_contract=[{"kind": "rounding", "granularity": 1, "mode": "ceil", "why": "GB inteiro: arredonda para cima"}],
    tests=[{"input": 1, "expected": "134217728/125000000"}])

# taxa: a janela faz parte do tipo
RATE = claim(
    "CLM-EX-06", "pa:throttle_rpm", "exact", "pb:throttle_rps",
    T("decimal", quantity_kind="quantitykind:Count", unit="unit:NUM", rate_window="PT1M", range={"min": 0, "max": 6000}),
    T("decimal", quantity_kind="quantitykind:Count", unit="unit:NUM", rate_window="PT1S", range={"min": 0, "max": 100}),
    {"name": "rate_window_convert", "params": {"from": "PT1M", "to": "PT1S"}}, "equal", "lossless",
    tests=[{"input": 120, "expected": 2}])

# --------------------------------------------------------------------------------------------- broad/narrow
BROAD_ARCHIVE = claim(
    "CLM-BR-01", "pa:archive_class", "broad", "pb:storage_class",
    ENUM("flexible_retrieval", "deep_archive"), ENUM("standard", "nearline", "coldline", "archive"),
    EM({"flexible_retrieval": "coldline", "deep_archive": "archive"}), "subset", "lossless",
    tests=[{"input": "deep_archive", "expected": "archive"}],
    membership_predicate={"subset": "subject", "expr": {"op": "in", "values": ["coldline", "archive"]},
                          "tests": {"members": ["archive"], "non_members": ["standard"]}})

NARROW_TLS = claim(
    "CLM-NR-01", "pa:min_tls_version", "narrow", "pb:tls_policy_modern",
    ENUM("1.0", "1.1", "1.2", "1.3"), ENUM("P12", "P13"),
    EM({"1.2": "P12", "1.3": "P13"}), "superset", "partial",
    tests=[{"input": "1.3", "expected": "P13"}],
    membership_predicate={"subset": "object", "expr": {"op": "in", "values": ["1.2", "1.3"]},
                          "tests": {"members": ["1.2"], "non_members": ["1.0"]}})

# ---------------------------------------------------------------------------------------------------- close
CLOSE_VERSIONING = claim(
    "CLM-CL-01", "pa:versioning_status", "close", "pb:versioning_enabled",
    ENUM("Enabled", "Suspended"), BOOL, EM({"Enabled": True, "Suspended": False}), "equal", "declared_loss",
    loss_contract=[{"kind": "semantic", "values": ["Suspended"],
                    "what": "suspender preserva as versões existentes; 'desligado' no destino não diz isso"}],
    tests=[{"input": "Enabled", "expected": True}, {"input": "Suspended", "expected": False}],
    preserved_observations=["gravar duas vezes com versionamento ligado gera duas versões"])

CLOSE_VERSIONING_2 = claim(
    "CLM-CL-02", "pb:versioning_enabled", "close", "pc:versioning_mode",
    BOOL, ENUM("on", "paused"), EM({"true": "on", "false": "paused"}), "equal", "declared_loss",
    loss_contract=[{"kind": "semantic", "values": [False], "what": "'paused' do destino mantém regras de ciclo de vida; a origem não"}],
    tests=[{"input": True, "expected": "on"}])

# -------------------------------------------------------------------------------------------------- related
RELATED_KMS = claim(
    "CLM-RE-01", "pa:log_encryption_key", "related", "pb:bucket_default_encryption",
    T("string"), T("string"), None, "unknown", "none")
RELATED_KMS["proof"] = {"type": "none", "evidence": [], "tests": []}

# ----------------------------------------------------------------------------- fixed/default (lado sem atributo)
FIXED_ENCRYPTION = claim(
    "CLM-FX-01", "pa:encryption_at_rest_enabled", "exact", "pb:fixed_encryption_at_rest",
    BOOL, BOOL, {"name": "identity", "params": {}}, "superset", "partial",
    tests=[{"input": True, "expected": True}],
    fixed_default={"kind": "fixed", "value": True,
                   "context": {"all": [{"term": "object.provider_version", "op": "version_range",
                                        "value": {"min": "5.0"}}]},
                   "evidence": {"date": "2026-10-01", "source": "fixture:doc-sintetica#criptografia"}},
    guard={"all": [{"term": "object.provider_version", "op": "version_range", "value": {"min": "5.0"}}]})

# -------------------------------------------------------------------------------- sentinelas, durações, perdas
SENTINEL_RETENTION = claim(
    "CLM-SN-01", "pa:log_retention_days", "exact", "pb:log_retention_seconds",
    T("integer", quantity_kind="quantitykind:Time", unit="unit:DAY", range={"min": 1, "max": 3653},
      sentinels={"0": "nunca expira"}),
    SECS(86400, 315619200), UC("unit:DAY", "unit:SEC"), "subset", "lossless",
    loss_contract=[{"kind": "sentinel", "map": {"0": None}, "why": "destino não tem 'nunca expira'"}],
    tests=[{"input": 1, "expected": 86400}])

DURATION_MONTHS = claim(
    "CLM-DU-01", "pa:retention_period", "exact", "pb:retention_seconds",
    T("duration", quantity_kind="quantitykind:Time"), SECS(0, None), {"name": "duration_to_number", "params": {"to": "unit:SEC"}},
    "unknown", "partial", tests=[{"input": "P30D", "expected": 2592000}])

# -------------------------------------------------------------------------------- guardas e alternativas
def with_guard(c, atoms, term_types=None, cid=None):
    c = copy.deepcopy(c)
    c["guard"] = {"all": atoms}
    if term_types:
        c["guard"]["term_types"] = term_types
    if cid:
        c["claim_id"] = cid
    return c


EDITION_STD = [{"term": "object.edition", "op": "edition_in", "value": ["standard"]}]
EDITION_PREM = [{"term": "object.edition", "op": "edition_in", "value": ["premium"]}]
EDITION_ANY = [{"term": "object.edition", "op": "edition_in", "value": ["standard", "premium"]}]

# ------------------------------------------------------------------------------------- projeções e grupos
ALARM_QUERY_TYPE = T("string")
ALARM_TUPLE = T("tuple", components=[
    {"name": "metric", "type": T("string")},
    {"name": "window", "type": T("duration", quantity_kind="quantitykind:Time")},
    {"name": "statistic", "type": ENUM("mean", "max", "min", "sum", "count")},
    {"name": "operator", "type": ENUM("gt", "ge", "lt", "le", "eq", "ne")},
    {"name": "threshold", "type": T("decimal")}])


def all_examples() -> dict[str, dict]:
    return {k: v for k, v in globals().items() if k.isupper() and isinstance(v, dict) and "claim_id" in v}

TUPLE_ALARM = claim(
    "CLM-TU-01", "pa:alarm_query", "exact", "pb:alarm_condition", ALARM_QUERY_TYPE, ALARM_TUPLE,
    {"name": "split_alarm_query", "params": {}}, "unknown", "partial",
    tests=[{"input": "CpuUtilization[1m].mean() > 80",
            "expected": {"metric": "CpuUtilization", "window": "PT1M", "statistic": "mean", "operator": "gt",
                         "threshold": 80}}])

# composição com perda: dias -> horas (sem perda) -> dias com saturação e arredondamento (perda declarada)
RET_DAYS_HOURS = claim(
    "CLM-KF-01", "pa:retention_days", "exact", "pb:retention_hours", DAYS(1, 3650), HOURS(24, 87600),
    UC("unit:DAY", "unit:HR"), "subset", "lossless", tests=[{"input": 2, "expected": 48}])
RET_HOURS_DAYS = claim(
    "CLM-KF-02", "pb:retention_hours", "exact", "pc:retention_days", HOURS(24, 87600), DAYS(1, 365),
    UC("unit:HR", "unit:DAY"), "overlap", "declared_loss",
    loss_contract=[{"kind": "rounding", "granularity": 1, "mode": "floor", "why": "dia inteiro"},
                   {"kind": "saturation", "min": 1, "max": 365, "why": "máximo do destino"}],
    tests=[{"input": 48, "expected": 2}])

# não injetiva: sem inversa parcial única
TIER_CLOSE = claim(
    "CLM-TI-01", "pa:access_tier", "close", "pb:access_speed", ENUM("hot", "warm", "cold"), ENUM("fast", "slow"),
    EM({"hot": "fast", "warm": "slow", "cold": "slow"}), "equal", "declared_loss",
    loss_contract=[{"kind": "semantic", "values": ["warm", "cold"], "what": "morno e frio caem no mesmo valor"}],
    tests=[{"input": "hot", "expected": "fast"}])

# âncoras de glossário (F4): atom -> conceito, para o caminho átomo->conceito<-átomo
ANCHOR_A = claim(
    "ANC-A-01", "pa:backup_retention_days", "exact", "concept:backup_retention", DAYS(1, 35), DAYS(0, 3650),
    {"name": "identity", "params": {}}, "subset", "lossless", tests=[{"input": 7, "expected": 7}])
ANCHOR_B = claim(
    "ANC-B-01", "pb:backup_retention_seconds", "exact", "concept:backup_retention", SECS(0, 31536000), DAYS(0, 3650),
    UC("unit:SEC", "unit:DAY"), "unknown", "partial",
    loss_contract=[], tests=[{"input": 604800, "expected": 7}])

ALARM_PROJECTIONS = [
    {"projection_id": f"PRJ-AL-{c}", "field": "pa:alarm.query", "occurrence": {"scope": "resource"},
     "extractor": {"name": "split_alarm_query", "component": c}, "concept": f"concept:alarm_{c}",
     "type": t, "tests": [{"input": "CpuUtilization[1m].mean() > 80", "expected": e}]}
    for c, t, e in (("metric", T("string"), "CpuUtilization"), ("operator", ENUM("gt", "ge", "lt", "le", "eq", "ne"), "gt"),
                    ("threshold", T("decimal"), 80), ("window", T("duration", quantity_kind="quantitykind:Time"), "PT1M"),
                    ("statistic", ENUM("mean", "max", "min", "sum", "count"), "mean"))]

PORT_GROUP = {  # N:M — (protocolo, porta inicial, porta final) -> (protocolo, faixa 'p1-p2')
    "bo_group_id": "GRP-PORTS-01", "cardinality": "N:M",
    "variables": [
        {"name": "?proto", "side": "subject", "field": "pa:rule.protocol", "occurrence": "?r"},
        {"name": "?from", "side": "subject", "field": "pa:rule.from_port", "occurrence": "?r"},
        {"name": "?to", "side": "subject", "field": "pa:rule.to_port", "occurrence": "?r"},
        {"name": "?proto_b", "side": "object", "field": "pb:allow.protocol", "occurrence": "?a"},
        {"name": "?ports", "side": "object", "field": "pb:allow.ports", "occurrence": "?a"}],
    "occurrence_vars": ["?r", "?a"], "joins": [],
    "steps": [{"name": "identity", "inputs": {"value": "?proto"}, "outputs": {"value": "?proto_b"}},
              {"name": "join_port_range", "inputs": {"from_port": "?from", "to_port": "?to"}, "outputs": {"ports": "?ports"}}]}

ALARM_GROUP = {  # 1:N — uma consulta -> métrica, operador, limiar (cruzando para três atributos do destino)
    "bo_group_id": "GRP-ALARM-01", "cardinality": "1:N",
    "variables": [
        {"name": "?q", "side": "subject", "field": "pa:alarm.query", "occurrence": "?al"},
        {"name": "?metric", "side": "object", "field": "pb:alarm.metric_name", "occurrence": "?bl"},
        {"name": "?op", "side": "object", "field": "pb:alarm.comparison", "occurrence": "?bl"},
        {"name": "?thr", "side": "object", "field": "pb:alarm.threshold", "occurrence": "?bl"},
        {"name": "?win", "side": "object", "field": "pb:alarm.period", "occurrence": "?bl"},
        {"name": "?stat", "side": "object", "field": "pb:alarm.statistic", "occurrence": "?bl"}],
    "occurrence_vars": ["?al", "?bl"], "joins": [],
    "steps": [{"name": "split_alarm_query", "inputs": {"query": "?q"},
               "outputs": {"metric": "?metric", "operator": "?op", "threshold": "?thr", "window": "?win",
                           "statistic": "?stat"}}]}

CIDR_GROUP = {  # N:1 cruzando facetas — endereço (faceta de rede) + prefixo (faceta de sub-rede) -> CIDR
    "bo_group_id": "GRP-CIDR-01", "cardinality": "N:1",
    "variables": [
        {"name": "?addr", "side": "subject", "field": "pa:network.base_address", "occurrence": "?n"},
        {"name": "?plen", "side": "subject", "field": "pa:subnet_sizing.prefix_length", "occurrence": "?s"},
        {"name": "?cidr", "side": "object", "field": "pb:subnet.cidr", "occurrence": "?b"}],
    "occurrence_vars": ["?n", "?s", "?b"],
    "joins": [{"left": "?s", "right": "?n", "via": "facet_of"}],
    "steps": [{"name": "join_cidr", "inputs": {"address": "?addr", "prefix_length": "?plen"}, "outputs": {"cidr": "?cidr"}}]}

REALIZATIONS_EXCLUSIVE = [
    {"realization_id": "R-STD", "guard": {"all": EDITION_STD}, "exclusivity": "ProvenExclusive"},
    {"realization_id": "R-PREM", "guard": {"all": EDITION_PREM}, "exclusivity": "ProvenExclusive"}]
